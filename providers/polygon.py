"""
providers/polygon.py – Polygon.io REST + WebSocket provider.

REST endpoints used:
  GET /v2/aggs/ticker/{symbol}/range/{mult}/{span}/{from}/{to}
  GET /v3/reference/tickers  (universe)
  GET /vX/reference/financials  (fundamentals)

WebSocket: wss://socket.polygon.io/stocks
  Subscribe to AM.* (aggregate-minute events) and map to completed bars.

Rate-limit notes:
  - Free/Starter plan: 5 req/min on reference, unlimited on aggregates.
  - Starter/Developer: unlimited.
  - tenacity retries handle 429 responses.

Assumptions / known gaps:
  - Polygon does NOT provide diluted-EPS growth or revenue-growth directly
    from the financials endpoint; we derive them from consecutive quarterly
    filings when two periods are available.
  - Polygon does NOT provide ROIC or FCF margin as first-class fields; we
    approximate them from the financials income/cash-flow/balance-sheet data.
  - Sub-minute bars are not used; the minimum timeframe is 1m.
  - Adjusted prices use the 'adjusted=true' query parameter (split + dividend).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from providers.base import FundamentalData, OHLCVBar, ProviderBase, TickerInfo

logger = logging.getLogger(__name__)

# Map our timeframe strings → Polygon (multiplier, span)
_TF_MAP: dict[str, tuple[int, str]] = {
    "1m": (1, "minute"),
    "5m": (5, "minute"),
    "15m": (15, "minute"),
    "30m": (30, "minute"),
    "1h": (1, "hour"),
    "4h": (4, "hour"),
    "1d": (1, "day"),
}

_POLYGON_REST = "https://api.polygon.io"
_POLYGON_WS = "wss://socket.polygon.io/stocks"


class PolygonProvider(ProviderBase):
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("Polygon API key is required")
        self._key = api_key
        self._session: aiohttp.ClientSession | None = None

    # ── HTTP session ──────────────────────────────────────────────────────────
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"******"},
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Generic GET with retry ────────────────────────────────────────────────
    @retry(
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _get(self, path: str, params: dict | None = None) -> dict:
        session = await self._get_session()
        url = f"{_POLYGON_REST}{path}"
        async with session.get(url, params=params) as resp:
            if resp.status == 429:
                retry_after = int(resp.headers.get("Retry-After", "60"))
                logger.warning("Polygon rate-limited; sleeping %ds", retry_after)
                await asyncio.sleep(retry_after)
                raise aiohttp.ClientResponseError(
                    resp.request_info, resp.history, status=429
                )
            resp.raise_for_status()
            return await resp.json()

    # ── Universe ─────────────────────────────────────────────────────────────
    async def fetch_universe(self) -> list[TickerInfo]:
        tickers: list[TickerInfo] = []
        cursor: str | None = None
        while True:
            params: dict = {
                "market": "stocks",
                "type": "CS",          # common stock only
                "active": "true",
                "limit": 1000,
            }
            if cursor:
                params["cursor"] = cursor
            data = await self._get("/v3/reference/tickers", params)
            for t in data.get("results", []):
                tickers.append(
                    TickerInfo(
                        symbol=t["ticker"],
                        name=t.get("name", ""),
                        exchange=t.get("primary_exchange", ""),
                        asset_class=t.get("type", "CS"),
                        primary_exchange=t.get("primary_exchange", ""),
                        market_cap=t.get("market_cap"),
                        is_active=t.get("active", True),
                    )
                )
            cursor = data.get("next_cursor")
            if not cursor:
                break
        logger.info("Polygon universe: %d tickers fetched", len(tickers))
        return tickers

    # ── Bars ──────────────────────────────────────────────────────────────────
    async def fetch_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        adjusted: bool = True,
    ) -> list[OHLCVBar]:
        if timeframe not in _TF_MAP:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        mult, span = _TF_MAP[timeframe]
        from_str = start.strftime("%Y-%m-%d")
        to_str = end.strftime("%Y-%m-%d")
        params = {
            "adjusted": "true" if adjusted else "false",
            "sort": "asc",
            "limit": 50000,
        }
        path = f"/v2/aggs/ticker/{symbol}/range/{mult}/{span}/{from_str}/{to_str}"
        bars: list[OHLCVBar] = []
        while True:
            data = await self._get(path, params)
            results = data.get("results") or []
            for r in results:
                ts = datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc)
                bars.append(
                    OHLCVBar(
                        symbol=symbol,
                        timestamp=ts,
                        open=r["o"],
                        high=r["h"],
                        low=r["l"],
                        close=r["c"],
                        volume=r["v"],
                        vwap=r.get("vw"),
                        trades=r.get("n"),
                        adjusted=adjusted,
                    )
                )
            # Polygon paginates via next_url
            next_url = data.get("next_url")
            if not next_url:
                break
            # Strip base URL and re-issue
            path_next = next_url.replace(_POLYGON_REST, "")
            params = {}  # next_url carries all params
            path = path_next
        return bars

    # ── Streaming (WebSocket) ─────────────────────────────────────────────────
    async def stream_bars(
        self,
        symbols: list[str],
        timeframe: str,
    ) -> AsyncIterator[OHLCVBar]:
        """
        Stream completed aggregate bars via Polygon WebSocket.
        Only minute-aggregate events (AM.*) are available for stocks.
        For timeframes > 1m the caller must aggregate from 1m bars.
        """
        import websockets

        sub_channel = "AM"  # aggregate per minute
        subs = [f"{sub_channel}.{s}" for s in symbols]

        async with websockets.connect(
            _POLYGON_WS,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            # Authenticate
            auth_msg = [{"action": "auth", "params": self._key}]
            await ws.send(__import__("json").dumps(auth_msg))
            resp = __import__("json").loads(await ws.recv())
            if resp[0].get("status") != "auth_success":
                raise ConnectionError(f"Polygon auth failed: {resp}")

            # Subscribe
            sub_msg = [{"action": "subscribe", "params": ",".join(subs)}]
            await ws.send(__import__("json").dumps(sub_msg))

            async for raw in ws:
                messages = __import__("json").loads(raw)
                for msg in messages:
                    if msg.get("ev") != sub_channel:
                        continue
                    ts = datetime.fromtimestamp(msg["s"] / 1000, tz=timezone.utc)
                    yield OHLCVBar(
                        symbol=msg["sym"],
                        timestamp=ts,
                        open=msg["o"],
                        high=msg["h"],
                        low=msg["l"],
                        close=msg["c"],
                        volume=msg["v"],
                        vwap=msg.get("vw"),
                        trades=msg.get("z"),
                        adjusted=False,  # WS bars are unadjusted; caller must handle
                    )

    # ── Fundamentals ─────────────────────────────────────────────────────────
    async def fetch_fundamentals(self, symbol: str) -> FundamentalData | None:
        """
        Pull the two most-recent annual filings and derive growth metrics.
        Fields derived: eps growth, revenue growth, debt_to_equity, fcf_margin.
        ROIC is estimated as (net_income / total_assets) – a proxy.
        Returns None if no financial data is available.
        """
        try:
            data = await self._get(
                "/vX/reference/financials",
                {"ticker": symbol, "timeframe": "annual", "limit": 2, "sort": "period_of_report_date"},
            )
        except Exception as exc:
            logger.debug("Fundamentals fetch failed for %s: %s", symbol, exc)
            return None

        results = data.get("results") or []
        if not results:
            return None

        def _safe(d: dict, *keys: str, default: float | None = None) -> float | None:
            cur: object = d
            for k in keys:
                if not isinstance(cur, dict):
                    return default
                cur = cur.get(k)
            if cur is None:
                return default
            try:
                return float(cur)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return default

        latest = results[-1].get("financials", {})
        prior = results[0].get("financials", {}) if len(results) >= 2 else {}

        # EPS growth
        eps_cur = _safe(latest, "income_statement", "diluted_earnings_per_share", "value")
        eps_prior = _safe(prior, "income_statement", "diluted_earnings_per_share", "value")
        eps_growth: float | None = None
        if eps_cur is not None and eps_prior and eps_prior != 0:
            eps_growth = (eps_cur - eps_prior) / abs(eps_prior)

        # Revenue growth
        rev_cur = _safe(latest, "income_statement", "revenues", "value")
        rev_prior = _safe(prior, "income_statement", "revenues", "value")
        rev_growth: float | None = None
        if rev_cur is not None and rev_prior and rev_prior != 0:
            rev_growth = (rev_cur - rev_prior) / abs(rev_prior)

        # D/E
        total_liab = _safe(latest, "balance_sheet", "liabilities", "value")
        total_equity = _safe(latest, "balance_sheet", "equity", "value")
        dte: float | None = None
        if total_liab is not None and total_equity and total_equity != 0:
            dte = total_liab / total_equity

        # FCF margin
        ocf = _safe(latest, "cash_flow_statement", "net_cash_flow_from_operating_activities", "value")
        capex_raw = _safe(latest, "cash_flow_statement", "net_cash_flow_from_investing_activities", "value")
        fcf_margin: float | None = None
        if ocf is not None and capex_raw is not None and rev_cur and rev_cur != 0:
            fcf = ocf + capex_raw  # capex is typically negative
            fcf_margin = fcf / rev_cur

        # ROIC proxy
        net_income = _safe(latest, "income_statement", "net_income_loss", "value")
        total_assets = _safe(latest, "balance_sheet", "assets", "value")
        roic: float | None = None
        if net_income is not None and total_assets and total_assets != 0:
            roic = net_income / total_assets

        count = sum(
            1
            for v in [eps_growth, rev_growth, roic, dte, fcf_margin]
            if v is not None
        )
        return FundamentalData(
            symbol=symbol,
            diluted_eps_growth=eps_growth,
            revenue_growth=rev_growth,
            roic=roic,
            debt_to_equity=dte,
            fcf_margin=fcf_margin,
            data_count=count,
        )

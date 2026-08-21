"""
providers/alpaca.py – Alpaca Markets REST + WebSocket provider.

REST endpoints:
  GET /v2/stocks/{symbol}/bars  (historical OHLCV, adjusted)
  GET /v2/assets                (universe)

WebSocket: wss://stream.data.alpaca.markets/v2/stp_feed (or iex/sip)
  Subscribe to bars.{symbol} for completed bars.

Assumptions / known gaps:
  - Alpaca does NOT provide fundamental data; fetch_fundamentals() returns None.
  - The free SIP feed is available on all account tiers as of 2024.
  - Adjusted bars via feed=sip&adjustment=all.
  - Bar WebSocket events already represent completed bars (pushed at bar close).
"""
from __future__ import annotations

import asyncio
import json
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

_TF_MAP: dict[str, str] = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "30m": "30Min",
    "1h": "1Hour",
    "4h": "4Hour",
    "1d": "1Day",
}

_ALPACA_DATA_REST = "https://data.alpaca.markets"
_ALPACA_BROKER_REST = "https://paper-api.alpaca.markets"
_ALPACA_WS = "wss://stream.data.alpaca.markets/v2/sip"


class AlpacaProvider(ProviderBase):
    def __init__(self, api_key: str, api_secret: str, base_url: str = _ALPACA_DATA_REST) -> None:
        if not api_key or not api_secret:
            raise ValueError("Alpaca API key and secret are required")
        self._key = api_key
        self._secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "APCA-API-KEY-ID": self._key,
                    "APCA-API-SECRET-KEY": self._secret,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    @retry(
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _get(self, path: str, params: dict | None = None) -> dict:
        session = await self._get_session()
        url = f"{self._base_url}{path}"
        async with session.get(url, params=params) as resp:
            if resp.status == 429:
                retry_after = int(resp.headers.get("Retry-After", "60"))
                logger.warning("Alpaca rate-limited; sleeping %ds", retry_after)
                await asyncio.sleep(retry_after)
                raise aiohttp.ClientResponseError(
                    resp.request_info, resp.history, status=429
                )
            resp.raise_for_status()
            return await resp.json()

    # ── Universe ──────────────────────────────────────────────────────────────
    async def fetch_universe(self) -> list[TickerInfo]:
        """
        Alpaca's /v2/assets returns all assets.
        We filter to tradeable common stocks on major exchanges.
        """
        session = await self._get_session()
        url = "https://paper-api.alpaca.markets/v2/assets"
        tickers: list[TickerInfo] = []
        params = {"status": "active", "asset_class": "us_equity"}
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            assets = await resp.json()
        for a in assets:
            if not a.get("tradable"):
                continue
            tickers.append(
                TickerInfo(
                    symbol=a["symbol"],
                    name=a.get("name", ""),
                    exchange=a.get("exchange", ""),
                    asset_class=a.get("class", "us_equity"),
                    primary_exchange=a.get("exchange", ""),
                    market_cap=None,   # Alpaca does not provide market cap in assets
                    is_active=a.get("status") == "active",
                )
            )
        logger.info("Alpaca universe: %d tickers fetched", len(tickers))
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
        tf = _TF_MAP[timeframe]
        bars: list[OHLCVBar] = []
        page_token: str | None = None

        while True:
            params: dict = {
                "timeframe": tf,
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "adjustment": "all" if adjusted else "raw",
                "feed": "sip",
                "limit": 10000,
            }
            if page_token:
                params["page_token"] = page_token
            data = await self._get(f"/v2/stocks/{symbol}/bars", params)
            for b in data.get("bars") or []:
                ts = datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
                bars.append(
                    OHLCVBar(
                        symbol=symbol,
                        timestamp=ts,
                        open=b["o"],
                        high=b["h"],
                        low=b["l"],
                        close=b["c"],
                        volume=b["v"],
                        vwap=b.get("vw"),
                        trades=b.get("n"),
                        adjusted=adjusted,
                    )
                )
            page_token = data.get("next_page_token")
            if not page_token:
                break
        return bars

    # ── Streaming ──────────────────────────────────────────────────────────────
    async def stream_bars(
        self,
        symbols: list[str],
        timeframe: str,
    ) -> AsyncIterator[OHLCVBar]:
        """
        Stream completed bars from Alpaca via WebSocket.
        Alpaca pushes bar events at close of each bar.
        For timeframes > 1m, caller must aggregate.
        """
        import websockets

        async with websockets.connect(_ALPACA_WS, ping_interval=20) as ws:
            # Auth
            auth = {"action": "auth", "key": self._key, "secret": self._secret}
            await ws.send(json.dumps(auth))
            resp = json.loads(await ws.recv())
            if not any(m.get("T") == "success" for m in resp):
                raise ConnectionError(f"Alpaca auth failed: {resp}")

            # Subscribe
            sub = {"action": "subscribe", "bars": symbols}
            await ws.send(json.dumps(sub))

            async for raw in ws:
                messages = json.loads(raw)
                for msg in messages:
                    if msg.get("T") != "b":
                        continue
                    ts = datetime.fromisoformat(msg["t"].replace("Z", "+00:00"))
                    yield OHLCVBar(
                        symbol=msg["S"],
                        timestamp=ts,
                        open=msg["o"],
                        high=msg["h"],
                        low=msg["l"],
                        close=msg["c"],
                        volume=msg["v"],
                        vwap=msg.get("vw"),
                        trades=msg.get("n"),
                        adjusted=False,
                    )

    async def fetch_fundamentals(self, symbol: str) -> FundamentalData | None:
        """Alpaca does not supply fundamental data."""
        return None

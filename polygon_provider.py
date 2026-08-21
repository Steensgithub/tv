from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiohttp
import websockets

from data_provider import MarketDataProvider
from models import OHLCVBar

LOGGER = logging.getLogger(__name__)


_TIMEFRAME_MULTIPLIER = {
    "1m": (1, "minute"),
    "5m": (5, "minute"),
    "15m": (15, "minute"),
    "30m": (30, "minute"),
    "1h": (1, "hour"),
    "1d": (1, "day"),
}


class PolygonProvider(MarketDataProvider):
    def __init__(self, api_key: str, session: aiohttp.ClientSession | None = None) -> None:
        self.api_key = api_key
        self._session = session

    async def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        include_extended: bool,
    ) -> list[OHLCVBar]:
        multiplier, span = _TIMEFRAME_MULTIPLIER[timeframe]
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{span}/"
            f"{int(start.timestamp() * 1000)}/{int(end.timestamp() * 1000)}"
        )
        params = {"adjusted": "true", "sort": "asc", "limit": "50000", "apiKey": self.api_key}
        if include_extended:
            params["session"] = "all"
        session = self._session or aiohttp.ClientSession()
        close_session = self._session is None
        try:
            async with session.get(url, params=params, timeout=30) as response:
                payload = await response.json()
                if response.status != 200:
                    raise RuntimeError(f"Polygon historical error {response.status}: {payload}")
                bars = []
                for item in payload.get("results", []):
                    bars.append(
                        OHLCVBar(
                            symbol=symbol,
                            timestamp=datetime.fromtimestamp(item["t"] / 1000, tz=UTC),
                            open=float(item["o"]),
                            high=float(item["h"]),
                            low=float(item["l"]),
                            close=float(item["c"]),
                            volume=float(item.get("v", 0)),
                        )
                    )
                return bars
        finally:
            if close_session:
                await session.close()

    async def stream_bars(
        self,
        symbols: list[str],
        timeframe: str,
        include_extended: bool,
    ) -> AsyncIterator[OHLCVBar]:
        del timeframe, include_extended
        backoff = 1.0
        while True:
            try:
                async with websockets.connect("wss://socket.polygon.io/stocks", ping_interval=20) as websocket:
                    await websocket.send(json.dumps({"action": "auth", "params": self.api_key}))
                    await websocket.send(
                        json.dumps({"action": "subscribe", "params": ",".join(f"AM.{s}" for s in symbols)})
                    )
                    backoff = 1.0
                    async for raw in websocket:
                        messages = json.loads(raw)
                        for item in messages:
                            if item.get("ev") != "AM":
                                continue
                            yield OHLCVBar(
                                symbol=item["sym"],
                                timestamp=datetime.fromtimestamp(item["s"] / 1000, tz=UTC),
                                open=float(item["o"]),
                                high=float(item["h"]),
                                low=float(item["l"]),
                                close=float(item["c"]),
                                volume=float(item.get("v", 0)),
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception("websocket failure, reconnecting: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def get_symbol_metadata(self, symbol: str) -> dict[str, str | bool | float | None]:
        url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
        params = {"apiKey": self.api_key}
        session = self._session or aiohttp.ClientSession()
        close_session = self._session is None
        try:
            async with session.get(url, params=params, timeout=30) as response:
                payload = await response.json()
                if response.status != 200:
                    raise RuntimeError(f"Polygon metadata error {response.status}: {payload}")
                item = payload.get("results", {})
                return {
                    "exchange": item.get("primary_exchange"),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "active": item.get("active"),
                }
        finally:
            if close_session:
                await session.close()

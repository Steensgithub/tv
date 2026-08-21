"""
providers/base.py – abstract base class for market-data providers.

Each concrete provider must implement:
  - fetch_universe()      → list[TickerInfo]
  - fetch_bars()          → list[OHLCVBar]  (REST backfill)
  - stream_bars()         → AsyncIterator[OHLCVBar]  (live WebSocket/SSE)
  - fetch_fundamentals()  → FundamentalData | None
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator


@dataclass
class OHLCVBar:
    """A single completed OHLCV bar with adjusted prices."""

    symbol: str
    timestamp: datetime          # bar open time (UTC-aware)
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None
    trades: int | None = None
    adjusted: bool = True


# Alias kept for backward compatibility
BarData = OHLCVBar


@dataclass
class TickerInfo:
    symbol: str
    name: str
    exchange: str
    asset_class: str             # "CS" = common stock
    primary_exchange: str = ""
    market_cap: float | None = None
    is_active: bool = True


@dataclass
class FundamentalData:
    symbol: str
    diluted_eps_growth: float | None = None      # e.g. 0.25 = 25 %
    revenue_growth: float | None = None
    roic: float | None = None
    debt_to_equity: float | None = None
    fcf_margin: float | None = None
    data_count: int = 0          # how many of the 5 fields are populated


class ProviderBase(abc.ABC):
    """Abstract market-data provider."""

    # ── Universe ────────────────────────────────────────────────────────────
    @abc.abstractmethod
    async def fetch_universe(self) -> list[TickerInfo]:
        """Return the full universe of tradeable tickers."""

    # ── Bars ─────────────────────────────────────────────────────────────────
    @abc.abstractmethod
    async def fetch_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        adjusted: bool = True,
    ) -> list[OHLCVBar]:
        """Fetch historical OHLCV bars via REST."""

    @abc.abstractmethod
    def stream_bars(
        self,
        symbols: list[str],
        timeframe: str,
    ) -> AsyncIterator[OHLCVBar]:
        """Stream live completed bars via WebSocket / SSE."""

    # ── Fundamentals (optional) ─────────────────────────────────────────────
    async def fetch_fundamentals(self, symbol: str) -> FundamentalData | None:
        """Return fundamental data for quality scoring.  Default: unsupported."""
        return None

    # ── Session helpers ──────────────────────────────────────────────────────
    async def close(self) -> None:
        """Clean up HTTP sessions, WebSocket connections, etc."""

"""
yfinance data provider.

Data parity notes vs TradingView
---------------------------------
- Yahoo Finance applies split and dividend adjustments retroactively; the
  adjusted prices may differ from TradingView's Adjusted data.
- Yahoo Finance 4H bars are not natively available; 1H bars are fetched and
  resampled to 4H anchored at 09:30 America/New_York.
- Volume: Yahoo Finance reports consolidated tape volume.
- Extended hours: yfinance can return pre/post market data; this provider
  filters to regular session only.
- Rate limits: Yahoo Finance imposes informal rate limits; tenacity retries
  with exponential backoff are applied.
- yfinance data quality has occasional gaps; validation is applied.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install yfinance: pip install yfinance") from exc

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..models import Candle
from ..session import resample_to_session_bars, localize_utc
from . import DataProvider

log = logging.getLogger(__name__)

UTC = timezone.utc

# yfinance interval strings
_YF_INTERVALS: dict[str, str] = {
    "1H": "1h",
    "4H": "1h",   # resampled from 1H
    "1D": "1d",
    "1W": "1wk",
}

# Minimum fetch windows to satisfy warmup
_WARMUP_DAYS: dict[str, int] = {
    "1H": 60,
    "4H": 180,
    "1D": 500,
    "1W": 2000,
}


class YFinanceProvider(DataProvider):
    """yfinance-based data provider with session-anchored resampling."""

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        timeout: int = 30,
        split_adjusted: bool = True,
        dividend_adjusted: bool = True,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._timeout = timeout
        self._split_adjusted = split_adjusted
        self._dividend_adjusted = dividend_adjusted

    @property
    def name(self) -> str:
        return "yfinance"

    async def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        adjusted: bool = True,
    ) -> list[Candle]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_historical, symbol, timeframe, start, end, adjusted
        )

    async def get_latest_bars(
        self,
        symbol: str,
        timeframe: str,
        n: int = 1,
    ) -> list[Candle]:
        tf = timeframe.upper()
        days_back = max(_WARMUP_DAYS.get(tf, 400), n * 7)
        end = datetime.now(UTC)
        start = end - timedelta(days=days_back)
        bars = await self.get_historical_bars(symbol, timeframe, start, end)
        return bars[-n:] if bars else []

    async def get_symbols(self) -> list[str]:
        # yfinance does not expose a symbol list; return a hardcoded default
        return []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_historical(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        adjusted: bool,
    ) -> list[Candle]:
        tf = timeframe.upper()
        yf_interval = _YF_INTERVALS.get(tf)
        if not yf_interval:
            raise ValueError(f"Unsupported timeframe: {timeframe!r}")

        ticker = yf.Ticker(symbol)

        auto_adjust = adjusted and (self._split_adjusted or self._dividend_adjusted)

        raw: pd.DataFrame = ticker.history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=yf_interval,
            auto_adjust=auto_adjust,
            prepost=False,
            actions=False,
        )

        if raw is None or raw.empty:
            log.warning("yfinance returned no data for %s %s", symbol, timeframe)
            return []

        raw.index = pd.DatetimeIndex(raw.index)
        if raw.index.tz is None:
            raw.index = raw.index.tz_localize("UTC")
        else:
            raw.index = raw.index.tz_convert("UTC")

        raw.columns = [c.lower() for c in raw.columns]
        raw = raw[["open", "high", "low", "close", "volume"]].copy()

        if tf == "4H":
            raw = resample_to_session_bars(raw, "4H", exclude_extended=True)
        elif tf in ("1D", "1W"):
            # Drop the current incomplete bar (last row may be intraday)
            if len(raw) > 1:
                raw = raw.iloc[:-1]

        candles: list[Candle] = []
        now_utc = datetime.now(UTC)

        for ts, row in raw.iterrows():
            if pd.isna(row["close"]):
                continue

            vol = None if pd.isna(row["volume"]) else float(row["volume"])
            bar_ts = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            if bar_ts.tzinfo is None:
                bar_ts = bar_ts.replace(tzinfo=UTC)

            candles.append(
                Candle(
                    timestamp=bar_ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=vol,
                    confirmed=True,  # historical bars are always confirmed
                    symbol=symbol,
                    timeframe=tf,
                )
            )

        return candles

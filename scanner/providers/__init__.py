"""
Abstract data provider interface.

All providers must implement this interface.

Notes on data parity with TradingView
--------------------------------------
- TradingView uses a proprietary data feed. Prices, splits, and dividend
  adjustments may differ from third-party providers.
- yfinance uses Yahoo Finance data which may have different split/dividend
  adjustment timing and different OHLCV values for extended hours.
- 4H bar anchoring: TradingView anchors 4H bars to the session open for
  equity markets; some providers anchor to midnight UTC. This scanner always
  resamples to 09:30 NY time anchoring via ``session.resample_to_session_bars``.
- Volume: yfinance reports consolidated tape volume; Alpaca reports
  consolidated tape volume. Both should be equivalent for US equities.
  Extended-hours volume is excluded when exclude_extended_hours=True.
"""

from __future__ import annotations

import abc
from datetime import datetime
from typing import AsyncIterator, Optional

from ..models import Candle


class DataProvider(abc.ABC):
    """Abstract interface for market data providers."""

    @abc.abstractmethod
    async def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        adjusted: bool = True,
    ) -> list[Candle]:
        """
        Retrieve historical OHLCV bars for *symbol* between *start* and *end*.

        Parameters
        ----------
        symbol    : ticker symbol, e.g., "AAPL"
        timeframe : "1H", "4H", "1D", "1W"
        start     : UTC-aware start datetime
        end       : UTC-aware end datetime
        adjusted  : whether to return split and dividend adjusted prices

        Returns
        -------
        List of Candle objects sorted oldest-first.
        All returned candles are marked confirmed=True (historical).
        """

    @abc.abstractmethod
    async def get_latest_bars(
        self,
        symbol: str,
        timeframe: str,
        n: int = 1,
    ) -> list[Candle]:
        """
        Retrieve the *n* most recent bars.

        The last bar in the returned list may be the currently forming bar.
        Use ``candle.confirmed`` to filter.
        """

    @abc.abstractmethod
    async def get_symbols(self) -> list[str]:
        """Return the list of available symbols."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider identifier string."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from models import OHLCVBar


class MarketDataProvider(ABC):
    @abstractmethod
    async def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        include_extended: bool,
    ) -> list[OHLCVBar]:
        raise NotImplementedError

    @abstractmethod
    async def stream_bars(
        self,
        symbols: list[str],
        timeframe: str,
        include_extended: bool,
    ) -> AsyncIterator[OHLCVBar]:
        raise NotImplementedError

    @abstractmethod
    async def get_symbol_metadata(self, symbol: str) -> dict[str, str | bool | float | None]:
        raise NotImplementedError

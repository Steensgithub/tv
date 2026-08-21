from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from models import OHLCVBar


_DURATION = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
}


@dataclass(slots=True)
class _PartialBar:
    bucket_start: datetime
    bar: OHLCVBar


class BarAggregator:
    def __init__(self, timeframe: str) -> None:
        self.timeframe = timeframe
        self.duration = _DURATION[timeframe]
        self._partial: dict[str, _PartialBar] = {}

    def update(self, bar: OHLCVBar) -> OHLCVBar | None:
        bucket = self._bucket_start(bar.timestamp)
        partial = self._partial.get(bar.symbol)
        if partial is None:
            self._partial[bar.symbol] = _PartialBar(bucket, OHLCVBar(**bar.__dict__))
            return None
        if partial.bucket_start == bucket:
            partial.bar.high = max(partial.bar.high, bar.high)
            partial.bar.low = min(partial.bar.low, bar.low)
            partial.bar.close = bar.close
            partial.bar.volume += bar.volume
            return None
        completed = partial.bar
        self._partial[bar.symbol] = _PartialBar(bucket, OHLCVBar(**bar.__dict__))
        return completed

    def flush(self, symbol: str) -> OHLCVBar | None:
        partial = self._partial.pop(symbol, None)
        return partial.bar if partial else None

    def _bucket_start(self, ts: datetime) -> datetime:
        ts_utc = ts.astimezone(UTC)
        if self.timeframe == "1d":
            return datetime(ts_utc.year, ts_utc.month, ts_utc.day, tzinfo=UTC)
        if self.timeframe == "1h":
            return datetime(ts_utc.year, ts_utc.month, ts_utc.day, ts_utc.hour, tzinfo=UTC)
        minute = ts_utc.minute
        step = int(self.duration.total_seconds() // 60)
        bucket_minute = minute - (minute % step)
        return datetime(
            ts_utc.year,
            ts_utc.month,
            ts_utc.day,
            ts_utc.hour,
            bucket_minute,
            tzinfo=UTC,
        )

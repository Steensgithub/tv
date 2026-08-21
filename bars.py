"""
bars.py – bar management: loading historical bars, aggregating intraday bars,
          and session filtering.

Key responsibilities:
  1. Fetch enough historical bars so all indicators can warm up (min_bars).
  2. Aggregate 1-min WebSocket bars into larger timeframes.
  3. Strip out out-of-session bars for intraday timeframes.
  4. Guarantee no lookahead: the "current" bar is always the *last closed* bar.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from config import ScannerConfig
from providers.base import OHLCVBar, ProviderBase

logger = logging.getLogger(__name__)

# Mapping timeframe → minutes for aggregation
_TF_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


def bars_to_df(bars: list[OHLCVBar]) -> pd.DataFrame:
    """Convert a list of OHLCVBar to a pandas DataFrame sorted by timestamp."""
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    records = [
        {
            "timestamp": b.timestamp,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in bars
    ]
    df = pd.DataFrame(records).set_index("timestamp").sort_index()
    return df


def filter_session(df: pd.DataFrame, cfg: ScannerConfig) -> pd.DataFrame:
    """Remove bars outside the configured trading session (intraday only)."""
    if cfg.timeframe == "1d":
        return df
    tz = ZoneInfo(cfg.session_tz)
    start_h, start_m = map(int, cfg.session_start.split(":"))
    end_h, end_m = map(int, cfg.session_end.split(":"))
    local_idx = df.index.tz_convert(tz)
    mask = (
        (local_idx.time >= __import__("datetime").time(start_h, start_m))
        & (local_idx.time <= __import__("datetime").time(end_h, end_m))
    )
    return df[mask]


def aggregate_bars(bars: list[OHLCVBar], target_tf: str) -> list[OHLCVBar]:
    """
    Aggregate 1-minute bars to a higher timeframe using OHLCV rules.
    Used when the provider streams only 1-min updates.
    """
    if target_tf == "1m" or not bars:
        return bars
    minutes = _TF_MINUTES.get(target_tf, 1)
    grouped: dict[datetime, list[OHLCVBar]] = defaultdict(list)
    for bar in bars:
        # Round down bar timestamp to the nearest `minutes` boundary
        ts = bar.timestamp
        epoch_minutes = int(ts.timestamp() // 60)
        bucket_minutes = (epoch_minutes // minutes) * minutes
        bucket_ts = datetime.fromtimestamp(bucket_minutes * 60, tz=timezone.utc)
        grouped[bucket_ts].append(bar)

    result: list[OHLCVBar] = []
    for bucket_ts in sorted(grouped):
        group = grouped[bucket_ts]
        agg = OHLCVBar(
            symbol=group[0].symbol,
            timestamp=bucket_ts,
            open=group[0].open,
            high=max(b.high for b in group),
            low=min(b.low for b in group),
            close=group[-1].close,
            volume=sum(b.volume for b in group),
            adjusted=group[0].adjusted,
        )
        result.append(agg)
    return result


async def load_history(
    symbol: str,
    provider: ProviderBase,
    cfg: ScannerConfig,
) -> pd.DataFrame:
    """
    Fetch enough historical bars for full indicator warm-up.
    Returns a DataFrame sorted by ascending timestamp with only session bars.
    """
    # We need at least min_bars completed bars.
    # To account for weekends/holidays, over-fetch by 2×.
    minutes = _TF_MINUTES.get(cfg.timeframe, 1440)
    total_minutes_needed = cfg.min_bars * minutes * 2
    lookback_days = max(int(total_minutes_needed / (6.5 * 60)) + 1, 365)

    end_dt = datetime.now(tz=timezone.utc)
    start_dt = end_dt - timedelta(days=lookback_days)

    try:
        bars = await provider.fetch_bars(
            symbol=symbol,
            timeframe=cfg.timeframe,
            start=start_dt,
            end=end_dt,
            adjusted=True,
        )
    except Exception as exc:
        logger.warning("Failed to load history for %s: %s", symbol, exc)
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    if not bars:
        logger.debug("No historical bars returned for %s", symbol)
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = bars_to_df(bars)
    df = filter_session(df, cfg)

    if len(df) < cfg.min_bars:
        logger.info(
            "Insufficient history for %s: got %d bars, need %d",
            symbol,
            len(df),
            cfg.min_bars,
        )
    return df


class BarBuffer:
    """
    Per-symbol ring buffer of completed OHLCV bars for live updates.
    Thread-safe append + DataFrame snapshot for indicator calculation.
    """

    def __init__(self, symbol: str, max_size: int = 5000) -> None:
        self.symbol = symbol
        self._bars: deque[OHLCVBar] = deque(maxlen=max_size)

    def load(self, df: pd.DataFrame) -> None:
        """Seed the buffer from a historical DataFrame."""
        for ts, row in df.iterrows():
            self._bars.append(
                OHLCVBar(
                    symbol=self.symbol,
                    timestamp=ts,
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    adjusted=True,
                )
            )

    def append(self, bar: OHLCVBar) -> None:
        self._bars.append(bar)

    def to_df(self) -> pd.DataFrame:
        return bars_to_df(list(self._bars))

    def __len__(self) -> int:
        return len(self._bars)

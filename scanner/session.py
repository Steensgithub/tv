"""
Session and candle helpers.

4H bar anchoring
----------------
Different data providers may anchor 4H bars differently (e.g., midnight UTC,
midnight NY, or the regular session open).  This scanner ALWAYS anchors 4H
(and other intraday) bars to the regular session open at 09:30 America/New_York.

If a provider returns bars anchored differently, ``resample_to_session_bars``
must be called to re-anchor them before any signal calculation.

Mixing extended-hours data with regular-session data is explicitly avoided.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)

# Supported intraday timeframes and their offset aliases for pandas
_TF_TO_PANDAS: dict[str, str] = {
    "1H": "1h",
    "4H": "4h",
    "1D": "1D",
    "1W": "1W",
}


def is_regular_session(dt_ny: datetime) -> bool:
    """Return True if *dt_ny* falls within the regular US equity session."""
    t = dt_ny.time()
    return SESSION_OPEN <= t < SESSION_CLOSE


def bar_is_confirmed(bar_close_time_utc: datetime, timeframe: str) -> bool:
    """
    Return True when the bar whose *open* is ``bar_close_time_utc`` has fully
    closed.  We require that the next bar's open time is <= now(UTC).

    For example, a 4H bar opening at 13:30 NY closes at 17:30 NY (or the
    session close at 16:00, whichever comes first under session anchoring).
    The safe check is simply: now >= bar_open + bar_duration.
    """
    now_utc = datetime.now(tz=UTC_TZ)
    duration = _tf_duration(timeframe)
    bar_end = bar_close_time_utc + duration
    return now_utc >= bar_end


def _tf_duration(timeframe: str) -> timedelta:
    tf = timeframe.upper()
    mapping = {
        "1H": timedelta(hours=1),
        "4H": timedelta(hours=4),
        "1D": timedelta(days=1),
        "1W": timedelta(weeks=1),
    }
    if tf not in mapping:
        raise ValueError(f"Unknown timeframe: {timeframe!r}")
    return mapping[tf]


def localize_utc(dt: datetime) -> datetime:
    """Ensure *dt* is UTC-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(UTC_TZ)


def to_ny(dt: datetime) -> datetime:
    """Convert UTC datetime to America/New_York."""
    return localize_utc(dt).astimezone(NY_TZ)


def resample_to_session_bars(
    df: pd.DataFrame,
    timeframe: str,
    exclude_extended: bool = True,
) -> pd.DataFrame:
    """
    Re-sample a minute/hourly DataFrame to *timeframe* bars anchored at
    09:30 America/New_York.

    Parameters
    ----------
    df : DataFrame with DatetimeIndex in UTC and columns [open, high, low, close, volume].
    timeframe : One of "1H", "4H", "1D", "1W".
    exclude_extended : Drop bars outside 09:30–16:00 NY before resampling.

    Returns
    -------
    DataFrame resampled to *timeframe* with UTC index, columns [open, high, low, close, volume].
    Only confirmed (fully closed) bars are returned.
    """
    df = df.copy()

    # Convert index to NY time
    df.index = df.index.tz_convert(NY_TZ)

    if exclude_extended:
        mask = (
            (df.index.time >= SESSION_OPEN)
            & (df.index.time < SESSION_CLOSE)
        )
        df = df[mask]

    if df.empty:
        return df

    tf = timeframe.upper()
    if tf == "1H":
        rule = "1h"
        offset = None
    elif tf == "4H":
        # Anchor 4H bars to session open 09:30
        rule = "4h"
        offset = "9h30min"
    elif tf == "1D":
        rule = "1D"
        offset = "9h30min"
    elif tf == "1W":
        rule = "1W"
        offset = "9h30min"
    else:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")

    resample_kwargs: dict = {"rule": rule, "closed": "left", "label": "left"}
    if offset:
        resample_kwargs["offset"] = offset

    resampled = df.resample(**resample_kwargs).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )

    # Drop bars where close is NaN (empty bucket)
    resampled = resampled.dropna(subset=["close"])

    # Drop the last (potentially unfinished) bar
    if len(resampled) > 1:
        resampled = resampled.iloc[:-1]

    # Convert index back to UTC
    resampled.index = resampled.index.tz_convert(UTC_TZ)

    return resampled

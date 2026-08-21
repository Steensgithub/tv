"""
Pine-compatible indicator calculations.

Key implementation notes
------------------------
EMA (Exponential Moving Average)
  Pine's ta.ema() seeds the first value with a simple average of the first
  ``length`` bars, then applies the standard EMA multiplier.  Our
  ``pine_ema()`` matches this exactly.

ATR (Average True Range)
  Pine's ta.atr() uses Wilder's smoothing (also called RMA or SMMA):
    rma[0] = (rma[1] * (length - 1) + tr[0]) / length
  with the first value seeded as the simple average of the first ``length``
  true-range values.  Do NOT use pandas-ta or TA-Lib defaults which may
  use EMA smoothing.

SMA (Simple Moving Average)
  Standard rolling mean.  Pine-compatible.

All functions accept numpy arrays and return numpy arrays.
Index 0 is the OLDEST bar; index -1 is the MOST RECENT (same as pandas).
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------


def pine_sma(close: np.ndarray, length: int) -> np.ndarray:
    """Pine-compatible SMA.  Returns NaN for the first (length-1) bars."""
    n = len(close)
    out = np.full(n, np.nan)
    for i in range(length - 1, n):
        out[i] = close[i - length + 1 : i + 1].mean()
    return out


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------


def pine_ema(close: np.ndarray, length: int) -> np.ndarray:
    """
    Pine-compatible EMA.

    Seeded with SMA of the first ``length`` bars.
    Returns NaN until the first valid seed point.
    """
    n = len(close)
    out = np.full(n, np.nan)
    if n < length:
        return out

    k = 2.0 / (length + 1.0)
    # Seed at index (length - 1) with SMA
    seed = close[:length].mean()
    out[length - 1] = seed

    for i in range(length, n):
        out[i] = close[i] * k + out[i - 1] * (1.0 - k)

    return out


# ---------------------------------------------------------------------------
# RMA (Wilder's smoothing) – used by Pine's ta.atr()
# ---------------------------------------------------------------------------


def pine_rma(values: np.ndarray, length: int) -> np.ndarray:
    """
    Wilder's RMA / SMMA.  Matches Pine's ta.rma().

    rma[0] = sma(values, length)[length-1]
    rma[i] = (rma[i-1] * (length - 1) + values[i]) / length
    """
    n = len(values)
    out = np.full(n, np.nan)
    if n < length:
        return out

    # Seed
    seed_idx = length - 1
    out[seed_idx] = values[:length].mean()

    for i in range(length, n):
        out[i] = (out[i - 1] * (length - 1) + values[i]) / length

    return out


# ---------------------------------------------------------------------------
# ATR – Pine-compatible
# ---------------------------------------------------------------------------


def pine_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    length: int,
) -> np.ndarray:
    """
    Pine-compatible ATR using Wilder's RMA smoothing.

    True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    """
    n = len(high)
    tr = np.full(n, np.nan)

    # First bar has no previous close, so TR = high - low
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hpc = abs(high[i] - close[i - 1])
        lpc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hpc, lpc)

    return pine_rma(tr, length)


# ---------------------------------------------------------------------------
# Signed-volume CVD proxy
# ---------------------------------------------------------------------------


def signed_volume_delta(
    close: np.ndarray,
    open_: np.ndarray,
    volume: np.ndarray,
) -> np.ndarray:
    """
    Signed-volume proxy for CVD.

    IMPORTANT: This is NOT true bid/ask order flow data.  It is a bar-close
    directional proxy:
      - If close > open  → delta = +volume (bullish bar)
      - If close < open  → delta = -volume (bearish bar)
      - If close == open → delta = 0

    This measure can be misleading in trending markets with large wicks.
    """
    delta = np.where(close > open_, volume, np.where(close < open_, -volume, 0.0))
    return delta


def window_cvd(
    close: np.ndarray,
    open_: np.ndarray,
    volume: np.ndarray,
    window: int,
) -> tuple[float, float, float, float]:
    """
    Calculate CVD proxy metrics over the last ``window`` bars.

    Returns:
        (windowCvd, windowTotalVolume, bullishCvdRatio, bearishCvdRatio)

    Raises:
        ValueError if volume contains NaN/None values.
    """
    if len(close) < window:
        raise ValueError(f"Need at least {window} bars, got {len(close)}")

    c = close[-window:]
    o = open_[-window:]
    v = volume[-window:]

    if np.any(np.isnan(v)):
        raise ValueError("Volume contains NaN – cannot compute CVD proxy")

    delta = signed_volume_delta(c, o, v)
    cvd = float(delta.sum())
    total_vol = float(v.sum())

    if total_vol == 0:
        return cvd, total_vol, 0.0, 0.0

    bullish_ratio = max(cvd, 0.0) / total_vol * 100.0
    bearish_ratio = max(-cvd, 0.0) / total_vol * 100.0

    return cvd, total_vol, bullish_ratio, bearish_ratio


# ---------------------------------------------------------------------------
# MA expansion
# ---------------------------------------------------------------------------


def ma_expansion_condition(
    ma2: np.ndarray,
    ma3: np.ndarray,
    ma4: np.ndarray,
    ma5: np.ndarray,
) -> np.ndarray:
    """
    MA expansion is True when each pairwise distance is strictly greater than
    the previous bar's distance.

    dist23 = abs(ma2 - ma3) / abs(ma3) * 100
    dist34 = abs(ma3 - ma4) / abs(ma4) * 100
    dist45 = abs(ma4 - ma5) / abs(ma5) * 100

    Expansion[i] = dist23[i] > dist23[i-1]
                 AND dist34[i] > dist34[i-1]
                 AND dist45[i] > dist45[i-1]

    Returns a boolean array (False for index 0 and any NaN positions).
    """
    n = len(ma2)
    out = np.zeros(n, dtype=bool)

    dist23 = np.where(ma3 != 0, np.abs(ma2 - ma3) / np.abs(ma3) * 100, np.nan)
    dist34 = np.where(ma4 != 0, np.abs(ma3 - ma4) / np.abs(ma4) * 100, np.nan)
    dist45 = np.where(ma5 != 0, np.abs(ma4 - ma5) / np.abs(ma5) * 100, np.nan)

    for i in range(1, n):
        if any(
            np.isnan(x)
            for x in [dist23[i], dist23[i - 1], dist34[i], dist34[i - 1], dist45[i], dist45[i - 1]]
        ):
            continue
        out[i] = (
            dist23[i] > dist23[i - 1]
            and dist34[i] > dist34[i - 1]
            and dist45[i] > dist45[i - 1]
        )

    return out

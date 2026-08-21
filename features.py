"""
features.py – pure-function signal feature calculation.

All formulas are faithful translations of the Pine Script specification.
No lookahead: every function accepts a closed-bar DataFrame (oldest first)
and produces output for the *last completed bar only*.

Convention:
  - df.index = UTC timestamps (DatetimeIndex, ascending)
  - df columns: open, high, low, close, volume  (float64)
  - All functions return np.nan when there is insufficient data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── Low-level helpers ────────────────────────────────────────────────────────


def _ema(series: pd.Series, length: int) -> pd.Series:
    """Exponential moving average (same as TradingView ta.ema)."""
    return series.ewm(span=length, adjust=False).mean()


def _sma(series: pd.Series, length: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=length, min_periods=length).mean()


def _wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    """
    Wilder ATR equivalent to TradingView's ta.atr().
    Uses RMA (Wilder smoothing) = EMA with alpha = 1/length.
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Wilder smoothing (RMA): alpha = 1/length
    return tr.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


# ── ADR / ATR ────────────────────────────────────────────────────────────────


def calc_adr(high: pd.Series, low: pd.Series, length: int) -> pd.Series:
    """ADR% = SMA((high/low - 1), length) * 100"""
    raw = (high / low) - 1.0
    return _sma(raw, length) * 100.0


def calc_atr_percent(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    length: int,
) -> pd.Series:
    """ATRPercent = ATR(length) / close * 100"""
    atr = _wilder_atr(high, low, close, length)
    return atr / close * 100.0


# ── Volume component ─────────────────────────────────────────────────────────


def calc_volume_feature(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    volume_ema_length: int,
    volume_multiplier: float,
) -> pd.Series:
    """
    Returns volumeFeature in [-1, 1].
    Also returns bullVolumeScore in [0, 1] = 0.5 + volumeFeature * 0.5
    """
    volume_ema = _ema(volume, volume_ema_length)
    volume_relative = volume / volume_ema
    denom = max(volume_multiplier - 0.5, 0.5)
    volume_strength = ((volume_relative - 0.5) / denom).clip(0, 1)

    hl_range = high - low
    volume_pressure = np.where(
        hl_range == 0.0,
        0.0,
        ((close - open_) / hl_range).clip(-1, 1),
    )
    volume_pressure_s = pd.Series(volume_pressure, index=close.index)
    feature = (volume_pressure_s * volume_strength).clip(-1, 1)
    return feature


def calc_volume_scores(feature: pd.Series) -> tuple[pd.Series, pd.Series]:
    bull = 0.5 + feature * 0.5
    bear = 1.0 - bull
    return bull, bear


# ── Trend component ──────────────────────────────────────────────────────────


def calc_trend_feature(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    trend_lookback: int,
) -> pd.Series:
    """
    Uses prior-bar SMA50 and ATR14 to compute trendSlope.
    trendFeature = clamp(trendSlope / 2, -1, 1)
    """
    sma50 = _sma(close, 50)
    atr14 = _wilder_atr(high, low, close, 14)

    # Use confirmed prior-bar values: shift(1) for [1], shift(lookback+1) for [lookback+1]
    sma50_1 = sma50.shift(1)
    sma50_lb1 = sma50.shift(trend_lookback + 1)
    atr14_1 = atr14.shift(1)

    trend_slope = np.where(
        atr14_1 > 0,
        (sma50_1 - sma50_lb1) / atr14_1,
        0.0,
    )
    trend_slope_s = pd.Series(trend_slope, index=close.index)
    feature = trend_slope_s.div(2).clip(-1, 1)
    return feature


def calc_trend_scores(feature: pd.Series) -> tuple[pd.Series, pd.Series]:
    bull = 0.5 + feature * 0.5
    bear = 1.0 - bull
    return bull, bear


# ── Volatility component ─────────────────────────────────────────────────────


def calc_volatility_components(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    adr_length: int,
    volatility_average_length: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Returns (volatilityRatio, volatilityRisk, atrPercent).
    volatilityRisk = clamp(|volatilityRatio - 1|, 0, 1)
    """
    atr_pct = calc_atr_percent(high, low, close, adr_length)
    atr_pct_avg = _sma(atr_pct, volatility_average_length)
    vol_ratio = atr_pct / atr_pct_avg
    vol_risk = (vol_ratio - 1.0).abs().clip(0, 1)
    return vol_ratio, vol_risk, atr_pct


# ── Adaptive accuracy ────────────────────────────────────────────────────────


def calc_adaptive_accuracy(
    feature: pd.Series,
    close: pd.Series,
    adaptive_lookback: int,
) -> pd.Series:
    """
    For each bar evaluate: was the previous bar's feature directionally correct?
    forward_score = 0.5 + prev_feature * actual_direction * 0.5
    Accuracy = SMA(forward_score, adaptive_lookback)
    """
    actual_direction = np.sign(close - close.shift(1))  # +1, -1, 0
    prev_feature = feature.shift(1)
    # Only evaluate when direction is non-zero
    forward_score = np.where(
        actual_direction != 0,
        0.5 + prev_feature * actual_direction * 0.5,
        np.nan,
    )
    forward_s = pd.Series(forward_score, index=close.index, dtype=float)
    accuracy = forward_s.rolling(adaptive_lookback, min_periods=1).mean().fillna(0.5)
    return accuracy


def calc_adaptive_factor(accuracy: pd.Series, adaptive_rate: float) -> pd.Series:
    """adaptiveFactor = clamp(1 + adaptiveRate * (accuracy - 0.5) * 2, 0.25, 3.0)"""
    return (1.0 + adaptive_rate * (accuracy - 0.5) * 2.0).clip(0.25, 3.0)


# ── Final confidence ─────────────────────────────────────────────────────────


def calc_confidence(
    bull_volume_score: pd.Series,
    bull_trend_score: pd.Series,
    vol_risk: pd.Series,
    volume_weight: float,
    trend_weight: float,
    volatility_weight: float,
    volume_adaptive_factor: pd.Series,
    trend_adaptive_factor: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """
    Returns (bullishConfidence, bearishConfidence) both in [0, 100].
    """
    adap_vol_w = volume_weight * volume_adaptive_factor
    adap_tr_w = trend_weight * trend_adaptive_factor
    adap_vola_w = pd.Series(volatility_weight, index=bull_volume_score.index)

    total_w = adap_vol_w + adap_tr_w + adap_vola_w
    total_w = total_w.clip(lower=1e-9)

    raw_bull = (
        100.0
        * (
            bull_volume_score * adap_vol_w
            + bull_trend_score * adap_tr_w
            + 0.5 * adap_vola_w
        )
        / total_w
    )

    # Volatility damping
    vola_damp = (1.0 - vol_risk * adap_vola_w / total_w).clip(0.25, 1.0)

    bull_conf = 50.0 + (raw_bull - 50.0) * vola_damp
    bear_conf = 100.0 - bull_conf
    return bull_conf, bear_conf


# ── All-in-one bar computation ───────────────────────────────────────────────


class BarFeatures:
    """Container for all computed features for the last completed bar."""

    __slots__ = (
        "adr_pct",
        "atr_pct",
        "volatility_ratio",
        "volatility_risk",
        "volume_relative",
        "volume_feature",
        "bull_volume_score",
        "bear_volume_score",
        "trend_slope",
        "trend_feature",
        "bull_trend_score",
        "bear_trend_score",
        "bull_confidence",
        "bear_confidence",
        "volume_agreement",
        "trend_agreement",
        "component_agreement",
        "volatility_filter_pass",
        "long_signal",
    )

    def __init__(self) -> None:
        for s in self.__slots__:
            setattr(self, s, float("nan"))
        self.long_signal = False
        self.volume_agreement = False
        self.trend_agreement = False
        self.volatility_filter_pass = False


def compute_features(df: pd.DataFrame, cfg: object) -> BarFeatures | None:
    """
    Compute all features for the last completed bar in df.

    Parameters
    ----------
    df  : DataFrame with columns [open, high, low, close, volume], ascending index.
    cfg : ScannerConfig instance.

    Returns None if there is insufficient data.
    """
    if len(df) < 2:
        return None

    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]

    # ── ADR / ATR ───────────────────────────────────────────────────────────
    adr_s = calc_adr(high, low, cfg.adr_length)
    atr_pct_s = calc_atr_percent(high, low, close, cfg.adr_length)

    # ── Volatility ──────────────────────────────────────────────────────────
    vol_ratio_s, vol_risk_s, _ = calc_volatility_components(
        high, low, close, cfg.adr_length, cfg.volatility_average_length
    )

    # ── Volume ──────────────────────────────────────────────────────────────
    vol_feature_s = calc_volume_feature(
        open_, high, low, close, volume,
        cfg.volume_ema_length, cfg.volume_multiplier,
    )
    bull_vol_s, bear_vol_s = calc_volume_scores(vol_feature_s)

    # Relative volume (volume / SMA(volume, length))
    vol_sma = _sma(volume, cfg.relative_volume_length)
    vol_relative_s = volume / vol_sma

    # ── Trend ────────────────────────────────────────────────────────────────
    trend_feature_s = calc_trend_feature(high, low, close, cfg.trend_lookback)
    bull_tr_s, bear_tr_s = calc_trend_scores(trend_feature_s)

    # Trend slope scalar for reporting
    sma50 = _sma(close, 50)
    atr14 = _wilder_atr(high, low, close, 14)
    trend_slope_s = pd.Series(
        np.where(atr14.shift(1) > 0,
                 (sma50.shift(1) - sma50.shift(cfg.trend_lookback + 1)) / atr14.shift(1),
                 0.0),
        index=close.index,
    )

    # ── Adaptive ────────────────────────────────────────────────────────────
    vol_acc_s = calc_adaptive_accuracy(vol_feature_s, close, cfg.adaptive_lookback)
    tr_acc_s = calc_adaptive_accuracy(trend_feature_s, close, cfg.adaptive_lookback)
    vol_adap_s = calc_adaptive_factor(vol_acc_s, cfg.adaptive_rate)
    tr_adap_s = calc_adaptive_factor(tr_acc_s, cfg.adaptive_rate)

    # ── Confidence ──────────────────────────────────────────────────────────
    bull_conf_s, bear_conf_s = calc_confidence(
        bull_vol_s, bull_tr_s, vol_risk_s,
        cfg.volume_weight, cfg.trend_weight, cfg.volatility_weight,
        vol_adap_s, tr_adap_s,
    )

    # ── Extract last bar values ───────────────────────────────────────────────
    def last(s: pd.Series) -> float:
        v = s.iloc[-1]
        return float(v) if pd.notna(v) else float("nan")

    f = BarFeatures()
    f.adr_pct = last(adr_s)
    f.atr_pct = last(atr_pct_s)
    f.volatility_ratio = last(vol_ratio_s)
    f.volatility_risk = last(vol_risk_s)
    f.volume_relative = last(vol_relative_s)
    f.volume_feature = last(vol_feature_s)
    f.bull_volume_score = last(bull_vol_s)
    f.bear_volume_score = last(bear_vol_s)
    f.trend_slope = last(trend_slope_s)
    f.trend_feature = last(trend_feature_s)
    f.bull_trend_score = last(bull_tr_s)
    f.bear_trend_score = last(bear_tr_s)
    f.bull_confidence = last(bull_conf_s)
    f.bear_confidence = last(bear_conf_s)

    return f

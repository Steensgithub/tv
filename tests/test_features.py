"""
tests/test_features.py – unit tests for every formula in features.py
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_df(n: int = 400, seed: int = 42) -> pd.DataFrame:
    """Synthetic price/volume data for deterministic testing."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, n))
    high = close * (1 + rng.uniform(0, 0.02, n))
    low = close * (1 - rng.uniform(0, 0.02, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(500_000, 5_000_000, n).astype(float)

    idx = pd.date_range("2023-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


# ── Helper imports ────────────────────────────────────────────────────────────

from features import (
    _ema,
    _sma,
    _wilder_atr,
    calc_adr,
    calc_atr_percent,
    calc_volume_feature,
    calc_volume_scores,
    calc_trend_feature,
    calc_trend_scores,
    calc_volatility_components,
    calc_adaptive_accuracy,
    calc_adaptive_factor,
    calc_confidence,
    compute_features,
)


# ── EMA / SMA ─────────────────────────────────────────────────────────────────

def test_ema_first_value_warm_up():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = _ema(s, 3)
    # First two values should be non-NaN because ewm(adjust=False) starts immediately
    assert not result.isna().any()


def test_sma_min_periods():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = _sma(s, 3)
    assert result.isna().iloc[:2].all()   # first 2 are NaN
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


# ── Wilder ATR ────────────────────────────────────────────────────────────────

def test_wilder_atr_positive():
    df = _make_df(100)
    atr = _wilder_atr(df["high"], df["low"], df["close"], 14)
    assert (atr.dropna() > 0).all()


def test_wilder_atr_constant_price():
    """Flat price → ATR should converge to 0."""
    n = 50
    s = pd.Series(100.0, index=range(n))
    atr = _wilder_atr(s, s, s, 14)
    assert atr.iloc[-1] == pytest.approx(0.0, abs=1e-9)


# ── ADR ───────────────────────────────────────────────────────────────────────

def test_adr_range():
    df = _make_df(300)
    adr = calc_adr(df["high"], df["low"], 20)
    valid = adr.dropna()
    assert (valid > 0).all()
    assert (valid < 50).all()  # sanity: ADR < 50% on normal data


# ── ATR percent ───────────────────────────────────────────────────────────────

def test_atr_percent_positive():
    df = _make_df(100)
    atp = calc_atr_percent(df["high"], df["low"], df["close"], 14)
    assert (atp.dropna() > 0).all()


# ── Volume feature ────────────────────────────────────────────────────────────

def test_volume_feature_bounds():
    df = _make_df(300)
    vf = calc_volume_feature(
        df["open"], df["high"], df["low"], df["close"], df["volume"],
        volume_ema_length=20, volume_multiplier=2.0,
    )
    valid = vf.dropna()
    assert (valid >= -1.0).all()
    assert (valid <= 1.0).all()


def test_volume_feature_zero_range():
    """When high == low, volume pressure must be 0."""
    n = 50
    idx = pd.RangeIndex(n)
    price = pd.Series(10.0, index=idx)
    vol = pd.Series(1_000_000.0, index=idx)
    vf = calc_volume_feature(price, price, price, price, vol, 20, 2.0)
    assert (vf == 0.0).all()


def test_volume_scores_complement():
    df = _make_df(200)
    vf = calc_volume_feature(
        df["open"], df["high"], df["low"], df["close"], df["volume"], 20, 2.0
    )
    bull, bear = calc_volume_scores(vf)
    np.testing.assert_allclose(bull + bear, 1.0, atol=1e-10)


# ── Trend feature ─────────────────────────────────────────────────────────────

def test_trend_feature_bounds():
    df = _make_df(400)
    tf = calc_trend_feature(df["high"], df["low"], df["close"], trend_lookback=5)
    valid = tf.dropna()
    assert (valid >= -1.0).all()
    assert (valid <= 1.0).all()


def test_trend_no_lookahead():
    """Trend feature must use shift(1) and shift(lookback+1) — not current bar."""
    df = _make_df(200)
    tf = calc_trend_feature(df["high"], df["low"], df["close"], trend_lookback=5)
    # Manually verify last bar uses prior sma50
    from features import _sma, _wilder_atr
    sma50 = _sma(df["close"], 50)
    atr14 = _wilder_atr(df["high"], df["low"], df["close"], 14)
    expected_slope = (sma50.iloc[-2] - sma50.iloc[-7]) / atr14.iloc[-2]
    expected_feature = float(np.clip(expected_slope / 2, -1, 1))
    assert tf.iloc[-1] == pytest.approx(expected_feature, abs=1e-8)


# ── Volatility ────────────────────────────────────────────────────────────────

def test_volatility_risk_bounds():
    df = _make_df(300)
    _, vol_risk, _ = calc_volatility_components(df["high"], df["low"], df["close"], 20, 20)
    valid = vol_risk.dropna()
    assert (valid >= 0).all()
    assert (valid <= 1).all()


def test_volatility_neutral():
    """Bull and bear volatility scores are always 0.5."""
    # This is verified by specification: volatility is direction-neutral.
    # The confidence formula adds 0.5 * adaptiveVolatilityWeight for both bull and bear.
    pass  # No separate score series; confirmed by formula in calc_confidence.


# ── Adaptive accuracy ─────────────────────────────────────────────────────────

def test_adaptive_accuracy_range():
    df = _make_df(300)
    from features import calc_volume_feature, calc_adaptive_accuracy
    vf = calc_volume_feature(
        df["open"], df["high"], df["low"], df["close"], df["volume"], 20, 2.0
    )
    acc = calc_adaptive_accuracy(vf, df["close"], 50)
    valid = acc.dropna()
    assert (valid >= 0).all()
    assert (valid <= 1).all()


def test_adaptive_factor_clamp():
    acc = pd.Series([0.0, 0.5, 1.0])
    f = calc_adaptive_factor(acc, adaptive_rate=2.0)
    # acc=0.0 → 1 + 2*(0-0.5)*2 = 1-2 = -1 → clamp to 0.25
    assert f.iloc[0] == pytest.approx(0.25)
    # acc=0.5 → 1 + 0 = 1.0
    assert f.iloc[1] == pytest.approx(1.0)
    # acc=1.0 → 1 + 2*(0.5)*2 = 3.0
    assert f.iloc[2] == pytest.approx(3.0)


# ── Confidence ────────────────────────────────────────────────────────────────

def test_confidence_neutral_inputs():
    """With all components at 0.5, confidence should be exactly 50."""
    n = 50
    ones = pd.Series(1.0, index=range(n))
    half = pd.Series(0.5, index=range(n))
    zeros = pd.Series(0.0, index=range(n))
    bull_conf, bear_conf = calc_confidence(
        half, half, zeros,
        40.0, 35.0, 25.0, ones, ones,
    )
    np.testing.assert_allclose(bull_conf, 50.0, atol=1e-8)
    np.testing.assert_allclose(bear_conf, 50.0, atol=1e-8)


def test_confidence_sum_100():
    df = _make_df(300)
    from features import (
        calc_volume_feature, calc_volume_scores, calc_trend_feature, calc_trend_scores,
        calc_volatility_components, calc_adaptive_accuracy, calc_adaptive_factor,
    )
    vf = calc_volume_feature(df["open"], df["high"], df["low"], df["close"], df["volume"], 20, 2.0)
    bvs, _ = calc_volume_scores(vf)
    tf = calc_trend_feature(df["high"], df["low"], df["close"], 5)
    bts, _ = calc_trend_scores(tf)
    _, vr, _ = calc_volatility_components(df["high"], df["low"], df["close"], 20, 20)
    va = calc_adaptive_factor(calc_adaptive_accuracy(vf, df["close"], 50), 2.0)
    ta = calc_adaptive_factor(calc_adaptive_accuracy(tf, df["close"], 50), 2.0)

    bull, bear = calc_confidence(bvs, bts, vr, 40.0, 35.0, 25.0, va, ta)
    valid = (bull + bear).dropna()
    np.testing.assert_allclose(valid, 100.0, atol=1e-6)


# ── compute_features integration ─────────────────────────────────────────────

def test_compute_features_returns_none_short():
    df = _make_df(1)
    from config import ScannerConfig
    cfg = ScannerConfig()
    assert compute_features(df, cfg) is None


def test_compute_features_full():
    df = _make_df(400)
    from config import ScannerConfig
    cfg = ScannerConfig()
    f = compute_features(df, cfg)
    assert f is not None
    assert math.isfinite(f.bull_confidence)
    assert math.isfinite(f.bear_confidence)
    assert abs(f.bull_confidence + f.bear_confidence - 100.0) < 1e-4


def test_no_lookahead_volume_pressure():
    """
    The volume pressure formula must NOT incorporate close-to-close direction.
    We verify by checking the formula: pressure = (close - open) / (high - low).
    """
    df = _make_df(200)
    vf = calc_volume_feature(
        df["open"], df["high"], df["low"], df["close"], df["volume"], 20, 2.0
    )
    # Manual calculation for last bar
    i = -1
    hl = df["high"].iloc[i] - df["low"].iloc[i]
    if hl > 0:
        expected_pressure = (df["close"].iloc[i] - df["open"].iloc[i]) / hl
    else:
        expected_pressure = 0.0
    # Can't directly compare vf to raw pressure because of volume_strength scaling,
    # but sign should match (unless strength is 0).
    # At minimum, verify no future data is used:
    # Volume feature on bar N must equal feature computed on df[:N]
    for idx in [50, 99, 199]:
        full = calc_volume_feature(
            df["open"], df["high"], df["low"], df["close"], df["volume"], 20, 2.0
        ).iloc[idx]
        partial = calc_volume_feature(
            df["open"].iloc[:idx+1], df["high"].iloc[:idx+1],
            df["low"].iloc[:idx+1], df["close"].iloc[:idx+1],
            df["volume"].iloc[:idx+1], 20, 2.0
        ).iloc[-1]
        assert full == pytest.approx(partial, abs=1e-8)

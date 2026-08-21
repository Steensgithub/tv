"""
Unit tests for Pine-compatible indicator calculations.

Covers:
  - pine_sma
  - pine_ema (seeding, convergence)
  - pine_rma / pine_atr (Wilder smoothing)
  - signed_volume_delta / window_cvd
  - ma_expansion_condition
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from scanner.indicators import (
    pine_ema,
    pine_sma,
    pine_rma,
    pine_atr,
    signed_volume_delta,
    window_cvd,
    ma_expansion_condition,
)


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------


class TestPineSma:
    def test_warmup_nans(self) -> None:
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = pine_sma(data, 3)
        assert math.isnan(result[0])
        assert math.isnan(result[1])
        assert not math.isnan(result[2])

    def test_values(self) -> None:
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = pine_sma(data, 3)
        assert math.isclose(result[2], 2.0)
        assert math.isclose(result[3], 3.0)
        assert math.isclose(result[4], 4.0)

    def test_length_1(self) -> None:
        data = np.array([5.0, 10.0, 15.0])
        result = pine_sma(data, 1)
        np.testing.assert_array_equal(result, data)


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------


class TestPineEma:
    def test_warmup_nans(self) -> None:
        data = np.ones(10)
        result = pine_ema(data, 5)
        # First 4 should be NaN
        for i in range(4):
            assert math.isnan(result[i])

    def test_seed_is_sma(self) -> None:
        """EMA seed at index (length-1) must equal SMA of first length bars."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        length = 3
        result = pine_ema(data, length)
        # Seed at index 2 = (1+2+3)/3 = 2.0
        assert math.isclose(result[2], 2.0)

    def test_constant_series(self) -> None:
        """EMA of a constant series must equal that constant."""
        data = np.full(50, 100.0)
        result = pine_ema(data, 10)
        valid = result[~np.isnan(result)]
        np.testing.assert_allclose(valid, 100.0, atol=1e-9)

    def test_insufficient_data(self) -> None:
        data = np.array([1.0, 2.0])
        result = pine_ema(data, 5)
        assert all(math.isnan(x) for x in result)

    def test_convergence(self) -> None:
        """EMA should converge to the input when input is constant after seed."""
        rng = np.random.default_rng(42)
        data = np.concatenate([rng.uniform(90, 110, 20), np.full(200, 100.0)])
        result = pine_ema(data, 10)
        # Last value should be very close to 100
        assert abs(result[-1] - 100.0) < 0.5


# ---------------------------------------------------------------------------
# RMA / ATR
# ---------------------------------------------------------------------------


class TestPineRma:
    def test_seed_is_sma(self) -> None:
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        length = 3
        result = pine_rma(data, length)
        # seed at index 2 = mean([1,2,3]) = 2.0
        assert math.isclose(result[2], 2.0)

    def test_constant_series(self) -> None:
        data = np.full(50, 5.0)
        result = pine_rma(data, 5)
        valid = result[~np.isnan(result)]
        np.testing.assert_allclose(valid, 5.0, atol=1e-9)


class TestPineAtr:
    def test_length_1(self) -> None:
        """ATR(1) = TR seeded by first bar."""
        high = np.array([10.0, 12.0, 11.0])
        low  = np.array([8.0,  9.0,  10.0])
        close = np.array([9.0, 11.0, 10.5])
        atr = pine_atr(high, low, close, 1)
        # TR[0] = 10 - 8 = 2; RMA(1) seed = 2
        assert math.isclose(atr[0], 2.0)

    def test_all_nans_when_insufficient(self) -> None:
        high = np.array([10.0, 11.0])
        low  = np.array([8.0, 9.0])
        close = np.array([9.0, 10.0])
        atr = pine_atr(high, low, close, 5)
        assert all(math.isnan(x) for x in atr)

    def test_wilder_smoothing(self) -> None:
        """
        Verify Wilder's formula: rma[i] = (rma[i-1]*(n-1) + tr[i]) / n
        """
        n = 3
        highs = np.array([10.0, 12.0, 11.0, 13.0, 12.0])
        lows  = np.array([ 8.0,  9.0,  9.0, 10.0, 10.0])
        closes= np.array([ 9.0, 11.0, 10.0, 12.0, 11.0])
        atr = pine_atr(highs, lows, closes, n)
        # Manually compute TR
        trs = []
        trs.append(highs[0] - lows[0])  # = 2
        for i in range(1, 5):
            trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
        # RMA seed at index 2 = mean(trs[0:3])
        seed = sum(trs[:3]) / 3
        rma_3 = seed
        rma_4 = (rma_3 * (n-1) + trs[3]) / n
        assert math.isclose(atr[2], seed, rel_tol=1e-9)
        assert math.isclose(atr[3], rma_4, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Signed-volume CVD proxy
# ---------------------------------------------------------------------------


class TestSignedVolumeDelta:
    def test_bullish_bar(self) -> None:
        d = signed_volume_delta(np.array([10.0]), np.array([9.0]), np.array([100.0]))
        assert d[0] == 100.0

    def test_bearish_bar(self) -> None:
        d = signed_volume_delta(np.array([9.0]), np.array([10.0]), np.array([100.0]))
        assert d[0] == -100.0

    def test_doji_bar(self) -> None:
        d = signed_volume_delta(np.array([10.0]), np.array([10.0]), np.array([100.0]))
        assert d[0] == 0.0


class TestWindowCvd:
    def _make_arrays(self) -> tuple:
        closes  = np.array([10.0, 11.0, 9.0, 12.0, 10.0, 11.0])
        opens   = np.array([ 9.0, 10.0,10.0, 10.0, 11.0, 10.0])
        volumes = np.array([100.0,200.0,150.0,300.0,100.0,250.0])
        return closes, opens, volumes

    def test_bullish_window(self) -> None:
        c, o, v = self._make_arrays()
        cvd, total, bull, bear = window_cvd(c, o, v, 6)
        # bars 0,1,3,5 are bullish → +100+200+300+250 = 850
        # bars 2,4 are bearish → -150-100 = -250
        assert math.isclose(cvd, 850 - 250)
        assert math.isclose(total, 1100.0)

    def test_insufficient_bars(self) -> None:
        c = np.array([1.0, 2.0])
        o = np.array([1.0, 1.0])
        v = np.array([100.0, 100.0])
        with pytest.raises(ValueError, match="Need at least"):
            window_cvd(c, o, v, 6)

    def test_nan_volume_raises(self) -> None:
        c = np.array([1.0]*6)
        o = np.array([1.0]*6)
        v = np.array([100.0, 100.0, np.nan, 100.0, 100.0, 100.0])
        with pytest.raises(ValueError, match="NaN"):
            window_cvd(c, o, v, 6)


# ---------------------------------------------------------------------------
# MA expansion
# ---------------------------------------------------------------------------


class TestMaExpansion:
    def test_expanding(self) -> None:
        """Distances should all be increasing."""
        # Create arrays where distances are strictly increasing
        n = 50
        # Use simple linear spreading
        ma2 = np.linspace(100, 110, n)
        ma3 = np.linspace(100, 105, n)
        ma4 = np.linspace(100, 102, n)
        ma5 = np.linspace(100, 101, n)
        result = ma_expansion_condition(ma2, ma3, ma4, ma5)
        # After warmup, most recent bars should be True
        assert result[-1] == True

    def test_contracting(self) -> None:
        """Distances converging → expansion should be False."""
        n = 50
        ma2 = np.linspace(110, 100, n)
        ma3 = np.linspace(105, 100, n)
        ma4 = np.linspace(102, 100, n)
        ma5 = np.linspace(101, 100, n)
        result = ma_expansion_condition(ma2, ma3, ma4, ma5)
        assert result[-1] == False

    def test_index_0_always_false(self) -> None:
        data = np.arange(1, 11, dtype=float)
        result = ma_expansion_condition(data, data * 0.9, data * 0.8, data * 0.7)
        assert result[0] == False

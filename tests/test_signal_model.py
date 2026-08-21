"""
tests/test_signal_model.py – unit tests for signal evaluation logic.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from config import ScannerConfig
from features import BarFeatures
from signal_model import evaluate_signal


def _make_cfg(**overrides) -> ScannerConfig:
    return ScannerConfig(**overrides)


def _make_features(**overrides) -> BarFeatures:
    f = BarFeatures()
    # Default: strong bullish setup
    defaults = dict(
        adr_pct=3.0,
        atr_pct=1.5,
        volatility_ratio=1.2,
        volatility_risk=0.2,
        volume_relative=1.5,
        volume_feature=0.6,
        bull_volume_score=0.8,
        bear_volume_score=0.2,
        trend_slope=0.5,
        trend_feature=0.4,
        bull_trend_score=0.7,
        bear_trend_score=0.3,
        bull_confidence=70.0,
        bear_confidence=30.0,
    )
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(f, k, v)
    return f


_TS = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)


def _call(f: BarFeatures, cfg: ScannerConfig) -> object:
    return evaluate_signal(
        symbol="AAPL",
        exchange="NASDAQ",
        bar_timestamp=_TS,
        timeframe="1d",
        close=150.0,
        volume=1_000_000,
        features=f,
        quality_score=65.0,
        quality_coverage=4,
        opportunity_score=60.0,
        combined_score=63.5,
        cfg=cfg,
    )


class TestLongSignalFires:
    def test_basic_long(self):
        f = _make_features()
        r = _call(f, _make_cfg())
        assert r.long_signal is True

    def test_event_id_format(self):
        r = _call(_make_features(), _make_cfg())
        assert "AAPL:1d:" in r.event_id
        assert r.event_id.endswith(":LONG")

    def test_signal_reason_contains_confidence(self):
        r = _call(_make_features(), _make_cfg())
        assert "70.0%" in r.signal_reason


class TestLongSignalBlocked:
    def test_low_confidence_no_signal(self):
        f = _make_features(bull_confidence=55.0, bear_confidence=45.0)
        r = _call(f, _make_cfg(confidence_threshold=60.0))
        assert r.long_signal is False

    def test_bear_dominates_no_signal(self):
        f = _make_features(bull_confidence=62.0, bear_confidence=65.0)
        r = _call(f, _make_cfg())
        assert r.long_signal is False

    def test_no_component_agreement(self):
        # Both volume and trend bearish → agreement=0
        f = _make_features(bull_volume_score=0.3, bull_trend_score=0.4)
        r = _call(f, _make_cfg(min_component_agreement=2))
        assert r.long_signal is False

    def test_volatility_filter_fails(self):
        f = _make_features(volatility_ratio=3.0)
        cfg = _make_cfg(high_volatility_filter=True, max_signal_volatility_ratio=2.0)
        r = _call(f, cfg)
        assert r.long_signal is False

    def test_volatility_nan_with_filter_enabled(self):
        f = _make_features(volatility_ratio=float("nan"))
        cfg = _make_cfg(high_volatility_filter=True)
        r = _call(f, cfg)
        assert r.long_signal is False

    def test_volatility_nan_with_filter_disabled(self):
        # When filter disabled, NaN volatility should not block signal
        f = _make_features(volatility_ratio=float("nan"))
        cfg = _make_cfg(high_volatility_filter=False)
        r = _call(f, cfg)
        assert r.long_signal is True


class TestComponentAgreement:
    def test_count_volume_and_trend(self):
        f = _make_features(bull_volume_score=0.6, bull_trend_score=0.6)
        r = _call(f, _make_cfg())
        assert r.component_agreement == 2

    def test_one_agreement(self):
        f = _make_features(bull_volume_score=0.4, bull_trend_score=0.6)
        r = _call(f, _make_cfg())
        assert r.component_agreement == 1

    def test_volatility_not_counted(self):
        """Volatility must never count toward directional agreement."""
        # We confirm component_agreement can never exceed 2 from volume+trend alone
        f = _make_features(bull_volume_score=0.9, bull_trend_score=0.9)
        r = _call(f, _make_cfg())
        assert r.component_agreement == 2  # max is 2, not 3

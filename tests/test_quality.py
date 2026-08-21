"""
tests/test_quality.py – unit tests for quality and opportunity scoring.
"""
from __future__ import annotations

import pytest
from providers.base import FundamentalData
from quality import calc_quality_score, _norm
from opportunity import calc_opportunity_score, calc_combined_score
from features import BarFeatures


# ── _norm ─────────────────────────────────────────────────────────────────────

def test_norm_lower_bound():
    assert _norm(-20.0, -20.0, 50.0) == pytest.approx(0.0)

def test_norm_upper_bound():
    assert _norm(50.0, -20.0, 50.0) == pytest.approx(1.0)

def test_norm_midpoint():
    assert _norm(15.0, -20.0, 50.0) == pytest.approx(0.5)

def test_norm_clamp_below():
    assert _norm(-30.0, -20.0, 50.0) == pytest.approx(0.0)

def test_norm_clamp_above():
    assert _norm(100.0, -20.0, 50.0) == pytest.approx(1.0)


# ── Quality score ─────────────────────────────────────────────────────────────

def test_quality_no_data():
    r = calc_quality_score(None)
    assert r.score == pytest.approx(50.0)
    assert r.data_coverage == 0

def test_quality_missing_fields_neutral():
    """Missing fields should default to 0.5, not 0."""
    fund = FundamentalData(symbol="X", diluted_eps_growth=0.40)  # above midpoint of [-20%, 50%]
    r = calc_quality_score(fund)
    # Only EPS growth is provided; coverage=1
    assert r.data_coverage == 1
    # Score must be > 50 because eps_growth=40% is well above midpoint of [-20%, 50%]
    assert r.score > 50.0

def test_quality_all_data():
    fund = FundamentalData(
        symbol="X",
        diluted_eps_growth=0.25,   # normalized ≈ 0.643
        revenue_growth=0.15,       # normalized ≈ 0.5
        roic=0.15,                 # normalized = 0.5
        debt_to_equity=1.0,        # inverse: (1 - (1/2)) = 0.5
        fcf_margin=0.10,           # normalized = 0.5
        data_count=5,
    )
    r = calc_quality_score(fund)
    assert r.data_coverage == 5
    assert 50.0 < r.score < 100.0

def test_quality_score_range():
    for epsv in [-0.25, 0.0, 0.5, 0.75]:
        fund = FundamentalData(symbol="X", diluted_eps_growth=epsv)
        r = calc_quality_score(fund)
        assert 0.0 <= r.score <= 100.0


# ── Opportunity score ─────────────────────────────────────────────────────────

def _make_features(**kw) -> BarFeatures:
    f = BarFeatures()
    defaults = dict(
        adr_pct=4.0,
        volume_relative=1.2,
        trend_feature=0.3,
        bull_volume_score=0.65,
        bull_trend_score=0.65,
        bull_confidence=65.0,
        bear_confidence=35.0,
        volatility_ratio=1.1,
        volatility_risk=0.1,
        volume_feature=0.3,
        bear_volume_score=0.35,
        bear_trend_score=0.35,
        trend_slope=0.2,
        atr_pct=1.5,
    )
    defaults.update(kw)
    for k, v in defaults.items():
        setattr(f, k, v)
    return f

def test_opportunity_score_range():
    f = _make_features()
    r = calc_opportunity_score(f, momentum_20=0.05)
    assert 0.0 <= r.score <= 100.0

def test_opportunity_no_momentum():
    f = _make_features()
    r = calc_opportunity_score(f, momentum_20=None)
    assert 0.0 <= r.score <= 100.0

def test_combined_score():
    q = 60.0
    o = 80.0
    c = calc_combined_score(q, o)
    assert c == pytest.approx(60.0 * 0.70 + 80.0 * 0.30)

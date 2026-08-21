"""
opportunity.py – Opportunity Score and Combined Score.

Opportunity components and weights:
  - Weighted momentum:  35%  (recent close-to-close % change, 20-bar)
  - ADR percentage:     25%
  - Relative volume:    20%
  - Trend strength:     20%  (abs(trend_feature))

Normalisation bounds:
  - Momentum:         -20% to +100%
  - ADR:              2% to 8%
  - Relative volume:  0.5× to 2.0×
  - Trend strength:   0 to 1 (abs trend feature is already in [0, 1])
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from features import BarFeatures


@dataclass
class OpportunityResult:
    score: float   # 0–100


def _norm(value: float, lower: float, upper: float) -> float:
    if upper == lower:
        return 0.5
    return max(0.0, min(1.0, (value - lower) / (upper - lower)))


def calc_opportunity_score(
    features: BarFeatures,
    momentum_20: float | None = None,
) -> OpportunityResult:
    """
    Parameters
    ----------
    features    : BarFeatures from the last closed bar.
    momentum_20 : 20-bar momentum as a fraction (e.g. 0.10 = +10%).
                  Caller computes: (close[-1] / close[-21] - 1).
                  Pass None → neutral 0.5.
    """

    def safe(v: float | None, lower: float, upper: float) -> float:
        if v is None or not math.isfinite(v):
            return 0.5
        return _norm(v, lower, upper)

    mom_score = safe(momentum_20, -0.20, 1.00)
    adr_score = safe(features.adr_pct, 2.0, 8.0)
    rvol_score = safe(features.volume_relative, 0.5, 2.0)
    trend_score = safe(abs(features.trend_feature), 0.0, 1.0)

    raw = (
        mom_score * 0.35
        + adr_score * 0.25
        + rvol_score * 0.20
        + trend_score * 0.20
    )
    return OpportunityResult(score=raw * 100.0)


def calc_combined_score(quality_score: float, opportunity_score: float) -> float:
    """CombinedScore = QualityScore * 0.70 + OpportunityScore * 0.30"""
    return quality_score * 0.70 + opportunity_score * 0.30

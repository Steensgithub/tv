"""
quality.py – fundamental quality score calculation.

Metrics and weights:
  - Diluted EPS growth (25%)
  - Revenue growth (20%)
  - ROIC (20%)
  - Debt-to-equity (15%, inverse)
  - FCF margin (20%)

Normalization bounds (fixed, as specified):
  - EPS growth:   [-20%, +50%]
  - Revenue growth: [-10%, +40%]
  - ROIC:         [0%, 30%]
  - D/E:          [0, 2]  (inverse: lower D/E = higher score)
  - FCF margin:   [-10%, +30%]

Missing data → neutral 0.5.  Track data_coverage count.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from providers.base import FundamentalData


@dataclass
class QualityResult:
    score: float          # 0–100
    data_coverage: int    # 0–5 (how many of the 5 metrics are populated)


def _norm(value: float, lower: float, upper: float) -> float:
    if upper == lower:
        return 0.5
    n = (value - lower) / (upper - lower)
    return max(0.0, min(1.0, n))


def calc_quality_score(fund: FundamentalData | None) -> QualityResult:
    """Compute quality score in [0, 100] from fundamental data."""
    if fund is None:
        return QualityResult(score=50.0, data_coverage=0)

    eps_g = fund.diluted_eps_growth
    rev_g = fund.revenue_growth
    roic = fund.roic
    dte = fund.debt_to_equity
    fcf = fund.fcf_margin

    coverage = sum(v is not None for v in [eps_g, rev_g, roic, dte, fcf])

    # Normalize each metric; use 0.5 if missing
    def safe(v: float | None, lower: float, upper: float, inverse: bool = False) -> float:
        if v is None or not math.isfinite(v):
            return 0.5
        n = _norm(v, lower, upper)
        return 1.0 - n if inverse else n

    eps_score = safe(eps_g, -0.20, 0.50)
    rev_score = safe(rev_g, -0.10, 0.40)
    roic_score = safe(roic, 0.00, 0.30)
    dte_score = safe(dte, 0.00, 2.00, inverse=True)
    fcf_score = safe(fcf, -0.10, 0.30)

    # Weighted sum → [0, 1]
    raw = (
        eps_score * 0.25
        + rev_score * 0.20
        + roic_score * 0.20
        + dte_score * 0.15
        + fcf_score * 0.20
    )
    return QualityResult(score=raw * 100.0, data_coverage=coverage)

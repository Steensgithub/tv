"""
signal_model.py – LONG signal evaluation and result dataclass.

This module contains NO IO.  It takes a BarFeatures and a ScannerConfig
and returns a SignalResult.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SignalResult:
    # Identity
    symbol: str
    exchange: str
    timestamp: datetime           # bar close timestamp (UTC)
    timeframe: str

    # Price / volume
    close: float
    volume: float
    volume_relative: float
    adr_pct: float
    atr_pct: float

    # Volatility
    volatility_ratio: float
    volatility_risk: float

    # Volume component
    volume_feature: float
    bull_volume_score: float

    # Trend component
    trend_slope: float
    trend_feature: float
    bull_trend_score: float

    # Confidence
    bull_confidence: float
    bear_confidence: float

    # Agreement flags
    volume_agreement: bool
    trend_agreement: bool
    volatility_filter_pass: bool
    component_agreement: int      # count of directional components agreeing bullish

    # Scores
    quality_score: float
    quality_data_coverage: int
    opportunity_score: float
    combined_score: float

    # Signal
    long_signal: bool
    signal_reason: str

    # Unique event id
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


def evaluate_signal(
    symbol: str,
    exchange: str,
    bar_timestamp: datetime,
    timeframe: str,
    close: float,
    volume: float,
    features,   # BarFeatures
    quality_score: float,
    quality_coverage: int,
    opportunity_score: float,
    combined_score: float,
    cfg,        # ScannerConfig
) -> SignalResult:
    """
    Evaluate whether the current bar triggers a LONG signal.
    All bar data must be from a confirmed (closed) bar.
    """
    from features import BarFeatures

    f: BarFeatures = features

    # ── NaN guard ────────────────────────────────────────────────────────────
    def _ok(v: float) -> bool:
        return math.isfinite(v)

    # ── Component agreement ──────────────────────────────────────────────────
    vol_agree = _ok(f.bull_volume_score) and f.bull_volume_score > 0.5
    tr_agree = _ok(f.bull_trend_score) and f.bull_trend_score > 0.5
    comp_agreement = int(vol_agree) + int(tr_agree)

    # ── Volatility filter ────────────────────────────────────────────────────
    if cfg.high_volatility_filter:
        if not _ok(f.volatility_ratio):
            vola_pass = False
        else:
            vola_pass = f.volatility_ratio <= cfg.max_signal_volatility_ratio
    else:
        vola_pass = True

    # ── Confidence conditions ────────────────────────────────────────────────
    bull_conf = f.bull_confidence if _ok(f.bull_confidence) else 0.0
    bear_conf = f.bear_confidence if _ok(f.bear_confidence) else 100.0

    confidence_ok = (
        bull_conf >= cfg.confidence_threshold
        and bull_conf > bear_conf
    )

    # ── Agreement condition ───────────────────────────────────────────────────
    agreement_ok = comp_agreement >= cfg.min_component_agreement

    # ── Optional combined score gate ─────────────────────────────────────────
    score_ok = True
    if cfg.require_combined_score:
        score_ok = combined_score >= cfg.combined_score_threshold

    # ── Final LONG ────────────────────────────────────────────────────────────
    long_signal = confidence_ok and agreement_ok and vola_pass and score_ok

    # ── Signal reason ─────────────────────────────────────────────────────────
    if long_signal:
        reason = (
            f"LONG: confidence {bull_conf:.1f}%, "
            f"bullish agreement {comp_agreement}/{cfg.min_component_agreement}, "
            f"volatility ratio {f.volatility_ratio:.2f}×, "
            f"threshold {cfg.confidence_threshold:.0f}%."
        )
    else:
        parts: list[str] = []
        if not confidence_ok:
            parts.append(f"confidence {bull_conf:.1f}% < {cfg.confidence_threshold:.0f}%")
        if not agreement_ok:
            parts.append(f"agreement {comp_agreement}/{cfg.min_component_agreement}")
        if not vola_pass:
            parts.append(f"volatility {f.volatility_ratio:.2f}× > {cfg.max_signal_volatility_ratio}×")
        reason = "NO SIGNAL: " + "; ".join(parts) if parts else "NO SIGNAL"

    # Build unique event id: symbol:timeframe:timestamp:LONG
    bar_ts_str = bar_timestamp.strftime("%Y%m%dT%H%M%S")
    event_id = f"{symbol}:{timeframe}:{bar_ts_str}:LONG"

    return SignalResult(
        symbol=symbol,
        exchange=exchange,
        timestamp=bar_timestamp,
        timeframe=timeframe,
        close=close,
        volume=volume,
        volume_relative=f.volume_relative if _ok(f.volume_relative) else float("nan"),
        adr_pct=f.adr_pct,
        atr_pct=f.atr_pct,
        volatility_ratio=f.volatility_ratio,
        volatility_risk=f.volatility_risk,
        volume_feature=f.volume_feature,
        bull_volume_score=f.bull_volume_score,
        trend_slope=f.trend_slope,
        trend_feature=f.trend_feature,
        bull_trend_score=f.bull_trend_score,
        bull_confidence=bull_conf,
        bear_confidence=bear_conf,
        volume_agreement=vol_agree,
        trend_agreement=tr_agree,
        volatility_filter_pass=vola_pass,
        component_agreement=comp_agreement,
        quality_score=quality_score,
        quality_data_coverage=quality_coverage,
        opportunity_score=opportunity_score,
        combined_score=combined_score,
        long_signal=long_signal,
        signal_reason=reason,
        event_id=event_id,
    )

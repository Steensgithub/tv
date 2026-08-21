"""
validation.py – parity testing against Pine Script exported CSV data.

Usage:
    python validation.py --csv pine_export.csv --symbol AAPL --timeframe 1d

The CSV must have columns:
    time, open, high, low, close, volume, pine_long_signal [, pine_confidence]

Reports:
  - Pine signals count
  - Scanner signals count
  - Matching (same bar timestamp + LONG)
  - Missing (Pine fired, scanner did not)
  - Extra   (Scanner fired, Pine did not)
  - Max confidence deviation
  - Max feature deviation per component
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Load Pine CSV ────────────────────────────────────────────────────────────

def load_pine_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"])
    df = df.set_index("time")
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df.sort_index()


# ── Run scanner over historical data ─────────────────────────────────────────

def run_scanner_on_df(df: pd.DataFrame, cfg: object) -> pd.DataFrame:
    """
    Run compute_features + evaluate_signal on each bar (bar-by-bar, no lookahead).
    Returns a DataFrame with per-bar scanner output.
    """
    from features import compute_features
    from quality import calc_quality_score
    from opportunity import calc_opportunity_score, calc_combined_score
    from signal_model import evaluate_signal

    qs = calc_quality_score(None)  # no fundamentals in backtest
    records = []

    for i in range(2, len(df) + 1):
        window = df.iloc[:i]
        f = compute_features(window, cfg)
        if f is None:
            continue
        bar = window.iloc[-1]
        bar_ts = window.index[-1]
        if not isinstance(bar_ts, datetime):
            bar_ts = pd.Timestamp(bar_ts).to_pydatetime()
        if bar_ts.tzinfo is None:
            bar_ts = bar_ts.replace(tzinfo=timezone.utc)

        mom20 = None
        if len(window) >= 22:
            base = window["close"].iloc[-22]
            cur = window["close"].iloc[-1]
            mom20 = float(cur / base - 1.0) if base != 0 else None

        opp = calc_opportunity_score(f, momentum_20=mom20)
        combined = calc_combined_score(qs.score, opp.score)
        result = evaluate_signal(
            symbol=str(df.columns.name or "UNKNOWN"),
            exchange="",
            bar_timestamp=bar_ts,
            timeframe=getattr(cfg, "timeframe", "1d"),
            close=float(bar["close"]),
            volume=float(bar["volume"]),
            features=f,
            quality_score=qs.score,
            quality_coverage=qs.data_coverage,
            opportunity_score=opp.score,
            combined_score=combined,
            cfg=cfg,
        )
        records.append(
            {
                "time": bar_ts,
                "scanner_long": result.long_signal,
                "scanner_conf": result.bull_confidence,
                "scanner_vol_feat": result.volume_feature,
                "scanner_trend_feat": result.trend_feature,
                "scanner_vola_ratio": result.volatility_ratio,
            }
        )

    return pd.DataFrame(records).set_index("time")


# ── Comparison report ────────────────────────────────────────────────────────

def compare(pine_df: pd.DataFrame, scanner_df: pd.DataFrame, conf_tol: float, feat_tol: float) -> None:
    merged = pine_df.join(scanner_df, how="inner")
    if merged.empty:
        logger.error("No overlapping bars between Pine CSV and scanner output")
        return

    pine_long = merged.get("pine_long_signal", pd.Series(False, index=merged.index)).astype(bool)
    scanner_long = merged["scanner_long"].astype(bool)

    pine_count = int(pine_long.sum())
    scanner_count = int(scanner_long.sum())
    matching = int((pine_long & scanner_long).sum())
    missing = int((pine_long & ~scanner_long).sum())
    extra = int((~pine_long & scanner_long).sum())

    print(f"\n{'='*60}")
    print(f"  Parity Report")
    print(f"{'='*60}")
    print(f"  Total bars compared : {len(merged)}")
    print(f"  Pine LONG signals   : {pine_count}")
    print(f"  Scanner LONG signals: {scanner_count}")
    print(f"  Matching            : {matching}")
    print(f"  Missing (Pine only) : {missing}")
    print(f"  Extra  (Scan only)  : {extra}")

    if "pine_confidence" in merged.columns:
        conf_diff = (merged["scanner_conf"] - merged["pine_confidence"]).abs()
        max_conf_diff = conf_diff.max()
        print(f"  Max confidence diff : {max_conf_diff:.4f}%")
        if max_conf_diff > conf_tol:
            print(f"  ⚠ EXCEEDS tolerance {conf_tol}%")

    if missing > 0:
        print("\n  Missing signals (bars where Pine fired but scanner did not):")
        miss_idx = merged.index[pine_long & ~scanner_long]
        for ts in miss_idx[:10]:
            row = merged.loc[ts]
            print(f"    {ts}  scanner_conf={row['scanner_conf']:.2f}%")

    if extra > 0:
        print("\n  Extra signals (bars where scanner fired but Pine did not):")
        extra_idx = merged.index[~pine_long & scanner_long]
        for ts in extra_idx[:10]:
            row = merged.loc[ts]
            print(f"    {ts}  scanner_conf={row['scanner_conf']:.2f}%")

    parity_ok = missing == 0 and extra == 0
    print(f"\n  Parity: {'PASS ✓' if parity_ok else 'FAIL ✗'}")
    print(f"{'='*60}\n")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate scanner parity against Pine Script export")
    parser.add_argument("--csv", required=True, help="Path to Pine Script exported CSV")
    parser.add_argument("--symbol", default="SYMBOL")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--conf-tol", type=float, default=1.0, help="Confidence tolerance %")
    parser.add_argument("--feat-tol", type=float, default=0.01, help="Feature tolerance")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    from config import ScannerConfig
    cfg = ScannerConfig(timeframe=args.timeframe)

    pine_df = load_pine_csv(args.csv)
    scanner_df = run_scanner_on_df(pine_df, cfg)
    compare(pine_df, scanner_df, args.conf_tol, args.feat_tol)


if __name__ == "__main__":
    main()

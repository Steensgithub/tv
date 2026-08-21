"""
Smoke test module (also invoked via `tv-scanner self-test`).
"""

from __future__ import annotations

import math
import tempfile
from datetime import datetime, timezone

import numpy as np

UTC = timezone.utc


def run_smoke_tests() -> None:
    print("Running smoke tests…")
    _test_indicators()
    _test_db()
    _test_order_blocks()
    print("All smoke tests passed. ✓")


def _test_indicators() -> None:
    from scanner.indicators import pine_ema, pine_sma, pine_atr, window_cvd

    data = np.linspace(100, 200, 50)
    ema = pine_ema(data, 8)
    assert not any(math.isnan(x) for x in ema[8:]), "EMA has unexpected NaN after warmup"

    sma = pine_sma(data, 50)
    assert math.isclose(sma[-1], 150.0, rel_tol=0.01), f"SMA[-1] = {sma[-1]}"

    high = data + 2
    low  = data - 2
    atr  = pine_atr(high, low, data, 14)
    assert not math.isnan(atr[-1]), "ATR[-1] is NaN"

    closes = np.full(6, 10.0)
    opens  = np.full(6, 9.0)
    vols   = np.full(6, 1000.0)
    cvd, total, bull, bear = window_cvd(closes, opens, vols, 6)
    assert cvd > 0, "CVD should be positive for bullish bars"

    print("  ✓ Indicators")


def _test_db() -> None:
    from scanner.models import SignalRecord, ScannerStatus, ScannerState
    from scanner.state_store import StateStore

    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        store = StateStore(f.name)

        sig = SignalRecord(
            symbol="AAPL",
            signal_timestamp_utc=datetime(2024, 1, 1, tzinfo=UTC),
            signal_timestamp_ny="2024-01-01T09:30:00-05:00",
            signal_timeframe="4H",
            htf_timeframe="1D",
            close_price=200.0,
            ema_8=198.0, ema_21=195.0, ema_34=190.0, sma_50=185.0, sma_200=170.0,
            htf_regime="bullish", htf_bandwidth_atr=1.0,
            ma_expansion=True, ma_ribbon_distance_pct=0.5,
            cvd_window=100.0, bullish_cvd_ratio=60.0,
            six_bar_avg_volume=1e6, relative_volume_ratio=120.0,
            atr=2.0, initial_stop=197.0, tp1=202.0, tp2=204.0,
        )

        assert store.save_signal(sig) is True
        assert store.save_signal(sig) is False  # duplicate

        rows = store.get_signals()
        assert len(rows) == 1

        status = ScannerStatus(state=ScannerState.RUNNING, symbols_scanned=10)
        store.update_status(status)
        st = store.get_status()
        assert st["state"] == "running"

    print("  ✓ Database")


def _test_order_blocks() -> None:
    from scanner.order_blocks import OrderBlockTracker

    tracker = OrderBlockTracker(left_bars=5, right_bars=5, use_body=True,
                                 max_bullish_zones=10, remove_on_first_touch=True)
    n = 25
    ts = np.array([datetime(2024, 1, 1, i, tzinfo=UTC) for i in range(n)])
    opens  = np.full(n, 100.0)
    highs  = np.full(n, 105.0)
    lows   = np.full(n, 95.0)
    closes = np.full(n, 102.0)

    pivot = 7
    lows[pivot] = 70.0
    for i in range(max(0, pivot - 5), pivot):
        lows[i] = 80.0 + (i - pivot + 5)
    for i in range(pivot + 1, min(n, pivot + 6)):
        lows[i] = 80.0 + (i - pivot)
    opens[pivot] = 85.0
    closes[pivot] = 82.0

    for i in range(pivot + 5 + 1):
        tracker.process_bar(ts, opens, highs, lows, closes, i)

    zones = tracker.active_zones()
    assert len(zones) == 1, f"Expected 1 zone, got {len(zones)}"
    assert math.isclose(zones[0].bottom, 70.0)

    print("  ✓ Order blocks")


if __name__ == "__main__":
    run_smoke_tests()

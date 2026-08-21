"""
tests/test_bars.py – unit tests for bar aggregation and session filtering.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import pytest

from bars import aggregate_bars, filter_session, bars_to_df, BarBuffer
from providers.base import OHLCVBar
from config import ScannerConfig


def _bar(symbol: str, ts: datetime, o=10.0, h=11.0, l=9.0, c=10.5, v=1_000_000) -> OHLCVBar:
    return OHLCVBar(symbol=symbol, timestamp=ts, open=o, high=h, low=l, close=c, volume=v)


# ── bars_to_df ────────────────────────────────────────────────────────────────

def test_bars_to_df_empty():
    df = bars_to_df([])
    assert len(df) == 0


def test_bars_to_df_sorted():
    ts1 = datetime(2024, 1, 2, 10, tzinfo=timezone.utc)
    ts2 = datetime(2024, 1, 1, 10, tzinfo=timezone.utc)
    bars = [_bar("X", ts1), _bar("X", ts2)]
    df = bars_to_df(bars)
    assert df.index[0] < df.index[1]


# ── aggregate_bars ────────────────────────────────────────────────────────────

def _make_1m_bars(n: int) -> list[OHLCVBar]:
    base = datetime(2024, 1, 2, 14, 30, 0, tzinfo=timezone.utc)
    return [
        _bar("X", base + timedelta(minutes=i), o=float(i), h=float(i)+1, l=float(i)-0.5, c=float(i)+0.5, v=1000)
        for i in range(n)
    ]


def test_aggregate_5m():
    bars = _make_1m_bars(10)
    agg = aggregate_bars(bars, "5m")
    assert len(agg) == 2  # 2 complete 5-min bars
    # First 5-min bar: open from bar 0, close from bar 4
    assert agg[0].open == pytest.approx(0.0)
    assert agg[0].close == pytest.approx(4.5)
    assert agg[0].high == pytest.approx(5.0)
    assert agg[0].low == pytest.approx(-0.5)
    assert agg[0].volume == pytest.approx(5000.0)


def test_aggregate_1m_passthrough():
    bars = _make_1m_bars(5)
    result = aggregate_bars(bars, "1m")
    assert result == bars


# ── filter_session ────────────────────────────────────────────────────────────

def test_filter_session_daily_passthrough():
    cfg = ScannerConfig(timeframe="1d")
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)
    result = filter_session(df, cfg)
    assert len(result) == len(df)


def test_filter_session_removes_premarket():
    cfg = ScannerConfig(timeframe="1m")
    # Create bars at 8:00, 9:30, 10:00, 16:00, 16:30 ET
    import pytz
    et = pytz.timezone("America/New_York")
    times_et = ["08:00", "09:30", "10:00", "16:00", "16:30"]
    idx = pd.DatetimeIndex([
        et.localize(datetime.strptime(f"2024-01-02 {t}", "%Y-%m-%d %H:%M")).astimezone(timezone.utc)
        for t in times_et
    ])
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)
    result = filter_session(df, cfg)
    # 08:00 and 16:30 should be excluded; 09:30, 10:00, 16:00 kept
    assert len(result) == 3


# ── BarBuffer ─────────────────────────────────────────────────────────────────

def test_bar_buffer_append_and_len():
    buf = BarBuffer("AAPL")
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    buf.append(_bar("AAPL", ts))
    assert len(buf) == 1


def test_bar_buffer_to_df():
    buf = BarBuffer("AAPL")
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    buf.append(_bar("AAPL", ts, c=42.0))
    df = buf.to_df()
    assert df["close"].iloc[0] == pytest.approx(42.0)


def test_bar_buffer_max_size():
    buf = BarBuffer("AAPL", max_size=10)
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(20):
        buf.append(_bar("AAPL", base + timedelta(hours=i)))
    assert len(buf) == 10

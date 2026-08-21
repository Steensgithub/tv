"""
Tests for the state store (SQLite persistence, deduplication, status).
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone

import pytest

from scanner.models import SignalRecord, ScannerStatus, ScannerState
from scanner.state_store import StateStore

UTC = timezone.utc


def _make_signal(**kwargs) -> SignalRecord:
    defaults = dict(
        symbol="AAPL",
        exchange="NASDAQ",
        signal_timestamp_utc=datetime(2024, 3, 10, 20, 0, 0, tzinfo=UTC),
        signal_timestamp_ny="2024-03-10T16:00:00-04:00",
        signal_timeframe="4H",
        htf_timeframe="1D",
        strategy_version="1.0",
        close_price=218.42,
        ema_8=216.0,
        ema_21=213.0,
        ema_34=210.0,
        sma_50=205.0,
        sma_200=190.0,
        htf_regime="bullish",
        htf_bandwidth_atr=1.2,
        ma_expansion=True,
        ma_ribbon_distance_pct=0.65,
        cvd_window=500_000.0,
        bullish_cvd_ratio=62.5,
        six_bar_avg_volume=1_000_000.0,
        relative_volume_ratio=134.5,
        order_block_bottom=215.80,
        order_block_top=217.10,
        atr=2.5,
        initial_stop=214.67,
        tp1=220.92,
        tp2=223.42,
        signal_reason="LONG_SIGNAL",
        data_provider="yfinance",
        data_freshness_seconds=12.0,
        bar_confirmed=True,
    )
    defaults.update(kwargs)
    return SignalRecord(**defaults)


@pytest.fixture
def store(tmp_path) -> StateStore:
    return StateStore(str(tmp_path / "test.db"))


class TestStateStore:
    def test_save_signal(self, store: StateStore) -> None:
        sig = _make_signal()
        result = store.save_signal(sig)
        assert result is True

    def test_duplicate_suppressed(self, store: StateStore) -> None:
        sig = _make_signal()
        store.save_signal(sig)
        result = store.save_signal(sig)
        assert result is False

    def test_get_signals_symbol_filter(self, store: StateStore) -> None:
        store.save_signal(_make_signal(symbol="AAPL"))
        store.save_signal(_make_signal(
            symbol="MSFT",
            signal_timestamp_utc=datetime(2024, 3, 10, 20, 0, 0, tzinfo=UTC),
        ))
        # Different timestamp for MSFT dedup
        store.save_signal(_make_signal(
            symbol="MSFT",
            signal_timestamp_utc=datetime(2024, 3, 11, 20, 0, 0, tzinfo=UTC),
        ))
        aapl = store.get_signals(symbol="AAPL")
        assert len(aapl) == 1
        assert aapl[0]["symbol"] == "AAPL"

    def test_get_signals_timeframe_filter(self, store: StateStore) -> None:
        store.save_signal(_make_signal(signal_timeframe="4H"))
        store.save_signal(_make_signal(
            signal_timeframe="1H",
            signal_timestamp_utc=datetime(2024, 3, 11, 20, 0, 0, tzinfo=UTC),
        ))
        results = store.get_signals(signal_timeframe="1H")
        assert len(results) == 1
        assert results[0]["signal_timeframe"] == "1H"

    def test_get_signals_since_filter(self, store: StateStore) -> None:
        store.save_signal(_make_signal(
            signal_timestamp_utc=datetime(2024, 1, 1, tzinfo=UTC)
        ))
        store.save_signal(_make_signal(
            symbol="MSFT",
            signal_timestamp_utc=datetime(2024, 6, 1, tzinfo=UTC)
        ))
        results = store.get_signals(since=datetime(2024, 3, 1, tzinfo=UTC))
        assert len(results) == 1
        assert results[0]["symbol"] == "MSFT"

    def test_get_signals_confirmed_filter(self, store: StateStore) -> None:
        store.save_signal(_make_signal(bar_confirmed=True))
        store.save_signal(_make_signal(
            bar_confirmed=False,
            signal_timestamp_utc=datetime(2024, 3, 11, 20, 0, 0, tzinfo=UTC),
        ))
        results = store.get_signals(confirmed_only=True)
        assert all(r["bar_confirmed"] for r in results)

    def test_update_and_get_status(self, store: StateStore) -> None:
        status = ScannerStatus(
            state=ScannerState.RUNNING,
            symbols_scanned=15,
            new_signals_total=3,
            data_errors=0,
            provider_latency_ms=250.0,
        )
        store.update_status(status)
        row = store.get_status()
        assert row["state"] == "running"
        assert row["symbols_scanned"] == 15

    def test_symbol_state_roundtrip(self, store: StateStore) -> None:
        ts = datetime(2024, 3, 10, 20, 0, 0, tzinfo=UTC)
        store.set_symbol_state("AAPL", "4H", ts, True, ts)
        state = store.get_symbol_state("AAPL", "4H")
        assert state["last_long_condition"] == 1
        assert "2024-03-10" in state["last_candle_ts"]

    def test_pagination(self, store: StateStore) -> None:
        for i in range(5):
            ts = datetime(2024, 3, i + 1, 20, 0, 0, tzinfo=UTC)
            store.save_signal(_make_signal(signal_timestamp_utc=ts))

        page1 = store.get_signals(limit=2, offset=0)
        page2 = store.get_signals(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        # No overlap
        ids1 = {r["id"] for r in page1}
        ids2 = {r["id"] for r in page2}
        assert ids1.isdisjoint(ids2)

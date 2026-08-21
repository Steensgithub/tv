from __future__ import annotations

from datetime import UTC, datetime

from models import SymbolEngineState
from state_store import StateStore


def test_duplicate_alert_prevention(tmp_path) -> None:
    store = StateStore(str(tmp_path / "state.db"))
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    assert store.mark_alert_sent("AAPL", "5m", "LONG", ts) is True
    assert store.mark_alert_sent("AAPL", "5m", "LONG", ts) is False


def test_state_recovery_after_restart(tmp_path) -> None:
    path = tmp_path / "state.db"
    store = StateStore(str(path))
    state = SymbolEngineState()
    state.prev_atr = 1.23
    state.trade.active = True
    store.save_symbol_state("AAPL", state)
    store.close()

    store2 = StateStore(str(path))
    loaded = store2.load_symbol_state("AAPL")
    assert loaded is not None
    assert loaded.prev_atr == 1.23
    assert loaded.trade.active is True

"""
Unit tests for Stock Screener V4 (stock_screener_v4.py).

Tests cover the six fix areas described in the problem statement:
1. Enhanced logging
2. Validation & error handling (scores never None, response validated)
3. Guaranteed UI refresh after data updates
4. State management (apply_snapshot populates state under lock)
5. Retry logic with exponential back-off
6. Discovery improvements (score + status feedback)

tkinter is not available in headless CI.  We stub it in sys.modules so the
module can be imported and all non-GUI logic tested directly.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Stub tkinter before any import of the module under test
# ---------------------------------------------------------------------------
import sys
import types
from unittest.mock import MagicMock


def _make_tk_stub() -> types.ModuleType:
    """Return a lightweight tkinter stub that satisfies the module's imports."""
    tk = types.ModuleType("tkinter")

    # Constants used in stock_screener_v4
    for name in ("BOTH", "LEFT", "RIGHT", "TOP", "X", "Y"):
        setattr(tk, name, name)

    class _Var:
        def __init__(self, value=None):
            self._v = value

        def get(self):
            return self._v

        def set(self, v):
            self._v = v

    tk.BooleanVar = _Var
    tk.StringVar = _Var

    class _Widget:
        def __init__(self, *a, **kw):
            pass

        def pack(self, **kw):
            pass

        def configure(self, **kw):
            pass

        config = configure

        def get_children(self):
            return []

        def delete(self, *a):
            pass

        def insert(self, *a, **kw):
            pass

        def heading(self, *a, **kw):
            pass

        def column(self, *a, **kw):
            pass

        def yview(self, *a):
            pass

        def protocol(self, *a, **kw):
            pass

        def geometry(self, *a):
            pass

        def title(self, *a):
            pass

        def destroy(self):
            pass

        def mainloop(self):
            pass

        def after(self, *a, **kw):
            pass

        def clipboard_clear(self):
            pass

        def clipboard_append(self, *a):
            pass

    tk.Tk = _Widget
    tk.Toplevel = _Widget

    # messagebox stub
    mb = types.ModuleType("tkinter.messagebox")
    mb.showwarning = MagicMock()
    mb.showinfo = MagicMock()
    tk.messagebox = mb

    # ttk stub
    ttk = types.ModuleType("tkinter.ttk")
    for widget in (
        "Frame", "Checkbutton", "Button", "Notebook", "Treeview",
        "Scrollbar", "Label", "Entry",
    ):
        setattr(ttk, widget, _Widget)
    tk.ttk = ttk

    return tk, mb, ttk


_tk_stub, _mb_stub, _ttk_stub = _make_tk_stub()
sys.modules.setdefault("tkinter", _tk_stub)
sys.modules.setdefault("tkinter.messagebox", _mb_stub)
sys.modules.setdefault("tkinter.ttk", _ttk_stub)

# ---------------------------------------------------------------------------
# Now import the module under test
# ---------------------------------------------------------------------------
import math
import queue
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

import stock_screener_v4 as mod


# ---------------------------------------------------------------------------
# Helper: build a minimal app instance without running __init__ fully
# ---------------------------------------------------------------------------

def _make_app() -> mod.StockScreenerV4App:
    """Return a StockScreenerV4App with GUI side-effects patched out."""
    app = object.__new__(mod.StockScreenerV4App)

    # Core state
    app.lock = threading.RLock()
    app.state: dict[str, mod.SymbolState] = {}
    app.universe = {k: list(v) for k, v in mod.DEFAULT_UNIVERSE.items()}
    app.discovery: list[str] = []
    app.stop_event = threading.Event()
    app.ws_stop_event = threading.Event()
    app.ws_thread = None
    app.ws_reconnect_count = 0
    app.ui_refresh_queue: queue.Queue[str] = queue.Queue(maxsize=500)

    # Stub GUI handles
    app.realtime_var = _tk_stub.BooleanVar(value=False)
    app.status_var = _tk_stub.StringVar(value="Ready")
    app.trees: dict[str, MagicMock] = {}

    # Lightweight root stub with trackable after() calls
    root = MagicMock()
    after_log: list[tuple] = []
    root.after = lambda *a, **kw: after_log.append(a)
    app.root = root
    app._root_after_log = after_log  # expose for assertions

    return app


# ---------------------------------------------------------------------------
# 1. SymbolState.as_row – serialisation
# ---------------------------------------------------------------------------
class TestSymbolStateAsRow(unittest.TestCase):
    def test_as_row_fields_and_types(self):
        st = mod.SymbolState(symbol="AAPL", region="US")
        st.last = 185.5
        st.vcp_score = 42.0
        st.gap_go_score = 12.3
        st.rs_pullback_score = 8.1
        st.total_score = 62.4
        st.reason = "VCP structure"
        st.updated_at = 1_700_000_000.0
        row = st.as_row()
        self.assertEqual(len(row), 8)
        self.assertEqual(row[0], "AAPL")
        self.assertIn("185.50", row[1])
        self.assertIn("42.0", row[2])
        self.assertIn("62.4", row[5])
        self.assertEqual(row[6], "VCP structure")

    def test_as_row_zero_updated_at_shows_dash(self):
        st = mod.SymbolState(symbol="X", region="EU")
        row = st.as_row()
        self.assertEqual(row[7], "-")


# ---------------------------------------------------------------------------
# 2. Scoring – values never None, bounds checking
# ---------------------------------------------------------------------------
class TestScoringValidation(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()

    def _zero_state(self) -> mod.SymbolState:
        st = mod.SymbolState(symbol="Z", region="US")
        st.last = st.open = st.high = st.low = 0.0
        st.volume = 0
        return st

    def test_vcp_zero_inputs_returns_zero_not_none(self):
        score = self.app.score_vcp(self._zero_state())
        self.assertIsNotNone(score)
        self.assertEqual(score, 0.0)

    def test_gap_go_zero_open_returns_zero_not_none(self):
        score = self.app.score_gap_go(self._zero_state())
        self.assertIsNotNone(score)
        self.assertEqual(score, 0.0)

    def test_rs_pullback_zero_range_returns_zero_not_none(self):
        score = self.app.score_rs_pullback(self._zero_state())
        self.assertIsNotNone(score)
        self.assertEqual(score, 0.0)

    def test_scores_finite_and_non_negative_on_real_data(self):
        st = mod.SymbolState(symbol="T", region="US")
        st.last = 150.0
        st.open = 100.0
        st.high = 160.0
        st.low = 90.0
        st.volume = 10_000_000
        for score in (self.app.score_vcp(st), self.app.score_gap_go(st), self.app.score_rs_pullback(st)):
            self.assertGreaterEqual(score, 0.0)
            self.assertTrue(math.isfinite(score))


# ---------------------------------------------------------------------------
# 3. apply_snapshot – state management + guaranteed UI refresh
# ---------------------------------------------------------------------------
class TestApplySnapshot(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.app.state["MSFT"] = mod.SymbolState(symbol="MSFT", region="US")
        self._refresh_reasons: list[str] = []
        self.app._schedule_ui_refresh = lambda r: self._refresh_reasons.append(r)

    def _data(self, last=310.5) -> dict:
        return {"last": last, "open": 305.0, "high": 315.0, "low": 303.0, "volume": 8_000_000}

    def test_populates_price_fields(self):
        self.app.apply_snapshot("MSFT", self._data(), source="refresh")
        st = self.app.state["MSFT"]
        self.assertAlmostEqual(st.last, 310.5)
        self.assertAlmostEqual(st.open, 305.0)
        self.assertEqual(st.volume, 8_000_000)

    def test_sets_updated_at_timestamp(self):
        before = time.time()
        self.app.apply_snapshot("MSFT", self._data(), source="refresh")
        self.assertGreaterEqual(self.app.state["MSFT"].updated_at, before)

    def test_computes_all_scores(self):
        self.app.apply_snapshot("MSFT", self._data(), source="refresh")
        st = self.app.state["MSFT"]
        for attr in ("vcp_score", "gap_go_score", "rs_pullback_score", "total_score"):
            self.assertIsNotNone(getattr(st, attr))

    def test_schedules_ui_refresh(self):
        self.app.apply_snapshot("MSFT", self._data(), source="refresh")
        self.assertGreaterEqual(len(self._refresh_reasons), 1)
        self.assertIn("refresh", self._refresh_reasons[-1])

    def test_sets_reason_string(self):
        self.app.apply_snapshot("MSFT", self._data(), source="test")
        reason = self.app.state["MSFT"].reason
        self.assertIsInstance(reason, str)
        self.assertGreater(len(reason), 0)

    def test_creates_new_state_if_absent(self):
        self.app.apply_snapshot("NEWCO", self._data(), source="test")
        self.assertIn("NEWCO", self.app.state)


# ---------------------------------------------------------------------------
# 4. fetch_with_retry – exponential back-off + retry logic
# ---------------------------------------------------------------------------
class TestFetchWithRetry(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()

    def _good(self):
        return {"last": 100.0, "open": 99.0, "high": 102.0, "low": 98.0, "volume": 1000}

    def test_succeeds_on_first_attempt(self):
        self.app.fetch_snapshot = MagicMock(return_value=self._good())
        result = self.app.fetch_with_retry("AAPL", max_attempts=3)
        self.assertEqual(result, self._good())
        self.app.fetch_snapshot.assert_called_once_with("AAPL")

    def test_retries_on_transient_failure_then_succeeds(self):
        self.app.fetch_snapshot = MagicMock(side_effect=[RuntimeError("timeout"), self._good()])
        with patch("time.sleep"):
            result = self.app.fetch_with_retry("AAPL", max_attempts=3)
        self.assertEqual(result, self._good())
        self.assertEqual(self.app.fetch_snapshot.call_count, 2)

    def test_raises_after_all_retries_exhausted(self):
        self.app.fetch_snapshot = MagicMock(side_effect=RuntimeError("network down"))
        with patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                self.app.fetch_with_retry("FAIL", max_attempts=3)
        self.assertEqual(self.app.fetch_snapshot.call_count, 3)

    def test_backoff_grows_between_retries(self):
        """time.sleep is called with non-decreasing delays (exponential backoff)."""
        self.app.fetch_snapshot = MagicMock(side_effect=RuntimeError("err"))
        sleep_calls: list[float] = []
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            try:
                self.app.fetch_with_retry("X", max_attempts=4)
            except RuntimeError:
                pass
        # 3 sleeps between 4 attempts
        self.assertEqual(len(sleep_calls), 3)
        for i in range(1, len(sleep_calls)):
            self.assertGreaterEqual(sleep_calls[i], sleep_calls[i - 1])


# ---------------------------------------------------------------------------
# 5. fetch_snapshot – validates Stooq/CSV response
# ---------------------------------------------------------------------------
class TestFetchSnapshot(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()

    def _mock_urlopen(self, csv_body: str):
        resp = MagicMock()
        resp.read.return_value = csv_body.encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_parses_valid_csv(self):
        csv_body = (
            "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
            "AAPL,2024-01-01,09:30,180,185,178,182,1000000\n"
        )
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(csv_body)):
            data = self.app.fetch_snapshot("AAPL")
        self.assertAlmostEqual(data["last"], 182.0)
        self.assertAlmostEqual(data["open"], 180.0)
        self.assertEqual(data["volume"], 1_000_000)

    def test_raises_on_empty_response(self):
        csv_body = "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(csv_body)):
            with self.assertRaises((ValueError, RuntimeError)):
                self.app.fetch_snapshot("AAPL")

    def test_raises_on_nd_close(self):
        csv_body = (
            "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
            "AAPL,2024-01-01,09:30,N/D,N/D,N/D,N/D,N/D\n"
        )
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(csv_body)):
            with self.assertRaises((ValueError, RuntimeError)):
                self.app.fetch_snapshot("AAPL")

    def test_raises_on_zero_close(self):
        csv_body = (
            "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
            "AAPL,2024-01-01,09:30,0,0,0,0,0\n"
        )
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(csv_body)):
            with self.assertRaises((ValueError, RuntimeError)):
                self.app.fetch_snapshot("AAPL")


# ---------------------------------------------------------------------------
# 6. _refresh_worker – status feedback, failure counting, UI refresh
# ---------------------------------------------------------------------------
class TestRefreshWorker(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.app.universe = {"US": ["AAPL", "MSFT"], "EU": []}
        for sym in ("AAPL", "MSFT"):
            self.app.state[sym] = mod.SymbolState(symbol=sym, region="US")
        self.statuses: list[str] = []
        self.app.set_status = lambda m: self.statuses.append(m)
        self.refreshes: list[str] = []
        self.app._schedule_ui_refresh = lambda r: self.refreshes.append(r)

    def _good(self):
        return {"last": 150.0, "open": 148.0, "high": 152.0, "low": 147.0, "volume": 500_000}

    def test_fetches_all_symbols(self):
        self.app.fetch_with_retry = MagicMock(return_value=self._good())
        self.app._refresh_worker()
        self.assertEqual(self.app.fetch_with_retry.call_count, 2)

    def test_reports_completion_status(self):
        self.app.fetch_with_retry = MagicMock(return_value=self._good())
        self.app._refresh_worker()
        final = self.statuses[-1]
        self.assertIn("symbols=2", final)
        self.assertIn("failed=0", final)

    def test_counts_failures_in_status(self):
        self.app.fetch_with_retry = MagicMock(side_effect=RuntimeError("network"))
        self.app._refresh_worker()
        final = self.statuses[-1]
        self.assertIn("failed=2", final)

    def test_schedules_ui_refresh_on_completion(self):
        self.app.fetch_with_retry = MagicMock(return_value=self._good())
        self.app._refresh_worker()
        self.assertGreaterEqual(len(self.refreshes), 1)


# ---------------------------------------------------------------------------
# 7. _discover_worker – discovery result + status + UI refresh
# ---------------------------------------------------------------------------
class TestDiscoverWorker(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.app.universe = {"US": ["AAPL", "MSFT", "NVDA"], "EU": []}
        for sym in ("AAPL", "MSFT", "NVDA"):
            self.app.state[sym] = mod.SymbolState(symbol=sym, region="US")
        self.statuses: list[str] = []
        self.app.set_status = lambda m: self.statuses.append(m)
        self.refreshes: list[str] = []
        self.app._schedule_ui_refresh = lambda r: self.refreshes.append(r)

    def _high_score_data(self) -> dict:
        return {"last": 150.0, "open": 120.0, "high": 160.0, "low": 90.0, "volume": 50_000_000}

    def test_populates_discovery_list(self):
        self.app.fetch_with_retry = MagicMock(return_value=self._high_score_data())
        self.app._discover_worker()
        with self.app.lock:
            self.assertGreater(len(self.app.discovery), 0)

    def test_reports_status_with_match_count(self):
        self.app.fetch_with_retry = MagicMock(return_value=self._high_score_data())
        self.app._discover_worker()
        final = self.statuses[-1]
        self.assertIn("matches=", final)

    def test_reports_failure_count_in_status(self):
        self.app.fetch_with_retry = MagicMock(side_effect=RuntimeError("network"))
        self.app._discover_worker()
        final = self.statuses[-1]
        self.assertIn("failed=3", final)

    def test_schedules_ui_refresh(self):
        self.app.fetch_with_retry = MagicMock(return_value=self._high_score_data())
        self.app._discover_worker()
        self.assertGreaterEqual(len(self.refreshes), 1)

    def test_results_sorted_by_score_descending(self):
        """Discovery results must be ordered highest-score first."""
        base_scores = {"AAPL": 50.0, "MSFT": 30.0, "NVDA": 70.0}

        def fake_fetch(sym, **_):
            offset = base_scores[sym]
            return {
                "last": 100.0 + offset,
                "open": 90.0,
                "high": 110.0 + offset,
                "low": 80.0,
                "volume": 10_000_000,
            }

        self.app.fetch_with_retry = MagicMock(side_effect=lambda sym, **kw: fake_fetch(sym))
        with patch.object(mod, "DISCOVERY_THRESHOLD", 0.0):
            self.app._discover_worker()

        with self.app.lock:
            disc = list(self.app.discovery)

        if len(disc) >= 2:
            first_score = self.app.state[disc[0]].total_score
            second_score = self.app.state[disc[1]].total_score
            self.assertGreaterEqual(first_score, second_score)


# ---------------------------------------------------------------------------
# 8. _schedule_ui_refresh / _drain_ui_queue
# ---------------------------------------------------------------------------
class TestUIRefresh(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()

    def test_schedule_puts_reason_in_queue(self):
        self.app._schedule_ui_refresh("test-reason")
        self.assertFalse(self.app.ui_refresh_queue.empty())
        reason = self.app.ui_refresh_queue.get_nowait()
        self.assertEqual(reason, "test-reason")

    def test_schedule_falls_back_to_root_after_on_full_queue(self):
        # Fill the queue to capacity
        for i in range(self.app.ui_refresh_queue.maxsize):
            try:
                self.app.ui_refresh_queue.put_nowait(f"item-{i}")
            except queue.Full:
                break
        self.app.refresh_market_ui = MagicMock()
        before = len(self.app._root_after_log)
        self.app._schedule_ui_refresh("overflow")
        self.assertGreater(len(self.app._root_after_log), before)

    def test_drain_calls_refresh_when_items_present(self):
        self.app._schedule_ui_refresh("data-ready")
        self.app.refresh_market_ui = MagicMock()
        statuses: list[str] = []
        self.app.set_status = lambda m: statuses.append(m)
        self.app._drain_ui_queue()
        self.app.refresh_market_ui.assert_called_once()

    def test_drain_no_refresh_when_queue_empty(self):
        self.app.refresh_market_ui = MagicMock()
        self.app._drain_ui_queue()
        self.app.refresh_market_ui.assert_not_called()


# ---------------------------------------------------------------------------
# 9. get_or_create_state_locked – thread-safe state access
# ---------------------------------------------------------------------------
class TestGetOrCreateStateLocked(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()

    def test_creates_when_missing(self):
        st = self.app.get_or_create_state_locked("NEWCO")
        self.assertEqual(st.symbol, "NEWCO")

    def test_returns_existing_without_duplicate(self):
        existing = mod.SymbolState(symbol="AAPL", region="US")
        existing.last = 190.0
        self.app.state["AAPL"] = existing
        result = self.app.get_or_create_state_locked("AAPL")
        self.assertIs(result, existing)

    def test_concurrent_access_yields_same_object(self):
        results: list[mod.SymbolState] = []
        lock = threading.Lock()

        def worker():
            st = self.app.get_or_create_state_locked("CONCURRENT")
            with lock:
                results.append(st)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 10)
        first = results[0]
        for st in results[1:]:
            self.assertIs(st, first)


# ---------------------------------------------------------------------------
# 10. set_status – always reaches status_var; background threads use root.after
# ---------------------------------------------------------------------------
class TestSetStatus(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        # Bind the real method
        self.app.set_status = mod.StockScreenerV4App.set_status.__get__(
            self.app, mod.StockScreenerV4App
        )
        self.app.status_var = MagicMock()
        after_log: list[tuple] = []
        self.app.root.after = lambda *a, **kw: after_log.append(a)
        self.app._root_after_log = after_log

    def test_main_thread_sets_directly(self):
        self.app.set_status("hello")
        self.app.status_var.set.assert_called_with("hello")

    def test_background_thread_uses_root_after(self):
        done = threading.Event()

        def worker():
            self.app.set_status("from worker")
            done.set()

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=2)

        # root.after(0, ...) should have been recorded
        self.assertGreaterEqual(len(self.app._root_after_log), 1)
        self.assertEqual(self.app._root_after_log[0][0], 0)


if __name__ == "__main__":
    unittest.main()

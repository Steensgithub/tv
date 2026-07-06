"""
Stock Screener V4 (Standalone Download)

Dependencies:
- Python 3.10+
- tkinter (usually bundled with Python)
- websockets

Install and run:
1) pip install websockets
2) python stock_screener_v4_download.py
3) Check "Realtime" to start WS
4) Click "Refresh" to fetch data
5) Click "Discover Now" to scan
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import math
import random
import site
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from queue import Empty, Queue
from tkinter import BOTH, LEFT, RIGHT, TOP, X, Y, BooleanVar, StringVar, Tk, Toplevel, messagebox, ttk

try:
    import websockets  # type: ignore
    WEBSOCKETS_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    websockets = None
    WEBSOCKETS_IMPORT_ERROR = exc


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("stock_screener_v4")


DEFAULT_UNIVERSE = {
    "US": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"],
    "EU": ["SAP.DE", "ASML.AS", "AIR.PA", "SAN.PA", "ADS.DE"],
}


@dataclass
class SymbolState:
    symbol: str
    region: str
    last: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: int = 0
    updated_at: float = 0.0
    vcp_score: float = 0.0
    gap_go_score: float = 0.0
    rs_pullback_score: float = 0.0
    total_score: float = 0.0
    reason: str = ""

    def as_row(self) -> tuple[str, str, str, str, str, str, str, str]:
        ts = datetime.fromtimestamp(self.updated_at).strftime("%H:%M:%S") if self.updated_at else "-"
        return (
            self.symbol,
            f"{self.last:.2f}",
            f"{self.vcp_score:.1f}",
            f"{self.gap_go_score:.1f}",
            f"{self.rs_pullback_score:.1f}",
            f"{self.total_score:.1f}",
            self.reason,
            ts,
        )


class StockScreenerV4App:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("Stock Screener V4 Download")
        self.root.geometry("1180x700")

        self.lock = threading.RLock()
        self.state: dict[str, SymbolState] = {}
        self.universe = {k: list(v) for k, v in DEFAULT_UNIVERSE.items()}
        self.discovery: list[str] = []

        self.stop_event = threading.Event()
        self.ws_stop_event = threading.Event()
        self.ws_thread: threading.Thread | None = None
        self.ws_reconnect_count = 0

        self.ui_refresh_queue: Queue[str] = Queue(maxsize=500)

        self.realtime_var = BooleanVar(value=False)
        self.status_var = StringVar(value="Ready")

        self.trees: dict[str, ttk.Treeview] = {}
        self._build_ui()
        self._seed_initial_state()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(250, self._drain_ui_queue)
        self._log_runtime_diagnostics()
        self.set_status("Ready. Click Refresh to fetch data.")

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=8)
        top.pack(side=TOP, fill=X)

        ttk.Checkbutton(
            top,
            text="Realtime",
            variable=self.realtime_var,
            command=self.toggle_realtime,
        ).pack(side=LEFT, padx=(0, 10))

        ttk.Button(top, text="Refresh", command=self.refresh_clicked).pack(side=LEFT, padx=4)
        ttk.Button(top, text="Discover Now", command=self.discover_now_clicked).pack(side=LEFT, padx=4)
        ttk.Button(top, text="Copy Tickers", command=self.copy_tickers_dialog).pack(side=LEFT, padx=4)

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        for tab_name in ("All", "US", "EU", "Discovery"):
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=tab_name)

            cols = ("Symbol", "Last", "VCP", "Gap&Go", "RS Pullback", "Total", "Reason", "Updated")
            tree = ttk.Treeview(frame, columns=cols, show="headings", height=24)
            for c in cols:
                tree.heading(c, text=c)
                width = 150 if c in {"Reason"} else 110
                tree.column(c, width=width, anchor="center")
            tree.column("Reason", anchor="w", width=260)

            yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=yscroll.set)
            tree.pack(side=LEFT, fill=BOTH, expand=True)
            yscroll.pack(side=RIGHT, fill=Y)

            self.trees[tab_name] = tree

        status = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        status.pack(side=TOP, fill=X, padx=8, pady=(0, 8))

    def _seed_initial_state(self) -> None:
        with self.lock:
            for region, symbols in self.universe.items():
                for s in symbols:
                    self.state[s] = SymbolState(symbol=s, region=region)
        self._schedule_ui_refresh("Universe loaded")

    def get_or_create_state_locked(self, symbol: str, region: str | None = None) -> SymbolState:
        with self.lock:
            st = self.state.get(symbol)
            if st is None:
                st = SymbolState(symbol=symbol, region=region or self._region_for(symbol))
                self.state[symbol] = st
            return st

    def _region_for(self, symbol: str) -> str:
        if symbol in self.universe.get("US", []):
            return "US"
        if symbol in self.universe.get("EU", []):
            return "EU"
        return "US"

    def set_status(self, msg: str) -> None:
        if threading.current_thread() is threading.main_thread():
            self.status_var.set(msg)
        else:
            self.root.after(0, lambda m=msg: self.status_var.set(m))
        log.info("STATUS: %s", msg)

    def _log_runtime_diagnostics(self) -> None:
        log.info("Python executable: %s", sys.executable)
        log.info("Python version: %s", sys.version.split()[0])
        try:
            log.info("User site-packages: %s", site.getusersitepackages())
        except Exception:
            pass
        if websockets is None:
            log.error("websockets import FAILED: %r", WEBSOCKETS_IMPORT_ERROR)
        else:
            log.info("websockets import OK: %s", getattr(websockets, "__version__", "unknown"))

    def _schedule_ui_refresh(self, reason: str) -> None:
        try:
            self.ui_refresh_queue.put_nowait(reason)
        except Exception:
            log.warning("UI refresh queue full; forcing immediate refresh")
            self.root.after(0, self.refresh_market_ui)

    def _drain_ui_queue(self) -> None:
        last_reason: str | None = None
        while True:
            try:
                last_reason = self.ui_refresh_queue.get_nowait()
            except Empty:
                break
        if last_reason:
            self.refresh_market_ui()
            self.set_status(f"UI refreshed: {last_reason}")
        self.root.after(300, self._drain_ui_queue)

    def refresh_clicked(self) -> None:
        threading.Thread(target=self._refresh_worker, daemon=True, name="refresh-worker").start()

    def discover_now_clicked(self) -> None:
        threading.Thread(target=self._discover_worker, daemon=True, name="discover-worker").start()

    def _refresh_worker(self) -> None:
        self.set_status("Refreshing market data...")
        symbols = self.all_symbols()
        failures = 0
        for sym in symbols:
            try:
                data = self.fetch_with_retry(sym)
                self.apply_snapshot(sym, data, source="refresh")
            except Exception as exc:
                failures += 1
                log.exception("Refresh failed for %s: %s", sym, exc)
        self._schedule_ui_refresh("manual refresh complete")
        self.set_status(f"Refresh complete. symbols={len(symbols)}, failed={failures}")

    def _discover_worker(self) -> None:
        self.set_status("Running Discovery Now scan...")
        selected: list[tuple[float, str]] = []
        symbols = self.all_symbols()
        failures = 0

        for sym in symbols:
            try:
                data = self.fetch_with_retry(sym)
                self.apply_snapshot(sym, data, source="discover")
                st = self.get_or_create_state_locked(sym)
                if st.total_score >= 90:
                    selected.append((st.total_score, sym))
            except Exception:
                failures += 1

        selected.sort(reverse=True)
        with self.lock:
            self.discovery = [sym for _, sym in selected[:30]]

        self._schedule_ui_refresh("discovery scan complete")
        self.set_status(f"Discovery complete. matches={len(self.discovery)} failed={failures}")

    def all_symbols(self) -> list[str]:
        with self.lock:
            vals = list(self.universe.get("US", [])) + list(self.universe.get("EU", []))
        return vals

    def fetch_with_retry(self, symbol: str, max_attempts: int = 4) -> dict[str, float | int]:
        backoff = 0.7
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                log.info("Fetching %s (attempt %s/%s)", symbol, attempt, max_attempts)
                return self.fetch_snapshot(symbol)
            except Exception as exc:
                last_exc = exc
                log.warning("Fetch attempt failed for %s: %s", symbol, exc)
                if attempt < max_attempts:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 6.0)
        raise RuntimeError(f"Failed to fetch {symbol}: {last_exc}")

    def fetch_snapshot(self, symbol: str) -> dict[str, float | int]:
        # Public CSV endpoint for lightweight snapshots.
        query_symbol = symbol.lower().replace(".", "")
        url = (
            "https://stooq.com/q/l/?"
            + urllib.parse.urlencode({"s": query_symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"})
        )
        log.debug("Requesting URL %s", url)
        req = urllib.request.Request(url=url, headers={"User-Agent": "stock-screener-v4-download/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error for {symbol}: {exc}") from exc

        reader = csv.DictReader(io.StringIO(raw))
        rows = list(reader)
        if not rows:
            raise ValueError(f"No data returned for {symbol}")

        row = rows[0]
        if row.get("Close") in {None, "N/D"}:
            raise ValueError(f"Invalid quote for {symbol}: {row}")

        close = float(row.get("Close", "0") or 0)
        opn = float(row.get("Open", "0") or 0)
        high = float(row.get("High", "0") or 0)
        low = float(row.get("Low", "0") or 0)
        volume = int(float(row.get("Volume", "0") or 0))

        if close <= 0:
            raise ValueError(f"Non-positive close for {symbol}")

        return {
            "last": close,
            "open": opn,
            "high": high,
            "low": low,
            "volume": volume,
        }

    def apply_snapshot(self, symbol: str, data: dict[str, float | int], source: str) -> None:
        with self.lock:
            st = self.get_or_create_state_locked(symbol)
            st.last = float(data.get("last", st.last))
            st.open = float(data.get("open", st.open))
            st.high = float(data.get("high", st.high))
            st.low = float(data.get("low", st.low))
            st.volume = int(data.get("volume", st.volume))
            st.updated_at = time.time()

            st.vcp_score = self.score_vcp(st)
            st.gap_go_score = self.score_gap_go(st)
            st.rs_pullback_score = self.score_rs_pullback(st)
            st.total_score = st.vcp_score + st.gap_go_score + st.rs_pullback_score

            if st.total_score >= 130:
                st.reason = "Strong multi-setup"
            elif st.gap_go_score >= 50:
                st.reason = "Gap&Go candidate"
            elif st.vcp_score >= 45:
                st.reason = "VCP structure"
            elif st.rs_pullback_score >= 45:
                st.reason = "RS pullback"
            else:
                st.reason = "Monitor"

        log.info(
            "Applied %s update | %s last=%.2f vcp=%.1f gap=%.1f rs=%.1f total=%.1f",
            source,
            symbol,
            st.last,
            st.vcp_score,
            st.gap_go_score,
            st.rs_pullback_score,
            st.total_score,
        )
        self._schedule_ui_refresh(f"{source} update for {symbol}")

    def score_vcp(self, st: SymbolState) -> float:
        if st.high <= 0 or st.low <= 0 or st.last <= 0:
            return 0.0
        range_ratio = max(0.0, min(1.0, (st.high - st.low) / max(st.last, 1e-6)))
        contraction = 1.0 - min(range_ratio * 5, 1.0)
        close_position = max(0.0, min(1.0, (st.last - st.low) / max(st.high - st.low, 1e-6)))
        volume_quality = min(math.log10(max(st.volume, 1)) / 7.0, 1.0)
        return round(60 * contraction + 25 * close_position + 15 * volume_quality, 1)

    def score_gap_go(self, st: SymbolState) -> float:
        if st.open <= 0:
            return 0.0
        gap = (st.last - st.open) / st.open
        gap_score = max(0.0, min(1.0, gap / 0.08)) * 70
        breakout = max(0.0, min(1.0, (st.last - ((st.high + st.low) / 2)) / max(st.high, 1e-6))) * 20
        vol_boost = min(math.log10(max(st.volume, 1)) / 7.0, 1.0) * 10
        return round(gap_score + breakout + vol_boost, 1)

    def score_rs_pullback(self, st: SymbolState) -> float:
        if st.high <= st.low or st.last <= 0:
            return 0.0
        mid = (st.high + st.low) / 2
        pullback_depth = max(0.0, min(1.0, (mid - st.low) / max(st.high - st.low, 1e-6)))
        hold_above_mid = 1.0 if st.last >= mid else max(0.0, st.last / max(mid, 1e-6))
        recovery = max(0.0, min(1.0, (st.last - st.low) / max(st.high - st.low, 1e-6)))
        return round(40 * pullback_depth + 35 * hold_above_mid + 25 * recovery, 1)

    def refresh_market_ui(self) -> None:
        with self.lock:
            items = list(self.state.values())
            discovery_set = set(self.discovery)

        all_sorted = sorted(items, key=lambda s: s.total_score, reverse=True)
        us_sorted = [s for s in all_sorted if s.region == "US"]
        eu_sorted = [s for s in all_sorted if s.region == "EU"]
        disc_sorted = [s for s in all_sorted if s.symbol in discovery_set]

        self._replace_tree("All", all_sorted)
        self._replace_tree("US", us_sorted)
        self._replace_tree("EU", eu_sorted)
        self._replace_tree("Discovery", disc_sorted)

    def _replace_tree(self, name: str, rows: list[SymbolState]) -> None:
        tree = self.trees[name]
        tree.delete(*tree.get_children())
        for st in rows:
            tree.insert("", "end", values=st.as_row())

    def copy_tickers_dialog(self) -> None:
        with self.lock:
            ranked = sorted(self.state.values(), key=lambda s: s.total_score, reverse=True)
            tickers = [s.symbol for s in ranked[:25]]

        if not tickers:
            messagebox.showinfo("Copy Tickers", "No tickers available yet. Refresh first.")
            return

        dialog = Toplevel(self.root)
        dialog.title("Copy Tickers")
        dialog.geometry("480x280")

        ttk.Label(dialog, text="Top tickers (comma-separated):", padding=8).pack(fill=X)
        text = ttk.Entry(dialog)
        text.pack(fill=X, padx=8)
        joined = ", ".join(tickers)
        text.insert(0, joined)

        output = ttk.Label(dialog, text="", padding=8)
        output.pack(fill=X)

        def do_copy() -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(joined)
            output.config(text="Copied to clipboard")
            self.set_status("Copied tickers to clipboard")

        ttk.Button(dialog, text="Copy", command=do_copy).pack(pady=8)

    def toggle_realtime(self) -> None:
        if self.realtime_var.get():
            ok = self.start_realtime()
            if not ok:
                self.realtime_var.set(False)
        else:
            self.stop_realtime()

    def start_realtime(self) -> bool:
        if websockets is None:
            messagebox.showwarning(
                "Realtime unavailable",
                "websockets import failed. Run: pip install websockets",
            )
            self.set_status("Realtime unavailable: install websockets")
            log.error("Realtime start failed: websockets not importable (%r)", WEBSOCKETS_IMPORT_ERROR)
            return False

        if self.ws_thread and self.ws_thread.is_alive():
            self.set_status("Realtime already running")
            return True

        self.ws_stop_event.clear()
        self.ws_thread = threading.Thread(target=self._run_ws_thread, daemon=True, name="ws-thread")
        self.ws_thread.start()
        self.set_status("Realtime connecting...")
        return True

    def stop_realtime(self) -> None:
        self.ws_stop_event.set()
        self.set_status("Realtime stopped")

    def _run_ws_thread(self) -> None:
        try:
            asyncio.run(self._ws_loop())
        except Exception as exc:
            log.exception("WS thread crashed: %s", exc)
            self.set_status(f"Realtime failed: {exc}")

    async def _ws_loop(self) -> None:
        # Echo endpoint is used as a lightweight websocket transport.
        # Incoming messages trigger small simulated ticks for tracked symbols.
        url = "wss://echo.websocket.events"
        backoff = 1.0

        while not self.ws_stop_event.is_set() and not self.stop_event.is_set():
            self.ws_reconnect_count += 1
            reconnect_no = self.ws_reconnect_count
            try:
                log.info("WS connect attempt #%s", reconnect_no)
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=4) as ws:
                    self.set_status(f"Realtime connected (attempt #{reconnect_no})")
                    backoff = 1.0
                    while not self.ws_stop_event.is_set() and not self.stop_event.is_set():
                        payload = {
                            "type": "heartbeat",
                            "ts": time.time(),
                            "symbols": self.all_symbols(),
                        }
                        await ws.send(json.dumps(payload))
                        msg = await asyncio.wait_for(ws.recv(), timeout=20)
                        self._handle_ws_message(msg)
                        await asyncio.sleep(2.0)
            except Exception as exc:
                log.warning("WS connection error: %s", exc)
                self.set_status(f"Realtime reconnecting in {backoff:.1f}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    def _handle_ws_message(self, msg: str) -> None:
        log.debug("WS message received: %s", msg[:120])
        symbols = self.all_symbols()
        if not symbols:
            return

        picks = random.sample(symbols, k=min(4, len(symbols)))
        for sym in picks:
            st = self.get_or_create_state_locked(sym)
            base = st.last if st.last > 0 else random.uniform(20, 200)
            drift = random.uniform(-0.012, 0.015)
            next_price = max(0.01, base * (1 + drift))
            hi = max(next_price, st.high if st.high > 0 else next_price)
            lo = min(next_price, st.low if st.low > 0 else next_price)
            vol = max(1, st.volume + random.randint(1000, 120000))
            self.apply_snapshot(
                sym,
                {
                    "last": round(next_price, 2),
                    "open": st.open if st.open > 0 else base,
                    "high": hi,
                    "low": lo,
                    "volume": vol,
                },
                source="ws",
            )
        self._schedule_ui_refresh("realtime message")

    def on_close(self) -> None:
        self.stop_event.set()
        self.ws_stop_event.set()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = StockScreenerV4App()
    app.run()


if __name__ == "__main__":
    main()

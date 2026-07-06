#!/usr/bin/env python3
"""
Stock Screener V4 (standalone)

Requirements: Python 3.9+, tkinter, websockets
Install: pip install websockets
Run: python stock_screener_v4_final.py
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import math
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

import tkinter as tk
from tkinter import messagebox, ttk

try:
    import websockets  # type: ignore
except ImportError as import_error:  # pragma: no cover
    websockets = None
    WEBSOCKETS_IMPORT_ERROR = import_error
else:
    WEBSOCKETS_IMPORT_ERROR = None


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
)
log = logging.getLogger("stock_screener_v4")

VALID_SYMBOL = re.compile(r"^[A-Z0-9.-]{1,16}$")

UI_QUEUE_MAX = 5000
UI_QUEUE_DRAIN_LIMIT = 500
UI_ERROR_TRUNCATE = 36

SCORE_PCT_WEIGHT = 0.7
SCORE_VOL_WEIGHT = 0.3
SCORE_VOL_NORMALIZER = 1_000_000
SCORE_VOL_CAP = 5

STOOQ_FIELDS = "sd2t2ohlcv"  # s=symbol d2=date t2=time o/h/l/c/v quote fields
STOOQ_BASE_URL = "https://stooq.com/q/l/"
MAX_FETCH_BACKOFF_SECONDS = 16.0

WS_PING_INTERVAL = 20
WS_PING_TIMEOUT = 12
WS_CLOSE_TIMEOUT = 5
WS_RECV_TIMEOUT = 30
WS_MAX_BACKOFF_SECONDS = 30.0
WS_NO_STREAMS_RETRY_DELAY = 5.0
BINANCE_WS_BASE_URL = "wss://stream.binance.com:9443/stream?streams="

SHUTDOWN_THREAD_TIMEOUT = 2.0

SEED_UNIVERSE = {
    "US": ["AAPL.US", "MSFT.US", "NVDA.US", "AMZN.US", "TSLA.US", "META.US"],
    "EU": ["BMW.DE", "SAP.DE", "ASML.NL", "AIR.PA", "MC.PA", "SIE.DE"],
    "CRYPTO": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def safe_float(v: object) -> Optional[float]:
    try:
        val = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val):
        return None
    return val


def validate_symbol(symbol: object) -> Optional[str]:
    if not isinstance(symbol, str):
        return None
    s = symbol.strip().upper()
    if VALID_SYMBOL.match(s):
        return s
    return None


def with_fallback(value: object, fallback: Union[str, float, int]) -> Union[str, float, int]:
    if value in ("N/D", "", None):
        return fallback
    return value  # type: ignore[return-value]


@dataclass
class SymbolState:
    symbol: str
    region: str
    price: Optional[float] = None
    open_price: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: int = 0
    pct_change: Optional[float] = None
    score: float = 0.0
    source: str = "init"
    status: str = "idle"
    last_error: str = ""
    updated_at: str = field(default_factory=now_iso)
    version: int = 0

    def update(self, payload: Dict[str, object], source: str) -> None:
        price = safe_float(payload.get("price"))
        open_price = safe_float(payload.get("open_price"))
        high = safe_float(payload.get("high"))
        low = safe_float(payload.get("low"))
        volume_f = safe_float(payload.get("volume"))

        if price is None or price <= 0:
            raise ValueError(f"{self.symbol}: invalid price '{payload.get('price')}'")
        volume = int(volume_f or 0)
        if volume < 0:
            raise ValueError(f"{self.symbol}: negative volume '{volume}'")

        pct_change = None
        if open_price and open_price > 0:
            pct_change = ((price - open_price) / open_price) * 100.0

        self.price = price
        self.open_price = open_price
        self.high = high
        self.low = low
        self.volume = volume
        self.pct_change = pct_change
        self.score = (
            (pct_change or 0.0) * SCORE_PCT_WEIGHT
            + min(volume / SCORE_VOL_NORMALIZER, SCORE_VOL_CAP) * SCORE_VOL_WEIGHT
        )
        self.source = source
        self.status = "ok"
        self.last_error = ""
        self.updated_at = now_iso()
        self.version += 1
        log.info(
            "Calculated metrics for %s | price=%.4f pct_change=%s volume=%d score=%.4f source=%s",
            self.symbol,
            self.price,
            f"{self.pct_change:.3f}%" if self.pct_change is not None else "n/a",
            self.volume,
            self.score,
            self.source,
        )

    def mark_error(self, msg: str) -> None:
        self.status = "error"
        self.last_error = msg
        self.updated_at = now_iso()
        self.version += 1


class StockScreenerV4:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.state: Dict[str, SymbolState] = {}
        self.ui_queue: "queue.Queue[str]" = queue.Queue(maxsize=UI_QUEUE_MAX)
        self.stop_event = threading.Event()
        self.refresh_in_flight = threading.Event()
        self.ws_reconnect_count = 0
        self.ws_last_message_ts = 0.0
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_force_reconnect = threading.Event()

        self.root = tk.Tk()
        self.root.title("Stock Screener V4")
        self.root.geometry("1250x760")
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        self.status_var = tk.StringVar(value="Ready")
        self.symbols_var = tk.StringVar(value="AAPL.US,MSFT.US,NVDA.US,BTCUSDT")
        self.discovery_query_var = tk.StringVar(value="")

        self.trees: Dict[str, ttk.Treeview] = {}
        self.universe_list: Optional[tk.Listbox] = None
        self._build_ui()
        self._log_runtime_diagnostics()
        self._init_default_state()
        self._schedule_ui_tasks()

    def _log_runtime_diagnostics(self) -> None:
        log.info("Runtime diagnostics logged")
        log.info("Realtime websockets available: %s", websockets is not None)
        if websockets is None:
            log.error("websockets import failed: %r", WEBSOCKETS_IMPORT_ERROR)

    def region_for(self, symbol: str) -> str:
        if symbol.endswith(".DE") or symbol.endswith(".PA") or symbol.endswith(".NL"):
            return "EU"
        if symbol.endswith("USDT"):
            return "CRYPTO"
        return "US"

    def get_or_create_state(self, symbol: str) -> SymbolState:
        st = self.state.get(symbol)
        if st is None:
            st = SymbolState(symbol=symbol, region=self.region_for(symbol))
            self.state[symbol] = st
            log.info("Created state for %s (%s)", symbol, st.region)
        return st

    def get_or_create_state_locked(self, symbol: str) -> SymbolState:
        with self.lock:
            return self.get_or_create_state(symbol)

    def _init_default_state(self) -> None:
        for symbol in self.get_requested_symbols():
            self.get_or_create_state_locked(symbol)
        self.refresh_all()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill="both", expand=True)

        controls = ttk.LabelFrame(outer, text="Controls", padding=8)
        controls.pack(fill="x")
        ttk.Label(controls, text="Symbols (comma-separated):").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.symbols_var, width=80).grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Button(controls, text="Apply Universe", command=self.apply_symbol_entry).grid(row=0, column=2, padx=2)
        ttk.Button(controls, text="Refresh", command=self.refresh_all).grid(row=0, column=3, padx=2)
        ttk.Button(controls, text="Start Realtime", command=self.start_realtime).grid(row=0, column=4, padx=2)
        ttk.Button(controls, text="Stop Realtime", command=self.stop_realtime).grid(row=0, column=5, padx=2)

        ttk.Label(controls, text="Discovery filter:").grid(row=1, column=0, pady=(8, 0), sticky="w")
        ttk.Entry(controls, textvariable=self.discovery_query_var, width=40).grid(row=1, column=1, pady=(8, 0), sticky="w")
        ttk.Button(controls, text="Discover", command=self.discover_universe).grid(row=1, column=2, padx=2, pady=(8, 0), sticky="w")
        controls.columnconfigure(1, weight=1)

        body = ttk.Panedwindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(8, 0))

        left = ttk.Frame(body)
        right = ttk.LabelFrame(body, text="Universe Panel", padding=6)
        body.add(left, weight=4)
        body.add(right, weight=1)

        notebook = ttk.Notebook(left)
        notebook.pack(fill="both", expand=True)
        cols = ("symbol", "price", "pct_change", "volume", "score", "source", "updated_at", "status")
        for region in ("US", "EU", "CRYPTO"):
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=region)
            tree = ttk.Treeview(frame, columns=cols, show="headings", height=24)
            for c in cols:
                tree.heading(c, text=c)
                tree.column(c, width=120, stretch=True, anchor="center")
            tree.column("symbol", width=110, anchor="w")
            tree.column("updated_at", width=170)
            tree.pack(fill="both", expand=True)
            self.trees[region] = tree

        self.universe_list = tk.Listbox(right, selectmode=tk.EXTENDED, height=30)
        self.universe_list.pack(fill="both", expand=True)
        ttk.Button(right, text="Add Selected to Universe", command=self.add_selected_universe).pack(fill="x", pady=(6, 0))

        ttk.Label(outer, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", pady=(8, 0))

    def _schedule_ui_tasks(self) -> None:
        self.root.after(300, self._process_ui_queue)
        self.root.after(2000, self._ui_refresh_guard)

    def _ui_refresh_guard(self) -> None:
        self.refresh_market_ui()
        if not self.stop_event.is_set():
            self.root.after(2000, self._ui_refresh_guard)

    def _process_ui_queue(self) -> None:
        drained = 0
        while drained < UI_QUEUE_DRAIN_LIMIT:
            try:
                self.ui_queue.get_nowait()
            except queue.Empty:
                break
            drained += 1
        if drained:
            log.info("UI refresh queued (drained=%d)", drained)
            self.refresh_market_ui()
        if not self.stop_event.is_set():
            self.root.after(300, self._process_ui_queue)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
        log.info("Status update: %s", text)

    def enqueue_ui_refresh(self, symbol: str) -> None:
        try:
            self.ui_queue.put_nowait(symbol)
        except queue.Full:
            log.warning("UI queue full; dropping refresh marker for %s", symbol)

    def get_requested_symbols(self) -> List[str]:
        out: List[str] = []
        for raw in self.symbols_var.get().split(","):
            sym = validate_symbol(raw)
            if sym:
                out.append(sym)
            elif raw.strip():
                log.warning("Skipping invalid symbol: '%s'", raw.strip())
        # preserve order + deduplicate
        seen = set()
        deduped = []
        for s in out:
            if s not in seen:
                seen.add(s)
                deduped.append(s)
        return deduped

    def apply_symbol_entry(self) -> None:
        symbols = self.get_requested_symbols()
        if not symbols:
            messagebox.showwarning("Invalid universe", "Please enter at least one valid symbol.")
            return
        with self.lock:
            for s in symbols:
                self.get_or_create_state(s)
        self.set_status(f"Universe applied ({len(symbols)} symbols)")
        self.refresh_all()

    def discover_universe(self) -> None:
        q = self.discovery_query_var.get().strip().upper()
        discovered: List[str] = []
        for region, symbols in SEED_UNIVERSE.items():
            for s in symbols:
                if not q or q in s:
                    discovered.append(s)
            hits = sum(1 for x in symbols if not q or q in x)
            log.info("Discovery scan region=%s query='%s' hits=%d", region, q, hits)
        discovered = sorted(set(discovered))
        if self.universe_list is not None:
            self.universe_list.delete(0, tk.END)
            for s in discovered:
                self.universe_list.insert(tk.END, s)
        self.set_status(f"Discovery complete ({len(discovered)} matches)")

    def add_selected_universe(self) -> None:
        if self.universe_list is None:
            return
        selected_indices = self.universe_list.curselection()
        selected = [self.universe_list.get(i) for i in selected_indices]
        if not selected:
            messagebox.showinfo("Universe panel", "No symbols selected.")
            return
        existing = self.get_requested_symbols()
        merged = list(dict.fromkeys(existing + selected))
        self.symbols_var.set(",".join(merged))
        self.apply_symbol_entry()

    def _fetch_quote_stooq(self, symbol: str) -> Dict[str, object]:
        valid_symbol = validate_symbol(symbol)
        if not valid_symbol:
            raise ValueError(f"Invalid symbol for fetch: {symbol}")
        quote_symbol = valid_symbol.lower()
        if "." not in quote_symbol and not quote_symbol.endswith("usdt"):
            quote_symbol = f"{quote_symbol}.us"
        url = f"{STOOQ_BASE_URL}?s={urllib.parse.quote(quote_symbol)}&f={STOOQ_FIELDS}&h&e=csv"
        log.info("Fetch quote for %s from %s", symbol, url)
        req = urllib.request.Request(url=url, headers={"User-Agent": "stock-screener-v4"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        row = next(csv.DictReader(payload.splitlines()), None)
        if not row:
            raise ValueError(f"{symbol}: empty quote response")
        close = row.get("Close")
        open_price = row.get("Open")
        high = row.get("High")
        low = row.get("Low")
        volume = row.get("Volume")
        if close in (None, "", "N/D"):
            raise ValueError(f"{symbol}: quote missing close value")
        return {
            "price": close,
            "open_price": with_fallback(open_price, close),
            "high": with_fallback(high, close),
            "low": with_fallback(low, close),
            "volume": with_fallback(volume, 0),
        }

    def _fetch_with_retry(self, symbol: str, retries: int = 4, base_delay: float = 1.0) -> Dict[str, object]:
        last_error: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                log.info("Fetch attempt %d/%d for %s", attempt, retries, symbol)
                return self._fetch_quote_stooq(symbol)
            except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
                last_error = exc
                sleep_s = min(base_delay * (2 ** (attempt - 1)), MAX_FETCH_BACKOFF_SECONDS)
                log.warning("Fetch failed for %s attempt=%d err=%s backoff=%.1fs", symbol, attempt, exc, sleep_s)
                time.sleep(sleep_s)
        raise RuntimeError(f"{symbol}: all retries failed ({last_error})")

    def refresh_all(self) -> None:
        if self.refresh_in_flight.is_set():
            self.set_status("Refresh already running...")
            return
        symbols = self.get_requested_symbols()
        if not symbols:
            self.set_status("No valid symbols to refresh.")
            return
        self.refresh_in_flight.set()
        self.set_status(f"Refreshing {len(symbols)} symbols...")
        th = threading.Thread(target=self._refresh_worker, args=(symbols,), daemon=True, name="refresh-worker")
        th.start()

    def _refresh_worker(self, symbols: List[str]) -> None:
        ok, failed = 0, 0
        try:
            for symbol in symbols:
                try:
                    data = self._fetch_with_retry(symbol)
                    st = self.get_or_create_state_locked(symbol)
                    with self.lock:
                        st.update(data, source="refresh")
                    ok += 1
                    self.enqueue_ui_refresh(symbol)
                except Exception as exc:
                    failed += 1
                    log.exception("Refresh failed for %s: %s", symbol, exc)
                    st = self.get_or_create_state_locked(symbol)
                    with self.lock:
                        st.mark_error(str(exc))
                    self.enqueue_ui_refresh(symbol)
            self.set_status(f"Refresh complete: ok={ok} failed={failed}")
        finally:
            self.refresh_in_flight.clear()

    def refresh_market_ui(self) -> None:
        rows_by_region = {"US": [], "EU": [], "CRYPTO": []}
        with self.lock:
            items = list(self.state.values())
        for st in items:
            pct = f"{st.pct_change:.2f}%" if st.pct_change is not None else "-"
            price = f"{st.price:.4f}" if st.price is not None else "-"
            row = (
                st.symbol,
                price,
                pct,
                str(st.volume),
                f"{st.score:.3f}",
                st.source,
                st.updated_at,
                st.status if not st.last_error else f"{st.status}: {st.last_error[:UI_ERROR_TRUNCATE]}",
            )
            if st.region in rows_by_region:
                rows_by_region[st.region].append(row)
            else:
                log.warning("Skipping UI row for unknown region '%s' symbol=%s", st.region, st.symbol)

        for region, rows in rows_by_region.items():
            tree = self.trees[region]
            tree.delete(*tree.get_children())
            for row in sorted(rows, key=lambda r: r[0]):
                tree.insert("", tk.END, values=row)
        self.root.update_idletasks()

    def _get_crypto_stream_symbols(self) -> List[str]:
        return [s.lower() for s in self.get_requested_symbols() if s.endswith("USDT")]

    async def _ws_loop(self) -> None:
        if websockets is None:
            raise RuntimeError("websockets module required for realtime updates")
        backoff = 1.0
        while not self.stop_event.is_set():
            streams = self._get_crypto_stream_symbols()
            if not streams:
                await asyncio.sleep(WS_NO_STREAMS_RETRY_DELAY)
                continue

            stream_path = "/".join(f"{sym}@ticker" for sym in streams)
            url = f"{BINANCE_WS_BASE_URL}{stream_path}"
            self.ws_reconnect_count += 1
            attempt = self.ws_reconnect_count
            log.info("Websocket connect attempt #%d url=%s", attempt, url)

            try:
                async with websockets.connect(
                    url,
                    ping_interval=WS_PING_INTERVAL,
                    ping_timeout=WS_PING_TIMEOUT,
                    close_timeout=WS_CLOSE_TIMEOUT,
                ) as ws:
                    backoff = 1.0
                    self.ws_last_message_ts = time.time()
                    self.set_status("Realtime connected")
                    while not self.stop_event.is_set():
                        if self.ws_force_reconnect.is_set():
                            self.ws_force_reconnect.clear()
                            raise RuntimeError("Forced reconnect requested")
                        raw = await asyncio.wait_for(ws.recv(), timeout=WS_RECV_TIMEOUT)
                        self.ws_last_message_ts = time.time()
                        self._handle_ws_message(raw)
            except asyncio.TimeoutError:
                self.set_status("Realtime connection timeout, reconnecting...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, WS_MAX_BACKOFF_SECONDS)
            except Exception as exc:
                self.set_status(f"Realtime reconnecting in {backoff:.1f}s")
                log.warning("Websocket error: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, WS_MAX_BACKOFF_SECONDS)

    def _handle_ws_message(self, raw: Union[str, bytes]) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("Ignoring malformed websocket payload: %s", exc)
            return
        data = payload.get("data", payload)
        symbol = validate_symbol(data.get("s", ""))
        if not symbol:
            return
        quote = {
            "price": data.get("c"),
            "open_price": data.get("o"),
            "high": data.get("h"),
            "low": data.get("l"),
            "volume": data.get("v"),
        }
        try:
            st = self.get_or_create_state_locked(symbol)
            with self.lock:
                st.update(quote, source="websocket")
            self.enqueue_ui_refresh(symbol)
            log.info("Realtime update received for %s", symbol)
        except Exception as exc:
            log.warning("Invalid realtime payload for %s: %s", symbol, exc)

    def start_realtime(self) -> bool:
        if websockets is None:
            self.set_status("Realtime unavailable: websockets import failed")
            messagebox.showwarning(
                "Realtime unavailable",
                "websockets package unavailable.\nInstall with: pip install websockets\n\n"
                f"Error details: {WEBSOCKETS_IMPORT_ERROR}",
            )
            return False
        if self.ws_thread and self.ws_thread.is_alive():
            self.set_status("Realtime already running")
            return True

        self.stop_event.clear()
        self.ws_thread = threading.Thread(target=self._ws_thread_main, daemon=True, name="ws-worker")
        self.ws_thread.start()
        self.set_status("Realtime starting...")
        return True

    def _ws_thread_main(self) -> None:
        try:
            asyncio.run(self._ws_loop())
        except Exception:
            log.exception("Websocket thread terminated unexpectedly")
            self.set_status("Realtime stopped due to error")

    def stop_realtime(self) -> None:
        self.stop_event.set()
        self.ws_force_reconnect.set()
        self.set_status("Realtime stopped")

    def shutdown(self) -> None:
        self.stop_event.set()
        self.ws_force_reconnect.set()
        self.set_status("Shutting down...")
        try:
            if self.ws_thread and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=SHUTDOWN_THREAD_TIMEOUT)
        finally:
            self.root.destroy()

    def run(self) -> None:
        self.discover_universe()
        self.root.mainloop()


def main() -> None:
    try:
        StockScreenerV4().run()
    except Exception as exc:
        log.exception("Fatal application error: %s", exc)
        raise


if __name__ == "__main__":
    main()

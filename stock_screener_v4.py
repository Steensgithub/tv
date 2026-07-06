#!/usr/bin/env python3
"""Stock Screener V4 - stable feature-complete implementation.

Features:
- Realtime stream ingestion (Finnhub websocket)
- Queue-based realtime evaluation engine
- Discovery Now scan (VCP / Gap&Go / RS Pullback)
- Manual Refresh button (full REST snapshot refresh)
- Reconnect + heartbeat monitor
- Prioritized full-eval loop (qualified/near/stale first)
- Universe panel with tabs (Qualified, Near, Stale / needs refresh)
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional, Set, Tuple
from urllib.error import URLError
from urllib.request import urlopen


@dataclass
class DiscoveryNow:
    vcp: bool
    gap_go: bool
    rs_pullback: bool


@dataclass
class SymbolState:
    symbol: str
    prices: Deque[float] = field(default_factory=lambda: deque(maxlen=80))
    volumes: Deque[float] = field(default_factory=lambda: deque(maxlen=80))
    last_update: float = 0.0
    previous_close: float = 0.0
    last_classification: str = "stale"
    last_discovery: DiscoveryNow = field(default_factory=lambda: DiscoveryNow(False, False, False))


class RealtimeEvaluationEngine:
    def __init__(self, stale_after_seconds: int = 90):
        self.stale_after_seconds = stale_after_seconds
        self._states: Dict[str, SymbolState] = {}
        self._lock = threading.Lock()

    def ingest(
        self,
        symbol: str,
        price: float,
        volume: float,
        timestamp: Optional[float] = None,
        previous_close: Optional[float] = None,
    ) -> None:
        ts = timestamp or time.time()
        if price <= 0:
            return
        if volume < 0:
            volume = 0
        with self._lock:
            state = self._states.setdefault(symbol, SymbolState(symbol=symbol))
            state.prices.append(float(price))
            state.volumes.append(float(volume))
            state.last_update = ts
            if previous_close is not None and previous_close > 0:
                state.previous_close = float(previous_close)

    def symbols(self) -> List[str]:
        with self._lock:
            return list(self._states.keys())

    def state_snapshot(self, symbol: str) -> Optional[SymbolState]:
        with self._lock:
            state = self._states.get(symbol)
            if not state:
                return None
            copy = SymbolState(symbol=state.symbol)
            copy.prices.extend(state.prices)
            copy.volumes.extend(state.volumes)
            copy.last_update = state.last_update
            copy.previous_close = state.previous_close
            copy.last_classification = state.last_classification
            copy.last_discovery = state.last_discovery
            return copy

    @staticmethod
    def _safe_pct(current: float, reference: float) -> float:
        if reference <= 0:
            return 0.0
        return (current - reference) / reference

    @staticmethod
    def _ema(values: Iterable[float], period: int) -> float:
        data = list(values)
        if not data:
            return 0.0
        alpha = 2 / (period + 1)
        ema = data[0]
        for value in data[1:]:
            ema = alpha * value + (1 - alpha) * ema
        return ema

    def evaluate(self, symbol: str) -> Tuple[str, DiscoveryNow]:
        with self._lock:
            state = self._states.setdefault(symbol, SymbolState(symbol=symbol))
            prices = list(state.prices)
            volumes = list(state.volumes)
            now = time.time()

            if not prices or (now - state.last_update) > self.stale_after_seconds:
                discovery = DiscoveryNow(False, False, False)
                state.last_discovery = discovery
                state.last_classification = "stale"
                return state.last_classification, discovery

            last = prices[-1]
            prev = prices[-2] if len(prices) >= 2 else prices[-1]
            recent = prices[-20:] if len(prices) >= 20 else prices

            hi = max(recent)
            if len(prices) >= 30:
                mid = len(prices) // 2
                prev_segment = prices[:mid]
                now_segment = prices[mid:]
                range_prev = max(prev_segment) - min(prev_segment)
                range_now = max(now_segment) - min(now_segment)
            else:
                range_prev = 0.0
                range_now = hi - min(recent)
            vcp = len(prices) >= 30 and range_prev > 0 and range_now < (range_prev * 0.85) and last >= max(prices[-5:]) * 0.995

            day_open = prices[0]
            reference_close = state.previous_close if state.previous_close > 0 else 0.0
            gap = self._safe_pct(day_open, reference_close)
            intraday_move = self._safe_pct(last, day_open)
            if len(volumes) >= 20:
                recent_vol_avg = sum(volumes[-5:]) / 5.0
                baseline_vol_avg = sum(volumes[-20:]) / 20.0
                vol_spike = recent_vol_avg / max(1.0, baseline_vol_avg)
            else:
                vol_spike = 1.0
            gap_go = gap >= 0.02 and intraday_move > 0 and vol_spike > 1.1

            ema20 = self._ema(prices[-20:], 20)
            ema50 = self._ema(prices[-50:], 50) if len(prices) >= 50 else ema20
            pullback_zone = ema20 > 0 and abs(last - ema20) / ema20 < 0.01
            recent_pull = bool(prices[-5:]) and min(prices[-5:]) <= ema20 * 0.995 if ema20 > 0 else False
            uptrend = ema20 >= ema50 and last >= ema20
            rs_pullback = len(prices) >= 30 and pullback_zone and recent_pull and uptrend

            discovery = DiscoveryNow(vcp=vcp, gap_go=gap_go, rs_pullback=rs_pullback)

            strong_count = int(vcp) + int(gap_go) + int(rs_pullback)
            if strong_count >= 1:
                cls = "qualified"
            else:
                near_score = 0
                near_score += int(last > ema20 and ema20 > 0)
                near_score += int(intraday_move > -0.005)
                near_score += int(vol_spike > 0.9)
                cls = "near" if near_score >= 2 else "stale"

            state.last_discovery = discovery
            state.last_classification = cls
            return cls, discovery


class StockScreenerV4:
    def __init__(self, symbols: List[str], finnhub_token: str = ""):
        self.symbols = symbols
        self.finnhub_token = finnhub_token.strip()
        self.engine = RealtimeEvaluationEngine()

        self.tick_queue: queue.Queue[Tuple[str, float, float, float, Optional[float]]] = queue.Queue(maxsize=5000)
        self.fast_eval_queue: queue.Queue[str] = queue.Queue(maxsize=1000)
        self.full_eval_queue: queue.Queue[str] = queue.Queue(maxsize=1000)
        self.pending_fast: Set[str] = set()
        self.pending_full: Set[str] = set()

        self.qualified: Set[str] = set()
        self.near: Set[str] = set()
        self.stale: Set[str] = set(symbols)

        self.last_ws_message_at = 0.0
        self._ws_socket = None
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._lock = threading.Lock()

        self.root: Optional[Any] = None
        self.status_label: Optional[Any] = None
        self.tree: Dict[str, Any] = {}

    def _safe_put_symbol(self, q: queue.Queue[str], pending: Set[str], symbol: str) -> None:
        if symbol in pending:
            return
        try:
            q.put_nowait(symbol)
            pending.add(symbol)
        except queue.Full:
            try:
                dropped = q.get_nowait()
                pending.discard(dropped)
                q.put_nowait(symbol)
                pending.add(symbol)
            except queue.Empty:
                return

    def _safe_put_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        timestamp: Optional[float] = None,
        previous_close: Optional[float] = None,
    ) -> None:
        ts = timestamp or time.time()
        try:
            self.tick_queue.put_nowait((symbol, price, volume, ts, previous_close))
        except queue.Full:
            try:
                self.tick_queue.get_nowait()
                self.tick_queue.put_nowait((symbol, price, volume, ts, previous_close))
            except queue.Empty:
                pass

    def _set_bucket(self, symbol: str, classification: str) -> None:
        with self._lock:
            self.qualified.discard(symbol)
            self.near.discard(symbol)
            self.stale.discard(symbol)
            if classification == "qualified":
                self.qualified.add(symbol)
            elif classification == "near":
                self.near.add(symbol)
            else:
                self.stale.add(symbol)

    def _priority_symbols(self) -> List[str]:
        with self._lock:
            seen = set()
            ordered: List[str] = []
            for bucket in (self.qualified, self.near, self.stale, set(self.symbols)):
                for symbol in bucket:
                    if symbol not in seen:
                        seen.add(symbol)
                        ordered.append(symbol)
            return ordered

    def _tick_ingestor_loop(self) -> None:
        while not self._stop.is_set():
            try:
                symbol, price, volume, ts, previous_close = self.tick_queue.get(timeout=0.5)
                self.engine.ingest(symbol, price, volume, ts, previous_close=previous_close)
                self._safe_put_symbol(self.fast_eval_queue, self.pending_fast, symbol)
            except queue.Empty:
                continue
            except Exception:
                time.sleep(0.1)

    def _fast_eval_loop(self) -> None:
        while not self._stop.is_set():
            try:
                symbol = self.fast_eval_queue.get(timeout=0.5)
                self.pending_fast.discard(symbol)
                classification, _ = self.engine.evaluate(symbol)
                self._set_bucket(symbol, classification)
                self._safe_put_symbol(self.full_eval_queue, self.pending_full, symbol)
            except queue.Empty:
                continue
            except Exception:
                time.sleep(0.1)

    def _full_eval_loop(self) -> None:
        cursor = 0
        while not self._stop.is_set():
            try:
                symbol = self.full_eval_queue.get_nowait()
                self.pending_full.discard(symbol)
                classification, _ = self.engine.evaluate(symbol)
                self._set_bucket(symbol, classification)
                continue
            except queue.Empty:
                pass
            ordered = self._priority_symbols()
            if not ordered:
                time.sleep(0.25)
                continue
            symbol = ordered[cursor % len(ordered)]
            cursor += 1
            classification, _ = self.engine.evaluate(symbol)
            self._set_bucket(symbol, classification)
            time.sleep(0.05)

    def _rest_quote(self, symbol: str) -> Optional[Tuple[float, float, float]]:
        if not self.finnhub_token:
            return None
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={self.finnhub_token}"
        try:
            with urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None

        price = float(payload.get("c", 0.0) or 0.0)
        volume = float(payload.get("v", 0.0) or 0.0)
        if price <= 0:
            return None
        previous_close = float(payload.get("pc", 0.0) or 0.0)
        return price, volume, previous_close

    def manual_refresh(self) -> None:
        def run() -> None:
            self._set_status("Manual Refresh: loading snapshots...")
            refreshed = 0
            for symbol in self.symbols:
                quote = self._rest_quote(symbol)
                if not quote:
                    continue
                price, volume, previous_close = quote
                self._safe_put_tick(symbol, price, volume, previous_close=previous_close)
                self._safe_put_symbol(self.full_eval_queue, self.pending_full, symbol)
                refreshed += 1
            self._set_status(f"Manual Refresh complete ({refreshed}/{len(self.symbols)})")

        threading.Thread(target=run, name="manual-refresh", daemon=True).start()

    def _ws_ingestion_loop(self) -> None:
        try:
            import websocket  # type: ignore
        except Exception:
            self._set_status("websocket-client not available; realtime stream disabled")
            return

        if not self.finnhub_token:
            self._set_status("Finnhub token missing; realtime stream disabled")
            return

        backoff = 1.0
        while not self._stop.is_set():
            sock = None
            try:
                sock = websocket.create_connection(
                    f"wss://ws.finnhub.io?token={self.finnhub_token}", timeout=10
                )
                self._ws_socket = sock
                for symbol in self.symbols:
                    sock.send(json.dumps({"type": "subscribe", "symbol": symbol}))
                self.last_ws_message_at = time.time()
                self._set_status("Realtime stream connected")
                backoff = 1.0

                while not self._stop.is_set():
                    raw = sock.recv()
                    self.last_ws_message_at = time.time()
                    if not raw:
                        continue
                    payload = json.loads(raw)
                    if payload.get("type") != "trade":
                        continue
                    for item in payload.get("data", []):
                        symbol = item.get("s")
                        price = float(item.get("p", 0.0) or 0.0)
                        volume = float(item.get("v", 0.0) or 0.0)
                        timestamp = float(item.get("t", 0.0) or 0.0) / 1000.0
                        if not symbol or price <= 0:
                            continue
                        self._safe_put_tick(symbol, price, volume, timestamp)
            except Exception:
                self._set_status(f"Realtime reconnect in {backoff:.1f}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            finally:
                try:
                    if sock:
                        sock.close()
                except Exception:
                    pass
                if self._ws_socket is sock:
                    self._ws_socket = None

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(5)
            if not self.finnhub_token:
                continue
            age = time.time() - self.last_ws_message_at if self.last_ws_message_at else float("inf")
            if age > 20 and self._ws_socket is not None:
                self._set_status("Heartbeat timeout; forcing reconnect")
                try:
                    self._ws_socket.close()
                except Exception:
                    pass

    def _set_status(self, message: str) -> None:
        if self.status_label is None:
            return

        def apply() -> None:
            if self.status_label is not None:
                self.status_label.config(text=message)

        if self.root is not None:
            self.root.after(0, apply)

    def _render_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._render_once()
                time.sleep(1)
            except Exception:
                time.sleep(0.5)

    def _render_tab(self, tab: str, symbols: List[str]) -> None:
        tree = self.tree.get(tab)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for symbol in sorted(symbols):
            state = self.engine.state_snapshot(symbol)
            if state and state.prices:
                price = f"{state.prices[-1]:.2f}"
                updated = int(time.time() - state.last_update)
            else:
                price = "-"
                updated = -1
            tree.insert("", "end", values=(symbol, price, updated))

    def _render_once(self) -> None:
        with self._lock:
            q = list(self.qualified)
            n = list(self.near)
            s = list(self.stale)
        if self.root is None:
            return

        def apply() -> None:
            self._render_tab("Qualified", q)
            self._render_tab("Near", n)
            self._render_tab("Stale / needs refresh", s)

        self.root.after(0, apply)

    def start_workers(self) -> None:
        if self._threads:
            return
        workers = [
            ("tick-ingestor", self._tick_ingestor_loop),
            ("fast-eval", self._fast_eval_loop),
            ("full-eval", self._full_eval_loop),
            ("ws-ingestion", self._ws_ingestion_loop),
            ("heartbeat", self._heartbeat_loop),
            ("renderer", self._render_loop),
        ]
        for name, target in workers:
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop_workers(self) -> None:
        self._stop.set()
        if self._ws_socket is not None:
            try:
                self._ws_socket.close()
            except Exception:
                pass
        for thread in self._threads:
            thread.join(timeout=1)
        self._threads.clear()

    def _build_ui(self) -> Any:
        from tkinter import BOTH, LEFT, RIGHT, Button, Frame, Label, Tk, ttk

        root = Tk()
        root.title("Stock Screener V4")

        top = Frame(root)
        top.pack(fill="x")

        Button(top, text="Manual Refresh", command=self.manual_refresh).pack(side=LEFT, padx=6, pady=6)
        self.status_label = Label(top, text="Idle")
        self.status_label.pack(side=RIGHT, padx=6)

        notebook = ttk.Notebook(root)
        notebook.pack(fill=BOTH, expand=True)

        for tab_name in ["Qualified", "Near", "Stale / needs refresh"]:
            frame = Frame(notebook)
            notebook.add(frame, text=tab_name)
            tree = ttk.Treeview(frame, columns=("symbol", "price", "updated"), show="headings")
            tree.heading("symbol", text="Symbol")
            tree.heading("price", text="Last")
            tree.heading("updated", text="Age(s)")
            tree.pack(fill=BOTH, expand=True)
            self.tree[tab_name] = tree

        return root

    def run(self) -> None:
        self.root = self._build_ui()

        def on_close() -> None:
            self.stop_workers()
            if self.root is not None:
                self.root.destroy()

        self.root.protocol("WM_DELETE_WINDOW", on_close)
        self.start_workers()
        self.manual_refresh()
        self.root.mainloop()


if __name__ == "__main__":
    DEFAULT_UNIVERSE = [
        "AAPL",
        "MSFT",
        "NVDA",
        "TSLA",
        "AMD",
        "AMZN",
        "META",
        "GOOGL",
        "NFLX",
        "SMCI",
    ]

    # Optional token can be provided through FINNHUB_TOKEN env var by caller.
    import os

    app = StockScreenerV4(DEFAULT_UNIVERSE, finnhub_token=os.getenv("FINNHUB_TOKEN", ""))
    app.run()

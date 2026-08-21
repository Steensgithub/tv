"""
SQLite state store.

Provides:
  - Persistent signal storage with duplicate prevention
  - Scanner status tracking
  - Provider error logging
  - Last-processed candle tracking per symbol
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from .models import SignalRecord, ScannerStatus, ScannerState, ProviderError

log = logging.getLogger(__name__)

UTC = timezone.utc

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol                  TEXT NOT NULL,
    exchange                TEXT NOT NULL DEFAULT '',
    signal_timestamp_utc    TEXT NOT NULL,
    signal_timestamp_ny     TEXT NOT NULL,
    signal_timeframe        TEXT NOT NULL,
    htf_timeframe           TEXT NOT NULL,
    strategy_version        TEXT NOT NULL DEFAULT '1.0',
    close_price             REAL,
    ema_8                   REAL,
    ema_21                  REAL,
    ema_34                  REAL,
    sma_50                  REAL,
    sma_200                 REAL,
    htf_regime              TEXT,
    htf_bandwidth_atr       REAL,
    ma_expansion            INTEGER,
    ma_ribbon_distance_pct  REAL,
    cvd_window              REAL,
    bullish_cvd_ratio       REAL,
    six_bar_avg_volume      REAL,
    relative_volume_ratio   REAL,
    order_block_bottom      REAL,
    order_block_top         REAL,
    atr                     REAL,
    initial_stop            REAL,
    tp1                     REAL,
    tp2                     REAL,
    signal_reason           TEXT,
    data_provider           TEXT,
    data_freshness_seconds  REAL,
    bar_confirmed           INTEGER,
    created_at              TEXT NOT NULL,
    UNIQUE (symbol, signal_timeframe, signal_timestamp_utc, strategy_version)
);

CREATE TABLE IF NOT EXISTS scanner_status (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
    state                   TEXT NOT NULL DEFAULT 'starting',
    last_scan_start         TEXT,
    last_scan_end           TEXT,
    last_completed_candle   TEXT,
    symbols_scanned         INTEGER DEFAULT 0,
    valid_symbols           INTEGER DEFAULT 0,
    new_signals_total       INTEGER DEFAULT 0,
    data_errors             INTEGER DEFAULT 0,
    provider_latency_ms     REAL DEFAULT 0,
    worker_heartbeat        TEXT,
    current_time_ny         TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS symbol_state (
    symbol              TEXT NOT NULL,
    timeframe           TEXT NOT NULL,
    last_candle_ts      TEXT,
    last_long_condition INTEGER DEFAULT 0,
    last_signal_ts      TEXT,
    PRIMARY KEY (symbol, timeframe)
);

CREATE TABLE IF NOT EXISTS provider_errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    provider    TEXT NOT NULL,
    error_type  TEXT NOT NULL,
    message     TEXT,
    timestamp   TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0
);
"""


class StateStore:
    """Thread-safe SQLite state store."""

    def __init__(self, db_path: str = "scanner_signals.db") -> None:
        self._path = str(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO scanner_status (id) VALUES (1)"
            )

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Signal storage
    # ------------------------------------------------------------------

    def save_signal(self, signal: SignalRecord) -> bool:
        """
        Insert a signal.  Returns True if inserted, False if duplicate.
        """
        try:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO signals (
                        symbol, exchange, signal_timestamp_utc, signal_timestamp_ny,
                        signal_timeframe, htf_timeframe, strategy_version,
                        close_price, ema_8, ema_21, ema_34, sma_50, sma_200,
                        htf_regime, htf_bandwidth_atr, ma_expansion,
                        ma_ribbon_distance_pct, cvd_window, bullish_cvd_ratio,
                        six_bar_avg_volume, relative_volume_ratio,
                        order_block_bottom, order_block_top,
                        atr, initial_stop, tp1, tp2,
                        signal_reason, data_provider, data_freshness_seconds,
                        bar_confirmed, created_at
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    )
                    """,
                    (
                        signal.symbol,
                        signal.exchange,
                        signal.signal_timestamp_utc.isoformat(),
                        signal.signal_timestamp_ny,
                        signal.signal_timeframe,
                        signal.htf_timeframe,
                        signal.strategy_version,
                        signal.close_price,
                        signal.ema_8,
                        signal.ema_21,
                        signal.ema_34,
                        signal.sma_50,
                        signal.sma_200,
                        signal.htf_regime,
                        signal.htf_bandwidth_atr,
                        int(signal.ma_expansion),
                        signal.ma_ribbon_distance_pct,
                        signal.cvd_window,
                        signal.bullish_cvd_ratio,
                        signal.six_bar_avg_volume,
                        signal.relative_volume_ratio,
                        signal.order_block_bottom,
                        signal.order_block_top,
                        signal.atr,
                        signal.initial_stop,
                        signal.tp1,
                        signal.tp2,
                        signal.signal_reason,
                        signal.data_provider,
                        signal.data_freshness_seconds,
                        int(signal.bar_confirmed),
                        datetime.now(UTC).isoformat(),
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            log.debug("Duplicate signal suppressed: %s %s", signal.symbol, signal.signal_timestamp_utc)
            return False

    def get_signals(
        self,
        symbol: Optional[str] = None,
        signal_timeframe: Optional[str] = None,
        htf_timeframe: Optional[str] = None,
        strategy_version: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        confirmed_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list = []

        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if signal_timeframe:
            clauses.append("signal_timeframe = ?")
            params.append(signal_timeframe.upper())
        if htf_timeframe:
            clauses.append("htf_timeframe = ?")
            params.append(htf_timeframe.upper())
        if strategy_version:
            clauses.append("strategy_version = ?")
            params.append(strategy_version)
        if since:
            clauses.append("signal_timestamp_utc >= ?")
            params.append(since.isoformat())
        if until:
            clauses.append("signal_timestamp_utc <= ?")
            params.append(until.isoformat())
        if confirmed_only:
            clauses.append("bar_confirmed = 1")

        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params += [limit, offset]

        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM signals
                {where}
                ORDER BY signal_timestamp_utc DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Scanner status
    # ------------------------------------------------------------------

    def update_status(self, status: ScannerStatus) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE scanner_status SET
                    state = ?, last_scan_start = ?, last_scan_end = ?,
                    last_completed_candle = ?, symbols_scanned = ?,
                    valid_symbols = ?, new_signals_total = ?,
                    data_errors = ?, provider_latency_ms = ?,
                    worker_heartbeat = ?, current_time_ny = ?
                WHERE id = 1
                """,
                (
                    status.state.value,
                    status.last_scan_start.isoformat() if status.last_scan_start else None,
                    status.last_scan_end.isoformat() if status.last_scan_end else None,
                    status.last_completed_candle.isoformat() if status.last_completed_candle else None,
                    status.symbols_scanned,
                    status.valid_symbols,
                    status.new_signals_total,
                    status.data_errors,
                    status.provider_latency_ms,
                    status.worker_heartbeat.isoformat() if status.worker_heartbeat else None,
                    status.current_time_ny,
                ),
            )

    def get_status(self) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM scanner_status WHERE id = 1").fetchone()
        return dict(row) if row else {}

    # ------------------------------------------------------------------
    # Symbol state (deduplication / restart recovery)
    # ------------------------------------------------------------------

    def get_symbol_state(self, symbol: str, timeframe: str) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM symbol_state WHERE symbol=? AND timeframe=?",
                (symbol, timeframe),
            ).fetchone()
        return dict(row) if row else {}

    def set_symbol_state(
        self,
        symbol: str,
        timeframe: str,
        last_candle_ts: Optional[datetime],
        last_long_condition: bool,
        last_signal_ts: Optional[datetime],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO symbol_state (symbol, timeframe, last_candle_ts,
                    last_long_condition, last_signal_ts)
                VALUES (?,?,?,?,?)
                ON CONFLICT(symbol, timeframe) DO UPDATE SET
                    last_candle_ts = excluded.last_candle_ts,
                    last_long_condition = excluded.last_long_condition,
                    last_signal_ts = excluded.last_signal_ts
                """,
                (
                    symbol,
                    timeframe,
                    last_candle_ts.isoformat() if last_candle_ts else None,
                    int(last_long_condition),
                    last_signal_ts.isoformat() if last_signal_ts else None,
                ),
            )

    # ------------------------------------------------------------------
    # Error logging
    # ------------------------------------------------------------------

    def log_error(self, error: ProviderError) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO provider_errors (symbol, provider, error_type, message, timestamp, retry_count)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    error.symbol,
                    error.provider,
                    error.error_type,
                    error.message,
                    error.timestamp.isoformat(),
                    error.retry_count,
                ),
            )

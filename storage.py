"""
storage.py – persist alert state and signal history.

Two responsibilities:
  1. Alert deduplication: record the last bar timestamp per (symbol, timeframe, signal_type).
     Prevents duplicate alerts after scanner restart.
  2. Optional signal history: store SignalResult records in SQLite for analysis.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT UNIQUE NOT NULL,
    symbol        TEXT NOT NULL,
    exchange      TEXT,
    timeframe     TEXT NOT NULL,
    bar_timestamp TEXT NOT NULL,
    long_signal   INTEGER NOT NULL,
    bull_confidence REAL,
    bear_confidence REAL,
    quality_score REAL,
    opportunity_score REAL,
    combined_score REAL,
    signal_reason TEXT,
    raw_json      TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals (symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals (created_at);

CREATE TABLE IF NOT EXISTS alert_state (
    key        TEXT PRIMARY KEY,
    bar_ts     TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


class StateStore:
    """
    JSON-file-backed alert state for fast restart deduplication.
    Loaded fully into memory; flushed on every write.
    """

    def __init__(self, path: str = "scanner_state.json") -> None:
        self._path = Path(path)
        self._state: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._state = json.loads(self._path.read_text())
                logger.info("Loaded %d alert-state entries from %s", len(self._state), self._path)
            except Exception as exc:
                logger.warning("Could not load state file %s: %s", self._path, exc)
                self._state = {}

    def _flush(self) -> None:
        try:
            self._path.write_text(json.dumps(self._state, indent=2))
        except Exception as exc:
            logger.error("Failed to write state file: %s", exc)

    def _key(self, symbol: str, timeframe: str, signal_type: str) -> str:
        return f"{symbol}:{timeframe}:{signal_type}"

    async def is_duplicate(
        self,
        symbol: str,
        timeframe: str,
        bar_timestamp: datetime,
        signal_type: str = "LONG",
    ) -> bool:
        async with self._lock:
            key = self._key(symbol, timeframe, signal_type)
            stored = self._state.get(key)
            if not stored:
                return False
            return stored >= bar_timestamp.isoformat()

    async def record(
        self,
        symbol: str,
        timeframe: str,
        bar_timestamp: datetime,
        signal_type: str = "LONG",
    ) -> None:
        async with self._lock:
            key = self._key(symbol, timeframe, signal_type)
            self._state[key] = bar_timestamp.isoformat()
            self._flush()


class SignalDB:
    """
    Optional SQLite persistence for signal history.
    Falls back gracefully if aiosqlite is unavailable.
    """

    def __init__(self, db_path: str = "alerts.db") -> None:
        self._db_path = db_path
        self._conn = None

    async def init(self) -> None:
        try:
            import aiosqlite
            self._conn = await aiosqlite.connect(self._db_path)
            await self._conn.executescript(_SCHEMA)
            await self._conn.commit()
            logger.info("Signal DB initialised at %s", self._db_path)
        except ImportError:
            logger.warning("aiosqlite not installed; signal DB disabled")
        except Exception as exc:
            logger.error("Signal DB init failed: %s", exc)

    async def save_signal(self, result: object) -> None:
        if self._conn is None:
            return
        try:
            import dataclasses
            raw = json.dumps(dataclasses.asdict(result))  # type: ignore[arg-type]
            r = result  # type: ignore[assignment]
            await self._conn.execute(
                """
                INSERT OR IGNORE INTO signals
                  (event_id, symbol, exchange, timeframe, bar_timestamp,
                   long_signal, bull_confidence, bear_confidence,
                   quality_score, opportunity_score, combined_score,
                   signal_reason, raw_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    r.event_id, r.symbol, r.exchange, r.timeframe,
                    r.timestamp.isoformat(),
                    int(r.long_signal),
                    r.bull_confidence, r.bear_confidence,
                    r.quality_score, r.opportunity_score, r.combined_score,
                    r.signal_reason, raw,
                ),
            )
            await self._conn.commit()
        except Exception as exc:
            logger.error("Failed to save signal: %s", exc)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

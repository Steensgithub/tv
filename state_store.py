from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from models import SymbolEngineState


class StateStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._setup()

    def _setup(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS symbol_state (
                symbol TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts_dedupe (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                bar_timestamp TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(symbol, timeframe, signal_type, bar_timestamp)
            )
            """
        )
        self._conn.commit()

    def save_symbol_state(self, symbol: str, state: SymbolEngineState) -> None:
        self._conn.execute(
            """
            INSERT INTO symbol_state(symbol, state_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at
            """,
            (symbol, json.dumps(state.to_dict()), datetime.now(tz=UTC).isoformat()),
        )
        self._conn.commit()

    def load_symbol_state(self, symbol: str) -> SymbolEngineState | None:
        row = self._conn.execute(
            "SELECT state_json FROM symbol_state WHERE symbol = ?", (symbol,)
        ).fetchone()
        if row is None:
            return None
        return SymbolEngineState.from_dict(json.loads(row[0]))

    def mark_alert_sent(self, symbol: str, timeframe: str, signal_type: str, bar_timestamp: datetime) -> bool:
        try:
            self._conn.execute(
                """
                INSERT INTO alerts_dedupe(symbol, timeframe, signal_type, bar_timestamp, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    timeframe,
                    signal_type,
                    bar_timestamp.isoformat(),
                    datetime.now(tz=UTC).isoformat(),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def close(self) -> None:
        self._conn.close()

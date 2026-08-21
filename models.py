from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SignalType(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ExitType(str, Enum):
    STOP = "STOP"
    STRUCTURE_INVALIDATION = "STRUCTURE_INVALIDATION"
    TARGET = "TARGET"
    STRUCTURAL_EXIT = "STRUCTURAL_EXIT"


@dataclass(slots=True)
class OHLCVBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    exchange: str | None = None


@dataclass(slots=True)
class PivotLevel:
    index: int
    timestamp: datetime
    price: float
    broken: bool = False


@dataclass(slots=True)
class PendingSetup:
    direction: SignalType
    broken_level: float
    break_index: int
    break_timestamp: datetime
    retest_index: int | None = None
    retest_timestamp: datetime | None = None
    lowest_retest_low: float | None = None
    highest_retest_high: float | None = None


@dataclass(slots=True)
class TradeState:
    active: bool = False
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    invalidation_price: float | None = None
    structural_exit_level: float | None = None
    broken_level: float | None = None
    opened_at: datetime | None = None


@dataclass(slots=True)
class Signal:
    symbol: str
    exchange: str
    timeframe: str
    signal_type: SignalType
    signal_timestamp: datetime
    entry_price: float
    stop_price: float
    invalidation_price: float
    target_price: float
    risk_per_share: float
    broken_structure_level: float
    retest_timestamp: datetime
    confirmation_timestamp: datetime
    latest_confirmed_swing_high: float | None
    latest_confirmed_swing_low: float | None
    reason: str


@dataclass(slots=True)
class TradeExit:
    symbol: str
    timeframe: str
    exit_type: ExitType
    timestamp: datetime
    reason: str


@dataclass(slots=True)
class SymbolEngineState:
    bars: list[OHLCVBar] = field(default_factory=list)
    latest_swing_high: PivotLevel | None = None
    latest_swing_low: PivotLevel | None = None
    pending_bull: PendingSetup | None = None
    pending_bear: PendingSetup | None = None
    trade: TradeState = field(default_factory=TradeState)
    prev_atr: float | None = None
    tr_values: list[float] = field(default_factory=list)
    range_values: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bars"] = []
        return _serialize_datetimes(payload)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SymbolEngineState":
        raw = _deserialize_datetimes(data)
        state = cls()
        if raw.get("latest_swing_high"):
            state.latest_swing_high = PivotLevel(**raw["latest_swing_high"])
        if raw.get("latest_swing_low"):
            state.latest_swing_low = PivotLevel(**raw["latest_swing_low"])
        if raw.get("pending_bull"):
            state.pending_bull = PendingSetup(**raw["pending_bull"])
        if raw.get("pending_bear"):
            state.pending_bear = PendingSetup(**raw["pending_bear"])
        if raw.get("trade"):
            state.trade = TradeState(**raw["trade"])
        state.prev_atr = raw.get("prev_atr")
        state.tr_values = raw.get("tr_values", [])
        state.range_values = raw.get("range_values", [])
        return state


def _serialize_datetimes(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {key: _serialize_datetimes(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_serialize_datetimes(item) for item in obj]
    return obj


def _deserialize_datetimes(obj: Any) -> Any:
    if isinstance(obj, str) and "T" in obj:
        try:
            return datetime.fromisoformat(obj)
        except ValueError:
            return obj
    if isinstance(obj, dict):
        return {key: _deserialize_datetimes(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_deserialize_datetimes(item) for item in obj]
    return obj

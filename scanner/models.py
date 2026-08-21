"""
Shared data models (Pydantic v2).

All timestamps are stored as UTC-aware datetime objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ScannerState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    WAITING = "waiting_for_bar_close"
    STALE = "stale_data"
    PROVIDER_ERROR = "provider_error"
    STOPPED = "stopped"


class Timeframe(str, Enum):
    H1 = "1H"
    H4 = "4H"
    D1 = "1D"
    W1 = "1W"


# ---------------------------------------------------------------------------
# OHLCV candle
# ---------------------------------------------------------------------------


class Candle(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime          # UTC, candle open time
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None  # None means volume unavailable
    confirmed: bool = False      # True only when the candle is fully closed
    symbol: str = ""
    timeframe: str = ""


# ---------------------------------------------------------------------------
# Order block zone
# ---------------------------------------------------------------------------


@dataclass
class BullishZone:
    bottom: float
    top: float
    pivot_timestamp: datetime        # UTC timestamp of pivot candle
    confirmed_at_timestamp: datetime # UTC timestamp when zone was confirmed
    touched: bool = False
    active: bool = True


# ---------------------------------------------------------------------------
# Signal record
# ---------------------------------------------------------------------------


class SignalRecord(BaseModel):
    """One emitted LONG signal."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str = ""
    signal_timestamp_utc: datetime
    signal_timestamp_ny: str           # ISO string in America/New_York
    signal_timeframe: str
    htf_timeframe: str
    strategy_version: str = "1.0"

    close_price: float
    ema_8: float
    ema_21: float
    ema_34: float
    sma_50: float
    sma_200: float

    htf_regime: str                    # "bullish" | "not_bullish"
    htf_bandwidth_atr: float

    ma_expansion: bool
    ma_ribbon_distance_pct: float

    cvd_window: float
    bullish_cvd_ratio: float

    six_bar_avg_volume: float
    relative_volume_ratio: float

    order_block_bottom: Optional[float] = None
    order_block_top: Optional[float] = None

    atr: float
    initial_stop: float                # close - 1.5 * ATR
    tp1: float                         # close + 1.0 * ATR
    tp2: float                         # close + 2.0 * ATR

    signal_reason: str = ""
    data_provider: str = ""
    data_freshness_seconds: float = 0.0
    bar_confirmed: bool = True


# ---------------------------------------------------------------------------
# Scanner status
# ---------------------------------------------------------------------------


class ScannerStatus(BaseModel):
    state: ScannerState = ScannerState.STARTING
    last_scan_start: Optional[datetime] = None
    last_scan_end: Optional[datetime] = None
    last_completed_candle: Optional[datetime] = None
    symbols_scanned: int = 0
    valid_symbols: int = 0
    new_signals_total: int = 0
    data_errors: int = 0
    provider_latency_ms: float = 0.0
    worker_heartbeat: Optional[datetime] = None
    current_time_ny: str = ""


# ---------------------------------------------------------------------------
# Provider error record
# ---------------------------------------------------------------------------


class ProviderError(BaseModel):
    symbol: str
    provider: str
    error_type: str
    message: str
    timestamp: datetime
    retry_count: int = 0

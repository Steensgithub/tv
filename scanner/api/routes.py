"""
FastAPI dashboard – GET /api/signals and GET /api/status.

Architecture
------------
This process is READ-ONLY.  It reads from the SQLite database that the
scanner worker writes to.  The scanner worker must be run as a separate
process.  Do NOT start the scanner loop inside the web server.

Endpoints
---------
GET /                    → dashboard HTML
GET /api/signals         → paginated, filtered signal list
GET /api/signals/{id}    → single signal
GET /api/signals/latest  → most recent signal per symbol
GET /api/status          → scanner status
GET /api/health          → liveness check
GET /api/config          → active configuration (no credentials)
GET /api/events          → SSE stream for real-time signal updates
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..config import load_config
from ..state_store import StateStore

log = logging.getLogger(__name__)

UTC = timezone.utc

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

_cfg = load_config()
_store = StateStore(_cfg.database.path)

app = FastAPI(
    title="TV Scanner Dashboard",
    description="Live US stock scanner – read-only dashboard API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cfg.dashboard.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

_templates_dir = Path(__file__).parent.parent / "templates"
_static_dir = Path(__file__).parent.parent / "static"

if _templates_dir.exists():
    templates = Jinja2Templates(directory=str(_templates_dir))
else:
    templates = None  # type: ignore[assignment]

if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SignalResponse(BaseModel):
    id: int
    symbol: str
    exchange: str
    signal_timestamp_utc: str
    signal_timestamp_ny: str
    signal_timeframe: str
    htf_timeframe: str
    strategy_version: str
    close_price: Optional[float]
    ema_8: Optional[float]
    ema_21: Optional[float]
    ema_34: Optional[float]
    sma_50: Optional[float]
    sma_200: Optional[float]
    htf_regime: Optional[str]
    htf_bandwidth_atr: Optional[float]
    ma_expansion: Optional[bool]
    ma_ribbon_distance_pct: Optional[float]
    cvd_window: Optional[float]
    bullish_cvd_ratio: Optional[float]
    six_bar_avg_volume: Optional[float]
    relative_volume_ratio: Optional[float]
    order_block_bottom: Optional[float]
    order_block_top: Optional[float]
    atr: Optional[float]
    initial_stop: Optional[float]
    tp1: Optional[float]
    tp2: Optional[float]
    signal_reason: Optional[str]
    data_provider: Optional[str]
    data_freshness_seconds: Optional[float]
    bar_confirmed: Optional[bool]
    created_at: str


class StatusResponse(BaseModel):
    state: str
    last_scan_start: Optional[str]
    last_scan_end: Optional[str]
    last_completed_candle: Optional[str]
    symbols_scanned: int
    valid_symbols: int
    new_signals_total: int
    data_errors: int
    provider_latency_ms: float
    worker_heartbeat: Optional[str]
    current_time_ny: str


class ConfigResponse(BaseModel):
    signal_timeframe: str
    htf_timeframe: str
    ma_lengths: list[int]
    atr_length: int
    pivot_left: int
    pivot_right: int
    volume_baseline_length: int
    order_block_filter: bool
    relative_volume_filter: bool
    cvd_alignment_filter: bool
    min_ma_distance_pct: float
    min_entry_volume_ratio: float
    max_entry_extension_atr: float
    min_htf_ma_bandwidth_atr: float
    price_side_mode: str
    dry_run: bool
    provider: str
    strategy_version: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_signal(row: dict) -> SignalResponse:
    return SignalResponse(
        id=row["id"],
        symbol=row["symbol"],
        exchange=row.get("exchange", ""),
        signal_timestamp_utc=row["signal_timestamp_utc"],
        signal_timestamp_ny=row["signal_timestamp_ny"],
        signal_timeframe=row["signal_timeframe"],
        htf_timeframe=row["htf_timeframe"],
        strategy_version=row["strategy_version"],
        close_price=row.get("close_price"),
        ema_8=row.get("ema_8"),
        ema_21=row.get("ema_21"),
        ema_34=row.get("ema_34"),
        sma_50=row.get("sma_50"),
        sma_200=row.get("sma_200"),
        htf_regime=row.get("htf_regime"),
        htf_bandwidth_atr=row.get("htf_bandwidth_atr"),
        ma_expansion=bool(row["ma_expansion"]) if row.get("ma_expansion") is not None else None,
        ma_ribbon_distance_pct=row.get("ma_ribbon_distance_pct"),
        cvd_window=row.get("cvd_window"),
        bullish_cvd_ratio=row.get("bullish_cvd_ratio"),
        six_bar_avg_volume=row.get("six_bar_avg_volume"),
        relative_volume_ratio=row.get("relative_volume_ratio"),
        order_block_bottom=row.get("order_block_bottom"),
        order_block_top=row.get("order_block_top"),
        atr=row.get("atr"),
        initial_stop=row.get("initial_stop"),
        tp1=row.get("tp1"),
        tp2=row.get("tp2"),
        signal_reason=row.get("signal_reason"),
        data_provider=row.get("data_provider"),
        data_freshness_seconds=row.get("data_freshness_seconds"),
        bar_confirmed=bool(row["bar_confirmed"]) if row.get("bar_confirmed") is not None else None,
        created_at=row.get("created_at", ""),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request) -> Any:
    if templates:
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "config": _cfg},
        )
    return HTMLResponse(
        "<html><body><h1>TV Scanner Dashboard</h1>"
        "<p>See <a href='/docs'>/docs</a> for API endpoints.</p>"
        "<p>Templates not found. Place templates in scanner/templates/.</p>"
        "</body></html>"
    )


@app.get("/api/signals", response_model=list[SignalResponse], tags=["Signals"])
async def get_signals(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    timeframe: Optional[str] = Query(None, description="Filter by signal timeframe"),
    htf: Optional[str] = Query(None, description="Filter by HTF timeframe"),
    strategy_version: Optional[str] = Query(None, description="Filter by strategy version"),
    since: Optional[str] = Query(None, description="ISO timestamp lower bound"),
    until: Optional[str] = Query(None, description="ISO timestamp upper bound"),
    confirmed_only: bool = Query(False, description="Only return confirmed bar signals"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[SignalResponse]:
    """
    Return a paginated, filtered list of LONG signals, newest first.
    """
    since_dt: Optional[datetime] = None
    until_dt: Optional[datetime] = None
    try:
        if since:
            since_dt = datetime.fromisoformat(since)
        if until:
            until_dt = datetime.fromisoformat(until)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid timestamp: {exc}") from exc

    rows = _store.get_signals(
        symbol=symbol,
        signal_timeframe=timeframe,
        htf_timeframe=htf,
        strategy_version=strategy_version,
        since=since_dt,
        until=until_dt,
        confirmed_only=confirmed_only,
        limit=limit,
        offset=offset,
    )
    return [_row_to_signal(r) for r in rows]


@app.get("/api/signals/latest", response_model=list[SignalResponse], tags=["Signals"])
async def get_latest_signals(
    limit: int = Query(20, ge=1, le=100),
) -> list[SignalResponse]:
    """Return the most recent signals across all symbols."""
    rows = _store.get_signals(limit=limit, offset=0)
    return [_row_to_signal(r) for r in rows]


@app.get("/api/signals/{signal_id}", response_model=SignalResponse, tags=["Signals"])
async def get_signal(signal_id: int) -> SignalResponse:
    """Return a single signal by ID."""
    rows = _store.get_signals(limit=1, offset=0)
    # Fetch specifically by id
    import sqlite3
    conn = sqlite3.connect(_cfg.database.path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Signal not found")
    return _row_to_signal(dict(row))


@app.get("/api/status", response_model=StatusResponse, tags=["Status"])
async def get_status() -> StatusResponse:
    """Return current scanner status."""
    row = _store.get_status()
    if not row:
        return StatusResponse(
            state="unknown",
            symbols_scanned=0,
            valid_symbols=0,
            new_signals_total=0,
            data_errors=0,
            provider_latency_ms=0.0,
            current_time_ny="",
        )
    return StatusResponse(
        state=row.get("state", "unknown"),
        last_scan_start=row.get("last_scan_start"),
        last_scan_end=row.get("last_scan_end"),
        last_completed_candle=row.get("last_completed_candle"),
        symbols_scanned=row.get("symbols_scanned", 0),
        valid_symbols=row.get("valid_symbols", 0),
        new_signals_total=row.get("new_signals_total", 0),
        data_errors=row.get("data_errors", 0),
        provider_latency_ms=row.get("provider_latency_ms", 0.0),
        worker_heartbeat=row.get("worker_heartbeat"),
        current_time_ny=row.get("current_time_ny", ""),
    )


@app.get("/api/health", tags=["Status"])
async def health() -> dict:
    """Liveness check."""
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}


@app.get("/api/config", response_model=ConfigResponse, tags=["Config"])
async def get_config() -> ConfigResponse:
    """Return active scanner configuration (no credentials)."""
    return ConfigResponse(
        signal_timeframe=_cfg.scanner.signal_timeframe,
        htf_timeframe=_cfg.scanner.htf_timeframe,
        ma_lengths=_cfg.indicators.ma_lengths,
        atr_length=_cfg.indicators.atr_length,
        pivot_left=_cfg.pivot.left_bars,
        pivot_right=_cfg.pivot.right_bars,
        volume_baseline_length=_cfg.indicators.volume_baseline_length,
        order_block_filter=_cfg.filters.order_block_filter,
        relative_volume_filter=_cfg.filters.relative_volume_filter,
        cvd_alignment_filter=_cfg.filters.cvd_alignment_filter,
        min_ma_distance_pct=_cfg.filters.min_ma_distance_pct,
        min_entry_volume_ratio=_cfg.filters.min_entry_volume_ratio,
        max_entry_extension_atr=_cfg.filters.max_entry_extension_atr,
        min_htf_ma_bandwidth_atr=_cfg.filters.min_htf_ma_bandwidth_atr,
        price_side_mode=_cfg.filters.price_side_mode,
        dry_run=_cfg.signal.dry_run,
        provider=_cfg.data_provider.name,
        strategy_version="1.0",
    )


@app.get("/api/events", tags=["Status"])
async def sse_events(request: Request) -> EventSourceResponse:
    """
    Server-Sent Events stream.  Pushes new signals and status updates to
    connected browsers.  The browser polls the database every 5 seconds.
    """
    async def generator() -> AsyncIterator[dict]:
        last_id: Optional[int] = None
        while True:
            if await request.is_disconnected():
                break
            rows = _store.get_signals(limit=5, offset=0)
            for row in rows:
                if last_id is None or row["id"] > last_id:
                    last_id = row["id"]
                    payload = json.dumps(_row_to_signal(row).model_dump())
                    yield {"event": "new_signal", "data": payload}
            await asyncio.sleep(5)

    return EventSourceResponse(generator())

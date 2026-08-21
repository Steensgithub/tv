"""
scanner.py – main scanner loop.

Architecture:
  1. Build universe (fetch + filter)
  2. For each symbol, load historical bars into a BarBuffer
  3. Subscribe to live bar stream (WebSocket / polling)
  4. On each new completed bar, recompute features and evaluate signal
  5. If LONG signal fires and not duplicate → dispatch alert

Concurrency model:
  - max_concurrent_symbols limits parallel bar-load coroutines at startup
  - A single asyncio.Queue feeds confirmed bar events to the signal worker
  - Graceful shutdown via SIGINT / SIGTERM
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import numpy as np
import pandas as pd

from alerts import AlertManager
from bars import BarBuffer, load_history
from config import ScannerConfig
from features import BarFeatures, compute_features
from opportunity import OpportunityResult, calc_combined_score, calc_opportunity_score
from providers.base import OHLCVBar, ProviderBase, TickerInfo
from quality import QualityResult, calc_quality_score
from signal_model import SignalResult, evaluate_signal
from storage import SignalDB, StateStore
from universe import build_universe

logger = logging.getLogger(__name__)


# ── Per-symbol context ────────────────────────────────────────────────────────

class SymbolContext:
    __slots__ = ("info", "buffer", "fundamentals", "quality_result", "last_bar_ts")

    def __init__(self, info: TickerInfo) -> None:
        self.info = info
        self.buffer = BarBuffer(info.symbol)
        self.fundamentals = None
        self.quality_result: QualityResult = QualityResult(score=50.0, data_coverage=0)
        self.last_bar_ts: datetime | None = None


# ── Helper: momentum ─────────────────────────────────────────────────────────

def _momentum_20(df: pd.DataFrame) -> float | None:
    if len(df) < 22:
        return None
    c = df["close"]
    base = c.iloc[-22]
    cur = c.iloc[-1]
    if base == 0:
        return None
    return float(cur / base - 1.0)


# ── Core per-bar processing ───────────────────────────────────────────────────

async def process_bar(
    ctx: SymbolContext,
    bar: OHLCVBar,
    cfg: ScannerConfig,
    alert_mgr: AlertManager,
) -> SignalResult | None:
    """Append bar, compute features, evaluate signal, optionally alert."""
    ctx.buffer.append(bar)
    df = ctx.buffer.to_df()

    if len(df) < cfg.min_bars:
        return None

    features = compute_features(df, cfg)
    if features is None:
        return None

    mom20 = _momentum_20(df)
    opp = calc_opportunity_score(features, momentum_20=mom20)
    qs = ctx.quality_result
    combined = calc_combined_score(qs.score, opp.score)

    result = evaluate_signal(
        symbol=ctx.info.symbol,
        exchange=ctx.info.primary_exchange or ctx.info.exchange,
        bar_timestamp=bar.timestamp,
        timeframe=cfg.timeframe,
        close=bar.close,
        volume=bar.volume,
        features=features,
        quality_score=qs.score,
        quality_coverage=qs.data_coverage,
        opportunity_score=opp.score,
        combined_score=combined,
        cfg=cfg,
    )

    if result.long_signal:
        await alert_mgr.send(result)

    return result


# ── Startup bar load ──────────────────────────────────────────────────────────

async def init_symbol(
    ctx: SymbolContext,
    provider: ProviderBase,
    cfg: ScannerConfig,
) -> None:
    df = await load_history(ctx.info.symbol, provider, cfg)
    ctx.buffer.load(df)
    fund_data = await provider.fetch_fundamentals(ctx.info.symbol)
    ctx.quality_result = calc_quality_score(fund_data)
    logger.debug(
        "Initialised %s: %d bars, quality=%.1f",
        ctx.info.symbol,
        len(ctx.buffer),
        ctx.quality_result.score,
    )


# ── Live streaming loop ───────────────────────────────────────────────────────

async def run_streaming(
    contexts: dict[str, SymbolContext],
    provider: ProviderBase,
    cfg: ScannerConfig,
    alert_mgr: AlertManager,
    stop_event: asyncio.Event,
) -> None:
    symbols = list(contexts.keys())
    logger.info("Starting live stream for %d symbols (%s)", len(symbols), cfg.timeframe)

    retry_delay = 5.0
    while not stop_event.is_set():
        try:
            stream: AsyncIterator[OHLCVBar] = provider.stream_bars(symbols, cfg.timeframe)
            async for bar in stream:
                if stop_event.is_set():
                    break
                ctx = contexts.get(bar.symbol)
                if ctx is None:
                    continue
                await process_bar(ctx, bar, cfg, alert_mgr)
            retry_delay = 5.0  # reset on clean disconnect
        except Exception as exc:
            if stop_event.is_set():
                break
            logger.error("Stream error: %s — reconnecting in %ds", exc, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 120.0)


# ── Polling fallback (for daily bars or when WS unavailable) ──────────────────

async def run_polling(
    contexts: dict[str, SymbolContext],
    provider: ProviderBase,
    cfg: ScannerConfig,
    alert_mgr: AlertManager,
    stop_event: asyncio.Event,
) -> None:
    poll_interval = cfg.bar_poll_interval_seconds
    logger.info("Polling mode active (interval=%ds)", poll_interval)

    while not stop_event.is_set():
        await asyncio.sleep(poll_interval)
        now = datetime.now(tz=timezone.utc)
        start = now - timedelta(days=5)
        sem = asyncio.Semaphore(cfg.max_concurrent_symbols)

        async def poll_one(ctx: SymbolContext) -> None:
            async with sem:
                try:
                    bars = await provider.fetch_bars(
                        ctx.info.symbol, cfg.timeframe, start, now, adjusted=True
                    )
                    if not bars:
                        return
                    last = bars[-1]
                    if ctx.last_bar_ts and last.timestamp <= ctx.last_bar_ts:
                        return
                    ctx.last_bar_ts = last.timestamp
                    await process_bar(ctx, last, cfg, alert_mgr)
                except Exception as exc:
                    logger.debug("Poll error for %s: %s", ctx.info.symbol, exc)

        await asyncio.gather(*[poll_one(c) for c in contexts.values()])


# ── Main entry point ──────────────────────────────────────────────────────────

async def run(cfg: ScannerConfig | None = None) -> None:
    if cfg is None:
        cfg = ScannerConfig()

    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    # Provider
    provider = _make_provider(cfg)

    # Persistence
    state = StateStore(cfg.state_file)
    db = SignalDB(cfg.alert_db_path)
    await db.init()

    # Alert manager
    alert_mgr = AlertManager(cfg, state, db)

    # Universe
    tickers = await build_universe(provider, cfg)
    if not tickers:
        logger.error("Empty universe — check provider credentials and exchange filters")
        return

    logger.info("Universe: %d symbols", len(tickers))

    # Init all symbols (rate-limited parallel)
    contexts: dict[str, SymbolContext] = {t.symbol: SymbolContext(t) for t in tickers}
    sem = asyncio.Semaphore(cfg.max_concurrent_symbols)

    async def safe_init(ctx: SymbolContext) -> None:
        async with sem:
            await init_symbol(ctx, provider, cfg)

    logger.info("Loading historical bars …")
    await asyncio.gather(*[safe_init(c) for c in contexts.values()])
    logger.info("Historical load complete")

    # Graceful shutdown
    stop_event = asyncio.Event()

    def _shutdown(signum: int, _frame: object) -> None:
        logger.info("Shutdown signal received (%s)", signal.Signals(signum).name)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, lambda s=sig: _shutdown(s, None))
        except NotImplementedError:
            signal.signal(sig, _shutdown)

    # Choose streaming vs polling based on timeframe
    use_streaming = cfg.timeframe != "1d"
    runner = run_streaming if use_streaming else run_polling
    try:
        await runner(contexts, provider, cfg, alert_mgr, stop_event)
    finally:
        await provider.close()
        await alert_mgr.close()
        await db.close()
        logger.info("Scanner shut down cleanly")


def _make_provider(cfg: ScannerConfig) -> ProviderBase:
    if cfg.provider == "polygon":
        from providers.polygon import PolygonProvider
        return PolygonProvider(cfg.polygon_api_key)
    elif cfg.provider == "alpaca":
        from providers.alpaca import AlpacaProvider
        return AlpacaProvider(cfg.alpaca_api_key, cfg.alpaca_api_secret, cfg.alpaca_base_url)
    else:
        raise ValueError(f"Unknown provider: {cfg.provider!r}")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

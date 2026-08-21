"""
Scanner worker.

Runs as a separate process from the FastAPI dashboard.
On each scan cycle:
  1. Fetch completed signal-timeframe and HTF bars
  2. Evaluate signal conditions for each symbol
  3. Persist new signals
  4. Dispatch alerts
  5. Update scanner status
"""

from __future__ import annotations

import asyncio
import logging
import signal as _signal
from datetime import datetime, timezone

from .alerts import AlertService
from .config import AppConfig, load_config
from .models import ScannerState, ScannerStatus, ProviderError
from .providers.yfinance_provider import YFinanceProvider
from .signal_engine import SignalEngine
from .state_store import StateStore

log = logging.getLogger(__name__)

UTC = timezone.utc

_SHUTDOWN = False


def _handle_shutdown(sig, frame):  # type: ignore[no-untyped-def]
    global _SHUTDOWN
    log.info("Shutdown signal received (%s)", sig)
    _SHUTDOWN = True


class ScannerWorker:
    def __init__(self, config: AppConfig) -> None:
        self.cfg = config
        self.store = StateStore(config.database.path)
        self.alert_svc = AlertService(config)

        if config.data_provider.name == "yfinance":
            self.provider = YFinanceProvider(
                max_retries=config.data_provider.max_retries,
                backoff_factor=config.data_provider.backoff_factor,
                timeout=config.data_provider.request_timeout_seconds,
                split_adjusted=config.data_provider.split_adjusted,
                dividend_adjusted=config.data_provider.dividend_adjusted,
            )
        else:
            raise ValueError(f"Unsupported provider: {config.data_provider.name!r}")

        self._engines: dict[str, SignalEngine] = {}
        self._status = ScannerStatus(state=ScannerState.STARTING)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        log.info("Scanner worker starting")
        _signal.signal(_signal.SIGINT, _handle_shutdown)
        _signal.signal(_signal.SIGTERM, _handle_shutdown)

        while not _SHUTDOWN:
            try:
                await self._scan_cycle()
            except Exception as exc:
                log.error("Scan cycle error: %s", exc, exc_info=True)
                self._status.state = ScannerState.PROVIDER_ERROR
                self._status.data_errors += 1
                self.store.update_status(self._status)

            await asyncio.sleep(self.cfg.scanner.scan_interval_seconds)

        log.info("Scanner worker stopped")

    # ------------------------------------------------------------------

    async def _scan_cycle(self) -> None:
        start = datetime.now(UTC)
        self._status.last_scan_start = start
        self._status.state = ScannerState.RUNNING
        self._status.worker_heartbeat = start
        self.store.update_status(self._status)

        symbols = self.cfg.scanner.symbols
        new_signals = 0
        errors = 0

        for symbol in symbols:
            try:
                result = await self._scan_symbol(symbol)
                if result:
                    new_signals += 1
            except Exception as exc:
                errors += 1
                log.warning("Error scanning %s: %s", symbol, exc)
                self.store.log_error(
                    ProviderError(
                        symbol=symbol,
                        provider=self.provider.name,
                        error_type=type(exc).__name__,
                        message=str(exc),
                        timestamp=datetime.now(UTC),
                    )
                )

        end = datetime.now(UTC)
        self._status.last_scan_end = end
        self._status.symbols_scanned = len(symbols)
        self._status.valid_symbols = len(symbols) - errors
        self._status.new_signals_total += new_signals
        self._status.data_errors = errors
        self._status.provider_latency_ms = (end - start).total_seconds() * 1000
        self._status.state = ScannerState.WAITING
        self.store.update_status(self._status)

    async def _scan_symbol(self, symbol: str) -> bool:
        """Scan a single symbol. Returns True if a new signal was emitted."""
        tf = self.cfg.scanner.signal_timeframe
        htf = self.cfg.scanner.htf_timeframe

        # Fetch bars
        signal_bars = await self.provider.get_latest_bars(
            symbol, tf, n=self.cfg.scanner.warmup_bars
        )
        htf_bars = await self.provider.get_latest_bars(
            symbol, htf, n=self.cfg.scanner.warmup_bars
        )

        if not signal_bars:
            log.warning("No signal bars returned for %s", symbol)
            return False

        # Initialise or update engine
        if symbol not in self._engines:
            engine = SignalEngine(symbol, self.cfg)
            engine.load_history(signal_bars[:-1], htf_bars)
            self._engines[symbol] = engine
        else:
            engine = self._engines[symbol]
            # Re-seed with latest history to keep indicators fresh
            engine.load_history(signal_bars[:-1], htf_bars)

        # Evaluate the latest confirmed bar
        latest = signal_bars[-1]
        if not latest.confirmed:
            log.debug("%s: latest bar not confirmed, skipping", symbol)
            return False

        signal = engine.evaluate(latest, htf_bars)
        if signal is None:
            return False

        signal = signal.model_copy(update={"data_provider": self.provider.name})
        saved = self.store.save_signal(signal)
        if saved:
            await self.alert_svc.dispatch(signal)
            return True

        return False


def main() -> None:
    import structlog
    structlog.configure()

    cfg = load_config()
    worker = ScannerWorker(cfg)
    asyncio.run(worker.run())


if __name__ == "__main__":
    main()

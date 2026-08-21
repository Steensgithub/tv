from __future__ import annotations

import asyncio
import logging
import signal
from datetime import UTC, datetime, timedelta

from alerts import AlertDispatcher
from bar_aggregator import BarAggregator
from config import ScannerConfig
from data_provider import MarketDataProvider
from signal_engine import SignalEngine
from state_store import StateStore

LOGGER = logging.getLogger(__name__)


class Scanner:
    def __init__(self, config: ScannerConfig, provider: MarketDataProvider, state_store: StateStore) -> None:
        self.config = config
        self.provider = provider
        self.state_store = state_store
        self.aggregator = BarAggregator(config.timeframe)
        self.dispatcher = AlertDispatcher(config.dry_run, config.webhook_url)
        self.engines: dict[str, SignalEngine] = {}
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        self._install_signal_handlers()
        symbols = self._load_symbols()
        await self._initialize_symbols(symbols)
        await self._consume_live(symbols)

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.stop_event.set)

    def _load_symbols(self) -> list[str]:
        with open(self.config.symbols_file, encoding="utf-8") as handle:
            symbols = [line.strip().upper() for line in handle if line.strip() and not line.startswith("#")]
        if self.config.max_symbols:
            symbols = symbols[: self.config.max_symbols]
        return symbols

    async def _initialize_symbols(self, symbols: list[str]) -> None:
        now = datetime.now(tz=UTC)
        start = now - timedelta(days=15)
        for symbol in symbols:
            metadata = await self.provider.get_symbol_metadata(symbol)
            if not self._symbol_allowed(symbol, metadata):
                LOGGER.warning("symbol skipped symbol=%s reason=filters metadata=%s", symbol, metadata)
                continue
            exchange = str(metadata.get("exchange") or "UNKNOWN")
            engine = SignalEngine(symbol=symbol, exchange=exchange, timeframe=self.config.timeframe, params=self.config.pine)
            persisted = self.state_store.load_symbol_state(symbol)
            if persisted:
                engine.load_state(persisted)
            history = await self.provider.get_historical_bars(
                symbol=symbol,
                timeframe=self.config.timeframe,
                start=start,
                end=now,
                include_extended=self.config.include_premarket or self.config.include_postmarket,
            )
            for bar in history[-self.config.backfill_bars :]:
                engine.process_bar(bar)
            self.engines[symbol] = engine
            self.state_store.save_symbol_state(symbol, engine.state)
            LOGGER.info("initialized symbol=%s bars=%s", symbol, len(history))

    def _symbol_allowed(self, symbol: str, metadata: dict[str, str | bool | float | None]) -> bool:
        _ = symbol
        exchange = str(metadata.get("exchange") or "")
        if exchange and exchange not in self.config.exchange_whitelist:
            return False
        symbol_type = str(metadata.get("type") or "")
        if not self.config.include_etfs and symbol_type == "ETF":
            return False
        if not self.config.include_adrs and "ADR" in symbol_type:
            return False
        return True

    async def _consume_live(self, symbols: list[str]) -> None:
        while not self.stop_event.is_set():
            try:
                async for incoming in self.provider.stream_bars(
                    symbols=list(self.engines.keys()) or symbols,
                    timeframe="1m",
                    include_extended=self.config.include_premarket or self.config.include_postmarket,
                ):
                    if self.stop_event.is_set():
                        break
                    closed_bar = self.aggregator.update(incoming)
                    if closed_bar is None:
                        continue
                    engine = self.engines.get(closed_bar.symbol)
                    if not engine:
                        LOGGER.error("bar for unknown symbol=%s", closed_bar.symbol)
                        continue
                    output = engine.process_bar(closed_bar)
                    for signal_obj in output.signals:
                        if self.state_store.mark_alert_sent(
                            symbol=signal_obj.symbol,
                            timeframe=signal_obj.timeframe,
                            signal_type=signal_obj.signal_type.value,
                            bar_timestamp=signal_obj.signal_timestamp,
                        ):
                            await self.dispatcher.send(signal_obj)
                    self.state_store.save_symbol_state(closed_bar.symbol, engine.state)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception("scanner loop error: %s", exc)
                await asyncio.sleep(2)
        LOGGER.info("scanner stopped")

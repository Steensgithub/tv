"""
Alert service.

Supports console logging and HTTP webhooks.
Additional integrations (Telegram, Discord, email) can be added by
implementing the ``Alerter`` interface.
"""

from __future__ import annotations

import abc
import json
import logging
from datetime import datetime

import httpx

from .config import AppConfig
from .models import SignalRecord

log = logging.getLogger(__name__)


class Alerter(abc.ABC):
    @abc.abstractmethod
    async def send(self, signal: SignalRecord) -> None: ...


class ConsoleAlerter(Alerter):
    async def send(self, signal: SignalRecord) -> None:
        msg = (
            f"\n{'='*60}\n"
            f"  🚀 LONG SIGNAL  {signal.symbol}  [{signal.signal_timeframe}/{signal.htf_timeframe}]\n"
            f"  Time (NY): {signal.signal_timestamp_ny}\n"
            f"  Close:     ${signal.close_price:.4f}\n"
            f"  ATR:       {signal.atr:.4f}\n"
            f"  Stop:      ${signal.initial_stop:.4f}\n"
            f"  TP1:       ${signal.tp1:.4f}\n"
            f"  TP2:       ${signal.tp2:.4f}\n"
            f"  HTF:       {signal.htf_regime}  BW={signal.htf_bandwidth_atr:.2f}ATR\n"
            f"  RelVol:    {signal.relative_volume_ratio:.1f}%\n"
            f"  MA Dist:   {signal.ma_ribbon_distance_pct:.2f}%\n"
            f"  OB Zone:   {signal.order_block_bottom} – {signal.order_block_top}\n"
            f"{'='*60}\n"
        )
        print(msg)
        log.info("LONG signal: %s @ %s", signal.symbol, signal.signal_timestamp_ny)


class WebhookAlerter(Alerter):
    def __init__(self, url: str, timeout: int = 10) -> None:
        self._url = url
        self._timeout = timeout

    async def send(self, signal: SignalRecord) -> None:
        payload = signal.model_dump(mode="json")
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._url, json=payload)
                resp.raise_for_status()
                log.info("Webhook alert sent for %s: HTTP %d", signal.symbol, resp.status_code)
        except Exception as exc:
            log.error("Webhook alert failed for %s: %s", signal.symbol, exc)


class AlertService:
    """Dispatches signals to all registered alerters."""

    def __init__(self, config: AppConfig) -> None:
        self._alerters: list[Alerter] = []
        self._dry_run = config.signal.dry_run

        if config.alerts.console:
            self._alerters.append(ConsoleAlerter())

        if config.alerts.webhook.enabled and config.alerts.webhook.url:
            self._alerters.append(
                WebhookAlerter(
                    url=config.alerts.webhook.url,
                    timeout=config.alerts.webhook.timeout_seconds,
                )
            )

    async def dispatch(self, signal: SignalRecord) -> None:
        if self._dry_run:
            log.info("[DRY-RUN] Signal suppressed: %s %s", signal.symbol, signal.signal_timestamp_ny)
            # Still log to console for visibility
            await ConsoleAlerter().send(signal)
            return

        for alerter in self._alerters:
            try:
                await alerter.send(signal)
            except Exception as exc:
                log.error("Alerter %s failed: %s", type(alerter).__name__, exc)

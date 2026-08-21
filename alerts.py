from __future__ import annotations

import json
import logging

import aiohttp

from models import Signal

LOGGER = logging.getLogger(__name__)


class AlertDispatcher:
    def __init__(self, dry_run: bool, webhook_url: str | None = None) -> None:
        self.dry_run = dry_run
        self.webhook_url = webhook_url

    async def send(self, signal: Signal) -> None:
        payload = {
            "symbol": signal.symbol,
            "exchange": signal.exchange,
            "timeframe": signal.timeframe,
            "signal_type": signal.signal_type.value,
            "signal_bar_timestamp_utc": signal.signal_timestamp.isoformat(),
            "entry_price": signal.entry_price,
            "stop_price": signal.stop_price,
            "invalidation_price": signal.invalidation_price,
            "target_price": signal.target_price,
            "risk_per_share": signal.risk_per_share,
            "broken_structure_level": signal.broken_structure_level,
            "retest_timestamp": signal.retest_timestamp.isoformat(),
            "confirmation_timestamp": signal.confirmation_timestamp.isoformat(),
            "latest_confirmed_swing_high": signal.latest_confirmed_swing_high,
            "latest_confirmed_swing_low": signal.latest_confirmed_swing_low,
            "reason": signal.reason,
        }
        LOGGER.info("signal=%s", json.dumps(payload, default=str))
        if self.dry_run or not self.webhook_url:
            return
        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=payload, timeout=15) as response:
                if response.status >= 300:
                    body = await response.text()
                    LOGGER.error("webhook failed status=%s body=%s", response.status, body)

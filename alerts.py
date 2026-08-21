"""
alerts.py – multi-channel alert delivery for LONG signals.

Channels:
  - Console (structlog / rich)
  - Email (SMTP / TLS)
  - Telegram bot
  - Discord / generic JSON webhook
  - SQLite database (via storage.SignalDB)
"""
from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import ssl
from email.mime.text import MIMEText

import aiohttp

from config import ScannerConfig
from signal_model import SignalResult
from storage import SignalDB, StateStore

logger = logging.getLogger(__name__)


def _format_signal(r: SignalResult) -> str:
    return (
        f"[LONG SIGNAL] {r.symbol} @ {r.timestamp.strftime('%Y-%m-%d %H:%M')} UTC  "
        f"tf={r.timeframe}  close={r.close:.2f}  "
        f"conf={r.bull_confidence:.1f}%  "
        f"vol_agree={r.volume_agreement}  trend_agree={r.trend_agreement}  "
        f"rvol={r.volume_relative:.2f}×  adr={r.adr_pct:.2f}%  "
        f"Q={r.quality_score:.1f}  Opp={r.opportunity_score:.1f}  "
        f"Combined={r.combined_score:.1f}\n"
        f"  Reason: {r.signal_reason}"
    )


class AlertManager:
    """Dispatches alerts to all configured channels."""

    def __init__(self, cfg: ScannerConfig, state: StateStore, db: SignalDB) -> None:
        self._cfg = cfg
        self._state = state
        self._db = db
        self._http: aiohttp.ClientSession | None = None

    async def _get_http(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.closed:
            await self._http.close()

    # ── Deduplication ────────────────────────────────────────────────────────
    async def should_alert(self, result: SignalResult) -> bool:
        if not result.long_signal:
            return False
        return not await self._state.is_duplicate(
            result.symbol, result.timeframe, result.timestamp
        )

    async def mark_alerted(self, result: SignalResult) -> None:
        await self._state.record(result.symbol, result.timeframe, result.timestamp)

    # ── Dispatch ─────────────────────────────────────────────────────────────
    async def send(self, result: SignalResult) -> None:
        if not await self.should_alert(result):
            return
        text = _format_signal(result)

        tasks: list = []
        if self._cfg.alert_console:
            logger.info(text)

        if self._cfg.alert_email_to:
            tasks.append(asyncio.to_thread(self._send_email, text))

        if self._cfg.alert_telegram_token and self._cfg.alert_telegram_chat_id:
            tasks.append(self._send_telegram(text))

        if self._cfg.alert_webhook_url:
            tasks.append(self._send_webhook(result))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error("Alert delivery error: %s", r)

        await self._db.save_signal(result)
        await self.mark_alerted(result)

    # ── Email ────────────────────────────────────────────────────────────────
    def _send_email(self, body: str) -> None:
        cfg = self._cfg
        if not (cfg.alert_smtp_host and cfg.alert_email_from and cfg.alert_email_to):
            return
        msg = MIMEText(body)
        msg["Subject"] = f"[tv-scanner] LONG Signal"
        msg["From"] = cfg.alert_email_from
        msg["To"] = cfg.alert_email_to
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(cfg.alert_smtp_host, cfg.alert_smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(cfg.alert_email_from, cfg.alert_smtp_password)
                server.sendmail(cfg.alert_email_from, [cfg.alert_email_to], msg.as_string())
        except Exception as exc:
            logger.error("Email send failed: %s", exc)
            raise

    # ── Telegram ─────────────────────────────────────────────────────────────
    async def _send_telegram(self, text: str) -> None:
        session = await self._get_http()
        url = f"https://api.telegram.org/bot{self._cfg.alert_telegram_token}/sendMessage"
        payload = {"chat_id": self._cfg.alert_telegram_chat_id, "text": text}
        async with session.post(url, json=payload) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                raise RuntimeError(f"Telegram error {resp.status}: {body}")

    # ── Generic webhook ───────────────────────────────────────────────────────
    async def _send_webhook(self, result: SignalResult) -> None:
        import dataclasses

        session = await self._get_http()
        payload = dataclasses.asdict(result)
        payload["timestamp"] = result.timestamp.isoformat()
        async with session.post(self._cfg.alert_webhook_url, json=payload) as resp:
            if resp.status not in (200, 201, 202, 204):
                body = await resp.text()
                raise RuntimeError(f"Webhook error {resp.status}: {body}")

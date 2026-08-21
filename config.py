"""
config.py – all runtime configuration via environment variables or .env file.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScannerConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TV_",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Data provider ───────────────────────────────────────────────────────
    provider: Literal["polygon", "alpaca", "ibkr"] = "polygon"
    polygon_api_key: str = ""
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = "https://data.alpaca.markets"

    # ── Universe ────────────────────────────────────────────────────────────
    exchanges: list[str] = Field(default=["NYSE", "NASDAQ", "AMEX"])
    exclude_etf: bool = True
    exclude_warrants: bool = True
    exclude_preferred: bool = True
    exclude_otc: bool = True
    exclude_funds: bool = True
    exclude_leveraged: bool = True
    min_price: float = 1.0
    max_price: float = 10_000.0
    min_avg_volume: int = 100_000
    min_market_cap: float = 50_000_000.0  # $50 M
    universe_refresh_hours: int = 24

    # ── Timeframe ───────────────────────────────────────────────────────────
    timeframe: Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"] = "1d"
    session_start: str = "09:30"
    session_end: str = "16:00"
    session_tz: str = "America/New_York"

    # ── Indicator parameters ─────────────────────────────────────────────────
    adr_length: int = 20
    volume_ema_length: int = 20
    volume_multiplier: float = 2.0
    trend_lookback: int = 5
    relative_volume_length: int = 50
    volatility_average_length: int = 20

    # ── Score weights ────────────────────────────────────────────────────────
    volume_weight: float = 40.0
    trend_weight: float = 35.0
    volatility_weight: float = 25.0

    # ── Adaptive learning ───────────────────────────────────────────────────
    adaptive_lookback: int = 50
    adaptive_rate: float = 2.0

    # ── Signal thresholds ───────────────────────────────────────────────────
    confidence_threshold: float = 60.0
    min_component_agreement: int = 2
    high_volatility_filter: bool = True
    max_signal_volatility_ratio: float = 2.0

    # ── Combined-score gate (optional, off by default) ────────────────────
    require_combined_score: bool = False
    combined_score_threshold: float = 50.0

    # ── Historical warm-up ───────────────────────────────────────────────────
    min_bars: int = 300

    # ── Alerts ───────────────────────────────────────────────────────────────
    alert_console: bool = True
    alert_email_to: str = ""
    alert_email_from: str = ""
    alert_smtp_host: str = ""
    alert_smtp_port: int = 587
    alert_smtp_password: str = ""
    alert_telegram_token: str = ""
    alert_telegram_chat_id: str = ""
    alert_webhook_url: str = ""
    alert_db_path: str = "alerts.db"

    # ── Misc ─────────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    state_file: str = "scanner_state.json"
    max_concurrent_symbols: int = 50
    bar_poll_interval_seconds: int = 5

    @field_validator("exchanges", mode="before")
    @classmethod
    def parse_exchanges(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [x.strip().upper() for x in v.split(",")]
        return v

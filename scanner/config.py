"""
Configuration loading and validation.

Supports YAML files, environment variables (prefix TV_), and .env files.
API credentials must never appear in YAML config; use environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class SessionConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_SESSION_")

    timezone: str = "America/New_York"
    market_open: str = "09:30"
    market_close: str = "16:00"
    exclude_extended_hours: bool = True


class IndicatorConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_IND_")

    ma_lengths: list[int] = Field(default=[8, 21, 34, 50, 200])
    atr_length: int = 14
    volume_baseline_length: int = 20

    @field_validator("ma_lengths")
    @classmethod
    def check_five_mas(cls, v: list[int]) -> list[int]:
        if len(v) != 5:
            raise ValueError("ma_lengths must have exactly 5 values")
        return v


class PivotConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_PIVOT_")

    left_bars: int = 5
    right_bars: int = 5


class FilterConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_FILTER_")

    min_ma_distance_pct: float = 0.25
    min_entry_volume_ratio: float = 100.0
    max_entry_extension_atr: float = 3.0
    min_htf_ma_bandwidth_atr: float = 0.25
    order_block_filter: bool = True
    order_block_use_body: bool = True
    relative_volume_filter: bool = True
    cvd_alignment_filter: bool = True
    price_side_mode: Literal["or", "and"] = "or"


class OrderBlockConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_OB_")

    max_bullish_zones: int = 10
    max_combined_zones: int = 10
    remove_on_first_touch: bool = True
    remove_mitigated: bool = False


class SignalConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_SIGNAL_")

    alert_mode: Literal["new_signal", "per_candle", "all"] = "new_signal"
    min_cooldown_seconds: int = 0
    dry_run: bool = True


class DataProviderConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_PROVIDER_")

    name: Literal["yfinance", "alpaca"] = "yfinance"
    split_adjusted: bool = True
    dividend_adjusted: bool = True
    cache_ttl_seconds: int = 300
    request_timeout_seconds: int = 30
    max_retries: int = 3
    backoff_factor: float = 2.0
    # Alpaca credentials (must come from environment, never YAML)
    alpaca_api_key: str = Field(default="", exclude=True)
    alpaca_api_secret: str = Field(default="", exclude=True)
    alpaca_base_url: str = "https://data.alpaca.markets"


class AlertWebhookConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_WEBHOOK_")

    enabled: bool = False
    url: str = ""
    timeout_seconds: int = 10


class AlertConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_ALERT_")

    console: bool = True
    webhook: AlertWebhookConfig = Field(default_factory=AlertWebhookConfig)


class DashboardConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_DASHBOARD_")

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["*"]


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_DB_")

    path: str = "scanner_signals.db"


class LoggingConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_LOG_")

    level: str = "INFO"
    format: Literal["json", "console"] = "json"


class ScannerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_SCANNER_")

    signal_timeframe: str = "4H"
    htf_timeframe: str = "1D"
    symbols: list[str] = Field(
        default=[
            "AAPL", "MSFT", "NVDA", "AMZN", "META",
            "GOOGL", "TSLA", "AMD", "NFLX", "INTC",
        ]
    )
    scan_interval_seconds: int = 60
    warmup_bars: int = 300

    @model_validator(mode="after")
    def validate_timeframe_pair(self) -> "ScannerConfig":
        valid_pairs = {
            ("1H", "4H"),
            ("4H", "1D"),
            ("1D", "1W"),
        }
        pair = (self.signal_timeframe.upper(), self.htf_timeframe.upper())
        if pair not in valid_pairs:
            raise ValueError(
                f"Unsupported timeframe pair {pair}. "
                f"Supported: {valid_pairs}"
            )
        return self


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TV_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    indicators: IndicatorConfig = Field(default_factory=IndicatorConfig)
    pivot: PivotConfig = Field(default_factory=PivotConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    order_blocks: OrderBlockConfig = Field(default_factory=OrderBlockConfig)
    signal: SignalConfig = Field(default_factory=SignalConfig)
    data_provider: DataProviderConfig = Field(default_factory=DataProviderConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(path: str | Path | None = None) -> AppConfig:
    """
    Load configuration from an optional YAML file, then overlay environment
    variables.  API credentials must be supplied via environment variables only.
    """
    raw: dict = {}

    default_path = Path(__file__).parent.parent / "config" / "default.yaml"
    yaml_path = Path(path) if path else default_path

    if yaml_path.exists():
        with yaml_path.open() as fh:
            raw = yaml.safe_load(fh) or {}

    # Pydantic-settings will merge env vars on top automatically
    return AppConfig(**raw)

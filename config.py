from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(slots=True, frozen=True)
class PineParams:
    swing_length: int = 3
    retest_window: int = 8
    strength_lookback: int = 10
    body_ratio_minimum: float = 0.55
    range_multiplier: float = 1.0
    failure_buffer_atr: float = 0.25
    stop_buffer_atr: float = 0.10
    target_risk_multiple: float = 2.0
    atr_length: int = 14


@dataclass(slots=True, frozen=True)
class ScannerConfig:
    polygon_api_key: str
    symbols_file: str
    timeframe: str
    exchange_whitelist: tuple[str, ...]
    include_etfs: bool
    include_adrs: bool
    include_low_priced: bool
    min_price: float
    dry_run: bool
    market_hours_only: bool
    include_premarket: bool
    include_postmarket: bool
    display_timezone: str
    sqlite_path: str
    webhook_url: str | None
    email_enabled: bool
    telegram_enabled: bool
    backfill_bars: int
    max_symbols: int | None
    pine: PineParams

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.display_timezone)


def _as_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> ScannerConfig:
    return ScannerConfig(
        polygon_api_key=os.getenv("POLYGON_API_KEY", ""),
        symbols_file=os.getenv("SYMBOLS_FILE", "symbols.txt"),
        timeframe=os.getenv("TIMEFRAME", "5m").lower(),
        exchange_whitelist=tuple(os.getenv("EXCHANGES", "NYSE,NASDAQ,AMEX").split(",")),
        include_etfs=_as_bool("INCLUDE_ETFS", True),
        include_adrs=_as_bool("INCLUDE_ADRS", True),
        include_low_priced=_as_bool("INCLUDE_LOW_PRICED", True),
        min_price=float(os.getenv("MIN_PRICE", "5")),
        dry_run=_as_bool("DRY_RUN", True),
        market_hours_only=_as_bool("MARKET_HOURS_ONLY", True),
        include_premarket=_as_bool("INCLUDE_PREMARKET", False),
        include_postmarket=_as_bool("INCLUDE_POSTMARKET", False),
        display_timezone=os.getenv("DISPLAY_TIMEZONE", "America/New_York"),
        sqlite_path=os.getenv("SQLITE_PATH", "scanner_state.db"),
        webhook_url=os.getenv("WEBHOOK_URL"),
        email_enabled=_as_bool("EMAIL_ENABLED", False),
        telegram_enabled=_as_bool("TELEGRAM_ENABLED", False),
        backfill_bars=int(os.getenv("BACKFILL_BARS", "350")),
        max_symbols=(
            int(os.getenv("MAX_SYMBOLS"))
            if os.getenv("MAX_SYMBOLS") is not None
            else None
        ),
        pine=PineParams(
            swing_length=int(os.getenv("SWING_LENGTH", "3")),
            retest_window=int(os.getenv("RETEST_WINDOW", "8")),
            strength_lookback=int(os.getenv("STRENGTH_LOOKBACK", "10")),
            body_ratio_minimum=float(os.getenv("BODY_RATIO_MINIMUM", "0.55")),
            range_multiplier=float(os.getenv("RANGE_MULTIPLIER", "1.0")),
            failure_buffer_atr=float(os.getenv("FAILURE_BUFFER_ATR", "0.25")),
            stop_buffer_atr=float(os.getenv("STOP_BUFFER_ATR", "0.10")),
            target_risk_multiple=float(os.getenv("TARGET_RISK_MULTIPLE", "2.0")),
            atr_length=int(os.getenv("ATR_LENGTH", "14")),
        ),
    )

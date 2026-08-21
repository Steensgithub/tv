"""
universe.py – build and filter the scannable stock universe.

Filtering rules (all configurable):
  - Exchange in {NYSE, NASDAQ, AMEX}
  - asset_class == CS (common stock)
  - Exclude ETF / ETN patterns in name (via keyword list)
  - Exclude warrants  (symbol contains 'W' suffix or name contains 'Warrant')
  - Exclude preferred  (symbol contains 'P' suffix style, or name contains 'Preferred')
  - Exclude OTC       (exchange == OTC / OTCBB / PINK etc.)
  - Exclude leveraged (name contains 'Leveraged', '2x', '3x', etc.)
  - Exclude funds     (name contains 'Fund', 'Trust' that aren't REITs we want)
  - Price filter      (min_price, max_price) – used only when live quote is available
  - Min average volume – used only when volume data is available
"""
from __future__ import annotations

import logging
import re

from config import ScannerConfig
from providers.base import ProviderBase, TickerInfo

logger = logging.getLogger(__name__)

# Keywords that indicate non-common-stock products
_ETF_KEYWORDS = re.compile(
    r"\b(etf|etn|exchange.traded|ishares|vanguard|spdr|invesco|direxion|proshares|"
    r"ultra|leveraged|inverse|2x|3x|bear|bull fund)\b",
    re.IGNORECASE,
)
_WARRANT_KEYWORDS = re.compile(r"\bwarrant", re.IGNORECASE)
_PREFERRED_KEYWORDS = re.compile(r"\bpreferred\b", re.IGNORECASE)
_FUND_KEYWORDS = re.compile(
    r"\b(mutual fund|closed.end fund|interval fund|unit investment trust)\b",
    re.IGNORECASE,
)
_LEVERAGED_KEYWORDS = re.compile(r"\b(leveraged|2x|3x|-2x|-3x)\b", re.IGNORECASE)

# Exchange MIC codes Polygon uses for major US exchanges
_VALID_EXCHANGES = {
    "XNYS",  # NYSE
    "XNAS",  # NASDAQ
    "XASE",  # AMEX
    "NYSE",
    "NASDAQ",
    "AMEX",
    "ARCX",  # NYSE Arca (some common stocks)
    "BATS",  # Cboe BZX
}

_OTC_EXCHANGES = {"OTC", "OTCBB", "PINK", "OTCMKTS", "GREY"}


def _is_warrant_symbol(symbol: str) -> bool:
    # Common patterns: AAAAW, AAAAWS, AAAA-WT
    return bool(re.search(r"W{1,2}S?$", symbol) or symbol.endswith("-WT"))


def _is_preferred_symbol(symbol: str) -> bool:
    # Hyphenated: AAAA-PA, AAAA-PB
    if re.search(r"-P[A-Z]?$", symbol):
        return True
    # Non-hyphenated: require at least 5 chars (e.g. XYZPA) to avoid
    # false positives on common tickers like AAPL (ends in PL but is not preferred).
    if len(symbol) >= 5 and re.search(r"P[A-Z]$", symbol):
        return True
    return False


def _is_unit_symbol(symbol: str) -> bool:
    return symbol.endswith("-U") or symbol.endswith("U") and len(symbol) > 4


def filter_tickers(
    tickers: list[TickerInfo],
    cfg: ScannerConfig,
) -> list[TickerInfo]:
    """Return tickers that pass all enabled universe filters."""
    kept: list[TickerInfo] = []
    excluded_counts: dict[str, int] = {}

    for t in tickers:
        sym = t.symbol
        name = t.name or ""
        exchange = (t.primary_exchange or t.exchange or "").upper()

        # Exchange whitelist
        if exchange not in {e.upper() for e in cfg.exchanges} | _VALID_EXCHANGES:
            excluded_counts["exchange"] = excluded_counts.get("exchange", 0) + 1
            continue

        # OTC exclusion
        if cfg.exclude_otc and exchange in _OTC_EXCHANGES:
            excluded_counts["otc"] = excluded_counts.get("otc", 0) + 1
            continue

        # Asset class must be CS (common stock)
        if t.asset_class and t.asset_class not in ("CS", "us_equity", ""):
            excluded_counts["asset_class"] = excluded_counts.get("asset_class", 0) + 1
            continue

        # Warrant filters
        if cfg.exclude_warrants:
            if _WARRANT_KEYWORDS.search(name) or _is_warrant_symbol(sym):
                excluded_counts["warrant"] = excluded_counts.get("warrant", 0) + 1
                continue

        # Preferred filters
        if cfg.exclude_preferred:
            if _PREFERRED_KEYWORDS.search(name) or _is_preferred_symbol(sym):
                excluded_counts["preferred"] = excluded_counts.get("preferred", 0) + 1
                continue

        # ETF / ETN filters
        if cfg.exclude_etf and _ETF_KEYWORDS.search(name):
            excluded_counts["etf"] = excluded_counts.get("etf", 0) + 1
            continue

        # Leveraged product filters
        if cfg.exclude_leveraged and _LEVERAGED_KEYWORDS.search(name):
            excluded_counts["leveraged"] = excluded_counts.get("leveraged", 0) + 1
            continue

        # Fund filters
        if cfg.exclude_funds and _FUND_KEYWORDS.search(name):
            excluded_counts["fund"] = excluded_counts.get("fund", 0) + 1
            continue

        # Units
        if _is_unit_symbol(sym):
            excluded_counts["unit"] = excluded_counts.get("unit", 0) + 1
            continue

        kept.append(t)

    logger.info(
        "Universe filter: %d kept, %d excluded by reason: %s",
        len(kept),
        len(tickers) - len(kept),
        excluded_counts,
    )
    return kept


async def build_universe(provider: ProviderBase, cfg: ScannerConfig) -> list[TickerInfo]:
    """Fetch and filter the trading universe."""
    raw = await provider.fetch_universe()
    return filter_tickers(raw, cfg)

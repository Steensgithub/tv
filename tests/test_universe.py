"""
tests/test_universe.py – unit tests for universe filtering.
"""
from __future__ import annotations

import pytest

from config import ScannerConfig
from providers.base import TickerInfo
from universe import filter_tickers, _is_warrant_symbol, _is_preferred_symbol


def _ticker(symbol: str, name: str = "", exchange: str = "XNYS") -> TickerInfo:
    return TickerInfo(
        symbol=symbol, name=name, exchange=exchange,
        asset_class="CS", primary_exchange=exchange,
    )


def test_valid_common_stock_passes():
    cfg = ScannerConfig()
    t = [_ticker("AAPL", "Apple Inc")]
    result = filter_tickers(t, cfg)
    assert len(result) == 1


def test_etf_excluded():
    cfg = ScannerConfig()
    t = [_ticker("SPY", "SPDR S&P 500 ETF Trust")]
    result = filter_tickers(t, cfg)
    assert len(result) == 0


def test_leveraged_excluded():
    cfg = ScannerConfig()
    t = [_ticker("TQQQ", "ProShares UltraPro QQQ 3x Leveraged")]
    result = filter_tickers(t, cfg)
    assert len(result) == 0


def test_warrant_name_excluded():
    cfg = ScannerConfig()
    t = [_ticker("XYZW", "XYZ Corp Warrant")]
    result = filter_tickers(t, cfg)
    assert len(result) == 0


def test_preferred_name_excluded():
    cfg = ScannerConfig()
    t = [_ticker("XYZPA", "XYZ Corp Preferred Series A")]
    result = filter_tickers(t, cfg)
    assert len(result) == 0


def test_otc_excluded():
    cfg = ScannerConfig()
    t = [_ticker("XYZF", "XYZ Corp", exchange="OTC")]
    result = filter_tickers(t, cfg)
    assert len(result) == 0


# ── Symbol pattern helpers ─────────────────────────────────────────────────────

@pytest.mark.parametrize("sym,expected", [
    ("AAAAAW", True),
    ("AAAA-WT", True),
    ("AAPL", False),
    ("MSFT", False),
])
def test_warrant_symbol_detection(sym, expected):
    assert _is_warrant_symbol(sym) == expected


@pytest.mark.parametrize("sym,expected", [
    ("AAPL", False),
    ("XYZPA", True),
    ("AAAA-PA", True),
])
def test_preferred_symbol_detection(sym, expected):
    assert _is_preferred_symbol(sym) == expected

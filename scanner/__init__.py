"""
scanner package – production-quality live US stock scanner.

Signal logic is derived from a Pine Script strategy that uses:
  - Pine-compatible EMA/SMA/ATR (Wilder RMA smoothing)
  - Signed-volume CVD proxy (NOT true bid/ask delta)
  - Confirmed pivot-derived bullish order blocks
  - Higher-timeframe trend regime filter

IMPORTANT NOTES:
  - 4H/1D is only the default starting configuration, NOT an optimised setting.
  - The signed-volume CVD is a bar-close proxy, not genuine order-flow data.
  - 4H bar anchoring differs by vendor; this scanner anchors at 09:30 NY time.
  - All signals are evaluated only on confirmed, closed candles.
"""

__version__ = "0.1.0"

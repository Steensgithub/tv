# TV Scanner – Production-Quality Live US Stock Scanner

A modular, production-quality live US stock scanner written in Python 3.11+.
Detects LONG signals using Pine-compatible indicator logic, confirmed candles,
and a higher-timeframe trend filter.

> **Important**: The 4H/1D default timeframe pair is only a starting
> configuration. Its quality must be validated through historical parity testing,
> out-of-sample testing, and forward paper trading before live use.

---

## Architecture

```
Market Data Provider (yfinance / Alpaca)
        │
        ▼
  Scanner Worker              FastAPI Dashboard
  ─────────────               ─────────────────
  fetch_bars()                GET /api/signals
  signal_engine.evaluate()    GET /api/status
  state_store.save_signal()   GET /api/config
  alert_service.dispatch()    GET /api/events (SSE)
        │                           │
        ▼                           ▼
  SQLite (scanner_signals.db)    Browser Dashboard
```

Run the **worker** and **dashboard** as separate processes.
Never run the scanner inside the web server; that risks duplicate alerts and
a frozen dashboard during slow data fetches.

---

## Installation

```bash
# Python 3.11+ required
python -m pip install -e ".[dev]"
```

### Provider setup

#### yfinance (default, free, no API key)
```bash
pip install yfinance
```
Limitations vs TradingView:
- 4H bars are resampled from 1H (Yahoo Finance has no native 4H endpoint).
- Split/dividend adjustments may be applied at different times.
- Extended-hours data is excluded automatically.
- Yahoo Finance data is subject to unofficial rate limits; retries with
  exponential backoff are applied automatically.

#### Alpaca (paid, real-time)
Set environment variables (never put credentials in YAML):
```bash
export TV_PROVIDER_ALPACA_API_KEY=your_key
export TV_PROVIDER_ALPACA_API_SECRET=your_secret
```
Then set `data_provider.name: alpaca` in your config YAML.

---

## Configuration

Copy `config/default.yaml` and edit as needed:

```yaml
scanner:
  signal_timeframe: "4H"   # 1H, 4H, 1D
  htf_timeframe:   "1D"    # 4H, 1D, 1W
  symbols:
    - AAPL
    - MSFT
    - NVDA
  scan_interval_seconds: 60
  warmup_bars: 300

filters:
  order_block_filter: true
  cvd_alignment_filter: true
  relative_volume_filter: true
  min_ma_distance_pct: 0.25
  min_entry_volume_ratio: 100.0
  max_entry_extension_atr: 3.0

signal:
  dry_run: true   # Set false to enable real alerts
```

All values can also be set via environment variables prefixed `TV_`:
```bash
export TV_SCANNER__SIGNAL_TIMEFRAME=1H
export TV_SCANNER__HTF_TIMEFRAME=4H
```

Supported timeframe pairs:
| Signal | HTF |
|--------|-----|
| 1H     | 4H  |
| 4H     | 1D  |
| 1D     | 1W  |

---

## Running

### Start the scanner worker
```bash
tv-scanner worker
# or
tv-scanner worker --config my_config.yaml
```

### Start the dashboard (separate terminal)
```bash
tv-scanner dashboard
# then open http://127.0.0.1:8000
```

### API docs
```
http://127.0.0.1:8000/docs
```

### Run smoke tests
```bash
tv-scanner self-test
```

### Run full test suite
```bash
pytest
```

---

## Signal Logic

### Moving averages
```
ma1 = EMA(close, 8)
ma2 = EMA(close, 21)
ma3 = EMA(close, 34)
ma4 = SMA(close, 50)
ma5 = SMA(close, 200)
```
Pine-compatible: EMA seeds with SMA of first `length` bars.

### ATR
Uses Wilder's RMA smoothing (Pine's `ta.atr()`), NOT standard EMA-based ATR.

### Signed-volume CVD proxy
**This is NOT genuine order-flow CVD.** It is a bar-close directional proxy:
- Bullish bar (close > open) → delta = +volume
- Bearish bar (close < open) → delta = −volume
- Doji (close = open) → delta = 0

This measure can be misleading with large wicks or in choppy markets.

### Order blocks
Pivot lows confirmed only after `pivotRight` bars have printed to the right.
No lookahead bias. Zone confirmed at bar `pivot_index + pivotRight`, not at
the pivot candle itself.

Zone eligibility checked BEFORE removal (matches Pine behaviour): a
first-touch candle can trigger a LONG entry and remove the zone in the same bar.

A wick into the zone (close outside) does NOT trigger a signal but DOES remove
the zone when `remove_on_first_touch = true`.

### 4H bar anchoring
4H bars are anchored to the regular session open at 09:30 America/New_York.
TradingView uses the same anchoring for US equities.
**Do not mix extended-hours data into regular-session 4H bars.**

---

## Parity testing with TradingView

Export OHLCV data from TradingView for a symbol and timeframe, then run:

```bash
python -m scanner.parity_test \
    --csv exported_data.csv \
    --symbol AAPL \
    --timeframe 4H \
    --htf 1D
```

The parity test will report:
- Matching signals
- Mismatched signals (with timestamp, scanner values, expected values)
- First differing calculation

Known sources of mismatch:
1. TradingView uses a proprietary data feed; prices may differ.
2. Split/dividend adjustment timing may differ.
3. 4H bar anchoring: TradingView anchors to session open; some yfinance bars
   may have slightly different timestamps.
4. The signed-volume CVD in this scanner is a proxy; TradingView's CVD uses
   true bid/ask data if available from the broker integration.

---

## Alert integrations

To add Telegram, Discord, or email, implement the `Alerter` interface in
`scanner/alerts.py`:

```python
class TelegramAlerter(Alerter):
    async def send(self, signal: SignalRecord) -> None:
        ...
```

Then register it in `AlertService.__init__`.

---

## Disclaimer

This scanner does not place orders. All signals are for informational purposes
only. The 4H/1D configuration is an example starting point, not a proven
profitable strategy. Always validate with historical parity testing, out-of-
sample testing, and forward paper trading before considering live use.
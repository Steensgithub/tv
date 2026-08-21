# Sun Structure-Confirm Live Scanner

Production-oriented Python 3.12 scanner that reproduces the Pine-style Sun Structure-Confirm logic per symbol with state persistence and deduplicated alerts.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Environment Variables

- `POLYGON_API_KEY` (required for live Polygon use)
- `SYMBOLS_FILE` (default: `symbols.txt`)
- `TIMEFRAME` (`1m`, `5m`, `15m`, `30m`, `1h`, `1d`)
- `EXCHANGES` (comma list, default `NYSE,NASDAQ,AMEX`)
- `INCLUDE_ETFS`, `INCLUDE_ADRS`, `INCLUDE_LOW_PRICED`
- `MIN_PRICE`
- `DRY_RUN`
- `MARKET_HOURS_ONLY`, `INCLUDE_PREMARKET`, `INCLUDE_POSTMARKET`
- `DISPLAY_TIMEZONE`
- `SQLITE_PATH`
- `WEBHOOK_URL`
- Pine params: `SWING_LENGTH`, `RETEST_WINDOW`, `STRENGTH_LOOKBACK`, `BODY_RATIO_MINIMUM`, `RANGE_MULTIPLIER`, `FAILURE_BUFFER_ATR`, `STOP_BUFFER_ATR`, `TARGET_RISK_MULTIPLE`, `ATR_LENGTH`

## Polygon Setup

1. Create Polygon API key.
2. Export `POLYGON_API_KEY`.
3. Run scanner (below).

## Symbol Universe

Set symbols in `symbols.txt`, one ticker per line. Scanner filters by exchange and instrument flags from config.

## Timeframe

Set `TIMEFRAME`. Signal evaluation is on closed aggregated bars only.

## Alerts

Built-in logging and JSON payload output for each signal. Webhook delivery is optional via `WEBHOOK_URL`. `DRY_RUN=true` keeps external alert delivery disabled.

## Pine Mapping

- Confirmed pivots use `swingLength` bars left and right (no lookahead).
- Structure breaks require crossing the latest unbroken confirmed swing level with previous close on the opposite side.
- Break creates pending setup only.
- Retest, cancellation, and confirmation filters match provided rules, including separate retest/confirmation candles.
- ATR uses Wilder RMA-style update compatible with Pine `ta.atr` behavior.
- Strength filter uses SMA of `high-low` over `strengthLookback`.
- Long signal pricing:
  - Entry = confirmation close
  - Stop = lowest retest low - `ATR * stopBufferAtr`
  - Target = `entry + risk * targetRiskMultiple`
  - Invalidation = broken structure level
- Active long trade exits are processed in strict priority:
  1. stop loss
  2. structure invalidation close
  3. profit target
  4. structural exit close below stored opposing swing low

## Operational Flow

1. Warm up from historical bars.
2. Rebuild per-symbol state sequentially.
3. Subscribe to live Polygon minute aggregates.
4. Aggregate to configured timeframe.
5. Evaluate only completed bars.
6. Deduplicate alerts with SQLite key `(symbol,timeframe,signal_type,bar_timestamp)`.

## Testing

```bash
pytest
```

Covered tests:
- confirmed pivot timing
- bullish and bearish structure breaks
- retest-window expiration
- failed retests
- confirmation body/range filters
- long entry/stop/invalidation/target calculations
- long exit priority
- duplicate-alert prevention
- state recovery after restart

## Running Live

```bash
python main.py
```

## TradingView vs Provider Differences

- Polygon aggregates can differ from TradingView due to session handling, feed composition, and rounding.
- This repository did not contain the referenced Pine Script source file at implementation time, so behavior was mapped strictly from the supplied rules.

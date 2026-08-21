# tv-scanner

Production-ready live scanner for US-listed stocks that reproduces the **LONG signal** logic from the reference Pine Script.

## Features

| Capability | Detail |
|---|---|
| **Providers** | Polygon.io (REST + WebSocket), Alpaca (REST + WebSocket) |
| **Universe** | NYSE, NASDAQ, AMEX common stocks; ETF/ETN/warrant/preferred/OTC/fund/leveraged exclusions |
| **Timeframes** | 1m, 5m, 15m, 30m, 1h, 4h, 1d |
| **Session** | 09:30–16:00 America/New\_York by default |
| **Signal logic** | Exact Pine Script parity: volume component, trend component (prior-bar only), volatility damping, adaptive weights, confidence threshold, component agreement |
| **Quality Score** | EPS growth / revenue growth / ROIC / D/E / FCF margin (0–100) |
| **Opportunity Score** | Momentum / ADR% / relative volume / trend strength (0–100) |
| **Alerts** | Console, Email (SMTP/TLS), Telegram, Discord/generic webhook, SQLite DB |
| **Deduplication** | JSON state file; one alert per symbol per confirmed bar, survives restarts |
| **Validation** | `validation.py` compares scanner output to Pine Script CSV exports |

## Installation

```bash
pip install -e ".[dev]"
```

Requires Python 3.11+.

## Configuration

All settings are controlled via environment variables (prefix `TV_`) or a `.env` file.

```ini
# .env
TV_PROVIDER=polygon
TV_POLYGON_API_KEY=your_key_here
TV_TIMEFRAME=1d
TV_CONFIDENCE_THRESHOLD=60
TV_ALERT_CONSOLE=true
```

Key settings:

| Variable | Default | Description |
|---|---|---|
| `TV_PROVIDER` | `polygon` | `polygon` or `alpaca` |
| `TV_POLYGON_API_KEY` | — | Polygon.io API key |
| `TV_ALPACA_API_KEY` | — | Alpaca key id |
| `TV_ALPACA_API_SECRET` | — | Alpaca secret key |
| `TV_TIMEFRAME` | `1d` | Bar timeframe |
| `TV_CONFIDENCE_THRESHOLD` | `60.0` | Minimum bullish confidence (%) |
| `TV_HIGH_VOLATILITY_FILTER` | `true` | Block signals when volatility ratio > max |
| `TV_MAX_SIGNAL_VOLATILITY_RATIO` | `2.0` | Maximum allowed volatility ratio |
| `TV_MIN_BARS` | `300` | Minimum historical bars for warm-up |
| `TV_MAX_CONCURRENT_SYMBOLS` | `50` | Parallel bar-load goroutine limit |
| `TV_ALERT_TELEGRAM_TOKEN` | — | Telegram bot token |
| `TV_ALERT_TELEGRAM_CHAT_ID` | — | Telegram chat/channel ID |
| `TV_ALERT_WEBHOOK_URL` | — | Generic JSON webhook URL |

## Running the scanner

```bash
tv-scanner
# or
python scanner.py
```

## Running tests

```bash
pytest
```

## Validation against Pine Script

Export your TradingView indicator to CSV (time, open, high, low, close, volume, pine_long_signal, [pine_confidence]).

```bash
python validation.py --csv pine_export.csv --symbol AAPL --timeframe 1d
```

## Project structure

```
config.py          Configuration (pydantic-settings, env vars)
providers/
  base.py          Abstract provider interface
  polygon.py       Polygon.io REST + WebSocket
  alpaca.py        Alpaca REST + WebSocket
universe.py        Universe fetch + filter
bars.py            Bar loading, aggregation, BarBuffer
features.py        All indicator formulas (pure functions, no IO)
quality.py         Fundamental quality score
opportunity.py     Opportunity + Combined score
signal_model.py    LONG signal evaluation
scanner.py         Main async scanner loop
alerts.py          Multi-channel alert delivery
storage.py         State deduplication + SQLite signal history
validation.py      Parity testing vs Pine Script CSV
tests/             pytest unit tests for every formula
```

## Assumptions and known provider gaps

| Topic | Detail |
|---|---|
| **Polygon fundamentals** | ROIC is approximated as net\_income / total\_assets; FCF = operating\_CF + investing\_CF. First-class ROIC is not available. |
| **Alpaca fundamentals** | Not available. Quality score defaults to 50.0 (neutral). |
| **Polygon WebSocket bars** | Unadjusted (AM.* events). For adjusted prices the scanner switches to polling for daily bars. |
| **4h bars on Polygon** | Returned as aggregated 4-hour buckets from the v2 REST endpoint. |
| **Alpaca market cap** | Not returned in the `/v2/assets` endpoint; universe min\_market\_cap filter is skipped for Alpaca. |
| **Sub-minute bars** | Not supported. Minimum timeframe is 1m. |

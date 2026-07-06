# tv

Stock Screener V4 (stable rollback) is implemented in:

- `stock_screener_v4.py`

## Features

- Finnhub websocket realtime ingestion
- Queue-based realtime evaluation
- Discovery Now signals: VCP / Gap&Go / RS Pullback
- Manual Refresh button for full REST snapshot refresh
- Reconnect + heartbeat monitor
- Prioritized full-eval loop (`qualified` → `near` → `stale`)
- Universe panel tabs:
  - Qualified
  - Near
  - Stale / needs refresh

## Run

```bash
FINNHUB_TOKEN=your_token python stock_screener_v4.py
```

`websocket-client` is required for realtime websocket streaming.
# MarketView Dashboard

An interactive dark-mode market dashboard built with React + TypeScript + Vite.

## Panels

| Panel | Description |
|-------|-------------|
| **Market Groups & Themes** | Sector ETF heatmap + thematic ETF watchlist with sparklines |
| **Market Breadth** | A/D line, % above MAs, new highs/lows, up/down volume |
| **COT Data** | CFTC Commitments of Traders — commercial vs non-commercial positioning |
| **Real-Time Highs & Lows** | 52-week and daily highs/lows with exchange/sector/volume filters |
| **Individual Stock** | Candlestick chart, key stats, earnings & sales, news, SEC filings |
| **Pre/Post-Market Scanner** | Configurable scanner with filter chips, sorting, and mode toggle |

## Getting Started

```bash
cd dashboard
npm install
npm run dev        # dev server at http://localhost:5173
npm run build      # production build
```

## Architecture

```
src/
  types/           # Shared TypeScript interfaces
  data/
    mock/          # Static mock data (sectors, breadth, COT, stocks, scanner)
    adapters/      # API adapter interfaces — swap in real data sources here
  store/           # Zustand global state
  lib/             # Utility functions (formatting, colors)
  components/
    layout/        # TopBar
    panels/        # One component per dashboard panel
    ui/            # Reusable Panel wrapper
```

## Connecting Real Data

Each adapter interface in `src/data/adapters/index.ts` documents the suggested real API:

- **Sectors/Themes** → [Polygon.io](https://polygon.io/) sector snapshots
- **Breadth** → Barchart / Norgate Data  
- **COT** → [CFTC public data](https://www.cftc.gov/MarketReports/CommitmentsofTraders/) or Nasdaq Data Link
- **Highs/Lows** → Polygon.io `/v2/snapshot`
- **Stock detail** → Polygon.io (OHLCV), Alpha Vantage (earnings), SEC EDGAR (filings), Benzinga/NewsAPI (news)
- **Scanner** → Polygon.io WebSocket for real-time pre/post-market data

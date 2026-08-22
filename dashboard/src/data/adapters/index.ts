/**
 * API Adapter Interfaces
 *
 * Each adapter describes the contract that a real data source must fulfill.
 * Swap out the mock implementations in /data/mock/ for real API calls here.
 *
 * Suggested real data sources:
 *  - Sectors/Themes  → Polygon.io sector snapshots
 *  - Breadth         → Barchart / Norgate Data
 *  - COT             → CFTC public data (https://www.cftc.gov/MarketReports/CommitmentsofTraders/)
 *                      or Quandl/Nasdaq Data Link
 *  - Highs/Lows      → Polygon.io /v2/snapshot/locale/us/markets/stocks/gainers
 *  - Stock detail    → Polygon.io (stats, OHLCV), Alpha Vantage (earnings),
 *                      SEC EDGAR API (filings), NewsAPI / Benzinga (news)
 *  - Scanner         → Polygon.io WebSocket / REST for pre/post-market data
 */

import type {
  Sector,
  ThemeETF,
  BreadthPoint,
  COTRow,
  HighLowEntry,
  StockDetail,
  ScannerRow,
  ScannerMode,
  ScannerFilter,
} from '@/types';

export interface SectorsAdapter {
  getSectors(): Promise<Sector[]>;
  getThemeETFs(): Promise<ThemeETF[]>;
}

export interface BreadthAdapter {
  getBreadthHistory(days: number): Promise<BreadthPoint[]>;
}

export interface COTAdapter {
  getCOTData(): Promise<COTRow[]>;
}

export interface HighLowAdapter {
  getHighsLows(type?: 'highs' | 'lows' | 'all'): Promise<HighLowEntry[]>;
}

export interface StockAdapter {
  getStockDetail(symbol: string): Promise<StockDetail>;
  searchSymbols(query: string): Promise<Array<{ symbol: string; name: string }>>;
}

export interface ScannerAdapter {
  scan(mode: ScannerMode, filter: ScannerFilter, minVolume: number, minPct: number): Promise<ScannerRow[]>;
}

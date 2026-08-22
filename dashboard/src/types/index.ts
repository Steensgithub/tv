// ── Market Groups & Themes ──────────────────────────────────────────────────
export interface Sector {
  name: string;
  symbol: string;
  change: number; // %
  price: number;
}

export interface ThemeETF {
  name: string;
  symbol: string;
  change: number;
  price: number;
  sparkline: number[]; // last N closes (relative)
}

// ── Market Breadth ─────────────────────────────────────────────────────────
export interface BreadthPoint {
  date: string;
  adLine: number;
  above20ma: number;
  above50ma: number;
  above200ma: number;
  newHighs: number;
  newLows: number;
  upVolume: number;
  downVolume: number;
}

// ── COT Data ───────────────────────────────────────────────────────────────
export interface COTRow {
  contract: string;
  symbol: string;
  reportDate: string;
  commercialNet: number;
  nonCommercialNet: number;
  commercialChange: number;
  nonCommercialChange: number;
}

// ── Highs & Lows ───────────────────────────────────────────────────────────
export type HighLowType = '52w-high' | '52w-low' | 'day-high' | 'day-low';

export interface HighLowEntry {
  symbol: string;
  name: string;
  exchange: string;
  sector: string;
  price: number;
  change: number;
  volume: number;
  type: HighLowType;
  timestamp: string;
}

// ── Individual Stock ───────────────────────────────────────────────────────
export interface StockStats {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePct: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  avgVolume: number;
  marketCap: number;
  pe: number;
  eps: number;
  revenue: number;
  sector: string;
}

export interface OHLCVBar {
  time: number; // Unix timestamp (seconds)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface EarningsBar {
  quarter: string;
  epsEstimate: number;
  epsActual: number;
  revenueEstimate: number;
  revenueActual: number;
}

export interface NewsItem {
  id: string;
  headline: string;
  source: string;
  url: string;
  publishedAt: string;
  sentiment: 'positive' | 'negative' | 'neutral';
}

export interface SecFiling {
  type: '10-K' | '10-Q' | '8-K' | 'DEF 14A' | 'S-1';
  description: string;
  filedAt: string;
  url: string;
}

export interface StockDetail {
  stats: StockStats;
  ohlcv: OHLCVBar[];
  earnings: EarningsBar[];
  news: NewsItem[];
  filings: SecFiling[];
}

// ── Pre/Post-Market Scanner ─────────────────────────────────────────────────
export type ScannerMode = 'pre' | 'post';
export type ScannerFilter = 'gainers' | 'losers' | 'volume-surge' | 'gap-up' | 'gap-down';

export interface ScannerRow {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePct: number;
  volume: number;
  avgVolume: number;
  gap: number;
  sector: string;
  exchange: string;
  float: number;
}

// ── Store ──────────────────────────────────────────────────────────────────
export interface DashboardStore {
  selectedTicker: string;
  setSelectedTicker: (t: string) => void;
  scannerMode: ScannerMode;
  setScannerMode: (m: ScannerMode) => void;
  scannerFilter: ScannerFilter;
  setScannerFilter: (f: ScannerFilter) => void;
  scannerMinVolume: number;
  setScannerMinVolume: (v: number) => void;
  scannerMinPct: number;
  setScannerMinPct: (v: number) => void;
  collapsedPanels: Set<string>;
  togglePanel: (id: string) => void;
}

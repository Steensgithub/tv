import type { StockDetail, OHLCVBar } from '@/types';

function generateOHLCV(startPrice: number, days = 120): OHLCVBar[] {
  const bars: OHLCVBar[] = [];
  let price = startPrice;
  const baseTime = Math.floor(new Date('2025-02-01').getTime() / 1000);
  for (let i = 0; i < days; i++) {
    const daySeconds = 86400;
    const t = baseTime + i * daySeconds;
    const open = price;
    const move = (Math.random() - 0.48) * price * 0.025;
    const close = Math.max(open + move, 1);
    const high = Math.max(open, close) * (1 + Math.random() * 0.012);
    const low = Math.min(open, close) * (1 - Math.random() * 0.012);
    const volume = Math.round(20_000_000 + Math.random() * 60_000_000);
    bars.push({ time: t, open: +open.toFixed(2), high: +high.toFixed(2), low: +low.toFixed(2), close: +close.toFixed(2), volume });
    price = close;
  }
  return bars;
}

export const MOCK_STOCK_DETAIL: Record<string, StockDetail> = {
  AAPL: {
    stats: {
      symbol: 'AAPL', name: 'Apple Inc', price: 214.50, change: 2.44, changePct: 1.15,
      open: 212.10, high: 215.80, low: 211.50, volume: 55_200_000, avgVolume: 58_000_000,
      marketCap: 3_310_000_000_000, pe: 33.2, eps: 6.46, revenue: 391_000_000_000,
      sector: 'Technology',
    },
    ohlcv: generateOHLCV(175),
    earnings: [
      { quarter: 'Q3 2024', epsEstimate: 1.32, epsActual: 1.40, revenueEstimate: 84.5e9, revenueActual: 85.8e9 },
      { quarter: 'Q4 2024', epsEstimate: 2.10, epsActual: 2.18, revenueEstimate: 124e9, revenueActual: 124.3e9 },
      { quarter: 'Q1 2025', epsEstimate: 1.55, epsActual: 1.52, revenueEstimate: 89e9, revenueActual: 90.1e9 },
      { quarter: 'Q2 2025', epsEstimate: 1.48, epsActual: 1.65, revenueEstimate: 88e9, revenueActual: 93.3e9 },
    ],
    news: [
      { id: 'n1', headline: 'Apple Vision Pro sales exceed expectations in Q2 2025', source: 'Bloomberg', url: '#', publishedAt: new Date(Date.now() - 3_600_000).toISOString(), sentiment: 'positive' },
      { id: 'n2', headline: 'Apple expands AI features in iOS 19 beta', source: 'Reuters', url: '#', publishedAt: new Date(Date.now() - 7_200_000).toISOString(), sentiment: 'positive' },
      { id: 'n3', headline: 'Supply chain concerns in Southeast Asia weigh on outlook', source: 'WSJ', url: '#', publishedAt: new Date(Date.now() - 14_400_000).toISOString(), sentiment: 'negative' },
      { id: 'n4', headline: 'Apple raises quarterly dividend by 4% to $0.26 per share', source: 'Barron\'s', url: '#', publishedAt: new Date(Date.now() - 86_400_000).toISOString(), sentiment: 'positive' },
    ],
    filings: [
      { type: '10-Q', description: 'Quarterly Report (Q2 FY2025)', filedAt: '2025-05-02', url: 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=AAPL&type=10-Q' },
      { type: '10-K', description: 'Annual Report FY2024', filedAt: '2024-11-01', url: 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=AAPL&type=10-K' },
      { type: '8-K', description: 'Q2 2025 Earnings Release', filedAt: '2025-05-01', url: 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=AAPL&type=8-K' },
      { type: 'DEF 14A', description: 'Proxy Statement FY2025', filedAt: '2025-01-20', url: 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=AAPL&type=DEF+14A' },
    ],
  },
  NVDA: {
    stats: {
      symbol: 'NVDA', name: 'NVIDIA Corp', price: 142.80, change: 4.42, changePct: 3.19,
      open: 138.40, high: 143.90, low: 137.80, volume: 42_800_000, avgVolume: 38_000_000,
      marketCap: 3_500_000_000_000, pe: 68.5, eps: 2.08, revenue: 79_000_000_000,
      sector: 'Technology',
    },
    ohlcv: generateOHLCV(85),
    earnings: [
      { quarter: 'Q3 2024', epsEstimate: 0.68, epsActual: 0.81, revenueEstimate: 16.1e9, revenueActual: 18.1e9 },
      { quarter: 'Q4 2024', epsEstimate: 0.84, epsActual: 0.89, revenueEstimate: 20.0e9, revenueActual: 22.1e9 },
      { quarter: 'Q1 2025', epsEstimate: 0.96, epsActual: 1.04, revenueEstimate: 24.6e9, revenueActual: 26.0e9 },
      { quarter: 'Q2 2025', epsEstimate: 1.08, epsActual: 1.21, revenueEstimate: 28.0e9, revenueActual: 30.1e9 },
    ],
    news: [
      { id: 'n1', headline: 'NVIDIA Blackwell GPUs face record demand from hyperscalers', source: 'Bloomberg', url: '#', publishedAt: new Date(Date.now() - 1_800_000).toISOString(), sentiment: 'positive' },
      { id: 'n2', headline: 'NVIDIA partners with Saudi Arabia on AI infrastructure', source: 'FT', url: '#', publishedAt: new Date(Date.now() - 10_800_000).toISOString(), sentiment: 'positive' },
      { id: 'n3', headline: 'Export restrictions on H20 chips cloud near-term outlook', source: 'Reuters', url: '#', publishedAt: new Date(Date.now() - 21_600_000).toISOString(), sentiment: 'negative' },
    ],
    filings: [
      { type: '10-Q', description: 'Quarterly Report (Q1 FY2026)', filedAt: '2025-05-28', url: 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=NVDA&type=10-Q' },
      { type: '8-K', description: 'Q1 FY2026 Earnings', filedAt: '2025-05-28', url: 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=NVDA&type=8-K' },
      { type: '10-K', description: 'Annual Report FY2025', filedAt: '2025-02-26', url: 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=NVDA&type=10-K' },
    ],
  },
};

// Default fallback for any ticker not in the map
export function getMockStockDetail(symbol: string): StockDetail {
  return MOCK_STOCK_DETAIL[symbol] ?? MOCK_STOCK_DETAIL['AAPL'];
}

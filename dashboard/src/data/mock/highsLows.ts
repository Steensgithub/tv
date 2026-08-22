import type { HighLowEntry, HighLowType } from '@/types';

const entries: Array<[string, string, string, string, number, number, number, HighLowType]> = [
  ['NVDA', 'NVIDIA Corp', 'NASDAQ', 'Technology', 142.80, 3.21, 42_800_000, '52w-high'],
  ['META', 'Meta Platforms', 'NASDAQ', 'Comm. Services', 595.20, 2.45, 18_200_000, '52w-high'],
  ['GEV', 'GE Vernova', 'NYSE', 'Industrials', 388.40, 4.12, 3_400_000, '52w-high'],
  ['PLTR', 'Palantir Tech', 'NYSE', 'Technology', 38.90, 5.88, 62_100_000, '52w-high'],
  ['MSTR', 'MicroStrategy', 'NASDAQ', 'Technology', 1680.00, 8.34, 9_800_000, '52w-high'],
  ['WBA', 'Walgreens Boots', 'NASDAQ', 'Consumer Staples', 9.80, -4.42, 14_600_000, '52w-low'],
  ['MPW', 'Medical Prop Trust', 'NYSE', 'Real Estate', 3.42, -6.18, 22_100_000, '52w-low'],
  ['PARA', 'Paramount Global', 'NASDAQ', 'Comm. Services', 10.14, -3.77, 8_400_000, '52w-low'],
  ['VFC', 'VF Corporation', 'NYSE', 'Consumer Disc.', 12.88, -2.55, 5_200_000, '52w-low'],
  ['AAPL', 'Apple Inc', 'NASDAQ', 'Technology', 214.50, 1.14, 55_000_000, 'day-high'],
  ['TSLA', 'Tesla Inc', 'NASDAQ', 'Consumer Disc.', 188.90, 2.88, 92_000_000, 'day-high'],
  ['AMD', 'Adv Micro Devices', 'NASDAQ', 'Technology', 162.40, 3.55, 38_000_000, 'day-high'],
  ['PFE', 'Pfizer Inc', 'NYSE', 'Healthcare', 27.20, -1.82, 29_000_000, 'day-low'],
  ['T', 'AT&T Inc', 'NYSE', 'Comm. Services', 17.40, -2.14, 41_000_000, 'day-low'],
  ['BAC', 'Bank of America', 'NYSE', 'Financials', 38.60, 0.78, 48_000_000, 'day-high'],
];

export const MOCK_HIGH_LOW: HighLowEntry[] = entries.map(
  ([symbol, name, exchange, sector, price, change, volume, type]) => ({
    symbol,
    name,
    exchange,
    sector,
    price,
    change,
    volume,
    type,
    timestamp: new Date(Date.now() - Math.random() * 3_600_000).toISOString(),
  })
);

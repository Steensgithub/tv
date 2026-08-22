import type { ScannerRow } from '@/types';

// [symbol, name, price, change, changePct, volume, avgVolume, gap, sector, exchange, floatM]
const rows: Array<[string, string, number, number, number, number, number, number, string, string, number]> = [
  ['MSTR',  'MicroStrategy',     1680.00,  88.40,  5.55,  9_800_000,  4_200_000, 12.4,  'Technology',      'NASDAQ', 18],
  ['RIOT',  'Riot Platforms',    14.20,    1.28,   9.90,  42_000_000, 18_000_000, 8.8,  'Technology',      'NASDAQ', 120],
  ['SOUN',  'SoundHound AI',     8.44,     0.72,   9.32,  88_000_000, 30_000_000, 9.5,  'Technology',      'NASDAQ', 200],
  ['SMCI',  'Super Micro Comp.', 48.30,    3.88,   8.73,  28_000_000, 15_000_000, 7.2,  'Technology',      'NASDAQ', 85],
  ['PLUG',  'Plug Power',        3.92,     0.28,   7.69,  62_000_000, 28_000_000, 5.8,  'Industrials',     'NASDAQ', 310],
  ['RIVN',  'Rivian Automotive', 15.44,    0.98,   6.78,  38_000_000, 24_000_000, 6.4,  'Consumer Disc.',  'NASDAQ', 890],
  ['WOLF',  'Wolfspeed',         5.18,     0.31,   6.36,  22_000_000,  9_200_000, 4.2,  'Technology',      'NYSE',   140],
  ['NVDA',  'NVIDIA Corp',       142.80,   4.42,   3.19,  42_800_000, 38_000_000, 2.1,  'Technology',      'NASDAQ', 2450],
  ['WBA',   'Walgreens Boots',   9.80,    -0.45,  -4.39,  14_600_000, 11_000_000, -3.8, 'Consumer Staples','NASDAQ', 870],
  ['MPW',   'Medical Prop.',     3.42,    -0.23,  -6.30,  22_100_000, 14_000_000, -5.9, 'Real Estate',     'NYSE',   690],
  ['BBBY',  'Bed Bath Beyond',   0.88,    -0.08,  -8.33,  18_000_000,  7_000_000, -7.4, 'Consumer Disc.',  'NASDAQ', 430],
  ['PARA',  'Paramount Global',  10.14,   -0.42,  -3.98,   8_400_000,  5_200_000, -4.2, 'Comm. Services',  'NASDAQ', 600],
];

export const MOCK_SCANNER_ROWS: ScannerRow[] = rows.map(
  ([symbol, name, price, change, changePct, volume, avgVolume, gap, sector, exchange, floatM]) => ({
    symbol, name, price, change, changePct, volume, avgVolume, gap, sector, exchange,
    float: floatM * 1_000_000,
  })
);

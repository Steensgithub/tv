import type { Sector, ThemeETF } from '@/types';

export const MOCK_SECTORS: Sector[] = [
  { name: 'Technology', symbol: 'XLK', change: 1.24, price: 218.45 },
  { name: 'Healthcare', symbol: 'XLV', change: -0.38, price: 142.30 },
  { name: 'Financials', symbol: 'XLF', change: 0.82, price: 43.16 },
  { name: 'Consumer Disc.', symbol: 'XLY', change: 2.15, price: 185.90 },
  { name: 'Industrials', symbol: 'XLI', change: 0.44, price: 131.75 },
  { name: 'Energy', symbol: 'XLE', change: -1.92, price: 88.20 },
  { name: 'Utilities', symbol: 'XLU', change: -0.67, price: 67.44 },
  { name: 'Materials', symbol: 'XLB', change: 0.19, price: 89.63 },
  { name: 'Real Estate', symbol: 'XLRE', change: -1.44, price: 38.92 },
  { name: 'Comm. Services', symbol: 'XLC', change: 1.88, price: 79.31 },
  { name: 'Consumer Staples', symbol: 'XLP', change: -0.21, price: 77.58 },
];

const spark = (base: number, n = 10): number[] =>
  Array.from({ length: n }, (_, i) => +(base + (Math.random() - 0.48) * base * 0.015 * (i + 1)).toFixed(2));

export const MOCK_THEME_ETFS: ThemeETF[] = [
  { name: 'AI & Robotics', symbol: 'BOTZ', change: 2.41, price: 34.18, sparkline: spark(34.18) },
  { name: 'Semiconductors', symbol: 'SOXX', change: 1.73, price: 228.60, sparkline: spark(228.60) },
  { name: 'Clean Energy', symbol: 'ICLN', change: -0.85, price: 13.42, sparkline: spark(13.42) },
  { name: 'Cybersecurity', symbol: 'HACK', change: 0.97, price: 62.80, sparkline: spark(62.80) },
  { name: 'Biotech', symbol: 'IBB', change: -1.12, price: 145.30, sparkline: spark(145.30) },
  { name: 'Cloud Computing', symbol: 'SKYY', change: 1.55, price: 85.44, sparkline: spark(85.44) },
  { name: 'Space & Defense', symbol: 'ITA', change: 0.63, price: 156.70, sparkline: spark(156.70) },
  { name: 'Fintech', symbol: 'ARKF', change: 3.21, price: 22.15, sparkline: spark(22.15) },
];

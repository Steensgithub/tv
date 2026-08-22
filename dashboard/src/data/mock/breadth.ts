import type { BreadthPoint } from '@/types';

const days = 60;
const baseDate = new Date('2025-05-01');

export const MOCK_BREADTH: BreadthPoint[] = Array.from({ length: days }, (_, i) => {
  const d = new Date(baseDate);
  d.setDate(d.getDate() + i);
  const trend = i / days;
  return {
    date: d.toISOString().slice(0, 10),
    adLine: Math.round(2400 + trend * 800 + (Math.random() - 0.5) * 300),
    above20ma: Math.round(45 + trend * 20 + (Math.random() - 0.5) * 15),
    above50ma: Math.round(40 + trend * 18 + (Math.random() - 0.5) * 12),
    above200ma: Math.round(50 + trend * 12 + (Math.random() - 0.5) * 8),
    newHighs: Math.round(120 + trend * 80 + Math.random() * 60),
    newLows: Math.round(80 - trend * 40 + Math.random() * 40),
    upVolume: Math.round(3_200_000_000 + trend * 800_000_000 + Math.random() * 500_000_000),
    downVolume: Math.round(2_800_000_000 - trend * 400_000_000 + Math.random() * 400_000_000),
  };
});

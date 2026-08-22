import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmt(n: number, decimals = 2) {
  return n.toFixed(decimals);
}

export function fmtPct(n: number, decimals = 2) {
  return (n >= 0 ? '+' : '') + n.toFixed(decimals) + '%';
}

export function fmtLarge(n: number): string {
  if (n >= 1e12) return (n / 1e12).toFixed(2) + 'T';
  if (n >= 1e9)  return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6)  return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3)  return (n / 1e3).toFixed(1) + 'K';
  return n.toString();
}

export function changeColor(v: number) {
  if (v > 0) return 'text-emerald-400';
  if (v < 0) return 'text-red-400';
  return 'text-slate-400';
}

export function changeBg(v: number) {
  if (v > 1.5) return 'bg-emerald-500';
  if (v > 0.5) return 'bg-emerald-700';
  if (v > 0)   return 'bg-emerald-900';
  if (v < -1.5) return 'bg-red-500';
  if (v < -0.5) return 'bg-red-700';
  return 'bg-red-900';
}

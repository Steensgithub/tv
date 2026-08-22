import { create } from 'zustand';
import type { DashboardStore, ScannerMode, ScannerFilter } from '@/types';

export const useDashboardStore = create<DashboardStore>((set) => ({
  selectedTicker: 'AAPL',
  setSelectedTicker: (t) => set({ selectedTicker: t }),

  scannerMode: 'pre',
  setScannerMode: (m: ScannerMode) => set({ scannerMode: m }),

  scannerFilter: 'gainers',
  setScannerFilter: (f: ScannerFilter) => set({ scannerFilter: f }),

  scannerMinVolume: 500_000,
  setScannerMinVolume: (v) => set({ scannerMinVolume: v }),

  scannerMinPct: 2,
  setScannerMinPct: (v) => set({ scannerMinPct: v }),

  collapsedPanels: new Set<string>(),
  togglePanel: (id) =>
    set((state) => {
      const next = new Set(state.collapsedPanels);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { collapsedPanels: next };
    }),
}));

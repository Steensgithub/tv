import { TopBar } from '@/components/layout/TopBar';
import { MarketGroupsPanel } from '@/components/panels/MarketGroupsPanel';
import { MarketBreadthPanel } from '@/components/panels/MarketBreadthPanel';
import { COTPanel } from '@/components/panels/COTPanel';
import { HighsLowsPanel } from '@/components/panels/HighsLowsPanel';
import { StockPanel } from '@/components/panels/StockPanel';
import { ScannerPanel } from '@/components/panels/ScannerPanel';

export default function App() {
  return (
    <div className="min-h-screen bg-[#0a0b0f] text-slate-200">
      <TopBar />

      <main className="p-3 space-y-3">
        {/* Row 1: Groups + Breadth side by side */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          <MarketGroupsPanel />
          <MarketBreadthPanel />
        </div>

        {/* Row 2: COT + Highs & Lows */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          <COTPanel />
          <HighsLowsPanel />
        </div>

        {/* Row 3: Stock Panel full width */}
        <StockPanel />

        {/* Row 4: Scanner full width */}
        <ScannerPanel />
      </main>

      <footer className="text-center py-4 text-[10px] text-slate-700 border-t border-slate-800">
        MarketView Dashboard · Data shown is mock/simulated for demonstration ·{' '}
        <span className="text-slate-600">Swap adapters in <code className="font-mono">src/data/adapters/</code> to connect live data</span>
      </footer>
    </div>
  );
}

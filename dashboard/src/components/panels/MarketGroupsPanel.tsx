import { Panel } from '@/components/ui/Panel';
import { LayoutGrid } from 'lucide-react';
import { MOCK_SECTORS, MOCK_THEME_ETFS } from '@/data/mock/sectors';
import { changeBg, changeColor, fmtPct } from '@/lib/utils';
import { useDashboardStore } from '@/store';

function Sparkline({ data }: { data: number[] }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 60;
  const h = 24;
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x},${y}`;
    })
    .join(' ');
  const last = data[data.length - 1];
  const first = data[0];
  const color = last >= first ? '#34d399' : '#f87171';
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

export function MarketGroupsPanel() {
  const { setSelectedTicker } = useDashboardStore();

  return (
    <Panel id="panel-groups" title="Market Groups & Themes" icon={<LayoutGrid size={14} />}>
      {/* Sector heatmap */}
      <div className="mb-4">
        <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Sector ETFs</p>
        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-1.5">
          {MOCK_SECTORS.map((s) => (
            <button
              key={s.symbol}
              onClick={() => setSelectedTicker(s.symbol)}
              className={`relative flex flex-col items-center justify-center rounded-md p-2 cursor-pointer hover:opacity-90 transition-opacity ${changeBg(s.change)}`}
              title={`${s.name}: ${fmtPct(s.change)}`}
            >
              <span className="text-xs font-bold text-white">{s.symbol}</span>
              <span className="text-[10px] text-white/80 mt-0.5">{fmtPct(s.change)}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Thematic ETFs */}
      <div>
        <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Thematic ETFs</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {MOCK_THEME_ETFS.map((etf) => (
            <button
              key={etf.symbol}
              onClick={() => setSelectedTicker(etf.symbol)}
              className="flex items-center justify-between px-3 py-2 rounded-md bg-slate-800/60 hover:bg-slate-800 border border-slate-700/50 transition-colors text-left w-full"
            >
              <div>
                <span className="text-xs font-semibold text-white">{etf.symbol}</span>
                <span className="text-xs text-slate-500 ml-2">{etf.name}</span>
              </div>
              <div className="flex items-center gap-3">
                <Sparkline data={etf.sparkline} />
                <span className={`text-xs font-semibold tabular-nums ${changeColor(etf.change)}`}>{fmtPct(etf.change)}</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </Panel>
  );
}

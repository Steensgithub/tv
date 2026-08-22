import { useState, useMemo } from 'react';
import { Panel } from '@/components/ui/Panel';
import { ArrowUpCircle, ArrowDownCircle } from 'lucide-react';
import { MOCK_HIGH_LOW } from '@/data/mock/highsLows';
import { changeColor, fmtLarge, fmtPct } from '@/lib/utils';
import type { HighLowType } from '@/types';
import { useDashboardStore } from '@/store';

const TYPES: { id: HighLowType | 'all'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: '52w-high', label: '52W High' },
  { id: '52w-low', label: '52W Low' },
  { id: 'day-high', label: 'Day High' },
  { id: 'day-low', label: 'Day Low' },
];

export function HighsLowsPanel() {
  const [typeFilter, setTypeFilter] = useState<HighLowType | 'all'>('all');
  const [exchange, setExchange] = useState('all');
  const [minVol, setMinVol] = useState(0);
  const { setSelectedTicker } = useDashboardStore();

  const exchanges = useMemo(
    () => ['all', ...Array.from(new Set(MOCK_HIGH_LOW.map((r) => r.exchange)))],
    []
  );

  const filtered = useMemo(
    () =>
      MOCK_HIGH_LOW.filter(
        (r) =>
          (typeFilter === 'all' || r.type === typeFilter) &&
          (exchange === 'all' || r.exchange === exchange) &&
          r.volume >= minVol
      ),
    [typeFilter, exchange, minVol]
  );

  return (
    <Panel
      id="panel-highs-lows"
      title="Real-Time Highs & Lows"
      icon={<ArrowUpCircle size={14} />}
      actions={
        <div className="flex items-center gap-2">
          <select
            value={exchange}
            onChange={(e) => setExchange(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded text-[10px] text-slate-300 px-1.5 py-0.5 focus:outline-none"
          >
            {exchanges.map((ex) => <option key={ex} value={ex}>{ex === 'all' ? 'All Exchanges' : ex}</option>)}
          </select>
          <select
            value={minVol}
            onChange={(e) => setMinVol(Number(e.target.value))}
            className="bg-slate-800 border border-slate-700 rounded text-[10px] text-slate-300 px-1.5 py-0.5 focus:outline-none"
          >
            {[0, 500_000, 1_000_000, 5_000_000, 10_000_000].map((v) => (
              <option key={v} value={v}>{v === 0 ? 'Any Volume' : `> ${fmtLarge(v)}`}</option>
            ))}
          </select>
        </div>
      }
    >
      {/* Type filter chips */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {TYPES.map((t) => (
          <button
            key={t.id}
            onClick={() => setTypeFilter(t.id)}
            className={`px-2.5 py-0.5 rounded-full text-[10px] font-medium border transition-colors ${
              typeFilter === t.id
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'border-slate-700 text-slate-500 hover:text-slate-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-800">
              {['Symbol', 'Name', 'Price', 'Chg%', 'Volume', 'Type', 'Time'].map((h) => (
                <th key={h} className="text-left py-1.5 px-2 text-slate-500 font-medium uppercase text-[10px] tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => {
              const isHigh = row.type.includes('high');
              const time = new Date(row.timestamp).toLocaleTimeString('en-US', {
                hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York',
              });
              return (
                <tr
                  key={`${row.symbol}-${row.type}`}
                  className="border-b border-slate-800/50 hover:bg-slate-800/40 cursor-pointer transition-colors"
                  onClick={() => setSelectedTicker(row.symbol)}
                >
                  <td className="py-1.5 px-2 font-semibold text-blue-400">{row.symbol}</td>
                  <td className="py-1.5 px-2 text-slate-400 max-w-[120px] truncate">{row.name}</td>
                  <td className="py-1.5 px-2 text-white tabular-nums">${row.price.toFixed(2)}</td>
                  <td className={`py-1.5 px-2 tabular-nums font-medium ${changeColor(row.change)}`}>{fmtPct(row.change)}</td>
                  <td className="py-1.5 px-2 text-slate-400 tabular-nums">{fmtLarge(row.volume)}</td>
                  <td className="py-1.5 px-2">
                    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${isHigh ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'}`}>
                      {isHigh ? <ArrowUpCircle size={10} /> : <ArrowDownCircle size={10} />}
                      {row.type}
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-slate-500 tabular-nums">{time}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="text-center text-slate-600 py-6 text-xs">No entries match filters</p>
        )}
      </div>
    </Panel>
  );
}

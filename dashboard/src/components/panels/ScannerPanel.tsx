import { useMemo, useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Radar } from 'lucide-react';
import { MOCK_SCANNER_ROWS } from '@/data/mock/scanner';
import { useDashboardStore } from '@/store';
import { changeColor, fmtLarge, fmtPct } from '@/lib/utils';
import type { ScannerFilter } from '@/types';

const FILTERS: { id: ScannerFilter; label: string }[] = [
  { id: 'gainers', label: '% Gainers' },
  { id: 'losers', label: '% Losers' },
  { id: 'volume-surge', label: 'Vol Surge' },
  { id: 'gap-up', label: 'Gap Up' },
  { id: 'gap-down', label: 'Gap Down' },
];

const SECTORS = ['All', 'Technology', 'Consumer Disc.', 'Industrials', 'Healthcare', 'Financials', 'Real Estate', 'Comm. Services', 'Consumer Staples'];

type SortKey = keyof typeof MOCK_SCANNER_ROWS[0];

function applyFilter(rows: typeof MOCK_SCANNER_ROWS, filter: ScannerFilter, minVol: number, minPct: number) {
  return rows.filter((r) => {
    if (r.volume < minVol) return false;
    switch (filter) {
      case 'gainers': return r.changePct >= minPct;
      case 'losers': return r.changePct <= -minPct;
      case 'volume-surge': return r.volume / r.avgVolume >= 2;
      case 'gap-up': return r.gap >= minPct;
      case 'gap-down': return r.gap <= -minPct;
      default: return true;
    }
  });
}

export function ScannerPanel() {
  const {
    scannerMode, setScannerMode,
    scannerFilter, setScannerFilter,
    scannerMinVolume, setScannerMinVolume,
    scannerMinPct, setScannerMinPct,
    setSelectedTicker,
  } = useDashboardStore();

  const [sector, setSector] = useState('All');
  const [sortKey, setSortKey] = useState<SortKey>('changePct');
  const [sortAsc, setSortAsc] = useState(false);

  const rows = useMemo(() => {
    let data = applyFilter(MOCK_SCANNER_ROWS, scannerFilter, scannerMinVolume, scannerMinPct);
    if (sector !== 'All') data = data.filter((r) => r.sector === sector);
    data = [...data].sort((a, b) => {
      const av = a[sortKey] as number;
      const bv = b[sortKey] as number;
      return sortAsc ? av - bv : bv - av;
    });
    return data;
  }, [scannerFilter, scannerMinVolume, scannerMinPct, sector, sortKey, sortAsc]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortAsc((a) => !a);
    else { setSortKey(key); setSortAsc(false); }
  }

  const SortTh = ({ k, label }: { k: SortKey; label: string }) => (
    <th
      className="text-left py-1.5 px-2 text-slate-500 font-medium text-[10px] uppercase cursor-pointer select-none hover:text-slate-300 transition-colors"
      onClick={() => toggleSort(k)}
    >
      {label} {sortKey === k ? (sortAsc ? '↑' : '↓') : ''}
    </th>
  );

  return (
    <Panel
      id="panel-scanner"
      title="Pre/Post-Market Scanner"
      icon={<Radar size={14} />}
      actions={
        <div className="flex gap-1">
          {(['pre', 'post'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setScannerMode(m)}
              className={`px-2.5 py-0.5 rounded text-[10px] font-semibold border transition-colors uppercase ${
                scannerMode === m
                  ? m === 'pre' ? 'bg-amber-500/20 border-amber-500/50 text-amber-400' : 'bg-blue-500/20 border-blue-500/50 text-blue-400'
                  : 'border-slate-700 text-slate-600 hover:text-slate-300'
              }`}
            >
              {m === 'pre' ? 'Pre-Market' : 'After Hours'}
            </button>
          ))}
        </div>
      }
    >
      {/* Filter chips */}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setScannerFilter(f.id)}
            className={`px-2.5 py-0.5 rounded-full text-[10px] font-medium border transition-colors ${
              scannerFilter === f.id
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'border-slate-700 text-slate-500 hover:text-slate-300'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-2 mb-3 text-xs">
        <label className="flex items-center gap-1 text-slate-500">
          Min Vol:
          <select
            value={scannerMinVolume}
            onChange={(e) => setScannerMinVolume(Number(e.target.value))}
            className="bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-slate-300 text-[10px] focus:outline-none"
          >
            {[0, 100_000, 500_000, 1_000_000, 5_000_000].map((v) => (
              <option key={v} value={v}>{v === 0 ? 'Any' : fmtLarge(v)}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-slate-500">
          Min %:
          <select
            value={scannerMinPct}
            onChange={(e) => setScannerMinPct(Number(e.target.value))}
            className="bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-slate-300 text-[10px] focus:outline-none"
          >
            {[0, 1, 2, 5, 10, 15].map((v) => (
              <option key={v} value={v}>{v}%</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-slate-500">
          Sector:
          <select
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-slate-300 text-[10px] focus:outline-none"
          >
            {SECTORS.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <span className="ml-auto text-[10px] text-slate-600">{rows.length} results</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-800">
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium text-[10px] uppercase">Symbol</th>
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium text-[10px] uppercase">Name</th>
              <SortTh k="price" label="Price" />
              <SortTh k="changePct" label="Chg%" />
              <SortTh k="gap" label="Gap%" />
              <SortTh k="volume" label="Volume" />
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium text-[10px] uppercase">Vol/Avg</th>
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium text-[10px] uppercase">Float</th>
              <th className="text-left py-1.5 px-2 text-slate-500 font-medium text-[10px] uppercase">Sector</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.symbol}
                onClick={() => setSelectedTicker(row.symbol)}
                className="border-b border-slate-800/50 hover:bg-slate-800/40 cursor-pointer transition-colors"
              >
                <td className="py-1.5 px-2 font-semibold text-blue-400">{row.symbol}</td>
                <td className="py-1.5 px-2 text-slate-400 max-w-[120px] truncate">{row.name}</td>
                <td className="py-1.5 px-2 text-white tabular-nums">${row.price.toFixed(2)}</td>
                <td className={`py-1.5 px-2 tabular-nums font-semibold ${changeColor(row.changePct)}`}>{fmtPct(row.changePct)}</td>
                <td className={`py-1.5 px-2 tabular-nums ${changeColor(row.gap)}`}>{row.gap >= 0 ? '+' : ''}{row.gap.toFixed(1)}%</td>
                <td className="py-1.5 px-2 text-slate-400 tabular-nums">{fmtLarge(row.volume)}</td>
                <td className="py-1.5 px-2 tabular-nums text-slate-400">
                  <span className={row.volume / row.avgVolume >= 3 ? 'text-amber-400 font-semibold' : ''}>
                    {(row.volume / row.avgVolume).toFixed(1)}x
                  </span>
                </td>
                <td className="py-1.5 px-2 text-slate-400 tabular-nums">{fmtLarge(row.float)}</td>
                <td className="py-1.5 px-2 text-slate-500 text-[10px]">{row.sector}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="text-center text-slate-600 py-6 text-xs">No results match current filters</p>
        )}
      </div>
    </Panel>
  );
}

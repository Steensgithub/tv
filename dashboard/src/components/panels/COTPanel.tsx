import { useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { FileText } from 'lucide-react';
import { MOCK_COT } from '@/data/mock/cot';
import { fmtLarge } from '@/lib/utils';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
} from 'recharts';

export function COTPanel() {
  const [selected, setSelected] = useState(MOCK_COT[0].symbol);

  const row = MOCK_COT.find((r) => r.symbol === selected) ?? MOCK_COT[0];

  const netData = MOCK_COT.map((r) => ({
    symbol: r.symbol,
    Commercial: r.commercialNet,
    'Non-Commercial': r.nonCommercialNet,
  }));

  const changeData = MOCK_COT.map((r) => ({
    symbol: r.symbol,
    CommChange: r.commercialChange,
    NCChange: r.nonCommercialChange,
  }));

  return (
    <Panel id="panel-cot" title="COT Data" icon={<FileText size={14} />}>
      {/* Selector */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {MOCK_COT.map((r) => (
          <button
            key={r.symbol}
            onClick={() => setSelected(r.symbol)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              selected === r.symbol
                ? 'bg-blue-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            {r.symbol}
          </button>
        ))}
      </div>

      {/* Detail cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        {[
          { label: 'Comm. Net', value: fmtLarge(row.commercialNet), positive: row.commercialNet > 0 },
          { label: 'Non-Comm. Net', value: fmtLarge(row.nonCommercialNet), positive: row.nonCommercialNet > 0 },
          { label: 'Comm. Chg', value: (row.commercialChange >= 0 ? '+' : '') + fmtLarge(row.commercialChange), positive: row.commercialChange > 0 },
          { label: 'NC Chg', value: (row.nonCommercialChange >= 0 ? '+' : '') + fmtLarge(row.nonCommercialChange), positive: row.nonCommercialChange > 0 },
        ].map((c) => (
          <div key={c.label} className="bg-slate-800/60 rounded-md px-3 py-2">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider">{c.label}</div>
            <div className={`text-sm font-semibold mt-0.5 ${c.positive ? 'text-emerald-400' : 'text-red-400'}`}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* Net positioning chart */}
      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Net Positioning</p>
      <div style={{ height: 140 }} className="mb-3">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={netData} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2130" />
            <XAxis dataKey="symbol" tick={{ fontSize: 9, fill: '#64748b' }} />
            <YAxis tick={{ fontSize: 9, fill: '#64748b' }} tickFormatter={(v) => fmtLarge(v)} />
            <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #1e2740', fontSize: 11 }} formatter={(v: unknown) => fmtLarge(Number(v as number))} />
            <ReferenceLine y={0} stroke="#334155" />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            <Bar dataKey="Commercial" fill="#60a5fa" opacity={0.85} />
            <Bar dataKey="Non-Commercial" fill="#f59e0b" opacity={0.85} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Week-over-week changes chart */}
      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">WoW Change</p>
      <div style={{ height: 120 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={changeData} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2130" />
            <XAxis dataKey="symbol" tick={{ fontSize: 9, fill: '#64748b' }} />
            <YAxis tick={{ fontSize: 9, fill: '#64748b' }} tickFormatter={(v) => fmtLarge(v)} />
            <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #1e2740', fontSize: 11 }} formatter={(v: unknown) => fmtLarge(Number(v as number))} />
            <ReferenceLine y={0} stroke="#334155" />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            <Bar dataKey="CommChange" fill="#34d399" name="Comm. Change" opacity={0.85} />
            <Bar dataKey="NCChange" fill="#f87171" name="NC Change" opacity={0.85} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

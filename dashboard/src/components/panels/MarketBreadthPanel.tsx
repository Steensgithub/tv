import { useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { BarChart2 } from 'lucide-react';
import { MOCK_BREADTH } from '@/data/mock/breadth';
import { fmtLarge } from '@/lib/utils';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from 'recharts';

type BreadthView = 'adline' | 'ma' | 'hlratio' | 'volume';

const VIEWS: { id: BreadthView; label: string }[] = [
  { id: 'adline', label: 'A/D Line' },
  { id: 'ma', label: 'MA Breadth' },
  { id: 'hlratio', label: 'Highs / Lows' },
  { id: 'volume', label: 'Up/Down Vol' },
];

const last = MOCK_BREADTH[MOCK_BREADTH.length - 1];

export function MarketBreadthPanel() {
  const [view, setView] = useState<BreadthView>('adline');

  const chartData = MOCK_BREADTH.map((d) => ({
    ...d,
    date: d.date.slice(5), // MM-DD
    upVolB: +(d.upVolume / 1e9).toFixed(2),
    downVolB: +(d.downVolume / 1e9).toFixed(2),
  }));

  return (
    <Panel
      id="panel-breadth"
      title="Market Breadth"
      icon={<BarChart2 size={14} />}
      actions={
        <div className="flex gap-1">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              onClick={() => setView(v.id)}
              className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                view === v.id
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
      }
    >
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        {[
          { label: 'Above 20MA', value: `${last.above20ma}%` },
          { label: 'Above 50MA', value: `${last.above50ma}%` },
          { label: 'Above 200MA', value: `${last.above200ma}%` },
          { label: 'Up/Down Vol', value: `${(last.upVolume / last.downVolume).toFixed(2)}x` },
        ].map((s) => (
          <div key={s.label} className="bg-slate-800/60 rounded-md px-3 py-2 text-center">
            <div className="text-xs text-slate-500">{s.label}</div>
            <div className="text-sm font-semibold text-white mt-0.5">{s.value}</div>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div style={{ height: 200 }}>
        <ResponsiveContainer width="100%" height="100%">
          {view === 'adline' ? (
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2130" />
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#64748b' }} interval={9} />
              <YAxis tick={{ fontSize: 9, fill: '#64748b' }} />
              <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #1e2740', fontSize: 11 }} />
              <Line type="monotone" dataKey="adLine" stroke="#60a5fa" strokeWidth={1.5} dot={false} name="A/D Line" />
            </ComposedChart>
          ) : view === 'ma' ? (
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2130" />
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#64748b' }} interval={9} />
              <YAxis tick={{ fontSize: 9, fill: '#64748b' }} domain={[0, 100]} />
              <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #1e2740', fontSize: 11 }} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Line type="monotone" dataKey="above20ma" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="% Above 20MA" />
              <Line type="monotone" dataKey="above50ma" stroke="#34d399" strokeWidth={1.5} dot={false} name="% Above 50MA" />
              <Line type="monotone" dataKey="above200ma" stroke="#a78bfa" strokeWidth={1.5} dot={false} name="% Above 200MA" />
            </ComposedChart>
          ) : view === 'hlratio' ? (
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2130" />
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#64748b' }} interval={9} />
              <YAxis tick={{ fontSize: 9, fill: '#64748b' }} />
              <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #1e2740', fontSize: 11 }} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Bar dataKey="newHighs" fill="#34d399" name="New Highs" opacity={0.8} />
              <Bar dataKey="newLows" fill="#f87171" name="New Lows" opacity={0.8} />
            </ComposedChart>
          ) : (
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2130" />
              <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#64748b' }} interval={9} />
              <YAxis tick={{ fontSize: 9, fill: '#64748b' }} unit="B" />
              <Tooltip
                contentStyle={{ background: '#0f1117', border: '1px solid #1e2740', fontSize: 11 }}
                formatter={(v: unknown) => fmtLarge(Number(v as number) * 1e9)}
              />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Bar dataKey="upVolB" fill="#34d399" name="Up Volume ($B)" opacity={0.8} />
              <Bar dataKey="downVolB" fill="#f87171" name="Down Volume ($B)" opacity={0.8} />
            </ComposedChart>
          )}
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

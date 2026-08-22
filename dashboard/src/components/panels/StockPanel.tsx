import { useEffect, useRef, useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { LineChart, ExternalLink, Newspaper, FolderOpen, TrendingUp } from 'lucide-react';
import { useDashboardStore } from '@/store';
import { getMockStockDetail } from '@/data/mock/stocks';
import { changeColor, fmtLarge, fmtPct } from '@/lib/utils';
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
} from 'recharts';
import { createChart, ColorType, CandlestickSeries, HistogramSeries } from 'lightweight-charts';

type StockTab = 'chart' | 'earnings' | 'news' | 'filings';

function CandlestickChart({ ohlcv }: { ohlcv: ReturnType<typeof getMockStockDetail>['ohlcv'] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const chart = createChart(el, {
      width: el.clientWidth,
      height: 260,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#64748b',
      },
      grid: {
        vertLines: { color: '#1e2130' },
        horzLines: { color: '#1e2130' },
      },
      timeScale: { borderColor: '#1e2130', timeVisible: true },
      rightPriceScale: { borderColor: '#1e2130' },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#34d399',
      downColor: '#f87171',
      borderUpColor: '#34d399',
      borderDownColor: '#f87171',
      wickUpColor: '#34d399',
      wickDownColor: '#f87171',
    });

    const volSeries = chart.addSeries(HistogramSeries, {
      color: '#3b82f6',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    candleSeries.setData(
      ohlcv.map((b) => ({ time: b.time as any, open: b.open, high: b.high, low: b.low, close: b.close }))
    );
    volSeries.setData(
      ohlcv.map((b) => ({
        time: b.time as any,
        value: b.volume,
        color: b.close >= b.open ? '#34d39940' : '#f8717140',
      }))
    );

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [ohlcv]);

  return <div ref={containerRef} className="w-full" />;
}

function EarningsChart({ earnings }: { earnings: ReturnType<typeof getMockStockDetail>['earnings'] }) {
  const data = earnings.map((e) => ({
    quarter: e.quarter,
    'EPS Est': +e.epsEstimate.toFixed(2),
    'EPS Act': +e.epsActual.toFixed(2),
    'Rev Est ($B)': +(e.revenueEstimate / 1e9).toFixed(1),
    'Rev Act ($B)': +(e.revenueActual / 1e9).toFixed(1),
  }));

  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2130" />
          <XAxis dataKey="quarter" tick={{ fontSize: 9, fill: '#64748b' }} />
          <YAxis yAxisId="eps" tick={{ fontSize: 9, fill: '#64748b' }} />
          <YAxis yAxisId="rev" orientation="right" tick={{ fontSize: 9, fill: '#64748b' }} unit="B" />
          <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #1e2740', fontSize: 11 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <ReferenceLine yAxisId="eps" y={0} stroke="#334155" />
          <Bar yAxisId="eps" dataKey="EPS Est" fill="#60a5fa" opacity={0.5} />
          <Bar yAxisId="eps" dataKey="EPS Act" fill="#34d399" opacity={0.85} />
          <Bar yAxisId="rev" dataKey="Rev Est ($B)" fill="#f59e0b" opacity={0.5} />
          <Bar yAxisId="rev" dataKey="Rev Act ($B)" fill="#a78bfa" opacity={0.85} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

const SENTIMENT_COLORS = {
  positive: 'text-emerald-400',
  negative: 'text-red-400',
  neutral: 'text-slate-400',
};

export function StockPanel() {
  const { selectedTicker, setSelectedTicker } = useDashboardStore();
  const [tab, setTab] = useState<StockTab>('chart');
  const [input, setInput] = useState('');

  const detail = getMockStockDetail(selectedTicker);
  const { stats, ohlcv, earnings, news, filings } = detail;

  const TABS: { id: StockTab; label: string; icon: React.ReactNode }[] = [
    { id: 'chart', label: 'Chart', icon: <LineChart size={12} /> },
    { id: 'earnings', label: 'Earnings', icon: <TrendingUp size={12} /> },
    { id: 'news', label: 'News', icon: <Newspaper size={12} /> },
    { id: 'filings', label: 'SEC Filings', icon: <FolderOpen size={12} /> },
  ];

  return (
    <Panel
      id="panel-stock"
      title="Individual Stock"
      icon={<LineChart size={14} />}
      actions={
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const t = input.trim().toUpperCase();
            if (t) { setSelectedTicker(t); setInput(''); }
          }}
          className="flex gap-1"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ticker…"
            className="w-20 bg-slate-800 border border-slate-700 rounded px-2 py-0.5 text-[10px] text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500"
          />
          <button type="submit" className="px-2 py-0.5 bg-blue-600 hover:bg-blue-500 text-white text-[10px] rounded transition-colors">
            Go
          </button>
        </form>
      }
    >
      {/* Ticker header */}
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-baseline gap-2">
            <h3 className="text-xl font-bold text-white">{stats.symbol}</h3>
            <span className="text-sm text-slate-400">{stats.name}</span>
          </div>
          <div className="flex items-baseline gap-2 mt-0.5">
            <span className="text-2xl font-bold text-white">${stats.price.toFixed(2)}</span>
            <span className={`text-sm font-semibold ${changeColor(stats.changePct)}`}>
              {stats.change >= 0 ? '+' : ''}{stats.change.toFixed(2)} ({fmtPct(stats.changePct)})
            </span>
          </div>
          <span className="text-[10px] text-slate-500">{stats.sector}</span>
        </div>

        {/* Key stats */}
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 text-xs">
          {[
            { label: 'Open', value: `$${stats.open.toFixed(2)}` },
            { label: 'High', value: `$${stats.high.toFixed(2)}` },
            { label: 'Low', value: `$${stats.low.toFixed(2)}` },
            { label: 'Volume', value: fmtLarge(stats.volume) },
            { label: 'Mkt Cap', value: fmtLarge(stats.marketCap) },
            { label: 'P/E', value: stats.pe.toFixed(1) },
            { label: 'EPS', value: `$${stats.eps.toFixed(2)}` },
            { label: 'Revenue', value: fmtLarge(stats.revenue) },
            { label: 'Avg Vol', value: fmtLarge(stats.avgVolume) },
          ].map((s) => (
            <div key={s.label} className="bg-slate-800/60 rounded px-2 py-1.5">
              <div className="text-[10px] text-slate-500">{s.label}</div>
              <div className="font-semibold text-white mt-0.5">{s.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-slate-800 mb-3">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
              tab === t.id
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-500 hover:text-slate-300'
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'chart' && <CandlestickChart ohlcv={ohlcv} />}

      {tab === 'earnings' && (
        <div>
          <EarningsChart earnings={earnings} />
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800">
                  {['Quarter', 'EPS Est', 'EPS Act', 'Beat?', 'Rev Est', 'Rev Act', 'Beat?'].map((h) => (
                    <th key={h} className="text-left py-1.5 px-2 text-slate-500 font-medium text-[10px] uppercase">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {earnings.map((e) => {
                  const epsBeat = e.epsActual >= e.epsEstimate;
                  const revBeat = e.revenueActual >= e.revenueEstimate;
                  return (
                    <tr key={e.quarter} className="border-b border-slate-800/50">
                      <td className="py-1.5 px-2 text-slate-300">{e.quarter}</td>
                      <td className="py-1.5 px-2 text-slate-400 tabular-nums">${e.epsEstimate.toFixed(2)}</td>
                      <td className="py-1.5 px-2 text-white tabular-nums font-medium">${e.epsActual.toFixed(2)}</td>
                      <td className={`py-1.5 px-2 font-medium text-[10px] ${epsBeat ? 'text-emerald-400' : 'text-red-400'}`}>{epsBeat ? '✓ Beat' : '✗ Miss'}</td>
                      <td className="py-1.5 px-2 text-slate-400 tabular-nums">{fmtLarge(e.revenueEstimate)}</td>
                      <td className="py-1.5 px-2 text-white tabular-nums font-medium">{fmtLarge(e.revenueActual)}</td>
                      <td className={`py-1.5 px-2 font-medium text-[10px] ${revBeat ? 'text-emerald-400' : 'text-red-400'}`}>{revBeat ? '✓ Beat' : '✗ Miss'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'news' && (
        <div className="space-y-2">
          {news.map((n) => {
            const age = Math.round((Date.now() - new Date(n.publishedAt).getTime()) / 60_000);
            const ageStr = age < 60 ? `${age}m ago` : `${Math.round(age / 60)}h ago`;
            return (
              <a
                key={n.id}
                href={n.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-3 p-3 rounded-lg bg-slate-800/40 hover:bg-slate-800 border border-slate-800 transition-colors group"
              >
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium leading-snug group-hover:text-white transition-colors ${SENTIMENT_COLORS[n.sentiment]}`}>
                    {n.headline}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] text-slate-500">{n.source}</span>
                    <span className="text-[10px] text-slate-600">•</span>
                    <span className="text-[10px] text-slate-600">{ageStr}</span>
                  </div>
                </div>
                <ExternalLink size={12} className="text-slate-600 group-hover:text-slate-400 shrink-0 mt-0.5 transition-colors" />
              </a>
            );
          })}
        </div>
      )}

      {tab === 'filings' && (
        <div className="space-y-2">
          {filings.map((f, i) => (
            <a
              key={i}
              href={f.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between p-3 rounded-lg bg-slate-800/40 hover:bg-slate-800 border border-slate-800 transition-colors group"
            >
              <div className="flex items-center gap-3">
                <span className="px-2 py-0.5 rounded bg-blue-600/20 text-blue-400 text-[10px] font-bold border border-blue-500/20">
                  {f.type}
                </span>
                <div>
                  <p className="text-xs font-medium text-slate-200">{f.description}</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">Filed: {f.filedAt}</p>
                </div>
              </div>
              <ExternalLink size={12} className="text-slate-600 group-hover:text-slate-400 transition-colors" />
            </a>
          ))}
          <p className="text-[10px] text-slate-600 text-center pt-1">
            Links open SEC EDGAR. Full filing data available via{' '}
            <a href={`https://efts.sec.gov/LATEST/search-index?q=%22${stats.symbol}%22`} className="text-blue-500 hover:underline" target="_blank" rel="noopener noreferrer">EDGAR full-text search</a>.
          </p>
        </div>
      )}
    </Panel>
  );
}

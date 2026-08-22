import { useState, useEffect } from 'react';
import { Search, Settings, Bell, TrendingUp } from 'lucide-react';
import { useDashboardStore } from '@/store';

type MarketSession = 'pre' | 'regular' | 'post' | 'closed';

function getMarketSession(): MarketSession {
  const now = new Date();
  const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const h = et.getHours();
  const m = et.getMinutes();
  const mins = h * 60 + m;
  const day = et.getDay();
  if (day === 0 || day === 6) return 'closed';
  if (mins >= 240 && mins < 570) return 'pre';    // 4:00–9:30 AM ET
  if (mins >= 570 && mins < 960) return 'regular'; // 9:30 AM–4:00 PM ET
  if (mins >= 960 && mins < 1200) return 'post';  // 4:00–8:00 PM ET
  return 'closed';
}

const SESSION_LABELS: Record<MarketSession, string> = {
  pre: 'Pre-Market',
  regular: 'Market Open',
  post: 'After Hours',
  closed: 'Market Closed',
};

const SESSION_COLORS: Record<MarketSession, string> = {
  pre: 'text-amber-400 border-amber-400/40 bg-amber-400/10',
  regular: 'text-emerald-400 border-emerald-400/40 bg-emerald-400/10',
  post: 'text-blue-400 border-blue-400/40 bg-blue-400/10',
  closed: 'text-slate-400 border-slate-600 bg-slate-800/40',
};

const INDICES = [
  { label: 'SPY', value: '+1.24%', pos: true },
  { label: 'QQQ', value: '+1.88%', pos: true },
  { label: 'DIA', value: '+0.44%', pos: true },
  { label: 'IWM', value: '-0.32%', pos: false },
  { label: 'VIX', value: '14.82', pos: null },
];

export function TopBar() {
  const [session, setSession] = useState<MarketSession>(getMarketSession());
  const [time, setTime] = useState(new Date());
  const [search, setSearch] = useState('');
  const { setSelectedTicker } = useDashboardStore();

  useEffect(() => {
    const interval = setInterval(() => {
      setTime(new Date());
      setSession(getMarketSession());
    }, 60_000);
    return () => clearInterval(interval);
  }, []);

  const etTime = time.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit' });

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const ticker = search.trim().toUpperCase();
    if (ticker) {
      setSelectedTicker(ticker);
      setSearch('');
      // Scroll to stock panel
      document.getElementById('panel-stock')?.scrollIntoView({ behavior: 'smooth' });
    }
  }

  return (
    <header className="sticky top-0 z-50 flex items-center gap-4 px-4 py-2 border-b border-slate-800 bg-slate-950/95 backdrop-blur-md">
      {/* Logo */}
      <div className="flex items-center gap-2 shrink-0">
        <TrendingUp size={20} className="text-blue-400" />
        <span className="font-bold text-white text-sm tracking-widest uppercase">MarketView</span>
      </div>

      {/* Index tickers */}
      <div className="hidden md:flex items-center gap-4 text-xs font-mono">
        {INDICES.map((idx) => (
          <span key={idx.label} className="flex items-center gap-1">
            <span className="text-slate-500">{idx.label}</span>
            <span className={idx.pos === true ? 'text-emerald-400' : idx.pos === false ? 'text-red-400' : 'text-slate-300'}>
              {idx.value}
            </span>
          </span>
        ))}
      </div>

      <div className="flex-1" />

      {/* Search */}
      <form onSubmit={handleSearch} className="relative">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search ticker…"
          className="w-40 bg-slate-800 border border-slate-700 rounded-md pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition"
        />
      </form>

      {/* Market session badge */}
      <span className={`hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-semibold ${SESSION_COLORS[session]}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${session === 'regular' ? 'bg-emerald-400 animate-pulse' : session === 'pre' ? 'bg-amber-400' : session === 'post' ? 'bg-blue-400' : 'bg-slate-500'}`} />
        {SESSION_LABELS[session]}
      </span>

      {/* Clock */}
      <span className="hidden lg:block font-mono text-xs text-slate-500 tabular-nums">{etTime} ET</span>

      {/* Icons */}
      <button className="text-slate-500 hover:text-slate-300 transition-colors" aria-label="Notifications">
        <Bell size={16} />
      </button>
      <button className="text-slate-500 hover:text-slate-300 transition-colors" aria-label="Settings">
        <Settings size={16} />
      </button>
    </header>
  );
}

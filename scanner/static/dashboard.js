/* dashboard.js – polling-based updates every 15 seconds */

const API = {
  signals: '/api/signals',
  status:  '/api/status',
  config:  '/api/config',
  events:  '/api/events',
};

let selectedSignalId = null;

// --- Clock ---
function updateClock() {
  const el = document.getElementById('clock');
  if (el) {
    el.textContent = new Date().toLocaleTimeString('en-US', {
      timeZone: 'America/New_York',
      hour12: false,
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    }) + ' NY';
  }
}
setInterval(updateClock, 1000);
updateClock();

// --- Status ---
async function loadStatus() {
  try {
    const r = await fetch(API.status);
    if (!r.ok) return;
    const s = await r.json();
    const badge = document.getElementById('scanner-state');
    if (badge) {
      badge.textContent = (s.state || 'unknown').toUpperCase().replace('_', ' ');
      badge.className = 'badge badge-' + (s.state || 'unknown').toLowerCase().replace(/\s/g, '_');
    }
    setText('st-symbols', s.symbols_scanned ?? '–');
    setText('st-signals', s.new_signals_total ?? '–');
    setText('st-errors', s.data_errors ?? '–');
    setText('st-latency', s.provider_latency_ms != null ? s.provider_latency_ms.toFixed(0) + ' ms' : '–');
    setText('st-last', fmtTs(s.last_scan_end));
    setText('st-heartbeat', fmtTs(s.worker_heartbeat));
  } catch (e) { console.warn('Status fetch failed', e); }
}

// --- Signals ---
async function loadSignals() {
  const sym = document.getElementById('filter-symbol')?.value?.trim() || '';
  const tf  = document.getElementById('filter-tf')?.value || '';
  const confirmed = document.getElementById('filter-confirmed')?.checked || false;
  let url = API.signals + '?limit=100';
  if (sym) url += '&symbol=' + encodeURIComponent(sym.toUpperCase());
  if (tf)  url += '&timeframe=' + encodeURIComponent(tf);
  if (confirmed) url += '&confirmed_only=true';

  try {
    const r = await fetch(url);
    if (!r.ok) return;
    const data = await r.json();
    renderSignals(data);
  } catch (e) { console.warn('Signals fetch failed', e); }
}

function renderSignals(signals) {
  const tbody = document.getElementById('signals-body');
  if (!tbody) return;
  if (!signals.length) {
    tbody.innerHTML = '<tr><td colspan="16" style="text-align:center;color:#8b949e">No signals yet</td></tr>';
    return;
  }
  tbody.innerHTML = signals.map(s => `
    <tr onclick="showDetail(${s.id})" data-id="${s.id}">
      <td><strong>${s.symbol}</strong></td>
      <td>${s.signal_timestamp_ny ? s.signal_timestamp_ny.replace('T', ' ').slice(0,19) : '–'}</td>
      <td>${s.signal_timeframe}</td>
      <td>${s.htf_timeframe}</td>
      <td>${fmt(s.close_price, 4)}</td>
      <td class="${s.htf_regime === 'bullish' ? 'htf-bullish' : 'htf-not'}">${s.htf_regime ?? '–'}</td>
      <td>${fmt(s.order_block_bottom, 4)}</td>
      <td>${fmt(s.order_block_top, 4)}</td>
      <td>${fmt(s.relative_volume_ratio, 1)}%</td>
      <td>${fmt(s.ma_ribbon_distance_pct, 2)}%</td>
      <td>${fmt(s.atr, 4)}</td>
      <td>${fmt(s.initial_stop, 4)}</td>
      <td>${fmt(s.tp1, 4)}</td>
      <td>${fmt(s.tp2, 4)}</td>
      <td>${s.data_provider ?? '–'}</td>
      <td class="${s.bar_confirmed ? 'confirmed' : 'unconfirmed'}">${s.bar_confirmed ? '✓' : '✗'}</td>
    </tr>
  `).join('');
}

function showDetail(id) {
  selectedSignalId = id;
  fetch('/api/signals/' + id)
    .then(r => r.json())
    .then(data => {
      const panel = document.getElementById('detail-panel');
      const pre = document.getElementById('detail-json');
      if (panel && pre) {
        pre.textContent = JSON.stringify(data, null, 2);
        panel.style.display = '';
        panel.scrollIntoView({ behavior: 'smooth' });
      }
    })
    .catch(e => console.warn('Detail fetch failed', e));
}

// --- Config ---
async function loadConfig() {
  try {
    const r = await fetch(API.config);
    if (!r.ok) return;
    const data = await r.json();
    const el = document.getElementById('config-json');
    if (el) el.textContent = JSON.stringify(data, null, 2);
  } catch (e) { console.warn('Config fetch failed', e); }
}

// --- SSE ---
function connectSSE() {
  const es = new EventSource(API.events);
  es.addEventListener('new_signal', (e) => {
    // Refresh signals table on new signal event
    loadSignals();
    loadStatus();
  });
  es.onerror = () => {
    // Reconnect after 15s on error
    setTimeout(connectSSE, 15000);
    es.close();
  };
}

// --- Utilities ---
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function fmt(val, decimals) {
  if (val == null || val === '') return '–';
  return Number(val).toFixed(decimals);
}

function fmtTs(ts) {
  if (!ts) return '–';
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      timeZone: 'America/New_York', hour12: false,
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  } catch { return ts; }
}

// --- Boot ---
loadStatus();
loadSignals();
loadConfig();
connectSSE();

setInterval(() => { loadStatus(); loadSignals(); }, 15000);

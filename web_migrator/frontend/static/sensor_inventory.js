// sensor_inventory.js — Sensor Inventory page logic

let allRows = [];
let activeSource = '';

async function init() {
  await Promise.all([loadSummary(), loadInventory()]);
}

// ── Summary cards ────────────────────────────────────────────────────────
async function loadSummary() {
  try {
    const res  = await fetch('/api/sensors/inventory/summary');
    const data = await res.json();
    const t    = data.totals;

    setText('card-total',   t.total);
    setText('card-total-sub', `en ${data.by_source.length} fuentes`);
    setText('card-ok',      t.ok);
    setText('card-ok-sub',  `${pct(t.ok, t.total)}% del total`);
    setText('card-offline', t.offline);
    setText('card-offline-sub', `${pct(t.offline, t.total)}% del total`);

    for (const src of data.by_source) {
      const key = src.source;
      const el = document.getElementById(`card-${key}`);
      if (el) {
        el.textContent = src.total;
        setText(`card-${key}-sub`,
          `${src.ok} online · ${src.offline} offline · ${src.fields} campo${src.fields !== 1 ? 's' : ''}`);
      }
    }
  } catch(e) { console.error(e); }
}

// ── Inventory table ──────────────────────────────────────────────────────
async function loadInventory() {
  try {
    const res  = await fetch('/api/sensors/inventory');
    const data = await res.json();
    allRows = data.rows;

    const fields = [...new Set(allRows.map(r => r.field).filter(Boolean))].sort();
    const sel = document.getElementById('fil-field');
    sel.innerHTML = '<option value="">Todos los campos</option>' +
      fields.map(f => `<option value="${esc(f)}">${esc(f)}</option>`).join('');

    renderTable();
  } catch(e) {
    document.getElementById('sensor-tbody').innerHTML =
      `<tr class="empty-row"><td colspan="9">Error cargando datos</td></tr>`;
  }
}

function renderTable() {
  const search    = document.getElementById('fil-search').value.toLowerCase();
  const fieldFil  = document.getElementById('fil-field').value;
  const statusFil = document.getElementById('fil-status').value;

  let filtered = allRows;
  if (activeSource) filtered = filtered.filter(r => r.source === activeSource);
  if (fieldFil)     filtered = filtered.filter(r => r.field  === fieldFil);
  if (statusFil)    filtered = filtered.filter(r => r.status === statusFil);
  if (search)       filtered = filtered.filter(r =>
    (r.sensor_name || '').toLowerCase().includes(search) ||
    (r.sensor_id   || '').toLowerCase().includes(search)
  );

  setText('tbl-count', `${filtered.length} sensor${filtered.length !== 1 ? 'es' : ''}`);

  if (!filtered.length) {
    document.getElementById('sensor-tbody').innerHTML =
      `<tr class="empty-row"><td colspan="9">Sin resultados para los filtros aplicados</td></tr>`;
    return;
  }

  const tbody = document.getElementById('sensor-tbody');
  tbody.innerHTML = '';
  for (const r of filtered) {
    const tr = document.createElement('tr');
    const lastSeen   = r.last_seen   ? fmtDate(r.last_seen) : '—';
    const lastValue  = r.last_value  != null ? Number(r.last_value).toLocaleString('es-CL', {maximumFractionDigits: 2}) : '—';
    const staleClass = isStale(r.last_seen) ? ' style="color:#dc2626;font-weight:700"' : '';

    tr.innerHTML = `
      <td><span class="badge badge-${esc(r.source)}">${esc(r.source)}</span></td>
      <td>${esc(r.field || '—')}</td>
      <td>${esc(r.zone  || '—')}</td>
      <td style="font-size:11px;color:#64748b">${esc(r.sensor_id || '—')}</td>
      <td>${esc(r.sensor_name || '—')}</td>
      <td style="color:#64748b">${esc(r.unit || '—')}</td>
      <td class="num">${lastValue}</td>
      <td${staleClass}>${lastSeen}</td>
      <td><span class="badge badge-${esc(r.status)}">${r.status === 'ok' ? 'Online' : 'Offline'}</span></td>
    `;
    tbody.appendChild(tr);
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────
function fmtDate(s) {
  if (!s) return '—';
  const [y, m, d] = s.split('-');
  return `${d}-${m}-${y}`;
}
function isStale(dateStr) {
  if (!dateStr) return false;
  const today = new Date(); today.setHours(0,0,0,0);
  const d = new Date(dateStr);
  return (today - d) / 86400000 > 2;
}
function pct(a, b) { return b ? Math.round(a / b * 100) : 0; }
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Events ───────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeSource = btn.dataset.source;
    renderTable();
  });
});
document.getElementById('fil-field').addEventListener('change', renderTable);
document.getElementById('fil-status').addEventListener('change', renderTable);
document.getElementById('fil-search').addEventListener('input', renderTable);

init();

// billing_order.js — Billing Order (Orden de Facturación) with same header as purchase_orders

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0
});

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatDisplayDate(isoStr) {
  if (!isoStr) return '';
  const [y, m, d] = isoStr.slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
}

function formatShortDate(isoStr) {
  if (!isoStr) return '';
  const [, m, d] = isoStr.slice(0, 10).split('-');
  return `${d}/${m}`;
}

function fmtPct(v) {
  if (v == null || v === '' || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  return n.toFixed(1).replace(/\.0$/, '').replace('.', ',') + '%';
}

function setPct(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = fmtPct(v);
}

function toISO(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// Worker column candidates (AppSheet names vary)
const WORKER_CANDIDATES = [
  'trabajador', 'Trabajador', 'nombre_trabajador', 'Nombre_trabajador',
  'worker', 'nombre', 'Nombre'
];
function detectWorkerCol(cols) {
  for (const c of WORKER_CANDIDATES) { if (cols.includes(c)) return c; }
  return null;
}

// ── Init dates (current week Mon–Sun) ─────────────────────────────────
function initDates() {
  const fromEl = document.getElementById('fil-from');
  const toEl = document.getElementById('fil-to');
  if (fromEl && fromEl.value && toEl && toEl.value) return;
  if (typeof currentWeekRange === 'function') {
    const w = currentWeekRange();
    fromEl.value = w.from;
    toEl.value = w.to;
    return;
  }
  const now = new Date();
  const day = now.getDay();
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  monday.setDate(monday.getDate() - (day === 0 ? 6 : day - 1));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  fromEl.value = toISO(monday);
  toEl.value   = toISO(sunday);
}

// ── Load filter dropdowns ──────────────────────────────────────────────
async function loadFilters() {
  if (window.globalFiltersReady) await window.globalFiltersReady;
}

function globalVal(id) {
  return document.getElementById(id)?.value || '';
}

// ── Generate ───────────────────────────────────────────────────────────
async function generate() {
  const contratista  = globalVal('fil-contratista');
  const empresa      = globalVal('fil-empresa');
  const fecha_inicio = globalVal('fil-from');
  const fecha_termino= globalVal('fil-to');

  if (!contratista || !empresa || !fecha_inicio || !fecha_termino) {
    showError('Seleccione contratista, empresa y rango de fechas.');
    return;
  }

  if (typeof showReportLoading === 'function') showReportLoading();
  const btn = document.getElementById('btn-generate');
  btn.disabled = true;
  btn.textContent = 'Cargando…';

  hideAll();

  try {
    const params = new URLSearchParams({ contratista, empresa, fecha_inicio, fecha_termino });

    // Single source (issue #156): header + pivot from the same Aprobado /
    // total_pagar query. Do NOT reuse /api/tarjas/contratista here — that
    // operational report intentionally shows all estados and total_trabajado.
    const res = await fetch('/api/odoo/facturacion/data?' + params);
    if (!res.ok) throw new Error('Error en API de facturación');

    const data = await res.json();

    if (!data.rows?.length) {
      document.getElementById('empty-box').classList.remove('hidden');
      return;
    }

    let header = data.header;
    if (!header) {
      const total = data.rows.reduce((s, r) => s + (Number(r.total_pagar) || 0), 0);
      header = {
        total,
        total_trato: 0,
        total_al_dia: total,
        total_trabajado: data.rows.reduce((s, r) => s + (Number(r.total_trabajado) || 0), 0),
        total_contratista: data.rows.reduce((s, r) => s + (Number(r.total_contratista) || 0), 0),
      };
    }

    renderHeader(header, contratista, empresa, fecha_inicio, fecha_termino);
    renderPivot(data.columns, data.rows, header);
    document.getElementById('bo-document').style.display = 'block';
    document.getElementById('btn-pdf').disabled = false;
    if (typeof syncFiltersToURL === 'function') syncFiltersToURL(FILTER_IDS);

  } catch (e) {
    showError('Error al generar la orden: ' + e.message);
    console.error(e);
  } finally {
    if (typeof hideReportLoading === 'function') hideReportLoading();
    btn.disabled = false;
    btn.textContent = 'Generar orden';
  }
}

// ── Render header (same structure as purchase_orders.js) ───────────────
function renderHeader(header, contratista, empresa, fechaFrom, fechaTo) {
  const h = header || {};

  document.getElementById('doc-company').textContent    = empresa;
  document.getElementById('doc-contractor').textContent = contratista;
  document.getElementById('doc-date-from').textContent  = formatDisplayDate(fechaFrom);
  document.getElementById('doc-date-to').textContent    = formatDisplayDate(fechaTo);

  // Glosa
  const d1 = formatDisplayDate(fechaFrom).replace(/\s/g, ' ');
  const d2 = formatDisplayDate(fechaTo).replace(/\s/g, ' ');
  document.getElementById('doc-glosa').textContent =
    `SERVICIOS DE LABORES AGRÍCOLAS ${d1.toUpperCase()} AL ${d2.toUpperCase()}`;

  // Week label
  document.getElementById('doc-week').textContent =
    `Semana desde ${formatDisplayDate(fechaFrom)} al ${formatDisplayDate(fechaTo)}`;

  // Totals
  const total = h.total ?? 0;
  document.getElementById('doc-grand-total').textContent  = fmtCLP.format(total);
  document.getElementById('doc-total-trabajadores').textContent = fmtCLP.format(h.total_trabajado ?? 0);
  document.getElementById('doc-total-comision').textContent = fmtCLP.format(h.total_contratista ?? 0);
  document.getElementById('doc-total-trato').textContent  = fmtCLP.format(h.total_trato  ?? 0);
  document.getElementById('doc-total-aldia').textContent  = fmtCLP.format(h.total_al_dia ?? 0);
  document.getElementById('doc-total').textContent        = fmtCLP.format(total);
  setPct('doc-pct-comision', h.pct_comision);
  setPct('doc-pct-trato', h.pct_comision_trato);
  setPct('doc-pct-aldia', h.pct_comision_al_dia);
}

// ── Render pivot table ─────────────────────────────────────────────────
function renderPivot(columns, rows, header) {
  if (!rows?.length) return;
  const h = header || {};

  const workerCol = detectWorkerCol(columns);

  // Collect unique dates
  const dateSet = new Set();
  rows.forEach(r => {
    const f = typeof r.fecha === 'string' ? r.fecha.slice(0, 10) : '';
    if (f) dateSet.add(f);
  });
  const dates = [...dateSet].sort();

  // Group by worker → sum totals per date (worker pay + commission + billable)
  const groups = new Map();
  rows.forEach(r => {
    const worker = workerCol ? (r[workerCol] ?? '(sin nombre)') : '(sin nombre)';
    const fecha  = typeof r.fecha === 'string' ? r.fecha.slice(0, 10) : '';
    const value  = Number(r.total_pagar) || 0;
    const trabajado = Number(r.total_trabajado) || 0;
    const comision = Number(r.total_contratista) || 0;

    if (!groups.has(worker)) {
      groups.set(worker, { worker, byDate: {}, tipos: new Set() });
    }
    const g = groups.get(worker);
    const tipos = String(r.tipo_pago || '').split(',').map(s => s.trim()).filter(Boolean);
    tipos.forEach(t => g.tipos.add(t));
    if (fecha) {
      const prev = g.byDate[fecha] || { total: 0, trabajado: 0, comision: 0 };
      g.byDate[fecha] = {
        total: prev.total + value,
        trabajado: prev.trabajado + trabajado,
        comision: prev.comision + comision,
      };
    }
  });

  const sorted = [...groups.values()].sort((a, b) =>
    a.worker.localeCompare(b.worker, 'es')
  );

  function tipoBadgeHtml(tipos) {
    const seen = new Set();
    const parts = [];
    for (const t of tipos) {
      const isTrato = t.toLowerCase() === 'trato';
      const key = isTrato ? 'trato' : 'aldia';
      if (seen.has(key)) continue;
      seen.add(key);
      const cls = isTrato ? 'badge-trato' : 'badge-aldia';
      const low = t.toLowerCase();
      const label = isTrato ? 'Trato' : (low === 'al dia' || low === 'al día' ? 'Al día' : t);
      parts.push(`<span class="badge ${cls}">${esc(label)}</span>`);
    }
    return parts.join(' ');
  }

  function dateCellHtml(cell) {
    const val = cell?.trabajado || 0;
    if (!val) return `<td class="cell-dash">-</td>`;
    return `<td class="cell-date">${fmtCLP.format(val)}</td>`;
  }

  const thead = document.getElementById('bo-pivot-thead');
  thead.innerHTML = `<tr>
    <th>Trabajador</th>
    ${dates.map(d => `<th class="num">${esc(formatShortDate(d))}</th>`).join('')}
    <th class="num">Suma</th>
  </tr>`;

  const colTotals = {};
  dates.forEach(d => { colTotals[d] = 0; });
  let grandTrabajado = 0;
  let grandComision = 0;
  let grandTotal = 0;

  let html = '';
  sorted.forEach(g => {
    const rowTrabajado = dates.reduce((s, d) => s + (g.byDate[d]?.trabajado || 0), 0);
    const rowComision = dates.reduce((s, d) => s + (g.byDate[d]?.comision || 0), 0);
    const rowTotal = dates.reduce((s, d) => s + (g.byDate[d]?.total || 0), 0);
    grandTrabajado += rowTrabajado;
    grandComision += rowComision;
    grandTotal += rowTotal;

    html += `<tr>`;
    html += `<td class="cell-worker">${esc(g.worker)} ${tipoBadgeHtml(g.tipos)}</td>`;
    dates.forEach(d => {
      const cell = g.byDate[d];
      if (cell) colTotals[d] += cell.trabajado;
      html += dateCellHtml(cell);
    });
    html += `<td class="cell-total">${fmtCLP.format(rowTrabajado)}</td>`;
    html += `</tr>`;
  });

  html += `<tr class="bo-totals-row">`;
  html += `<td>Subtotal</td>`;
  dates.forEach(d => {
    const v = colTotals[d];
    html += `<td>${v > 0 ? fmtCLP.format(v) : '-'}</td>`;
  });
  html += `<td>${fmtCLP.format(grandTrabajado)}</td>`;
  html += `</tr>`;

  document.getElementById('bo-pivot-tbody').innerHTML = html;
  const subtotal = h.total_trabajado ?? grandTrabajado;
  const adicional = h.total_contratista ?? grandComision;
  const billed = h.total ?? grandTotal;
  document.getElementById('doc-subtotal').textContent = fmtCLP.format(subtotal);
  document.getElementById('doc-summary-comision').textContent = fmtCLP.format(adicional);
  document.getElementById('doc-summary-total').textContent = fmtCLP.format(billed);
  setPct('doc-summary-pct-comision', h.pct_comision ?? (subtotal ? (adicional / subtotal * 100) : null));
}

// ── Helpers ────────────────────────────────────────────────────────────
function hideAll() {
  document.getElementById('bo-document').style.display = 'none';
  document.getElementById('error-box').classList.add('hidden');
  document.getElementById('empty-box').classList.add('hidden');
  document.getElementById('btn-pdf').disabled = true;
}

function showError(msg) {
  const el = document.getElementById('error-box');
  el.textContent = msg;
  el.classList.remove('hidden');
}

// ── URL filter sync ───────────────────────────────────────────────────
const FILTER_IDS = ['fil-from', 'fil-to', 'fil-contratista', 'fil-empresa'];

// ── Events ────────────────────────────────────────────────────────────
document.getElementById('btn-generate').addEventListener('click', () => {
  generate().then(() => {
    if (globalVal('fil-contratista') && globalVal('fil-empresa')) {
      syncFiltersToURL(FILTER_IDS);
    }
  });
});

document.getElementById('btn-pdf').addEventListener('click', () => {
  const contratista  = globalVal('fil-contratista');
  const empresa      = globalVal('fil-empresa');
  const fecha_inicio = globalVal('fil-from');
  const fecha_termino= globalVal('fil-to');
  if (!contratista || !empresa || !fecha_inicio || !fecha_termino) return;
  const params = new URLSearchParams({ contratista, empresa, fecha_inicio, fecha_termino });
  window.open('/api/odoo/facturacion/pdf?' + params, '_blank');
});

// ── Init ──────────────────────────────────────────────────────────────
initDates();
loadFilters().then(() => autoTriggerFromURL(FILTER_IDS, () => {
  if (!globalVal('fil-contratista') || !globalVal('fil-empresa') || !globalVal('fil-from') || !globalVal('fil-to')) return;
  return generate();
}));

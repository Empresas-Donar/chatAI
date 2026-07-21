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

function toISO(d) { return d.toISOString().slice(0, 10); }

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
  const now = new Date();
  const day = now.getDay();
  const monday = new Date(now);
  monday.setDate(now.getDate() - (day === 0 ? 6 : day - 1));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  document.getElementById('inp-date-from').value = toISO(monday);
  document.getElementById('inp-date-to').value   = toISO(sunday);
}

// ── Load filter dropdowns ──────────────────────────────────────────────
async function loadFilters() {
  try {
    const res  = await fetch('/api/purchase-orders/filters');
    const data = await res.json();
    fillSelect('sel-contractor', data.contratistas, '-- Seleccionar --');
    fillSelect('sel-company',    data.empresas,      '-- Seleccionar --');
  } catch (e) {
    console.error('Error loading filters:', e);
  }
}

function fillSelect(id, items, defaultLabel) {
  const sel = document.getElementById(id);
  sel.innerHTML = `<option value="">${defaultLabel}</option>` +
    items.map(i => `<option value="${esc(String(i))}">${esc(String(i))}</option>`).join('');
}

// ── Generate ───────────────────────────────────────────────────────────
async function generate() {
  const contratista  = document.getElementById('sel-contractor').value;
  const empresa      = document.getElementById('sel-company').value;
  const fecha_inicio = document.getElementById('inp-date-from').value;
  const fecha_termino= document.getElementById('inp-date-to').value;

  if (!contratista || !empresa || !fecha_inicio || !fecha_termino) {
    showError('Seleccione contratista, empresa y rango de fechas.');
    return;
  }

  const btn = document.getElementById('btn-generate');
  btn.disabled = true;
  btn.textContent = 'Cargando…';

  hideAll();

  try {
    const params = new URLSearchParams({ contratista, empresa, fecha_inicio, fecha_termino });

    const [headerRes, pivotRes] = await Promise.all([
      fetch('/api/purchase-orders?' + params),
      fetch('/api/tarjas/contratista?' + params),
    ]);

    if (!headerRes.ok) throw new Error('Error en API de cabecera');
    if (!pivotRes.ok)  throw new Error('Error en API de pivot');

    const headerData = await headerRes.json();
    const pivotData  = await pivotRes.json();

    if (!headerData.rows?.length && !pivotData.rows?.length) {
      document.getElementById('empty-box').classList.remove('hidden');
      return;
    }

    renderHeader(headerData.header, contratista, empresa, fecha_inicio, fecha_termino);
    renderPivot(pivotData.columns, pivotData.rows);
    document.getElementById('bo-document').style.display = 'block';
    document.getElementById('btn-pdf').disabled = false;

  } catch (e) {
    showError('Error al generar la orden: ' + e.message);
    console.error(e);
  } finally {
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
  document.getElementById('doc-total-trato').textContent  = fmtCLP.format(h.total_trato  ?? 0);
  document.getElementById('doc-total-aldia').textContent  = fmtCLP.format(h.total_al_dia ?? 0);
  document.getElementById('doc-total').textContent        = fmtCLP.format(total);
}

// ── Render pivot table ─────────────────────────────────────────────────
function renderPivot(columns, rows) {
  if (!rows?.length) return;

  const workerCol = detectWorkerCol(columns);

  // Collect unique dates
  const dateSet = new Set();
  rows.forEach(r => {
    const f = typeof r.fecha === 'string' ? r.fecha.slice(0, 10) : '';
    if (f) dateSet.add(f);
  });
  const dates = [...dateSet].sort();

  // Group by worker → sum totals per date
  const groups = new Map();
  rows.forEach(r => {
    const worker = workerCol ? (r[workerCol] ?? '(sin nombre)') : '(sin nombre)';
    const fecha  = typeof r.fecha === 'string' ? r.fecha.slice(0, 10) : '';
    const value  = Number(r.total_trabajado) || 0;

    if (!groups.has(worker)) {
      groups.set(worker, { worker, byDate: {} });
    }
    const g = groups.get(worker);
    if (fecha) g.byDate[fecha] = (g.byDate[fecha] || 0) + value;
  });

  const sorted = [...groups.values()].sort((a, b) =>
    a.worker.localeCompare(b.worker, 'es')
  );

  // Thead
  const thead = document.getElementById('bo-pivot-thead');
  thead.innerHTML = `<tr>
    <th>Total Trabajador</th>
    ${dates.map(d => `<th class="num">${esc(formatShortDate(d))}</th>`).join('')}
    <th class="num">Suma total</th>
  </tr>`;

  // Tbody + column totals
  const colTotals = {};
  dates.forEach(d => { colTotals[d] = 0; });
  let grandTotal = 0;

  let html = '';
  sorted.forEach(g => {
    const rowTotal = dates.reduce((s, d) => s + (g.byDate[d] || 0), 0);
    grandTotal += rowTotal;

    html += `<tr>`;
    html += `<td class="cell-worker">${esc(g.worker)}</td>`;
    dates.forEach(d => {
      const val = g.byDate[d] || 0;
      colTotals[d] += val;
      if (val > 0) {
        html += `<td class="cell-date">${fmtCLP.format(val)}</td>`;
      } else {
        html += `<td class="cell-dash">-</td>`;
      }
    });
    html += `<td class="cell-total">${fmtCLP.format(rowTotal)}</td>`;
    html += `</tr>`;
  });

  // Footer totals row
  html += `<tr class="bo-totals-row">`;
  html += `<td>Suma total</td>`;
  dates.forEach(d => {
    const v = colTotals[d];
    html += `<td>${v > 0 ? fmtCLP.format(v) : '-'}</td>`;
  });
  html += `<td>${fmtCLP.format(grandTotal)}</td>`;
  html += `</tr>`;

  document.getElementById('bo-pivot-tbody').innerHTML = html;
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
const FILTER_IDS = ['inp-date-from', 'inp-date-to', 'sel-contractor', 'sel-company'];

// ── Events ────────────────────────────────────────────────────────────
document.getElementById('btn-generate').addEventListener('click', () => {
  generate().then(() => {
    if (document.getElementById('sel-contractor').value && document.getElementById('sel-company').value) {
      syncFiltersToURL(FILTER_IDS);
    }
  });
});

document.getElementById('btn-pdf').addEventListener('click', () => {
  const contratista  = document.getElementById('sel-contractor').value;
  const empresa      = document.getElementById('sel-company').value;
  const fecha_inicio = document.getElementById('inp-date-from').value;
  const fecha_termino= document.getElementById('inp-date-to').value;
  if (!contratista || !empresa || !fecha_inicio || !fecha_termino) return;
  const params = new URLSearchParams({ contratista, empresa, fecha_inicio, fecha_termino });
  window.open('/api/odoo/facturacion/pdf?' + params, '_blank');
});

// ── Init ──────────────────────────────────────────────────────────────
initDates();
// Populate selects, then restore URL params; no auto-trigger (document requires deliberate action)
loadFilters().then(() => loadFiltersFromURL(FILTER_IDS));

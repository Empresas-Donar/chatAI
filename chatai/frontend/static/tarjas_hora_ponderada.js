// tarjas_hora_ponderada.js — Hora ponderada estandarizada a 9 horas (Labor x CC pivot)

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0
});

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toISO(d) { return d.toISOString().slice(0, 10); }

function formatShortDate(isoStr) {
  if (!isoStr) return '—';
  const [y, m, d] = isoStr.slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
}

// hora_ponderada_9h = ROUND(costo_hora * 9, 0), costo_hora = total / horas.
// Mirrors _hora_ponderada_9h() in tarjas_controller.py — returns null (→ '-')
// when horas is 0/NULL, same convention as costo_hora elsewhere.
function horaPonderada9h(total, horas) {
  return horas > 0 ? Math.round((total / horas) * 9) : null;
}

// ── Init dates (current week) ─────────────────────────────────────────
function initDates() {
  const now = new Date();
  const day = now.getDay();
  const monday = new Date(now);
  monday.setDate(now.getDate() - (day === 0 ? 6 : day - 1));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);

  document.getElementById('fil-from').value = toISO(monday);
  document.getElementById('fil-to').value = toISO(sunday);
}

// ── Load filter dropdowns ─────────────────────────────────────────────
async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/hora-ponderada-9h/filters');
    const data = await res.json();
    fillSelect('fil-contratista', data.contratistas, 'Todos');
    fillSelect('fil-empresa', data.empresas, 'Todas');
    fillSelect('fil-cc', data.centros_costo, 'Todos');
    fillSelect('fil-labor', data.labores, 'Todas');
  } catch (e) {
    console.error('Error loading filters:', e);
  }
}

function fillSelect(id, items, defaultLabel) {
  const sel = document.getElementById(id);
  sel.innerHTML = `<option value="">${defaultLabel}</option>` +
    items.map(i => `<option value="${esc(String(i))}">${esc(String(i))}</option>`).join('');
}

// ── Query & render ────────────────────────────────────────────────────
let _lastRows = null;

async function queryData() {
  const from = document.getElementById('fil-from').value;
  const to   = document.getElementById('fil-to').value;
  if (!from || !to) return;

  const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });

  const add = (key, id) => {
    const v = document.getElementById(id)?.value;
    if (v) params.append(key, v);
  };
  add('contratista', 'fil-contratista');
  add('empresa', 'fil-empresa');
  add('centro_costo', 'fil-cc');
  add('labor', 'fil-labor');

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';
  let _hasData = false;

  try {
    const res = await fetch('/api/tarjas/hora-ponderada-9h?' + params);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      console.error('API error:', err);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();

    if (!data.rows.length) {
      _lastRows = null;
      document.getElementById('pivot-section').style.display = 'none';
      document.getElementById('empty-state').style.display = 'block';
      return;
    }

    _lastRows = data.rows;
    document.getElementById('empty-state').style.display = 'none';
    renderPivot(data.rows);
    document.getElementById('pivot-section').style.display = '';
    _hasData = true;
  } catch (e) {
    console.error('Query error:', e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Consultar';
    setDownloadEnabled(_hasData);
  }
}

// ── Build & render the pivot table ────────────────────────────────────
// Rows come pre-aggregated one per Labor+CC+Fecha cell (SUM(total_trabajado),
// SUM(horas_trabajadas) already summed server-side). Groups here are keyed
// by Labor+CC (the pivot's row dimension); dates become columns.
function renderPivot(rows) {
  const dateSet = new Set();
  rows.forEach(r => {
    const f = typeof r.fecha === 'string' ? r.fecha.slice(0, 10) : '';
    if (f) dateSet.add(f);
  });
  const dates = [...dateSet].sort();

  const groups = new Map();
  let grandTotal = 0;
  let grandHoras = 0;

  rows.forEach(r => {
    const labor = r.labor ?? '';
    const cc    = r.centro_costo ?? '';
    const key   = `${labor}||${cc}`;
    const fecha = typeof r.fecha === 'string' ? r.fecha.slice(0, 10) : '';
    const total = Number(r.total_trabajado) || 0;
    const horas = Number(r.horas_trabajadas) || 0;

    if (!groups.has(key)) {
      groups.set(key, { labor, cc, totalTrabajado: 0, totalHoras: 0, byDate: {} });
    }
    const g = groups.get(key);
    g.totalTrabajado += total;
    g.totalHoras += horas;
    if (fecha) {
      g.byDate[fecha] = { total, horas };
    }
    grandTotal += total;
    grandHoras += horas;
  });

  // Sort groups by Labor then CC
  const sorted = [...groups.values()].sort((a, b) => {
    const cmp = a.labor.localeCompare(b.labor, 'es');
    return cmp !== 0 ? cmp : a.cc.localeCompare(b.cc, 'es');
  });

  // Render thead
  const thead = document.getElementById('pivot-thead');
  let hdr = `<tr>
    <th class="th-fixed">Labor</th>
    <th class="th-fixed">CC</th>`;
  dates.forEach(d => {
    hdr += `<th class="th-date">${formatShortDate(d)}</th>`;
  });
  hdr += `<th class="th-fixed th-total">Hora ponderada 9h</th>`;
  hdr += '</tr>';
  thead.innerHTML = hdr;

  // Render tbody
  const tbody = document.getElementById('pivot-tbody');
  let html = '';
  let prevLabor = null;

  // Per-date footer accumulators (blended across all Labor+CC rows for that date)
  const colTrabajado = {};
  const colHoras = {};
  dates.forEach(d => { colTrabajado[d] = 0; colHoras[d] = 0; });

  sorted.forEach(g => {
    const isFirst = g.labor !== prevLabor;
    prevLabor = g.labor;

    const rowClass = isFirst ? 'worker-first' : '';
    const laborCell = isFirst ? esc(g.labor) : '';

    html += `<tr class="${rowClass}">`;
    html += `<td class="cell-worker">${laborCell}</td>`;
    html += `<td class="cell-labor" title="${esc(g.cc)}">${esc(g.cc)}</td>`;

    dates.forEach(d => {
      const cell = g.byDate[d];
      if (cell) {
        colTrabajado[d] += cell.total;
        colHoras[d] += cell.horas;
      }
      const val = cell ? horaPonderada9h(cell.total, cell.horas) : null;
      if (val != null) {
        html += `<td class="cell-value">${fmtCLP.format(val)}</td>`;
      } else {
        html += `<td class="cell-value"><span class="cell-dash">-</span></td>`;
      }
    });

    // Row "Total" = costo_hora*9 recomputed over the whole selected range for
    // this Labor+CC (NOT a sum of the per-date projected cells above — see
    // spec Decisions: summing an hourly-rate projection across independent
    // dates is not economically meaningful).
    const rowTotal = horaPonderada9h(g.totalTrabajado, g.totalHoras);
    html += `<td class="cell-total">${rowTotal != null ? fmtCLP.format(rowTotal) : '<span class="cell-dash">-</span>'}</td>`;
    html += '</tr>';
  });

  // Footer row: blended hora_ponderada_9h — same rate formula recomputed over
  // the grand totals (per date, and overall), never a sum of the values above.
  const footerTotal = horaPonderada9h(grandTotal, grandHoras);
  html += `<tr class="tc-totals-row">`;
  html += `<td class="cell-worker"><strong>Hora ponderada 9h global</strong></td>`;
  html += `<td></td>`;
  dates.forEach(d => {
    const v = horaPonderada9h(colTrabajado[d], colHoras[d]);
    html += `<td class="cell-value cell-total-foot">${v != null ? fmtCLP.format(v) : '<span class="cell-dash">-</span>'}</td>`;
  });
  html += `<td class="cell-total cell-total-foot"><strong>${footerTotal != null ? fmtCLP.format(footerTotal) : '-'}</strong></td>`;
  html += '</tr>';

  tbody.innerHTML = html;
}

// ── Download helpers ──────────────────────────────────────────────────
function currentParams() {
  const p = new URLSearchParams({
    fecha_inicio: document.getElementById('fil-from').value,
    fecha_termino: document.getElementById('fil-to').value,
  });
  const add = (key, id) => { const v = document.getElementById(id)?.value; if (v) p.append(key, v); };
  add('contratista','fil-contratista');
  add('empresa','fil-empresa');
  add('centro_costo','fil-cc');
  add('labor','fil-labor');
  return p;
}
function setDownloadEnabled(on) {
  document.getElementById('btn-excel').disabled = !on;
  document.getElementById('btn-pdf').disabled = !on;
}

// ── URL filter sync ───────────────────────────────────────────────────
const FILTER_IDS = ['fil-from', 'fil-to', 'fil-contratista', 'fil-empresa', 'fil-cc', 'fil-labor'];

async function loadFiltersAndRestore() {
  initDates();
  await loadFilters();
  autoTriggerFromURL(FILTER_IDS, queryData);
}

// ── Events ────────────────────────────────────────────────────────────
document.getElementById('btn-apply').addEventListener('click', () => {
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
});

document.getElementById('btn-excel').addEventListener('click', () => {
  window.location.href = '/api/tarjas/hora-ponderada-9h/download-excel?' + currentParams();
});
document.getElementById('btn-pdf').addEventListener('click', () => {
  window.open('/api/tarjas/hora-ponderada-9h/download-pdf?' + currentParams(), '_blank');
});

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') queryData().then(() => syncFiltersToURL(FILTER_IDS)); });
});

bindPopstate(FILTER_IDS, queryData);

// ── Init ──────────────────────────────────────────────────────────────
loadFiltersAndRestore();

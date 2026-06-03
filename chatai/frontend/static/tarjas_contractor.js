// tarjas_contractor.js — Contractor detail pivot table

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0
});
const fmtCLPDec = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', minimumFractionDigits: 2, maximumFractionDigits: 2
});

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toISO(d) { return d.toISOString().slice(0, 10); }

function formatShortDate(isoStr) {
  const d = new Date(isoStr + 'T12:00:00');
  return d.toLocaleDateString('es-CL', { day: 'numeric', month: 'short', year: 'numeric' });
}

// Candidate column names for the worker field (AppSheet names vary)
const WORKER_CANDIDATES = [
  'trabajador', 'Trabajador', 'nombre_trabajador', 'Nombre_trabajador',
  'worker', 'nombre', 'Nombre'
];

function detectWorkerCol(cols) {
  for (const c of WORKER_CANDIDATES) {
    if (cols.includes(c)) return c;
  }
  return null;
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
    const res = await fetch('/api/tarjas/contratista/filters');
    const data = await res.json();
    fillSelect('fil-contratista', data.contratistas, 'Todos');
    fillSelect('fil-empresa', data.empresas, 'Todas');
    fillSelect('fil-cc', data.centros_costo, 'Todos');
    fillSelect('fil-labor', data.labores, 'Todas');
    fillSelect('fil-tipo', data.tipos_pago, 'Todos');
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
  add('tipo_pago', 'fil-tipo');
  add('labor', 'fil-labor');

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';

  try {
    const res = await fetch('/api/tarjas/contratista?' + params);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      console.error('API error:', err);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();

    if (!data.rows.length) {
      document.getElementById('pivot-section').style.display = 'none';
      document.getElementById('empty-state').style.display = 'block';
      setDownloadEnabled(false);
      return;
    }

    document.getElementById('empty-state').style.display = 'none';
    renderPivot(data.columns, data.rows);
    document.getElementById('pivot-section').style.display = '';
    setDownloadEnabled(true);
  } catch (e) {
    console.error('Query error:', e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Consultar';
  }
}

// ── Build & render the pivot table ────────────────────────────────────
function renderPivot(columns, rows) {
  const workerCol = detectWorkerCol(columns);
  if (!workerCol) {
    console.warn('Worker column not found. Available:', columns);
  }

  // Unique sorted dates
  const dateSet = new Set();
  rows.forEach(r => {
    const f = typeof r.fecha === 'string' ? r.fecha.slice(0, 10) : '';
    if (f) dateSet.add(f);
  });
  const dates = [...dateSet].sort();

  // Build groups keyed by worker|labor|tipo_pago
  const groups = new Map();
  let globalMax = 0;

  rows.forEach(r => {
    const worker = workerCol ? (r[workerCol] ?? '(sin nombre)') : '(sin nombre)';
    const labor  = r.labor ?? '';
    const tipo   = r.tipo_pago ?? '';
    const key    = `${worker}||${labor}||${tipo}`;
    const fecha  = typeof r.fecha === 'string' ? r.fecha.slice(0, 10) : '';
    const value  = Number(r.total_trabajado) || 0;

    if (!groups.has(key)) {
      groups.set(key, { worker, labor, tipo, rate: value, byDate: {} });
    }

    const g = groups.get(key);
    if (fecha) {
      g.byDate[fecha] = (g.byDate[fecha] || 0) + value;
      if (g.byDate[fecha] > globalMax) globalMax = g.byDate[fecha];
    }
  });

  // Sort groups by worker name then labor
  const sorted = [...groups.values()].sort((a, b) => {
    const cmp = a.worker.localeCompare(b.worker, 'es');
    return cmp !== 0 ? cmp : a.labor.localeCompare(b.labor, 'es');
  });

  // Render thead
  const thead = document.getElementById('pivot-thead');
  let hdr = `<tr>
    <th class="th-fixed">Trabajador</th>
    <th class="th-fixed">Labor</th>
    <th class="th-fixed">Tipo de pago</th>
    <th class="th-fixed" style="text-align:right">Valor por hr</th>`;
  dates.forEach(d => {
    hdr += `<th class="th-date">${formatShortDate(d)}</th>`;
  });
  hdr += '</tr>';
  thead.innerHTML = hdr;

  // Render tbody
  const tbody = document.getElementById('pivot-tbody');
  let html = '';
  let prevWorker = null;

  sorted.forEach(g => {
    const isFirst = g.worker !== prevWorker;
    prevWorker = g.worker;

    const rowClass = isFirst ? 'worker-first' : '';
    const workerCell = isFirst ? esc(g.worker) : '';

    const tipoCls = g.tipo.toLowerCase() === 'trato' ? 'tc-tipo-trato'
      : (g.tipo.toLowerCase().includes('dia') || g.tipo.toLowerCase().includes('día'))
        ? 'tc-tipo-aldia' : '';

    html += `<tr class="${rowClass}">`;
    html += `<td class="cell-worker">${workerCell}</td>`;
    html += `<td class="cell-labor" title="${esc(g.labor)}">${esc(g.labor)}</td>`;
    html += `<td><span class="${tipoCls}">${esc(g.tipo)}</span></td>`;
    html += `<td class="cell-rate">${fmtCLPDec.format(g.rate)}</td>`;

    dates.forEach(d => {
      const val = g.byDate[d];
      if (val != null && val > 0) {
        const pct = globalMax > 0 ? Math.max(4, (val / globalMax) * 100) : 0;
        html += `<td class="cell-value">
          <div class="bar-wrap">
            <div class="bar" style="width:${pct.toFixed(1)}%"></div>
            <span class="bar-text">${fmtCLPDec.format(val)}</span>
          </div>
        </td>`;
      } else {
        html += `<td class="cell-value"><span class="cell-dash">-</span></td>`;
      }
    });

    html += '</tr>';
  });

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
  add('tipo_pago','fil-tipo');
  add('labor','fil-labor');
  return p;
}
function setDownloadEnabled(on) {
  document.getElementById('btn-excel').disabled = !on;
  document.getElementById('btn-pdf').disabled = !on;
}
function printWithHeader(title, filters) {
  const chips = Object.entries(filters)
    .filter(([,v]) => v)
    .map(([k,v]) => `<span class="ph-chip"><strong>${esc(k)}:</strong> ${esc(v)}</span>`)
    .join('');
  const now = new Date().toLocaleDateString('es-CL', { day:'2-digit', month:'long', year:'numeric' });
  document.getElementById('print-header').innerHTML = `
    <div class="ph-top">
      <img class="ph-logo" src="/static/img/donar_logo.png" alt="Empresas Donar" />
      <div class="ph-title-block">
        <h2>${esc(title)}</h2>
        <p class="ph-subtitle">Generado el ${now}</p>
      </div>
    </div>
    <div class="ph-filters">${chips}</div>
  `;
  window.print();
}:</strong> ${esc(v)}</span>`)
    .join('');
  document.getElementById('print-header').innerHTML =
    `<h2>${esc(title)}</h2><div class="ph-filters">${chips}</div>`;
  window.print();
}

// ── Events ────────────────────────────────────────────────────────────
document.getElementById('btn-apply').addEventListener('click', queryData);
document.getElementById('btn-excel').addEventListener('click', () => {
  window.location.href = '/api/tarjas/contratista/download-excel?' + currentParams();
});
document.getElementById('btn-pdf').addEventListener('click', () => {
  const g = id => document.getElementById(id)?.value || '';
  printWithHeader('Detalle contratista — Tarjas', {
    'Desde': g('fil-from'), 'Hasta': g('fil-to'),
    'Contratista': g('fil-contratista'),
    'Empresa': g('fil-empresa'), 'CC': g('fil-cc'),
    'Tipo de pago': g('fil-tipo'), 'Labor': g('fil-labor'),
  });
});

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') queryData(); });
});

// ── Init ──────────────────────────────────────────────────────────────
initDates();
loadFilters();
queryData();

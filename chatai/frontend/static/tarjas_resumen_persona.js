// tarjas_resumen_persona.js — Worker summary pivot table

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0
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

// ── Load filters ──────────────────────────────────────────────────────
async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/resumen-persona/filters');
    const data = await res.json();

    const sel = document.getElementById('fil-trabajador');
    sel.innerHTML = '<option value="">Todos</option>' +
      data.trabajadores.map(t =>
        `<option value="${esc(t.trabajador)}">${esc(t.trabajador)}</option>`
      ).join('');

    const selContratista = document.getElementById('fil-contratista');
    selContratista.innerHTML = '<option value="">Todos</option>' +
      data.contratistas.map(c =>
        `<option value="${esc(c)}">${esc(c)}</option>`
      ).join('');

    const selEmpresa = document.getElementById('fil-empresa');
    selEmpresa.innerHTML = '<option value="">Todas</option>' +
      data.empresas.map(e =>
        `<option value="${esc(e)}">${esc(e)}</option>`
      ).join('');

    const selTipo = document.getElementById('fil-tipo');
    selTipo.innerHTML = '<option value="">Todos</option>' +
      data.tipos_pago.map(t =>
        `<option value="${esc(t)}">${esc(t)}</option>`
      ).join('');
  } catch (e) {
    console.error('Error loading filters:', e);
  }
}

// ── Query & render ────────────────────────────────────────────────────
async function queryData() {
  const from = document.getElementById('fil-from').value;
  const to   = document.getElementById('fil-to').value;
  if (!from || !to) return;

  const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });

  const vTrab = document.getElementById('fil-trabajador').value;
  const vContratista = document.getElementById('fil-contratista').value;
  const vTipo = document.getElementById('fil-tipo').value;
  const vEmp = document.getElementById('fil-empresa').value;
  if (vTrab) params.append('trabajador', vTrab);
  if (vContratista) params.append('contratista', vContratista);
  if (vTipo) params.append('tipo_pago', vTipo);
  if (vEmp) params.append('empresa', vEmp);

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';
  let _hasData = false;

  try {
    const res = await fetch('/api/tarjas/resumen-persona?' + params);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (!data.rows.length) {
      document.getElementById('pivot-section').style.display = 'none';
      document.getElementById('empty-state').style.display = 'block';
      return;
    }

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

// ── Pivot table ───────────────────────────────────────────────────────
function renderPivot(rows) {
  // Unique sorted dates
  const dates = [...new Set(rows.map(r => r.fecha))].sort();

  // Group by worker → tipo_pago → { dates }
  const workers = new Map();
  rows.forEach(r => {
    const w = r.trabajador ?? '(sin nombre)';
    if (!workers.has(w)) workers.set(w, new Map());
    const tipos = workers.get(w);
    if (!tipos.has(r.tipo_pago)) tipos.set(r.tipo_pago, { byDate: {}, total: 0 });
    const entry = tipos.get(r.tipo_pago);
    entry.byDate[r.fecha] = (entry.byDate[r.fecha] || 0) + Number(r.total_trabajado || 0);
    entry.total += Number(r.total_trabajado || 0);
  });

  // Sort workers by total descending
  const sortedWorkers = [...workers.entries()]
    .map(([name, tipos]) => {
      let grandTotal = 0;
      tipos.forEach(e => { grandTotal += e.total; });
      return { name, tipos, grandTotal };
    })
    .sort((a, b) => b.grandTotal - a.grandTotal);

  // Build thead
  const thead = document.getElementById('pivot-thead');
  let superHdr = '<tr class="trp-superheader">';
  superHdr += '<th class="th-empty" colspan="2"></th>';
  superHdr += `<th colspan="${dates.length}">fecha (Fecha) / total_trabajado</th>`;
  superHdr += '<th class="th-empty"></th>';
  superHdr += '</tr>';

  let hdr = '<tr>';
  hdr += '<th class="th-fixed">trabajador</th>';
  hdr += '<th class="th-fixed">tipo_pago</th>';
  dates.forEach(d => { hdr += `<th class="th-date">${formatShortDate(d)}</th>`; });
  hdr += '<th class="th-total">Total</th>';
  hdr += '</tr>';

  thead.innerHTML = superHdr + hdr;

  // Build tbody
  const tbody = document.getElementById('pivot-tbody');
  let html = '';

  sortedWorkers.forEach(w => {
    const tipoEntries = [...w.tipos.entries()];
    let isFirst = true;

    tipoEntries.forEach(([tipo, entry]) => {
      const rowClass = isFirst ? 'worker-first' : '';
      const workerCell = isFirst ? esc(w.name) : '';
      isFirst = false;

      html += `<tr class="${rowClass}">`;
      html += `<td class="cell-worker" title="${esc(w.name)}">${workerCell}</td>`;
      html += `<td class="cell-tipo">${esc(tipo)}</td>`;

      dates.forEach(d => {
        const val = entry.byDate[d];
        if (val && val > 0) {
          html += `<td class="cell-value has-value">${fmtCLP.format(val)}</td>`;
        } else {
          html += '<td class="cell-zero">0</td>';
        }
      });

      html += `<td class="cell-total">${fmtCLP.format(entry.total)}</td>`;
      html += '</tr>';
    });
  });

  tbody.innerHTML = html;
}

// ── Download helpers ──────────────────────────────────────────────────
function currentParams() {
  const from = document.getElementById('fil-from').value;
  const to   = document.getElementById('fil-to').value;
  const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });
  const vTrab = document.getElementById('fil-trabajador').value;
  const vContratista = document.getElementById('fil-contratista').value;
  const vTipo = document.getElementById('fil-tipo').value;
  const vEmp = document.getElementById('fil-empresa').value;
  if (vTrab) params.append('trabajador', vTrab);
  if (vContratista) params.append('contratista', vContratista);
  if (vTipo) params.append('tipo_pago', vTipo);
  if (vEmp) params.append('empresa', vEmp);
  return params;
}

function setDownloadEnabled(on) {
  document.getElementById('btn-excel').disabled = !on;
  document.getElementById('btn-pdf').disabled = !on;
}

function downloadExcel() {
  const params = currentParams();
  window.location.href = '/api/tarjas/resumen-persona/download-excel?' + params;
}

function downloadPdf() {
  window.open('/api/tarjas/resumen-persona/download-pdf?' + currentParams(), '_blank');
}

function printWithHeader(title, filters) {
  const chips = Object.entries(filters)
    .filter(([,v]) => v)
    .map(([k,v]) => '<span class="ph-chip"><strong>' + esc(k) + ':</strong> ' + esc(v) + '</span>')
    .join('');
  const now = new Date().toLocaleDateString('es-CL', { day:'2-digit', month:'long', year:'numeric' });
  const html = '<div class="ph-top">'
    + '<img class="ph-logo" src="/static/img/donar_logo.png" alt="Empresas Donar" />'
    + '<div class="ph-title-block">'
    + '<h2>' + esc(title) + '</h2>'
    + '<p class="ph-subtitle">Generado el ' + now + '</p>'
    + '</div></div>'
    + '<div class="ph-filters">' + chips + '</div>';
  const el = document.getElementById('print-header');
  el.innerHTML = html;
  window.print();
  window.addEventListener('afterprint', function cleanup() {
    el.innerHTML = '';
    window.removeEventListener('afterprint', cleanup);
  });
}

// ── URL filter sync ───────────────────────────────────────────────────
const FILTER_IDS = ['fil-from', 'fil-to', 'fil-trabajador', 'fil-contratista', 'fil-tipo', 'fil-empresa'];

async function loadFiltersAndRestore() {
  initDates();
  await loadFilters();
  autoTriggerFromURL(FILTER_IDS, queryData);
}

// ── Events ────────────────────────────────────────────────────────────
document.getElementById('btn-apply').addEventListener('click', () => {
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
});
document.getElementById('btn-excel').addEventListener('click', downloadExcel);
document.getElementById('btn-pdf').addEventListener('click', downloadPdf);

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') queryData().then(() => syncFiltersToURL(FILTER_IDS)); });
});

bindPopstate(FILTER_IDS, queryData);

// ── Init ──────────────────────────────────────────────────────────────
loadFiltersAndRestore();

// tarjas_jornadas_trabajador.js — Jornadas por trabajador report

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function toISO(d) { return d.toISOString().slice(0, 10); }

// ── Init dates (current week) ─────────────────────────────────────────
function initDates() {
  const now = new Date();
  const day = now.getDay();
  const monday = new Date(now);
  monday.setDate(now.getDate() - (day === 0 ? 6 : day - 1));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  document.getElementById('fil-from').value = toISO(monday);
  document.getElementById('fil-to').value   = toISO(sunday);
}

// ── Load filters ──────────────────────────────────────────────────────
async function loadFilters() {
  try {
    const res  = await fetch('/api/tarjas/jornadas-trabajador/filters');
    const data = await res.json();

    const selC = document.getElementById('fil-contratista');
    selC.innerHTML = '<option value="">Todos</option>' +
      data.contratistas.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');

    const selE = document.getElementById('fil-empresa');
    selE.innerHTML = '<option value="">Todas</option>' +
      data.empresas.map(e => `<option value="${esc(e)}">${esc(e)}</option>`).join('');
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
  const vC = document.getElementById('fil-contratista').value;
  const vE = document.getElementById('fil-empresa').value;
  if (vC) params.append('contratista', vC);
  if (vE) params.append('empresa', vE);

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';
  let hasData = false;

  try {
    const res = await fetch('/api/tarjas/jornadas-trabajador?' + params);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (!data.rows.length) {
      document.getElementById('table-section').style.display = 'none';
      document.getElementById('empty-state').style.display = 'block';
      return;
    }

    document.getElementById('empty-state').style.display = 'none';
    renderTable(data.rows);
    document.getElementById('table-section').style.display = '';
    hasData = true;
  } catch (e) {
    console.error('Query error:', e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Consultar';
    setDownloadEnabled(hasData);
  }
}

// ── Render table ──────────────────────────────────────────────────────
function renderTable(rows) {
  const tbody = document.getElementById('data-tbody');
  const tfoot = document.getElementById('data-tfoot');

  let html = '';
  let total = 0;
  rows.forEach(r => {
    const j = Number(r.jornadas || 0);
    total += j;
    html += `<tr>
      <td class="cell-worker">${esc(r.trabajador ?? '')}</td>
      <td>${esc(r.contratista ?? '')}</td>
      <td class="cell-total">${j}</td>
    </tr>`;
  });
  tbody.innerHTML = html;

  tfoot.innerHTML = `<tr class="trp-grand-total">
    <td><strong>Suma total</strong></td>
    <td></td>
    <td class="cell-total"><strong>${total}</strong></td>
  </tr>`;
}

// ── Download helpers ──────────────────────────────────────────────────
function currentParams() {
  const from = document.getElementById('fil-from').value;
  const to   = document.getElementById('fil-to').value;
  const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });
  const vC = document.getElementById('fil-contratista').value;
  const vE = document.getElementById('fil-empresa').value;
  if (vC) params.append('contratista', vC);
  if (vE) params.append('empresa', vE);
  return params;
}

function setDownloadEnabled(on) {
  document.getElementById('btn-excel').disabled = !on;
  document.getElementById('btn-pdf').disabled   = !on;
}

function downloadExcel() {
  window.location.href = '/api/tarjas/jornadas-trabajador/download-excel?' + currentParams();
}

function downloadPdf() {
  window.open('/api/tarjas/jornadas-trabajador/download-pdf?' + currentParams(), '_blank');
}

// ── URL filter sync ───────────────────────────────────────────────────
const FILTER_IDS = ['fil-from', 'fil-to', 'fil-contratista', 'fil-empresa'];

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
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter') queryData().then(() => syncFiltersToURL(FILTER_IDS));
  });
});

bindPopstate(FILTER_IDS, queryData);

// ── Init ──────────────────────────────────────────────────────────────
loadFiltersAndRestore();

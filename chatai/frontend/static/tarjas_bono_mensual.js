// tarjas_bono_mensual.js — Bonos mensuales report

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0
});

function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtDate(iso) {
  if (!iso) return '';
  const [y, m, d] = String(iso).split('-');
  return `${d}/${m}/${y}`;
}

// ── Init mes (current month) ─────────────────────────────────────────
function initMes() {
  const now = new Date();
  const mes = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  document.getElementById('fil-mes').value = mes;
}

// ── Load filter dropdowns ────────────────────────────────────────────
async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/bono-mensual/filters');
    const data = await res.json();
    fillSelect('fil-contratista', data.contratistas, 'Todos');
    fillSelect('fil-empresa', data.empresas, 'Todas');
    fillSelect('fil-campo', data.campos, 'Todos');
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
function currentParams() {
  const mes = document.getElementById('fil-mes').value;
  const params = new URLSearchParams({ mes });
  const add = (key, id) => { const v = document.getElementById(id)?.value; if (v) params.append(key, v); };
  add('contratista', 'fil-contratista');
  add('empresa', 'fil-empresa');
  add('campo', 'fil-campo');
  return params;
}

async function queryData() {
  const mes = document.getElementById('fil-mes').value;
  if (!mes) return;

  const params = currentParams();
  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';
  let hasData = false;

  try {
    const res = await fetch('/api/tarjas/bono-mensual?' + params);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (!data.rows.length) {
      document.getElementById('table-section').style.display = 'none';
      document.getElementById('empty-state').style.display = 'block';
      return;
    }

    document.getElementById('empty-state').style.display = 'none';
    renderTable(data.rows, data.count, data.total);
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
function renderTable(rows, count, total) {
  document.getElementById('row-count').textContent = `${count} registro${count !== 1 ? 's' : ''}`;

  const tbody = document.getElementById('data-tbody');
  tbody.innerHTML = rows.map(r => `<tr>
    <td>${esc(r.trabajador ?? '')}</td>
    <td>${esc(r.rut_trabajador ?? '')}</td>
    <td>${esc(r.contratista ?? '')}</td>
    <td>${esc(r.nombre_campo ?? '')}</td>
    <td>${esc(r.cc ?? '')}</td>
    <td>${fmtDate(r.fecha)}</td>
    <td class="num">${fmtCLP.format(r.monto || 0)}</td>
    <td>${esc(r.estado ?? '')}</td>
  </tr>`).join('');

  const tfoot = document.getElementById('data-tfoot');
  tfoot.innerHTML = `<tr>
    <td colspan="6"><strong>Suma total</strong></td>
    <td class="num"><strong>${fmtCLP.format(total || 0)}</strong></td>
    <td></td>
  </tr>`;
}

// ── Download helpers ──────────────────────────────────────────────────
function setDownloadEnabled(on) {
  document.getElementById('btn-excel').disabled = !on;
  document.getElementById('btn-pdf').disabled = !on;
}

function downloadExcel() {
  window.location.href = '/api/tarjas/bono-mensual/download-excel?' + currentParams();
}

function downloadPdf() {
  window.open('/api/tarjas/bono-mensual/download-pdf?' + currentParams(), '_blank');
}

// ── URL filter sync ───────────────────────────────────────────────────
const FILTER_IDS = ['fil-mes', 'fil-contratista', 'fil-empresa', 'fil-campo'];

async function loadFiltersAndRestore() {
  initMes();
  await loadFilters();
  autoTriggerFromURL(FILTER_IDS, queryData);
}

// ── Events ────────────────────────────────────────────────────────────
document.getElementById('btn-apply').addEventListener('click', () => {
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
});
document.getElementById('btn-excel').addEventListener('click', downloadExcel);
document.getElementById('btn-pdf').addEventListener('click', downloadPdf);

document.getElementById('fil-mes').addEventListener('keydown', e => {
  if (e.key === 'Enter') queryData().then(() => syncFiltersToURL(FILTER_IDS));
});

bindPopstate(FILTER_IDS, queryData);

// ── Init ──────────────────────────────────────────────────────────────
loadFiltersAndRestore();

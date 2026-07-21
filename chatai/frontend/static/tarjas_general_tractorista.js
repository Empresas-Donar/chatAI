// tarjas_general_tractorista.js — General tractorista overview

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

let chartInstance = null;

const CHART_COLORS = [
  '#3b82f6', '#f97316', '#8b5cf6', '#10b981', '#ef4444',
  '#06b6d4', '#f59e0b', '#ec4899', '#6366f1', '#14b8a6'
];

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

async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/general-tractorista/filters');
    const data = await res.json();
    fillSelect('fil-cc', data.centros_costo, 'Todos');
    fillSelect('fil-labor', data.labores, 'Todas');
    fillSelect('fil-contratista', data.contratistas, 'Todos');
    fillSelect('fil-empresa', data.empresas, 'Todas');
    if (data.maquinas && data.maquinas.length) {
      fillSelect('fil-maquina', data.maquinas, 'Todas');
      document.getElementById('maquina-filter-wrap').style.display = '';
    }
  } catch (e) {
    console.error('Error loading filters:', e);
  }
}

function fillSelect(id, items, defaultLabel) {
  const sel = document.getElementById(id);
  sel.innerHTML = `<option value="">${defaultLabel}</option>` +
    items.map(i => `<option value="${esc(String(i))}">${esc(String(i))}</option>`).join('');
}

async function queryData() {
  const from = document.getElementById('fil-from').value;
  const to   = document.getElementById('fil-to').value;
  if (!from || !to) return;

  const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });
  const add = (key, id) => {
    const v = document.getElementById(id)?.value;
    if (v) params.append(key, v);
  };
  add('centro_costo', 'fil-cc');
  add('labor', 'fil-labor');
  add('maquina', 'fil-maquina');
  add('contratista', 'fil-contratista');
  add('empresa', 'fil-empresa');

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';
  let _hasData = false;

  try {
    const res = await fetch('/api/tarjas/general-tractorista?' + params);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const hasData = data.labor_summary.length || data.person_ranking.length;
    if (!hasData) {
      hide('tables-section'); hide('chart-section');
      show('empty-state');
      return;
    }

    hide('empty-state');
    renderLaborTable(data.labor_summary);
    renderRanking(data.person_ranking);
    renderChart(data.chart_data);
    show('tables-section'); show('chart-section');
    _hasData = true;
  } catch (e) {
    console.error('Query error:', e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Consultar';
    setDownloadEnabled(_hasData);
  }
}

function show(id) { document.getElementById(id).style.display = ''; }
function hide(id) { document.getElementById(id).style.display = 'none'; }

function renderLaborTable(rows) {
  document.getElementById('labor-tbody').innerHTML = rows.map(r => `<tr>
    <td class="cell-labor" title="${esc(r.labor)}">${esc(r.labor)}</td>
    <td class="num">${fmtCLPDec.format(r.avg_rate)}</td>
    <td class="num">${fmtCLP.format(r.total)}</td>
  </tr>`).join('');
}

function renderRanking(rows) {
  document.getElementById('ranking-tbody').innerHTML = rows.map(r => `<tr>
    <td class="cell-worker" title="${esc(r.trabajador)}">${esc(r.trabajador)}</td>
    <td class="cell-contractor" title="${esc(r.contratista)}">${esc(r.contratista)}</td>
    <td class="num">${fmtCLPDec.format(r.avg_rate)}</td>
    <td class="num">${fmtCLP.format(r.total)}</td>
  </tr>`).join('');
}

function renderChart(data) {
  if (chartInstance) chartInstance.destroy();
  if (!data.length) return;

  const labors   = [...new Set(data.map(d => d.labor))];
  const workers  = [...new Set(data.map(d => d.trabajador))];
  const lookup   = {};
  data.forEach(d => {
    if (!lookup[d.labor]) lookup[d.labor] = {};
    lookup[d.labor][d.trabajador] = d.avg_daily;
  });

  const datasets = workers.map((w, i) => ({
    label: w,
    data: labors.map(l => lookup[l]?.[w] ?? 0),
    backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
    borderRadius: 3,
  }));

  const ctx = document.getElementById('chart-labor-cuadrilla').getContext('2d');
  chartInstance = new Chart(ctx, {
    type: 'bar',
    data: { labels: labors, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', labels: { font: { size: 12 }, boxWidth: 14, padding: 10 } },
        tooltip: { callbacks: { label: c => `${c.dataset.label}: ${fmtCLP.format(c.parsed.y)}` } }
      },
      scales: {
        x: { ticks: { font: { size: 11 }, maxRotation: 45 } },
        y: {
          beginAtZero: true,
          ticks: {
            callback: v => v >= 1000 ? (v / 1000).toFixed(0) + ' mil' : v,
            font: { size: 11 }
          }
        }
      }
    }
  });
}

function currentParams() {
  const p = new URLSearchParams({
    fecha_inicio: document.getElementById('fil-from').value,
    fecha_termino: document.getElementById('fil-to').value,
  });
  const add = (key, id) => { const v = document.getElementById(id)?.value; if (v) p.append(key, v); };
  add('centro_costo','fil-cc'); add('labor','fil-labor');
  add('maquina','fil-maquina'); add('contratista','fil-contratista');
  return p;
}
function setDownloadEnabled(on) {
  document.getElementById('btn-excel').disabled = !on;
  document.getElementById('btn-pdf').disabled = !on;
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
const FILTER_IDS = ['fil-from', 'fil-to', 'fil-cc', 'fil-labor', 'fil-maquina', 'fil-contratista', 'fil-empresa'];

async function loadFiltersAndRestore() {
  initDates();
  await loadFilters();
  loadFiltersFromURL(FILTER_IDS);
  queryData();
}

document.getElementById('btn-apply').addEventListener('click', () => {
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
});
document.getElementById('btn-excel').addEventListener('click', () => {
  window.location.href = '/api/tarjas/general-tractorista/download-excel?' + currentParams();
});
document.getElementById('btn-pdf').addEventListener('click', () => {
  window.open('/api/tarjas/general-tractorista/download-pdf?' + currentParams(), '_blank');
});

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') queryData().then(() => syncFiltersToURL(FILTER_IDS)); });
});

bindPopstate(FILTER_IDS, queryData);

loadFiltersAndRestore();

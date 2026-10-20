// cosecha_detalle.js — Harvest yield. Money is rendered from the API.
// Piece rate and daily floor are not Costo Empresa factors.

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0,
});
const fmtNum = new Intl.NumberFormat('es-CL');
const fmtRate = new Intl.NumberFormat('es-CL', {
  minimumFractionDigits: 1, maximumFractionDigits: 1,
});

const FILTER_IDS = [
  'fil-from', 'fil-to', 'fil-contratista', 'fil-empresa',
  'fil-cuartel', 'fil-cuadrilla', 'fil-cultivo',
];

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fmtDate(iso) {
  if (!iso || iso.length < 10) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
}

function fmtMoney(v) {
  return v == null ? '—' : fmtCLP.format(v);
}

function cell(value, numeric) {
  const cls = numeric ? ' class="num"' : '';
  return `<td${cls}>${value}</td>`;
}

function currentParams() {
  const params = new URLSearchParams({
    fecha_inicio: document.getElementById('fil-from').value,
    fecha_termino: document.getElementById('fil-to').value,
  });
  const add = (key, id) => {
    const v = document.getElementById(id)?.value;
    if (v) params.append(key, v);
  };
  add('empresa', 'fil-empresa');
  add('contratista', 'fil-contratista');
  add('cuartel', 'fil-cuartel');
  add('cuadrilla', 'fil-cuadrilla');
  add('cultivo', 'fil-cultivo');
  return params;
}

function setDownloadEnabled(on) {
  document.getElementById('btn-excel').disabled = !on;
}

let harvestCatalog = { empresas: [], contratistas: [] };

function foldName(value) {
  return String(value || '').normalize('NFD').replace(/\p{M}/gu, '').toUpperCase().trim();
}

function matchedHarvestValue(current, options) {
  const want = foldName(current);
  if (!want) return '';
  const exact = options.find(option => foldName(option) === want);
  if (exact) return exact;
  const hits = options.filter(option => {
    const name = foldName(option);
    return name.length >= 3 && (want.includes(name) || name.includes(want));
  });
  return hits.length === 1 ? hits[0] : '';
}

function fillHarvestSelect(id, options, emptyLabel) {
  const sel = document.getElementById(id);
  if (!sel) return;
  const next = matchedHarvestValue(sel.value, options);
  fillSelectOptions(sel, options, emptyLabel);
  sel.value = next;
}

function applyHarvestSelects() {
  fillHarvestSelect('fil-empresa', harvestCatalog.empresas, 'Todas');
  fillHarvestSelect('fil-contratista', harvestCatalog.contratistas, 'Todos');
}

const _tarjasFilters = (() => {
  try {
    return JSON.parse(localStorage.getItem('donar.globalFilters') || '{}') || {};
  } catch (_) {
    return {};
  }
})();

if (typeof saveGlobalFilters === 'function') {
  const _saveGlobalFilters = saveGlobalFilters;
  saveGlobalFilters = function () {
    _saveGlobalFilters();
    try {
      const data = JSON.parse(localStorage.getItem('donar.globalFilters') || '{}') || {};
      data['fil-empresa'] = _tarjasFilters['fil-empresa'] || '';
      data['fil-contratista'] = _tarjasFilters['fil-contratista'] || '';
      localStorage.setItem('donar.globalFilters', JSON.stringify(data));
    } catch (_) { /* private mode */ }
  };
}

if (typeof loadFiltersFromURL === 'function') {
  const _loadFiltersFromURL = loadFiltersFromURL;
  loadFiltersFromURL = function (ids) {
    const found = _loadFiltersFromURL(ids);
    if (harvestCatalog.empresas.length || harvestCatalog.contratistas.length) {
      applyHarvestSelects();
    }
    return found;
  };
}

async function fetchFilterOptions(empresa) {
  const res = await fetch('/api/cosecha/detalle/filters?' + new URLSearchParams({
    empresa: empresa || '',
    contratista: document.getElementById('fil-contratista')?.value || '',
    fecha_inicio: document.getElementById('fil-from')?.value || '',
    fecha_termino: document.getElementById('fil-to')?.value || '',
  }));
  if (!res.ok) return null;
  return res.json();
}

async function loadFilters() {
  const selectedEmpresa = document.getElementById('fil-empresa')?.value || '';
  try {
    let data = await fetchFilterOptions(selectedEmpresa);
    if (!data) return;
    const empresas = data.empresas || [];
    const empresa = matchedHarvestValue(selectedEmpresa, empresas);
    if (foldName(selectedEmpresa) !== foldName(empresa)) {
      const scoped = await fetchFilterOptions(empresa);
      if (scoped) data = scoped;
    }
    harvestCatalog = {
      empresas: data.empresas || empresas,
      contratistas: data.contratistas || [],
    };
    applyHarvestSelects();
    fillSelectOptions(document.getElementById('fil-cuartel'), data.cuarteles || [], 'Todos');
    fillSelectOptions(
      document.getElementById('fil-cuadrilla'),
      (data.cuadrillas || []).map(String),
      'Todas',
    );
    fillSelectOptions(document.getElementById('fil-cultivo'), data.cultivos || [], 'Todos');
  } catch (err) {
    console.error('Error loading cosecha filters:', err);
  }
}

function renderCards(totales) {
  document.getElementById('card-capachos').textContent = fmtNum.format(totales.capachos || 0);
  document.getElementById('card-trabajadores').textContent = fmtNum.format(totales.trabajadores || 0);
  document.getElementById('card-rendimiento').textContent = totales.capachos_persona == null
    ? '—'
    : fmtRate.format(totales.capachos_persona);
  document.getElementById('card-trato').textContent = fmtMoney(totales.trato);
  document.getElementById('card-pagar').textContent = fmtMoney(totales.a_pagar);
}

function renderResumen(rows, totales) {
  const body = document.getElementById('resumen-tbody');
  body.innerHTML = rows.map(r => `<tr>
    ${cell(esc(fmtDate(r.fecha)))}
    ${cell(esc(r.predio))}
    ${cell(esc(r.contratista || '—'))}
    ${cell(esc(r.cuadrilla ?? '—'), true)}
    ${cell(esc(r.cuartel || '—'))}
    ${cell(esc(r.cultivo || '—'))}
    ${cell(esc(r.variedad || '—'))}
    ${cell(fmtNum.format(r.trabajadores || 0), true)}
    ${cell(fmtNum.format(r.capachos || 0), true)}
    ${cell(r.capachos_persona == null ? '—' : fmtRate.format(r.capachos_persona), true)}
    ${cell(fmtNum.format(r.bins || 0), true)}
    ${cell(fmtMoney(r.trato), true)}
    ${cell(fmtMoney(r.a_pagar), true)}
  </tr>`).join('');
  document.getElementById('resumen-count').textContent =
    `${fmtNum.format(rows.length)} día${rows.length === 1 ? '' : 's'}`;
  document.getElementById('resumen-tfoot').innerHTML = `<tr>
    <td colspan="7">Total</td>
    <td class="num">${fmtNum.format(totales.trabajadores || 0)}</td>
    <td class="num">${fmtNum.format(totales.capachos || 0)}</td>
    <td class="num">${totales.capachos_persona == null ? '—' : fmtRate.format(totales.capachos_persona)}</td>
    <td></td>
    <td class="num">${fmtMoney(totales.trato)}</td>
    <td class="num">${fmtMoney(totales.a_pagar)}</td>
  </tr>`;
}

function renderDetail(rows, totales) {
  const body = document.getElementById('detail-tbody');
  body.innerHTML = rows.map(r => `<tr>
    ${cell(esc(fmtDate(r.fecha)))}
    ${cell(esc(r.cuadrilla ?? '—'), true)}
    ${cell(esc(r.trabajador || '—'))}
    ${cell(esc(r.cuartel || '—'))}
    ${cell(esc(r.variedad || '—'))}
    ${cell(fmtNum.format(r.capachos || 0), true)}
    ${cell(fmtMoney(r.precio), true)}
    ${cell(fmtMoney(r.trato), true)}
    ${cell(fmtMoney(r.piso), true)}
    ${cell(fmtMoney(r.a_pagar), true)}
  </tr>`).join('');
  document.getElementById('detail-count').textContent =
    `${fmtNum.format(rows.length)} registro${rows.length === 1 ? '' : 's'}`;
  document.getElementById('detail-tfoot').innerHTML = `<tr>
    <td colspan="5">Total</td>
    <td class="num">${fmtNum.format(totales.capachos || 0)}</td>
    <td></td>
    <td class="num">${fmtMoney(totales.trato)}</td>
    <td></td>
    <td class="num">${fmtMoney(totales.a_pagar)}</td>
  </tr>`;
}

function showEmpty(hint, from, to) {
  document.getElementById('summary-cards').style.display = 'none';
  document.getElementById('resumen-section').style.display = 'none';
  document.getElementById('detail-section').style.display = 'none';
  const text = document.getElementById('empty-text');
  if (hint && hint.capachos) {
    const span = hint.desde === hint.hasta
      ? fmtDate(hint.desde)
      : `${fmtDate(hint.desde)} – ${fmtDate(hint.hasta)}`;
    text.textContent =
      `No hay capachos entre el ${fmtDate(from)} y el ${fmtDate(to)}. ` +
      `Con estos filtros hay ${fmtNum.format(hint.capachos)} capachos el ${span}.`;
  } else {
    text.textContent = 'No hay capachos para la empresa, el contratista y las fechas seleccionadas.';
  }
  document.getElementById('empty-state').style.display = 'block';
}

async function queryData() {
  const from = document.getElementById('fil-from').value;
  const to = document.getElementById('fil-to').value;
  if (!from || !to) return;

  let hasData = false;
  try {
    const res = await fetch('/api/cosecha/detalle?' + currentParams());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const rows = data.rows || [];
    if (!rows.length) {
      showEmpty(data.hint, from, to);
      return;
    }
    document.getElementById('empty-state').style.display = 'none';
    renderCards(data.totales || {});
    renderResumen(data.resumen || [], data.totales || {});
    renderDetail(rows, data.totales || {});
    document.getElementById('summary-cards').style.display = '';
    document.getElementById('resumen-section').style.display = '';
    document.getElementById('detail-section').style.display = '';
    hasData = true;
  } catch (err) {
    console.error('Query error:', err);
    showEmpty(null, from, to);
    document.getElementById('empty-text').textContent = 'No se pudo cargar el reporte.';
  } finally {
    setDownloadEnabled(hasData);
  }
}

document.getElementById('btn-apply').addEventListener('click', () => {
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
});
document.getElementById('btn-excel').addEventListener('click', () => {
  window.location.href = '/api/cosecha/detalle/download-excel?' + currentParams();
});

bindPopstate(FILTER_IDS, queryData);

async function start() {
  if (window.globalFiltersReady) await window.globalFiltersReady;
  await loadFilters();
  autoTriggerFromURL(FILTER_IDS, queryData);
}

['fil-empresa', 'fil-contratista', 'fil-from', 'fil-to'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', loadFilters);
});
start();

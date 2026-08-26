// tarjas_registros_campo.js — App field-record audit timeline
// UI dates: DD/MM/YYYY

const PAGE_SIZE = 100;
const FILTER_IDS = [
  'fil-from', 'fil-to', 'fil-empresa', 'fil-labor',
  'fil-estado', 'fil-contratista', 'fil-supervisor',
];

const FLAG_LABELS = {
  missing_labor: 'Sin labor',
  missing_campo: 'Sin campo',
  missing_trabajador: 'Sin trabajador',
  missing_estado: 'Sin estado',
  unexpected_estado: 'Estado inesperado',
  invalid_fecha: 'Fecha inválida',
  missing_supervisor: 'Sin supervisor',
  bad_rut: 'RUT mal digitado',
  double_space_name: 'Nombre con espacios dobles',
  name_has_digits: 'Nombre con números',
  implausible_horas_extra: 'Horas extra improbables',
  hours_and_extras: 'Horas y extras a la vez',
  implausible_hours: 'Horas trabajadas improbables',
};

const DETAIL_FIELDS = [
  ['rut_trabajador', 'RUT'],
  ['horas_trabajadas', 'Horas trabajadas'],
  ['horas_extras', 'Horas extras'],
  ['rendimiento', 'Rendimiento'],
  ['valor_jornada', 'Valor jornada'],
  ['valor_trato', 'Valor trato'],
  ['base_trato', 'Base trato'],
  ['total_jornada', 'Total jornada'],
  ['total_trato', 'Total trato'],
  ['total_trabajado', 'Total trabajado'],
  ['total_hora_extra', 'Total hora extra'],
  ['total_pagar', 'Total a pagar'],
  ['contratista_jornada', 'Contratista jornada'],
  ['contratista_trato', 'Contratista trato'],
  ['total_contratista', 'Total contratista'],
  ['maquina', 'Máquina'],
  ['total_tractor', 'Total tractor'],
  ['id_Resumen', 'ID resumen'],
  ['id_tarja_supervisor', 'ID tarja supervisor'],
  ['id_labor', 'ID labor'],
  ['fecha', 'Fecha original'],
];

let loadedRows = [];
let totalRows = 0;
let currentOffset = 0;

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function pad2(n) {
  return String(n).padStart(2, '0');
}

function toISO(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

// UI dates: DD/MM/YYYY
function fmtDateDisplay(iso) {
  const s = String(iso || '').slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return iso || 'Sin fecha';
  return `${m[3]}/${m[2]}/${m[1]}`;
}

function fmtValue(v) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v.toLocaleString('es-CL');
  }
  return esc(v);
}

const MAL_DIGITADO_FLAGS = new Set([
  'bad_rut', 'double_space_name', 'name_has_digits',
  'implausible_horas_extra', 'hours_and_extras', 'implausible_hours',
]);
const EDITABLE_FIELDS = new Set([
  'trabajador', 'rut_trabajador', 'horas_trabajadas', 'horas_extras',
]);

function isAlertFlag(flags) {
  return flags.includes('invalid_fecha') || flags.includes('unexpected_estado');
}

function isMalDigitado(row) {
  if (row && row.mal_digitado) return true;
  const flags = Array.isArray(row && row.flags) ? row.flags : [];
  return flags.some(f => MAL_DIGITADO_FLAGS.has(f));
}

function apiDetail(data, status) {
  const d = data && data.detail;
  if (typeof d === 'string' && d) return d;
  if (Array.isArray(d) && d.length) {
    return d.map(x => (x && x.msg) ? x.msg : String(x)).join('; ');
  }
  return 'HTTP ' + status;
}

function initDates() {
  const to = new Date();
  const from = new Date();
  from.setDate(to.getDate() - 6);
  document.getElementById('fil-from').value = toISO(from);
  document.getElementById('fil-to').value = toISO(to);
}

function fillSelect(id, values, emptyLabel) {
  const sel = document.getElementById(id);
  const current = sel.value;
  sel.innerHTML = `<option value="">${emptyLabel}</option>` +
    values.map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
  if (current) sel.value = current;
}

async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/registros-campo/filters');
    const data = await res.json();
    fillSelect('fil-empresa', data.empresas || [], 'Todas');
    fillSelect('fil-labor', data.labores || [], 'Todas');
    fillSelect('fil-estado', data.estados || [], 'Todos');
    fillSelect('fil-contratista', data.contratistas || [], 'Todos');
    fillSelect('fil-supervisor', data.supervisores || [], 'Todos');
  } catch (e) {
    console.error('Error loading filters:', e);
  }
}

function currentParams(offset) {
  const from = document.getElementById('fil-from').value;
  const to = document.getElementById('fil-to').value;
  const params = new URLSearchParams({
    fecha_inicio: from,
    fecha_termino: to,
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  const vE = document.getElementById('fil-empresa').value;
  const vL = document.getElementById('fil-labor').value;
  const vS = document.getElementById('fil-estado').value;
  const vC = document.getElementById('fil-contratista').value;
  const vU = document.getElementById('fil-supervisor').value;
  if (vE) params.append('empresa', vE);
  if (vL) params.append('labor', vL);
  if (vS) params.append('estado', vS);
  if (vC) params.append('contratista', vC);
  if (vU) params.append('supervisor', vU);
  return params;
}

function setBusy(on, label) {
  const btn = document.getElementById('btn-apply');
  const more = document.getElementById('btn-more');
  btn.disabled = on;
  more.disabled = on;
  btn.textContent = on ? (label || 'Cargando…') : 'Consultar';
}

function setDownloadEnabled(on) {
  document.getElementById('btn-excel').disabled = !on;
}

function estadoBadge(estado) {
  const raw = String(estado || '').trim();
  if (!raw) return '<span class="trc-badge trc-badge-unknown">Sin estado</span>';
  const key = raw.toLowerCase();
  let cls = 'trc-badge-unknown';
  if (key === 'aprobado') cls = 'trc-badge-ok';
  else if (key === 'pendiente') cls = 'trc-badge-pending';
  return `<span class="trc-badge ${cls}">${esc(raw)}</span>`;
}

function flagBadges(flags) {
  if (!flags.length) return '';
  if (isAlertFlag(flags)) {
    return '<span class="trc-badge trc-badge-alert">Revisar</span>';
  }
  return '<span class="trc-badge trc-badge-flag">Incompleto</span>';
}

function groupByDate(rows) {
  const groups = [];
  const map = new Map();
  rows.forEach(r => {
    const key = String(r.fecha_iso || '').slice(0, 10) || 'sin-fecha';
    if (!map.has(key)) {
      const g = { date: key, rows: [] };
      map.set(key, g);
      groups.push(g);
    }
    map.get(key).rows.push(r);
  });
  return groups;
}

function renderCard(r, idx) {
  const flags = Array.isArray(r.flags) ? r.flags : [];
  const alert = isAlertFlag(flags);
  const flagged = flags.length > 0;
  const cls = [
    'trc-card',
    alert ? 'is-alert' : '',
    flagged && !alert ? 'is-flagged' : '',
    isMalDigitado(r) ? 'is-bad is-open' : '',
  ].filter(Boolean).join(' ');
  const labor = r.labor || 'Sin labor';
  const flagText = flags.map(f => FLAG_LABELS[f] || f).join(' · ');

  const warnKeys = new Set();
  if (flags.includes('bad_rut')) warnKeys.add('rut_trabajador');
  if (flags.includes('double_space_name') || flags.includes('name_has_digits') || flags.includes('missing_trabajador')) warnKeys.add('trabajador');
  if (flags.includes('implausible_horas_extra')) warnKeys.add('horas_extras');
  if (flags.includes('hours_and_extras')) {
    warnKeys.add('horas_trabajadas');
    warnKeys.add('horas_extras');
  }
  if (flags.includes('implausible_hours')) warnKeys.add('horas_trabajadas');
  if (flags.includes('missing_campo')) warnKeys.add('nombre_campo');
  if (flags.includes('missing_supervisor')) warnKeys.add('id_supervisor');
  if (flags.includes('invalid_fecha')) warnKeys.add('fecha');

  const details = DETAIL_FIELDS.map(([key, label]) => {
    const warn = warnKeys.has(key);
    const canEdit = isMalDigitado(r) && EDITABLE_FIELDS.has(key);
    const raw = r[key];
    const dd = canEdit
      ? `<input class="trc-edit" data-field="${esc(key)}" value="${raw === null || raw === undefined ? '' : esc(raw)}" />`
      : fmtValue(raw);
    return `<dt class="${warn ? 'is-warn' : ''}">${esc(label)}</dt><dd class="${warn ? 'is-warn' : ''}">${dd}</dd>`;
  }).join('');

  const extraEdits = [];
  if (isMalDigitado(r)) {
    ['trabajador', 'rut_trabajador'].forEach(key => {
      if (DETAIL_FIELDS.some(([k]) => k === key)) return;
      const raw = r[key];
      extraEdits.push(
        `<dt class="is-warn">${esc(key === 'trabajador' ? 'Trabajador' : 'RUT')}</dt>` +
        `<dd class="is-warn"><input class="trc-edit" data-field="${esc(key)}" value="${raw === null || raw === undefined ? '' : esc(raw)}" /></dd>`
      );
    });
  }

  function metaSpan(label, key, value) {
    const warn = warnKeys.has(key);
    return `<span${warn ? ' class="trc-meta-warn"' : ''}>${esc(label)} <strong>${esc(value || '—')}</strong></span>`;
  }

  const saveBar = isMalDigitado(r)
    ? `<div class="trc-save-row">
        <button type="button" class="btn btn-primary btn-sm" data-save-rec="${esc(r.id_Resumen || '')}">Guardar corrección</button>
        <span class="trc-save-msg" hidden></span>
      </div>`
    : '';

  return `<article class="${cls}" data-idx="${idx}">
    <div class="trc-card-top">
      <h3 class="trc-card-title">${esc(labor)}</h3>
      <div class="trc-card-badges">
        ${estadoBadge(r.estado)}
        ${isMalDigitado(r) ? '<span class="trc-badge trc-badge-bad">Mal digitado</span>' : flagBadges(flags)}
      </div>
    </div>
    <div class="trc-meta-line">
      ${metaSpan('Supervisor', 'id_supervisor', r.id_supervisor)}
      ${metaSpan('Campo', 'nombre_campo', r.nombre_campo)}
      ${metaSpan('Trabajador', 'trabajador', r.trabajador)}
      <span>Contratista <strong>${esc(r.contratista || '—')}</strong></span>
      <span>Pago <strong>${esc(r.tipo_pago || '—')}</strong></span>
      <span>CC <strong>${esc(r.cuartel_cc || '—')}</strong></span>
    </div>
    ${flagText ? `<div class="trc-flag-list">${esc(flagText)}</div>` : ''}
    <button type="button" class="trc-expand" data-toggle="${idx}">${isMalDigitado(r) ? 'Ocultar detalle' : 'Ver detalle'}</button>
    <div class="trc-payload">
      <dl class="trc-dl">${extraEdits.join('')}${details}</dl>
      ${saveBar}
    </div>
  </article>`;
}

function renderTimeline() {
  const root = document.getElementById('timeline');
  const groups = groupByDate(loadedRows);
  let html = '';
  let idx = 0;
  groups.forEach(g => {
    const label = g.date === 'sin-fecha' ? 'Sin fecha' : fmtDateDisplay(g.date);
    html += `<section class="trc-day">
      <div class="trc-day-head">
        <span class="trc-day-date">${esc(label)}</span>
        <span class="trc-day-count">${g.rows.length} registro${g.rows.length === 1 ? '' : 's'}</span>
      </div>
      ${g.rows.map(r => renderCard(r, idx++)).join('')}
    </section>`;
  });
  root.innerHTML = html;
}

function renderMeta() {
  const el = document.getElementById('meta-bar');
  const flagged = loadedRows.filter(r => (r.flags || []).length).length;
  el.style.display = '';
  el.textContent =
    `Mostrando ${loadedRows.length} de ${totalRows} registros` +
    (flagged ? ` · ${flagged} con alertas visuales` : '');
}

function showEmpty(on) {
  document.getElementById('empty-state').style.display = on ? 'block' : 'none';
}

function showLoading(on) {
  document.getElementById('loading-state').style.display = on ? 'block' : 'none';
}

function updateLoadMore() {
  const wrap = document.getElementById('load-more-wrap');
  const hasMore = loadedRows.length < totalRows;
  wrap.style.display = hasMore ? 'flex' : 'none';
}

async function fetchPage(reset) {
  const from = document.getElementById('fil-from').value;
  const to = document.getElementById('fil-to').value;
  if (!from || !to) return;

  if (reset) {
    currentOffset = 0;
    loadedRows = [];
    showEmpty(false);
    document.getElementById('timeline').style.display = 'none';
    document.getElementById('meta-bar').style.display = 'none';
    document.getElementById('load-more-wrap').style.display = 'none';
    showLoading(true);
  }

  setBusy(true);
  let hasData = false;
  try {
    const res = await fetch('/api/tarjas/registros-campo?' + currentParams(currentOffset));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    totalRows = data.total || 0;
    const rows = data.rows || [];
    loadedRows = reset ? rows : loadedRows.concat(rows);
    currentOffset = loadedRows.length;
    showLoading(false);

    if (!loadedRows.length) {
      document.getElementById('timeline').style.display = 'none';
      showEmpty(true);
      setDownloadEnabled(false);
      return;
    }

    showEmpty(false);
    renderTimeline();
    renderMeta();
    document.getElementById('timeline').style.display = '';
    updateLoadMore();
    hasData = true;
  } catch (e) {
    console.error('Query error:', e);
    showLoading(false);
    if (!loadedRows.length) showEmpty(true);
  } finally {
    setBusy(false);
    setDownloadEnabled(hasData || loadedRows.length > 0);
  }
}

function queryData() {
  return fetchPage(true);
}

function downloadExcel() {
  const params = currentParams(0);
  params.delete('limit');
  params.delete('offset');
  window.location.href = '/api/tarjas/registros-campo/download-excel?' + params;
}

async function saveTimelineRegistro(id, card) {
  const msg = card.querySelector('.trc-save-msg');
  const btn = card.querySelector('[data-save-rec]');
  const fields = {};
  card.querySelectorAll('.trc-edit').forEach(inp => {
    const key = inp.getAttribute('data-field');
    if (key && EDITABLE_FIELDS.has(key)) fields[key] = inp.value;
  });
  if (!id || !Object.keys(fields).length) return;
  if (btn) { btn.disabled = true; btn.textContent = 'Guardando…'; }
  if (msg) { msg.hidden = false; msg.textContent = ''; }
  try {
    const res = await fetch(
      '/api/tarjas/registros-campo/' + encodeURIComponent(id),
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fields }),
      }
    );
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(apiDetail(data, res.status));
    }
    const row = data.row;
    const idx = loadedRows.findIndex(r => String(r.id_Resumen) === String(id));
    if (idx >= 0 && row) loadedRows[idx] = row;
    renderTimeline();
    renderMeta();
  } catch (e) {
    console.error(e);
    if (btn) { btn.disabled = false; btn.textContent = 'Guardar corrección'; }
    if (msg) msg.textContent = e.message || 'No se pudo guardar.';
  }
}

async function loadFiltersAndRestore() {
  initDates();
  await loadFilters();
  if (location.search) {
    autoTriggerFromURL(FILTER_IDS, queryData);
  } else {
    queryData();
  }
}

document.getElementById('btn-apply').addEventListener('click', () => {
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
});
document.getElementById('btn-excel').addEventListener('click', downloadExcel);
document.getElementById('btn-more').addEventListener('click', () => fetchPage(false));

document.getElementById('timeline').addEventListener('click', (e) => {
  const saveBtn = e.target.closest('[data-save-rec]');
  if (saveBtn) {
    const card = saveBtn.closest('.trc-card');
    if (card) saveTimelineRegistro(saveBtn.getAttribute('data-save-rec'), card);
    return;
  }
  const btn = e.target.closest('[data-toggle]');
  if (!btn) return;
  const card = btn.closest('.trc-card');
  if (!card) return;
  const open = card.classList.toggle('is-open');
  btn.textContent = open ? 'Ocultar detalle' : 'Ver detalle';
});
document.getElementById('timeline').addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  if (!e.target.classList.contains('trc-edit')) return;
  e.preventDefault();
  const card = e.target.closest('.trc-card');
  const btn = card && card.querySelector('[data-save-rec]');
  if (btn) saveTimelineRegistro(btn.getAttribute('data-save-rec'), card);
});

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter') queryData().then(() => syncFiltersToURL(FILTER_IDS));
  });
});

bindPopstate(FILTER_IDS, queryData);
loadFiltersAndRestore();

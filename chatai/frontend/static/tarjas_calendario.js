// tarjas_calendario.js — App monthly calendar of field-record counts
// UI dates: DD/MM/YYYY

const FILTER_IDS = [
  'fil-month', 'fil-empresa', 'fil-labor',
  'fil-estado', 'fil-contratista', 'fil-supervisor',
];

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0,
});
// Money comes from tarjas_empresa.total_empresa() on the API.
// Do not apply Costo Empresa factors in the browser.

const WEEKDAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const PAGO_KINDS = [
  { id: 'trato', label: 'Trato' },
  { id: 'al_dia', label: 'Al día' },
  { id: 'tractorista', label: 'Tractorista' },
  { id: 'otro', label: 'Otros' },
];
const MONTHS = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
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

const MAL_DIGITADO_FLAGS = new Set([
  'bad_rut', 'double_space_name', 'name_has_digits',
  'implausible_horas_extra', 'hours_and_extras', 'implausible_hours',
]);

const EDITABLE_FIELDS = new Set([
  'trabajador', 'rut_trabajador', 'horas_trabajadas', 'horas_extras',
]);

const FLAG_TO_FIELD = {
  bad_rut: 'rut_trabajador',
  double_space_name: 'trabajador',
  name_has_digits: 'trabajador',
  implausible_horas_extra: 'horas_extras',
  hours_and_extras: ['horas_trabajadas', 'horas_extras'],
  implausible_hours: 'horas_trabajadas',
  missing_labor: 'labor',
  missing_campo: 'nombre_campo',
  missing_trabajador: 'trabajador',
  missing_estado: 'estado',
  unexpected_estado: 'estado',
  missing_supervisor: 'id_supervisor',
  invalid_fecha: 'fecha',
};

const FIELD_LABELS = {
  labor: 'Labor',
  rut_trabajador: 'RUT',
  trabajador: 'Trabajador',
  horas_extras: 'Horas extras',
  horas_trabajadas: 'Horas trabajadas',
  nombre_campo: 'Campo',
  estado: 'Estado',
  id_supervisor: 'Supervisor',
  fecha: 'Fecha',
};

const DETAIL_FIELDS = [
  ['total_empresa', 'Donar · Costo Empresa'],
  ['recargo', 'Recargo'],
  ['total_trabajado', 'Precio trabajador'],
  ['labor', 'Labor'],
  ['estado', 'Estado'],
  ['trabajador', 'Trabajador'],
  ['rut_trabajador', 'RUT'],
  ['contratista', 'Contratista'],
  ['nombre_campo', 'Campo'],
  ['cuartel_cc', 'Cuartel / CC'],
  ['id_supervisor', 'Supervisor'],
  ['tipo_pago', 'Tipo de pago'],
  ['horas_trabajadas', 'Horas trabajadas'],
  ['horas_extras', 'Horas extras'],
  ['rendimiento', 'Rendimiento'],
  ['valor_jornada', 'Valor jornada'],
  ['valor_trato', 'Valor trato'],
  ['total_jornada', 'Total jornada'],
  ['total_trato', 'Total trato'],
  ['total_hora_extra', 'Total hora extra'],
  ['maquina', 'Máquina'],
  ['total_tractor', 'Total tractor'],
  ['id_Resumen', 'ID resumen'],
  ['id_labor', 'ID labor'],
  ['fecha', 'Fecha original'],
];

const WEEKDAY_NAMES = [
  'domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado',
];

let dayRows = [];
let dayPlanes = [];
let monthContratistas = new Map();
let openContratistas = new Set();
let openFecha = null;
let panelTab = 'aplicados';
let panelLoading = false;
let dayRequestId = 0;
let syncingPanel = false;

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function pad2(n) {
  return String(n).padStart(2, '0');
}

function toMonthValue(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`;
}

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function fmtInt(n) {
  return Number(n || 0).toLocaleString('es-CL');
}

function fmtDateDisplay(iso) {
  const s = String(iso || '').slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return iso || 'Sin fecha';
  return `${m[3]}/${m[2]}/${m[1]}`;
}

function fmtMoney(v) {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return esc(v);
  return fmtCLP.format(n);
}

function costoEmpresa(row) {
  return Number(row && row.total_empresa) || 0;
}

function precioTrabajador(row) {
  return Number(row && row.total_trabajado) || 0;
}

function recargoLabel(row) {
  const v = row && row.recargo;
  if (!v || v === '—') return '';
  return String(v);
}

function isAprobado(row) {
  return String(row && row.estado || '').trim().toLowerCase() === 'aprobado';
}

function pagoKind(tipo) {
  const k = String(tipo || '').trim().toLowerCase()
    .normalize('NFD').replace(/\p{M}/gu, '');
  if (k === 'al dia') return 'al_dia';
  if (k === 'trato') return 'trato';
  if (k === 'tractorista') return 'tractorista';
  return 'otro';
}

function emptyKindBag() {
  return { trato: 0, al_dia: 0, tractorista: 0, otro: 0 };
}

function fmtValue(v) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v.toLocaleString('es-CL');
  }
  return esc(v);
}

function weekdayTitle(iso) {
  const s = String(iso || '').slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return fmtDateDisplay(iso);
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const name = WEEKDAY_NAMES[d.getDay()] || '';
  return `${name} ${fmtDateDisplay(iso)}`;
}

function addDaysISO(iso, delta) {
  const s = String(iso || '').slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return iso;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + delta);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function daysBetween(startIso, endIso) {
  const a = Date.parse(`${String(startIso).slice(0, 10)}T12:00:00`);
  const b = Date.parse(`${String(endIso).slice(0, 10)}T12:00:00`);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return 1;
  return Math.max(1, Math.round((b - a) / 86400000) + 1);
}

function initMonth() {
  const el = document.getElementById('fil-month');
  if (!el) return;
  el.value = toMonthValue(new Date());
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
    fillSelect('fil-labor', data.labores || [], 'Todas');
    fillSelect('fil-estado', data.estados || [], 'Todos');
    fillSelect('fil-supervisor', data.supervisores || [], 'Todos');
  } catch (e) {
    console.error('Error loading filters:', e);
  }
}

function currentParams() {
  const mes = document.getElementById('fil-month').value;
  const params = new URLSearchParams({ mes });
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

function heatClass(count, max) {
  if (!count || !max) return '';
  const ratio = count / max;
  if (ratio >= 0.8) return 'heat-5';
  if (ratio >= 0.6) return 'heat-4';
  if (ratio >= 0.4) return 'heat-3';
  if (ratio >= 0.2) return 'heat-2';
  return 'heat-1';
}

function buildMonthCells(year, month) {
  const first = new Date(year, month - 1, 1);
  const startOffset = (first.getDay() + 6) % 7;
  const start = new Date(year, month - 1, 1 - startOffset);
  const cells = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    cells.push({
      iso: `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`,
      day: d.getDate(),
      inMonth: d.getMonth() === month - 1,
    });
  }
  const lastInMonth = cells.map((c, i) => (c.inMonth ? i : -1)).reduce((a, b) => Math.max(a, b), 0);
  const weeks = Math.ceil((lastInMonth + 1) / 7);
  return cells.slice(0, weeks * 7);
}

function renderCalendar(data) {
  const mes = data.mes || document.getElementById('fil-month').value;
  const [year, month] = mes.split('-').map(Number);
  const byDate = new Map((data.days || []).map(d => [d.fecha, d]));
  const max = data.max || 0;
  const today = todayISO();
  const cells = buildMonthCells(year, month);

  let html = `<div class="tcal-title">${MONTHS[month - 1]} ${year}</div>`;
  html += '<div class="tcal-grid">';
  WEEKDAYS.forEach(w => { html += `<div class="tcal-dow">${w}</div>`; });
  cells.forEach(cell => {
    const info = byDate.get(cell.iso);
    const total = info ? info.total : 0;
    const planes = info ? (info.planes || 0) : 0;
    const sospechosos = info ? (info.sospechosos || 0) : 0;
    const cls = [
      'tcal-day',
      cell.inMonth ? '' : 'is-outside',
      total ? 'has-data' : '',
      planes && !total ? 'has-plan' : '',
      total || planes ? 'is-clickable' : '',
      heatClass(total, max),
      cell.iso === today ? 'is-today' : '',
      cell.iso === openFecha ? 'is-open' : '',
    ].filter(Boolean).join(' ');
    const split = info && (info.pendiente || info.aprobado)
      ? `<div class="tcal-split">${fmtInt(info.aprobado)} apr. · ${fmtInt(info.pendiente)} pend.</div>`
      : '';
    const count = total
      ? `<div class="tcal-count">${fmtInt(total)}</div>${split}`
      : '';
    const planChip = planes
      ? `<div class="tcal-plans">${fmtInt(planes)} plan${planes === 1 ? '' : 'es'}</div>`
      : '';
    const warn = sospechosos
      ? `<div class="tcal-suspect">${fmtInt(sospechosos)} mal digitado${sospechosos === 1 ? '' : 's'}</div>`
      : '';
    const href = (total || planes) ? ` data-fecha="${esc(cell.iso)}"` : '';
    html += `<div class="${cls}"${href}>
      <div class="tcal-day-num">${cell.day}</div>
      ${count}
      ${planChip}
      ${warn}
    </div>`;
  });
  html += '</div>';
  document.getElementById('calendar').innerHTML = html;
}

function renderMeta(data) {
  const el = document.getElementById('meta-bar');
  el.style.display = '';
  const suspect = data.sospechosos || 0;
  el.innerHTML =
    `<span><strong>${fmtInt(data.total || 0)}</strong> registros en el mes</span>` +
    `<span><span class="tcal-dot tcal-dot-plan"></span><strong>${fmtInt(data.planes || 0)}</strong> planes (rango)</span>` +
    `<span><span class="tcal-dot tcal-dot-ok"></span>${fmtInt(data.aprobado || 0)} aprobados</span>` +
    `<span><span class="tcal-dot tcal-dot-pend"></span>${fmtInt(data.pendiente || 0)} pendientes</span>` +
    (suspect
      ? `<span><span class="tcal-dot" style="background:#991b1b"></span>${fmtInt(suspect)} mal digitados</span>`
      : '');
}

function setBusy(on) {
  document.getElementById('btn-apply').disabled = on;
  document.getElementById('btn-prev').disabled = on;
  document.getElementById('btn-next').disabled = on;
  document.getElementById('btn-apply').textContent = on ? 'Cargando…' : 'Consultar';
}

async function queryData() {
  const mes = document.getElementById('fil-month').value;
  if (!mes) return;

  const emptyEl = document.getElementById('empty-state');
  const emptyTitle = emptyEl.querySelector('h3');
  const emptyP = emptyEl.querySelector('p');
  emptyEl.style.display = 'none';
  document.getElementById('calendar').style.display = 'none';
  document.getElementById('meta-bar').style.display = 'none';
  document.getElementById('loading-state').style.display = 'block';
  setBusy(true);

  try {
    const res = await fetch('/api/tarjas/calendario?' + currentParams(), {
      cache: 'no-store',
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(apiDetail(data, res.status));
    }
    monthContratistas = new Map(
      (data.contratistas || []).map(c => [c.contratista, c])
    );
    document.getElementById('loading-state').style.display = 'none';
    renderMeta(data);
    renderCalendar(data);
    document.getElementById('calendar').style.display = '';
    const empty = !data.total && !data.planes;
    if (empty) {
      emptyTitle.textContent = 'Sin actividad';
      emptyP.textContent = 'No hay planificación ni registros para los filtros seleccionados en este mes.';
    }
    emptyEl.style.display = empty ? 'block' : 'none';
  } catch (e) {
    console.error('Query error:', e);
    document.getElementById('loading-state').style.display = 'none';
    emptyTitle.textContent = 'No se pudo cargar el calendario';
    emptyP.textContent = e.message || 'Error de red o del servidor.';
    emptyEl.style.display = 'block';
  } finally {
    setBusy(false);
  }
}

function shiftMonth(delta) {
  const raw = document.getElementById('fil-month').value;
  if (!raw) return;
  const [y, m] = raw.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  document.getElementById('fil-month').value = toMonthValue(d);
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
}

function estadoBadge(estado) {
  const raw = String(estado || '').trim();
  if (!raw) return '<span class="tcal-badge tcal-badge-unknown">Sin estado</span>';
  const key = raw.toLowerCase();
  let cls = 'tcal-badge-unknown';
  if (key === 'aprobado') cls = 'tcal-badge-ok';
  else if (key === 'pendiente') cls = 'tcal-badge-pending';
  return `<span class="tcal-badge ${cls}">${esc(raw)}</span>`;
}

function apiDetail(data, status) {
  const d = data && data.detail;
  if (typeof d === 'string' && d) return d;
  if (Array.isArray(d) && d.length) {
    return d.map(x => (x && x.msg) ? x.msg : String(x)).join('; ');
  }
  return 'HTTP ' + status;
}

function isMalDigitado(row) {
  if (!row || typeof row !== 'object') return false;
  if (row.mal_digitado) return true;
  const flags = Array.isArray(row.flags) ? row.flags : [];
  return flags.some(f => MAL_DIGITADO_FLAGS.has(f));
}

function groupByContratista(rows) {
  const map = new Map();
  rows.forEach(r => {
    const key = String(r.contratista || '').trim() || 'Sin contratista';
    if (!map.has(key)) {
      map.set(key, {
        name: key,
        rows: [],
        facturar: 0,
        pendiente: 0,
        trab: 0,
        trabPendiente: 0,
        byKind: emptyKindBag(),
        byKindTrab: emptyKindBag(),
        nKind: emptyKindBag(),
        recargoByKind: {},
        maquinas: [],
      });
    }
    const g = map.get(key);
    g.rows.push(r);
    const amt = costoEmpresa(r);
    const trab = precioTrabajador(r);
    const kind = pagoKind(r.tipo_pago);
    g.nKind[kind] += 1;
    if (isAprobado(r)) {
      g.facturar += amt;
      g.trab += trab;
    } else {
      g.pendiente += amt;
      g.trabPendiente += trab;
    }
    g.byKind[kind] += amt;
    g.byKindTrab[kind] += trab;
    const recargo = recargoLabel(r);
    if (recargo && !g.recargoByKind[kind]) g.recargoByKind[kind] = recargo;
    const maq = String(r.maquina || '').trim();
    if (kind === 'tractorista' && maq && !g.maquinas.includes(maq)) {
      g.maquinas.push(maq);
    }
  });
  return [...map.values()].sort((a, b) =>
    b.facturar - a.facturar || b.pendiente - a.pendiente || a.name.localeCompare(b.name, 'es')
  );
}

function renderMixBar(byKind, nKind, recargoByKind, byKindTrab) {
  const parts = PAGO_KINDS.map(k => ({
    id: k.id,
    label: k.label,
    amount: Number(byKind[k.id]) || 0,
    trab: Number(byKindTrab && byKindTrab[k.id]) || 0,
    n: Number(nKind && nKind[k.id]) || 0,
    recargo: recargoByKind && recargoByKind[k.id],
  }));
  const total = parts.reduce((s, p) => s + p.amount, 0);
  if (total <= 0) return '';
  const segs = parts.filter(p => p.amount > 0).map(p => {
    const pct = (p.amount / total) * 100;
    return `<span class="tcal-mix-seg is-${p.id}" style="width:${pct.toFixed(2)}%" title="${esc(p.label)} ${fmtMoney(p.amount)}"></span>`;
  }).join('');
  const legend = parts.filter(p => p.amount > 0).map(p => {
    const pct = Math.round((p.amount / total) * 100);
    const count = p.n ? ` · ${fmtInt(p.n)}` : '';
    const recargo = p.recargo ? ` ${esc(p.recargo)}` : '';
    const trab = p.trab
      ? ` trab. ${fmtMoney(p.trab)} → Donar ${fmtMoney(p.amount)}`
      : ` ${fmtMoney(p.amount)}`;
    return `<span class="tcal-mix-item is-${p.id}"><span class="tcal-mix-swatch"></span>${esc(p.label)}${recargo}${trab} (${pct}%${count})</span>`;
  }).join('');
  return `<div class="tcal-mix">
    <div class="tcal-mix-bar" role="img" aria-label="Mix de Costo Empresa">${segs}</div>
    <div class="tcal-mix-legend">${legend}</div>
  </div>`;
}

function dayKindTotals(rows) {
  const byKind = emptyKindBag();
  const byKindTrab = emptyKindBag();
  const nKind = emptyKindBag();
  const recargoByKind = {};
  rows.forEach(r => {
    const kind = pagoKind(r.tipo_pago);
    byKind[kind] += costoEmpresa(r);
    byKindTrab[kind] += precioTrabajador(r);
    nKind[kind] += 1;
    const recargo = recargoLabel(r);
    if (recargo && !recargoByKind[kind]) recargoByKind[kind] = recargo;
  });
  return { byKind, byKindTrab, nKind, recargoByKind };
}

function setPanelTab(tab) {
  panelTab = tab === 'planificados' ? 'planificados' : 'aplicados';
  document.querySelectorAll('.tcal-tab').forEach(btn => {
    const on = btn.getAttribute('data-tab') === panelTab;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  document.getElementById('day-panel-toolbar').hidden = panelTab !== 'aplicados';
  renderDayRecords();
}

function updateTabCounts() {
  const solo = document.getElementById('fil-solo-sospechosos').checked;
  const recCount = solo ? dayRows.filter(isMalDigitado).length : dayRows.length;
  document.getElementById('tab-count-app').textContent = fmtInt(recCount);
  document.getElementById('tab-count-plan').textContent = fmtInt(dayPlanes.length);
}

function renderDayRecords() {
  const body = document.getElementById('day-panel-body');
  updateTabCounts();
  try {
    if (panelTab === 'planificados') {
      body.innerHTML = renderPlanSection(dayPlanes);
      return;
    }
    const soloEl = document.getElementById('fil-solo-sospechosos');
    const solo = Boolean(soloEl && soloEl.checked);
    const rows = solo ? dayRows.filter(isMalDigitado) : dayRows.slice();
    rows.sort((a, b) => Number(isMalDigitado(b)) - Number(isMalDigitado(a)));
    body.innerHTML = renderRecordSection(rows, solo);
  } catch (e) {
    console.error('Render day panel:', e);
    body.innerHTML = `<p class="tcal-panel-hint">Error al mostrar el día: ${esc(e.message || e)}</p>`;
  }
}

function rangeBar(p, selectedIso) {
  const start = String(p.fecha_inicio || '').slice(0, 10);
  const end = String(p.fecha_fin || start).slice(0, 10);
  const sel = String(selectedIso || '').slice(0, 10);
  const span = daysBetween(start, end);
  let marker = 0;
  if (span <= 1) {
    marker = 50;
  } else {
    const offset = daysBetween(start, sel) - 1;
    marker = Math.max(0, Math.min(100, (offset / (span - 1)) * 100));
  }
  const rango = `${fmtDateDisplay(start)} – ${fmtDateDisplay(end)}`;
  return `<div class="tcal-range">
    <div class="tcal-range-track" title="${esc(rango)}">
      <div class="tcal-range-fill"></div>
      <div class="tcal-range-marker" style="left:${marker}%"></div>
    </div>
    <div class="tcal-range-labels">
      <span>Inicio ${esc(fmtDateDisplay(start))}</span>
      <span>${fmtInt(p.dias || span)} día${(p.dias || span) === 1 ? '' : 's'}</span>
      <span>Fin ${esc(fmtDateDisplay(end))}</span>
    </div>
  </div>`;
}

function renderPlanSection(planes) {
  if (!planes.length) {
    return `<p class="tcal-panel-hint">Sin planificación que cubra este día.</p>`;
  }
  const groups = new Map();
  planes.forEach(p => {
    const key = String(p.contratista || '').trim() || 'Sin contratista';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(p);
  });
  const blocks = [...groups.entries()].map(([name, list]) => {
    const cards = list.map(p => {
      const title = p.labor || p.comentario || 'Plan';
      const rango = `${fmtDateDisplay(p.fecha_inicio)} – ${fmtDateDisplay(p.fecha_fin)}`;
      const people = p.numero_personas
        ? `${fmtInt(p.numero_personas)} persona${Number(p.numero_personas) === 1 ? '' : 's'}`
        : '';
      const meta = [p.nombre_campo, people].filter(Boolean).join(' · ');
      return `<article class="tcal-rec tcal-rec-plan tcal-rec-compact">
        <div class="tcal-rec-top">
          <h3 class="tcal-rec-title">${esc(title)}</h3>
          <span class="tcal-badge tcal-badge-plan">${esc(rango)}</span>
        </div>
        ${meta ? `<div class="tcal-rec-line">${esc(meta)}</div>` : ''}
        ${p.comentario ? `<div class="tcal-rec-line">${esc(p.comentario)}</div>` : ''}
        ${rangeBar(p, openFecha)}
      </article>`;
    }).join('');
    return `<section class="tcal-contractor${openContratistas.has(name) ? ' is-open' : ''}" data-contratista="${esc(name)}">
      <button type="button" class="tcal-contractor-toggle" data-contratista-toggle aria-expanded="${openContratistas.has(name) ? 'true' : 'false'}">
        <span class="tcal-chevron" aria-hidden="true"></span>
        <div class="tcal-contractor-summary">
          <div class="tcal-contractor-name">${esc(name)}</div>
          <div class="tcal-contractor-meta">${fmtInt(list.length)} plan${list.length === 1 ? '' : 'es'}</div>
        </div>
      </button>
      <div class="tcal-contractor-body">${cards}</div>
    </section>`;
  }).join('');
  return `<p class="tcal-section-hint">Cada plan cubre un rango de fechas; el punto marca el día abierto.</p>${blocks}`;
}

function renderCompactCard(r, idx) {
  const allFlags = Array.isArray(r.flags) ? r.flags : [];
  const flags = allFlags.filter(f => MAL_DIGITADO_FLAGS.has(f));
  const bad = isMalDigitado(r);
  const reasonsByField = {};
  allFlags.forEach(f => {
    const mapped = FLAG_TO_FIELD[f];
    if (!mapped) return;
    const fields = Array.isArray(mapped) ? mapped : [mapped];
    fields.forEach(field => {
      if (!reasonsByField[field]) reasonsByField[field] = [];
      reasonsByField[field].push(FLAG_LABELS[f] || f);
    });
  });
  const badFieldNames = [...new Set(
    flags.flatMap(f => {
      const mapped = FLAG_TO_FIELD[f];
      if (!mapped) return [];
      const fields = Array.isArray(mapped) ? mapped : [mapped];
      return fields.map(field => FIELD_LABELS[field] || field);
    })
  )];
  const fieldChips = badFieldNames.map(name =>
    `<span class="tcal-flag">${esc(name)}</span>`
  ).join('');
  const hours = [];
  const hTrab = Number(r.horas_trabajadas);
  const hExtra = Number(r.horas_extras);
  if (Number.isFinite(hTrab) && hTrab > 0) hours.push(`${fmtValue(hTrab)} h`);
  if (Number.isFinite(hExtra) && hExtra > 0) hours.push(`${fmtValue(hExtra)} extra`);
  const recargo = r.recargo && r.recargo !== '—' ? r.recargo : '';
  const tipo = [r.tipo_pago, recargo].filter(Boolean).join(' ');
  const maq = pagoKind(r.tipo_pago) === 'tractorista'
    ? String(r.maquina || '').trim()
    : '';
  const meta = [r.trabajador, tipo, maq, hours.join(' · ')].filter(Boolean);
  const details = DETAIL_FIELDS.map(([key, label]) => {
    const reasons = reasonsByField[key] || [];
    const warn = reasons.length > 0;
    const why = warn
      ? `<span class="tcal-kv-why">${esc(reasons.join(' · '))}</span>`
      : '';
    const raw = r[key];
    const shown = (key === 'total_empresa' || key === 'total_trabajado')
      ? fmtMoney(raw)
      : ((raw === null || raw === undefined || raw === '')
        ? '—'
        : (typeof raw === 'number' && Number.isFinite(raw)
          ? raw.toLocaleString('es-CL')
          : esc(raw)));
    const canEdit = bad && EDITABLE_FIELDS.has(key);
    const valueAttr = (raw === null || raw === undefined) ? '' : esc(raw);
    const dd = canEdit
      ? `<input class="tcal-edit" data-field="${esc(key)}" value="${valueAttr}" />`
      : shown;
    return `<div class="tcal-kv${warn ? ' is-warn' : ''}${canEdit ? ' is-edit' : ''}">
      <dt>${esc(label)}${why}</dt>
      <dd>${dd}</dd>
    </div>`;
  }).join('');
  const saveBar = bad
    ? `<div class="tcal-save-row">
        <button type="button" class="btn btn-primary btn-sm" data-save-rec="${esc(r.id_Resumen || '')}">Guardar corrección</button>
        <span class="tcal-save-msg" hidden></span>
      </div>`
    : '';
  const expanded = bad ? ' is-expanded' : '';
  const tract = pagoKind(r.tipo_pago) === 'tractorista' ? ' is-tract' : '';
  return `<article class="tcal-rec tcal-rec-compact${bad ? ' is-bad' : ''}${tract}${expanded}" data-rec="${idx}" data-id="${esc(r.id_Resumen || '')}">
    <div class="tcal-rec-top">
      <h3 class="tcal-rec-title">${esc(r.labor || 'Sin labor')}</h3>
      <div class="tcal-rec-prices">
        <div class="tcal-price tcal-price-trab"><span>Trabajador</span>${fmtMoney(precioTrabajador(r))}</div>
        <div class="tcal-price tcal-price-donar"><span>Donar</span>${fmtMoney(costoEmpresa(r))}</div>
      </div>
    </div>
    <div class="tcal-rec-line">
      ${estadoBadge(r.estado)}
      ${bad ? ' <span class="tcal-badge tcal-badge-bad">Mal digitado</span>' : ''}
      <span>${meta.map(esc).join(' · ')}</span>
    </div>
    ${fieldChips ? `<div class="tcal-rec-flags">Campos: ${fieldChips}</div>` : ''}
    <dl class="tcal-rec-grid">${details}</dl>
    ${saveBar}
  </article>`;
}

function renderKindGroups(rows) {
  const buckets = new Map(PAGO_KINDS.map(k => [k.id, []]));
  rows.forEach(r => {
    const kind = pagoKind(r.tipo_pago);
    if (!buckets.has(kind)) buckets.set(kind, []);
    buckets.get(kind).push(r);
  });
  return PAGO_KINDS.map(k => {
    const list = buckets.get(k.id) || [];
    if (!list.length) return '';
    const sumEmp = list.reduce((s, r) => s + costoEmpresa(r), 0);
    const sumTrab = list.reduce((s, r) => s + precioTrabajador(r), 0);
    const recargo = recargoLabel(list.find(r => recargoLabel(r)) || {});
    const kindTitle = recargo ? `${k.label} ${recargo}` : k.label;
    const cards = list.map((r, idx) => renderCompactCard(r, idx)).join('');
    return `<div class="tcal-kind is-${k.id}">
      <div class="tcal-kind-head">
        <span class="tcal-kind-label">${esc(kindTitle)}</span>
        <span class="tcal-kind-meta">${fmtInt(list.length)} · trab. ${fmtMoney(sumTrab)} · Donar ${fmtMoney(sumEmp)}</span>
      </div>
      ${cards}
    </div>`;
  }).join('');
}

function renderRecordSection(rows, solo) {
  const emptyHint = solo
    ? 'No hay registros mal digitados este día.'
    : 'Sin labores aplicadas este día.';
  if (!rows.length) {
    return `<p class="tcal-panel-hint">${emptyHint}</p>`;
  }

  let facturar = 0;
  let pendiente = 0;
  let trab = 0;
  rows.forEach(r => {
    const amt = costoEmpresa(r);
    if (isAprobado(r)) {
      facturar += amt;
      trab += precioTrabajador(r);
    } else pendiente += amt;
  });
  const dayMix = dayKindTotals(rows);
  const groups = groupByContratista(rows);
  const bill = `<div class="tcal-bill">
    <div class="tcal-bill-card is-main">
      <div class="tcal-bill-label">Donar · Costo Empresa</div>
      <div class="tcal-bill-amount">${fmtMoney(facturar)}</div>
      <div class="tcal-bill-note">${fmtInt(rows.filter(isAprobado).length)} labores aprobadas · lo que paga Donar</div>
    </div>
    <div class="tcal-bill-card">
      <div class="tcal-bill-label">Precio trabajador</div>
      <div class="tcal-bill-amount">${fmtMoney(trab)}</div>
      <div class="tcal-bill-note">Base antes del recargo Trato / Al día</div>
    </div>
    <div class="tcal-bill-card">
      <div class="tcal-bill-label">Pendiente Donar</div>
      <div class="tcal-bill-amount">${fmtMoney(pendiente)}</div>
      <div class="tcal-bill-note">${fmtInt(rows.length - rows.filter(isAprobado).length)} labores</div>
    </div>
  </div>
  <div class="tcal-day-mix">
    <div class="tcal-bill-label">Mix del día · Costo Empresa</div>
    ${renderMixBar(dayMix.byKind, dayMix.nKind, dayMix.recargoByKind, dayMix.byKindTrab)}
  </div>`;

  const blocks = groups.map(g => {
    const n = g.rows.length;
    const mes = monthContratistas.get(g.name);
    const mesLine = mes
      ? `mes Donar ${fmtMoney(mes.total_empresa)} · trab. ${fmtMoney(mes.total_trabajado)}`
      : '';
    const meta = [
      `hoy ${fmtInt(n)} labor${n === 1 ? '' : 'es'}`,
      g.pendiente ? `pendiente Donar ${fmtMoney(g.pendiente)}` : '',
      mesLine,
    ].filter(Boolean).join(' · ');
    const tractChip = g.byKind.tractorista
      ? `<span class="tcal-tract-chip">Tractorista ${fmtMoney(g.byKind.tractorista)}</span>`
      : '';
    const maq = g.maquinas.length
      ? `<div class="tcal-contractor-maq">Máquinas: ${esc(g.maquinas.join(', '))}</div>`
      : '';
    const open = openContratistas.has(g.name);
    return `<section class="tcal-contractor${g.byKind.tractorista ? ' has-tract' : ''}${open ? ' is-open' : ''}" data-contratista="${esc(g.name)}">
      <button type="button" class="tcal-contractor-toggle" data-contratista-toggle aria-expanded="${open ? 'true' : 'false'}">
        <span class="tcal-chevron" aria-hidden="true"></span>
        <div class="tcal-contractor-summary">
          <div class="tcal-contractor-name">${esc(g.name)} ${tractChip}</div>
          <div class="tcal-contractor-meta">${esc(meta)}</div>
          ${renderMixBar(g.byKind, g.nKind, g.recargoByKind, g.byKindTrab)}
        </div>
        <div class="tcal-contractor-prices">
          <div class="tcal-price tcal-price-trab"><span>Trabajador</span>${fmtMoney(g.trab)}</div>
          <div class="tcal-price tcal-price-donar"><span>Donar · Costo Empresa</span>${fmtMoney(g.facturar)}</div>
        </div>
      </button>
      <div class="tcal-contractor-body">
        ${maq}
        ${renderKindGroups(g.rows)}
      </div>
    </section>`;
  }).join('');

  return `${bill}${blocks}`;
}

async function saveRegistro(id, article) {
  const msg = article.querySelector('.tcal-save-msg');
  const btn = article.querySelector('[data-save-rec]');
  const fields = {};
  article.querySelectorAll('.tcal-edit').forEach(inp => {
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
    const idx = dayRows.findIndex(r => String(r.id_Resumen) === String(id));
    if (idx >= 0 && row) dayRows[idx] = row;
    renderDayRecords();
  } catch (e) {
    console.error(e);
    if (btn) { btn.disabled = false; btn.textContent = 'Guardar corrección'; }
    if (msg) msg.textContent = e.message || 'No se pudo guardar.';
  }
}

function closeDayPanel() {
  openFecha = null;
  document.getElementById('day-panel').hidden = true;
  document.getElementById('day-overlay').hidden = true;
  document.body.style.overflow = '';
  document.querySelectorAll('.tcal-day.is-open').forEach(el => el.classList.remove('is-open'));
}

async function openDay(fecha, opts = {}) {
  const keepTab = Boolean(opts.keepTab);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha || '')) return;
  const req = ++dayRequestId;
  if (openFecha !== fecha) openContratistas.clear();
  openFecha = fecha;
  document.querySelectorAll('.tcal-day[data-fecha]').forEach(el => {
    el.classList.toggle('is-open', el.getAttribute('data-fecha') === fecha);
  });
  const panel = document.getElementById('day-panel');
  const overlay = document.getElementById('day-overlay');
  panel.hidden = false;
  overlay.hidden = false;
  document.body.style.overflow = 'hidden';
  syncingPanel = true;
  document.getElementById('pan-fecha').value = fecha;
  setTimeout(() => { syncingPanel = false; }, 0);
  document.getElementById('day-panel-title').textContent = weekdayTitle(fecha);
  document.getElementById('day-panel-sub').textContent = 'Cargando…';
  document.getElementById('day-panel-body').innerHTML = '<p class="tcal-panel-hint">Cargando…</p>';
  if (!keepTab) {
    const soloEl = document.getElementById('fil-solo-sospechosos');
    if (soloEl) soloEl.checked = false;
  }
  panelLoading = true;
  dayRows = [];
  dayPlanes = [];
  updateTabCounts();
  document.getElementById('day-panel-toolbar').hidden = panelTab !== 'aplicados';

  const month = fecha.slice(0, 7);
  const monthInput = document.getElementById('fil-month');
  if (!opts.fromPanelFilters && monthInput.value !== month) {
    monthInput.value = month;
    queryData().then(() => syncFiltersToURL(FILTER_IDS));
  }

  const recParams = new URLSearchParams({
    fecha_inicio: fecha,
    fecha_termino: fecha,
    limit: '500',
    offset: '0',
  });
  const planParams = new URLSearchParams({ fecha });
  const vE = document.getElementById('fil-empresa').value;
  const vL = document.getElementById('fil-labor').value;
  const vS = document.getElementById('fil-estado').value;
  const vC = document.getElementById('fil-contratista').value;
  const vU = document.getElementById('fil-supervisor').value;
  if (vE) { recParams.append('empresa', vE); planParams.append('empresa', vE); }
  if (vL) { recParams.append('labor', vL); planParams.append('labor', vL); }
  if (vS) recParams.append('estado', vS);
  if (vC) { recParams.append('contratista', vC); planParams.append('contratista', vC); }
  if (vU) recParams.append('supervisor', vU);

  try {
    const [recRes, planRes] = await Promise.all([
      fetch('/api/tarjas/registros-campo?' + recParams),
      fetch('/api/tarjas/calendario/planes?' + planParams),
    ]);
    if (req !== dayRequestId) return;
    if (!recRes.ok) throw new Error(`Registros HTTP ${recRes.status}`);
    if (!planRes.ok) throw new Error(`Planes HTTP ${planRes.status}`);
    const recData = await recRes.json();
    const planData = await planRes.json();
    if (req !== dayRequestId) return;
    dayRows = recData.rows || [];
    dayPlanes = planData.rows || [];
    const bad = dayRows.filter(isMalDigitado).length;
    const facturar = dayRows.reduce((s, r) => s + (isAprobado(r) ? costoEmpresa(r) : 0), 0);
    const trab = dayRows.reduce((s, r) => s + (isAprobado(r) ? precioTrabajador(r) : 0), 0);
    document.getElementById('day-panel-sub').textContent =
      `${fmtInt(dayRows.length)} aplicadas · Donar ${fmtCLP.format(facturar)} · trabajador ${fmtCLP.format(trab)} · ${fmtInt(bad)} mal digitados`;
    panelLoading = false;
    if (!keepTab) {
      panelTab = dayRows.length ? 'aplicados' : (dayPlanes.length ? 'planificados' : 'aplicados');
    }
    setPanelTab(panelTab);
  } catch (e) {
    if (req !== dayRequestId) return;
    console.error(e);
    panelLoading = false;
    document.getElementById('day-panel-sub').textContent = 'No se pudieron cargar los datos del día.';
    document.getElementById('day-panel-body').innerHTML =
      `<p class="tcal-panel-hint">Error al consultar el día${e && e.message ? `: ${esc(e.message)}` : '.'}</p>`;
  }
}

async function loadFiltersAndRestore() {
  if (window.globalFiltersReady) await window.globalFiltersReady;
  initMonth();
  await loadFilters();
  autoTriggerFromURL(
    FILTER_IDS.filter(id => id !== 'fil-month'),
    () => queryData().then(() => {
      if (openFecha) return openDay(openFecha, { keepTab: true });
    }),
  );
}

document.getElementById('btn-apply').addEventListener('click', () => {
  queryData().then(() => {
    syncFiltersToURL(FILTER_IDS);
    if (openFecha) openDay(openFecha, { keepTab: true });
  });
});
document.getElementById('btn-prev').addEventListener('click', () => shiftMonth(-1));
document.getElementById('btn-next').addEventListener('click', () => shiftMonth(1));
document.getElementById('fil-month').addEventListener('change', () => {
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
});

document.getElementById('calendar').addEventListener('click', (e) => {
  const cell = e.target.closest('[data-fecha]');
  if (!cell) return;
  openDay(cell.getAttribute('data-fecha'));
});

document.getElementById('day-panel-close').addEventListener('click', closeDayPanel);
document.getElementById('day-overlay').addEventListener('click', closeDayPanel);
document.getElementById('day-panel-body').addEventListener('click', (e) => {
  const toggle = e.target.closest('[data-contratista-toggle]');
  if (toggle) {
    const section = toggle.closest('.tcal-contractor');
    if (!section) return;
    const name = section.getAttribute('data-contratista') || '';
    const open = section.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) openContratistas.add(name);
    else openContratistas.delete(name);
    return;
  }
  const btn = e.target.closest('[data-save-rec]');
  if (btn) {
    const article = btn.closest('article');
    if (!article) return;
    saveRegistro(btn.getAttribute('data-save-rec'), article);
    return;
  }
  if (e.target.closest('.tcal-edit, button, input, select, a, label')) return;
  const rec = e.target.closest('.tcal-rec[data-id]');
  if (rec && !rec.classList.contains('tcal-rec-plan')) {
    rec.classList.toggle('is-expanded');
  }
});
document.getElementById('day-panel-body').addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  if (!e.target.classList.contains('tcal-edit')) return;
  e.preventDefault();
  const article = e.target.closest('article');
  const btn = article && article.querySelector('[data-save-rec]');
  if (btn) saveRegistro(btn.getAttribute('data-save-rec'), article);
});
document.getElementById('fil-solo-sospechosos').addEventListener('change', renderDayRecords);
document.getElementById('day-prev').addEventListener('click', () => {
  if (!openFecha) return;
  openDay(addDaysISO(openFecha, -1), { keepTab: true });
});
document.getElementById('day-next').addEventListener('click', () => {
  if (!openFecha) return;
  openDay(addDaysISO(openFecha, 1), { keepTab: true });
});
document.getElementById('pan-fecha').addEventListener('change', (e) => {
  if (syncingPanel) return;
  const fecha = e.target.value;
  if (!fecha || fecha === openFecha) return;
  openDay(fecha, { keepTab: true });
});
document.querySelectorAll('.tcal-tab').forEach(btn => {
  btn.addEventListener('click', () => setPanelTab(btn.getAttribute('data-tab')));
});
document.addEventListener('keydown', (e) => {
  if (document.getElementById('day-panel').hidden) return;
  if (e.key === 'Escape') closeDayPanel();
  if (e.key === 'ArrowLeft' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
    openDay(addDaysISO(openFecha, -1), { keepTab: true });
  }
  if (e.key === 'ArrowRight' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
    openDay(addDaysISO(openFecha, 1), { keepTab: true });
  }
});

bindPopstate(FILTER_IDS, queryData);
loadFiltersAndRestore();

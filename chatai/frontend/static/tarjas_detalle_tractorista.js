// tarjas_detalle_tractorista.js — Looker nested pivot (fecha × trabajador × labor)

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0
});

function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toISO(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatDate(iso) {
  if (!iso) return '—';
  const [y, m, d] = String(iso).slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
}

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

function applyFilterOptions(data) {
  if (!data) return;
  fillSelect('fil-contratista', data.contratistas, 'Todos');
  fillSelect('fil-empresa', data.empresas, 'Todas');
  fillSelect('fil-cc', data.centros_costo, 'Todos');
  fillSelect('fil-labor', data.labores, 'Todas');
}

async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/detalle-tractorista/filters');
    if (!res.ok) return;
    applyFilterOptions(await res.json());
  } catch (e) {
    console.error('Error loading filters:', e);
  }
}

function fillSelect(id, items, defaultLabel) {
  const sel = document.getElementById(id);
  if (!sel || !Array.isArray(items) || !items.length) return;
  const prev = sel.value;
  sel.innerHTML = '';
  sel.add(new Option(defaultLabel, ''));
  items.forEach(item => sel.add(new Option(String(item), String(item))));
  if (prev && [...sel.options].some(o => o.value === prev)) sel.value = prev;
}

async function queryData() {
  const from = document.getElementById('fil-from').value;
  const to   = document.getElementById('fil-to').value;
  if (!from || !to) return;

  const params = new URLSearchParams({
    fecha_inicio: from,
    fecha_termino: to,
  });

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
    const res = await fetch('/api/tarjas/detalle-tractorista?' + params);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (!data.pivots || !data.pivots.length) {
      document.getElementById('pivot-section').style.display = 'none';
      document.getElementById('empty-state').style.display = 'block';
      return;
    }

    document.getElementById('empty-state').style.display = 'none';
    applyFilterOptions(data.filter_options);
    if ((document.getElementById('fil-contratista')?.options.length || 0) <= 1) {
      await loadFilters();
    }
    renderPivots(data.pivots);
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

function parseCLP(raw) {
  const digits = String(raw ?? '').replace(/[^\d]/g, '');
  if (!digits) return null;
  return Number(digits);
}

async function fetchRetry(url, opts, tries = 3) {
  let last;
  for (let i = 0; i < tries; i++) {
    last = await fetch(url, opts);
    if (last.status !== 503) return last;
    if (i < tries - 1) {
      showSaveStatus('Reintentando guardar…', 'pending');
      await new Promise(r => setTimeout(r, 500 * (i + 1)));
    }
  }
  return last;
}

function showSaveStatus(msg, kind) {
  const el = document.getElementById('tdt-save-status');
  if (!el) return;
  el.hidden = false;
  el.className = 'tdt-save-status tdt-save-' + (kind || 'ok');
  el.textContent = msg;
}

function moneyCell(p, d, c) {
  const v = p.matrix[d][c.key];
  if (v == null) return '<td class="cell-empty"></td>';
  return `<td class="num tdt-cell-edit">
    <input class="tdt-monto" inputmode="numeric"
      data-contratista="${esc(p.contratista)}"
      data-fecha="${esc(d)}"
      data-trabajador="${esc(c.trabajador)}"
      data-labor="${esc(c.labor)}"
      data-original="${v}"
      value="${esc(fmtCLP.format(v))}" />
  </td>`;
}

function estadoSelect(p, d) {
  const current = p.date_estados?.[d] || 'Pendiente';
  const known = current === 'Pendiente' || current === 'Aprobado';
  const mixto = known ? '' : `<option value="" selected disabled>${esc(current)}</option>`;
  return `<td class="tdt-estado-cell">
    <select class="tdt-estado"
      data-contratista="${esc(p.contratista)}"
      data-fecha="${esc(d)}"
      data-original="${esc(known ? current : '')}">
      ${mixto}
      <option value="Pendiente"${current === 'Pendiente' ? ' selected' : ''}>Pendiente</option>
      <option value="Aprobado"${current === 'Aprobado' ? ' selected' : ''}>Aprobado</option>
    </select>
  </td>`;
}

function renderOnePivot(p) {
  const nCols = p.columns.length;
  if (!nCols) return '';

  const workerRow = p.workers.map(w =>
    `<th class="th-worker" colspan="${w.labores.length}">${esc(w.name)}</th>`
  ).join('');
  const laborRow = p.columns.map(c =>
    `<th class="th-labor">${esc(c.labor)}</th>`
  ).join('');

  const body = p.dates.map(d => {
    const cells = p.columns.map(c => moneyCell(p, d, c)).join('');
    const rowClass = (p.date_estados?.[d] === 'Aprobado') ? 'row-aprobado' : 'row-pendiente';
    return `<tr class="${rowClass}" data-fecha="${esc(d)}" data-contratista="${esc(p.contratista)}">
      <td class="cell-date">${formatDate(d)}</td>
      ${estadoSelect(p, d)}
      ${cells}
      <td class="num cell-total">${fmtCLP.format(p.date_totals[d])}</td>
    </tr>`;
  }).join('');

  const foot = p.columns.map(c =>
    `<td class="num">${fmtCLP.format(p.col_totals[c.key])}</td>`
  ).join('');

  return `
  <div class="tdt-pivot-wrap">
    <div class="tdt-pivot-scroll">
      <table class="tdt-pivot">
        <thead>
          <tr>
            <th class="th-fecha" rowspan="3">Fecha</th>
            <th class="th-estado" rowspan="3">Estado</th>
            <th class="th-contratista" colspan="${nCols}">${esc(p.contratista)}</th>
            <th class="th-total" rowspan="3">Total ${esc(p.contratista)}</th>
          </tr>
          <tr>${workerRow}</tr>
          <tr>${laborRow}</tr>
        </thead>
        <tbody>${body}</tbody>
        <tfoot>
          <tr>
            <td colspan="2">Suma total</td>
            ${foot}
            <td class="num cell-total">${fmtCLP.format(p.grand_total)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  </div>`;
}

function renderPivots(pivots) {
  document.getElementById('pivot-section').innerHTML = pivots.map(renderOnePivot).join('');
}

async function saveEstado(sel) {
  const estado = sel.value;
  if (!estado || estado === sel.dataset.original) return;
  sel.disabled = true;
  showSaveStatus('Guardando estado…', 'pending');
  try {
    const res = await fetchRetry('/api/tarjas/detalle-tractorista/fila', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contratista: sel.dataset.contratista,
        fecha: sel.dataset.fecha,
        estado,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    sel.dataset.original = estado;
    const tr = sel.closest('tr');
    if (tr) {
      tr.classList.toggle('row-aprobado', estado === 'Aprobado');
      tr.classList.toggle('row-pendiente', estado !== 'Aprobado');
    }
    showSaveStatus('Estado guardado', 'ok');
  } catch (e) {
    sel.value = sel.dataset.original || 'Pendiente';
    showSaveStatus('No se pudo guardar el estado: ' + e.message, 'err');
  } finally {
    sel.disabled = false;
  }
}

async function saveMonto(input) {
  const next = parseCLP(input.value);
  const prev = Number(input.dataset.original);
  if (next == null) {
    input.value = fmtCLP.format(prev);
    return;
  }
  if (next === prev) {
    input.value = fmtCLP.format(prev);
    return;
  }
  input.disabled = true;
  showSaveStatus('Guardando monto…', 'pending');
  try {
    const res = await fetchRetry('/api/tarjas/detalle-tractorista/celda', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contratista: input.dataset.contratista,
        fecha: input.dataset.fecha,
        trabajador: input.dataset.trabajador,
        labor: input.dataset.labor,
        total_tractor: next,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const delta = next - prev;
    input.dataset.original = String(next);
    input.value = fmtCLP.format(next);
    const td = input.closest('td');
    const tr = input.closest('tr');
    const tds = [...tr.children];
    const colIndex = tds.indexOf(td);
    const totalCell = tr.querySelector('td.cell-total');
    if (totalCell) {
      totalCell.textContent = fmtCLP.format(parseCLP(totalCell.textContent) + delta);
    }
    const table = input.closest('table');
    const footCells = [...table.querySelectorAll('tfoot tr td')];
    const laborFoot = footCells[colIndex - 1];
    if (laborFoot && !laborFoot.classList.contains('cell-total')) {
      laborFoot.textContent = fmtCLP.format(parseCLP(laborFoot.textContent) + delta);
    }
    const grand = table.querySelector('tfoot td.cell-total');
    if (grand) {
      grand.textContent = fmtCLP.format(parseCLP(grand.textContent) + delta);
    }
    showSaveStatus('Monto guardado', 'ok');
  } catch (e) {
    input.value = fmtCLP.format(prev);
    showSaveStatus('No se pudo guardar el monto: ' + e.message, 'err');
  } finally {
    input.disabled = false;
  }
}

document.getElementById('pivot-section').addEventListener('change', (e) => {
  if (e.target.classList.contains('tdt-estado')) saveEstado(e.target);
});
document.getElementById('pivot-section').addEventListener('focusin', (e) => {
  if (e.target.classList.contains('tdt-monto')) e.target.select();
});
document.getElementById('pivot-section').addEventListener('blur', (e) => {
  if (e.target.classList.contains('tdt-monto')) saveMonto(e.target);
}, true);
document.getElementById('pivot-section').addEventListener('keydown', (e) => {
  if (!e.target.classList.contains('tdt-monto')) return;
  if (e.key === 'Enter') {
    e.preventDefault();
    e.target.blur();
  }
  if (e.key === 'Escape') {
    e.target.value = fmtCLP.format(Number(e.target.dataset.original));
    e.target.blur();
  }
});

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
const FILTER_IDS = ['fil-from', 'fil-to', 'fil-contratista', 'fil-empresa', 'fil-cc', 'fil-labor'];

async function loadFiltersAndRestore() {
  initDates();
  await loadFilters();
  const params = new URLSearchParams(location.search);
  if (!params.get('fil-empresa') && params.get('fil-campo')) {
    params.set('fil-empresa', params.get('fil-campo'));
    params.delete('fil-campo');
    history.replaceState(null, '', `${location.pathname}?${params}`);
  }
  autoTriggerFromURL(FILTER_IDS, queryData);
}

document.getElementById('btn-apply').addEventListener('click', () => {
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
});
document.getElementById('btn-excel').addEventListener('click', () => {
  window.location.href = '/api/tarjas/detalle-tractorista/download-excel?' + currentParams();
});
document.getElementById('btn-pdf').addEventListener('click', () => {
  window.open('/api/tarjas/detalle-tractorista/download-pdf?' + currentParams(), '_blank');
});

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') queryData().then(() => syncFiltersToURL(FILTER_IDS)); });
});

bindPopstate(FILTER_IDS, queryData);

loadFiltersAndRestore();

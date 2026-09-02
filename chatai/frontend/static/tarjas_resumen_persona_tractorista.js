// tarjas_resumen_persona_tractorista.js — Tractorista worker × date pivot

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0
});

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function toISO(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatShortDate(isoStr) {
  if (!isoStr) return '—';
  const [y, m, d] = isoStr.slice(0, 10).split('-');
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

async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/resumen-persona-tractorista/filters');
    const data = await res.json();

    const selTrab = document.getElementById('fil-trabajador');
    selTrab.innerHTML = '<option value="">Todos</option>' +
      data.trabajadores.map(t =>
        `<option value="${esc(t.trabajador)}">${esc(t.trabajador)}</option>`
      ).join('');

    const selTipo = document.getElementById('fil-tipo');
    selTipo.innerHTML = '<option value="">Todos</option>' +
      data.tipos_pago.map(t =>
        `<option value="${esc(t)}">${esc(t)}</option>`
      ).join('');

    const selCont = document.getElementById('fil-contratista');
    selCont.innerHTML = '<option value="">Todos</option>' +
      data.contratistas.map(c =>
        `<option value="${esc(c)}">${esc(c)}</option>`
      ).join('');

    const selEmp = document.getElementById('fil-empresa');
    selEmp.innerHTML = '<option value="">Todas</option>' +
      data.empresas.map(e =>
        `<option value="${esc(e)}">${esc(e)}</option>`
      ).join('');

    if (data.maquinas && data.maquinas.length) {
      const selMaq = document.getElementById('fil-maquina');
      selMaq.innerHTML = '<option value="">Todas</option>' +
        data.maquinas.map(m =>
          `<option value="${esc(m)}">${esc(m)}</option>`
        ).join('');
      document.getElementById('maquina-filter-wrap').style.display = '';
    }
  } catch (e) {
    console.error('Error loading filters:', e);
  }
}

async function queryData() {
  const from = document.getElementById('fil-from').value;
  const to   = document.getElementById('fil-to').value;
  if (!from || !to) return;

  const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });
  const add = (key, id) => {
    const el = document.getElementById(id);
    if (el && el.value) params.append(key, el.value);
  };
  add('trabajador', 'fil-trabajador');
  add('tipo_pago', 'fil-tipo');
  add('maquina', 'fil-maquina');
  add('contratista', 'fil-contratista');
  add('empresa', 'fil-empresa');

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';
  let _hasData = false;

  try {
    const res = await fetch('/api/tarjas/resumen-persona-tractorista?' + params);
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

function renderPivot(rows) {
  const dates = [...new Set(rows.map(r => r.fecha))].sort();

  // Group by trabajador+contratista (same grain as General ranking) then machine/hours
  const workers = new Map();
  rows.forEach(r => {
    const w = r.trabajador ?? '(sin nombre)';
    const c = r.contratista ?? '';
    const groupKey = `${w}||${c}`;
    const rowKey = `${r.maquina ?? ''}||${r.horas_extras ?? ''}`;
    if (!workers.has(groupKey)) {
      workers.set(groupKey, { name: w, contratista: c, rowMap: new Map() });
    }
    const rowMap = workers.get(groupKey).rowMap;
    if (!rowMap.has(rowKey)) {
      rowMap.set(rowKey, {
        maquina: r.maquina,
        horas_extras: r.horas_extras,
        byDate: {},
        total: 0,
      });
    }
    const entry = rowMap.get(rowKey);
    entry.byDate[r.fecha] = (entry.byDate[r.fecha] || 0) + Number(r.total_tractor || 0);
    entry.total += Number(r.total_tractor || 0);
  });

  // Sort by grand total desc — same order as General ranking
  const sortedWorkers = [...workers.values()]
    .map(g => {
      let grandTotal = 0;
      g.rowMap.forEach(e => { grandTotal += e.total; });
      return { ...g, grandTotal };
    })
    .sort((a, b) => b.grandTotal - a.grandTotal);

  const thead = document.getElementById('pivot-thead');
  let superHdr = '<tr class="trp-superheader">';
  superHdr += '<th class="th-empty" colspan="4"></th>';
  superHdr += `<th colspan="${dates.length}">Total tractorista por fecha</th>`;
  superHdr += '<th class="th-empty"></th>';
  superHdr += '</tr>';

  let hdr = '<tr>';
  hdr += '<th class="th-fixed">Trabajador</th>';
  hdr += '<th class="th-fixed">Contratista</th>';
  hdr += '<th class="th-fixed">Máquina</th>';
  hdr += '<th class="th-fixed">Horas extra</th>';
  dates.forEach(d => { hdr += `<th class="th-date">${formatShortDate(d)}</th>`; });
  hdr += '<th class="th-total">Total</th>';
  hdr += '</tr>';

  thead.innerHTML = superHdr + hdr;

  let html = '';
  let overall = 0;
  const dateTotals = Object.fromEntries(dates.map(d => [d, 0]));
  sortedWorkers.forEach(w => {
    const entries = [...w.rowMap.values()];
    let isFirst = true;
    overall += w.grandTotal;

    entries.forEach(entry => {
      const rowClass = isFirst ? 'worker-first' : '';
      isFirst = false;

      html += `<tr class="${rowClass}">`;
      html += `<td class="cell-worker" title="${esc(w.name)}">${esc(w.name)}</td>`;
      html += `<td class="cell-tipo" title="${esc(w.contratista)}">${w.contratista ? esc(w.contratista) : '<span class="cell-null">-</span>'}</td>`;
      html += `<td class="cell-tipo">${entry.maquina ? esc(entry.maquina) : '<span class="cell-null">-</span>'}</td>`;
      html += `<td class="cell-tipo">${entry.horas_extras ? esc(entry.horas_extras) : '<span class="cell-null">-</span>'}</td>`;

      dates.forEach(d => {
        const val = entry.byDate[d];
        if (val && val > 0) {
          dateTotals[d] += val;
          html += `<td class="cell-value has-value">${fmtCLP.format(val)}</td>`;
        } else {
          html += '<td class="cell-zero">0</td>';
        }
      });

      html += `<td class="cell-total">${fmtCLP.format(entry.total)}</td>`;
      html += '</tr>';
    });
  });

  document.getElementById('pivot-tbody').innerHTML = html;

  let foot = '<tr class="trp-grand-total"><td colspan="4">Suma total</td>';
  dates.forEach(d => {
    foot += `<td class="cell-total">${dateTotals[d] ? fmtCLP.format(dateTotals[d]) : ''}</td>`;
  });
  foot += `<td class="cell-total">${fmtCLP.format(overall)}</td></tr>`;
  let tfoot = document.getElementById('pivot-tfoot');
  if (!tfoot) {
    tfoot = document.createElement('tfoot');
    tfoot.id = 'pivot-tfoot';
    document.getElementById('pivot-table').appendChild(tfoot);
  }
  tfoot.innerHTML = foot;
}

function currentParams() {
  const p = new URLSearchParams({
    fecha_inicio: document.getElementById('fil-from').value,
    fecha_termino: document.getElementById('fil-to').value,
  });
  const add = (key, id) => { const el = document.getElementById(id); if (el?.value) p.append(key, el.value); };
  add('trabajador','fil-trabajador'); add('tipo_pago','fil-tipo');
  add('maquina','fil-maquina'); add('contratista','fil-contratista');
  add('empresa','fil-empresa');
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
const FILTER_IDS = ['fil-from', 'fil-to', 'fil-trabajador', 'fil-tipo', 'fil-contratista', 'fil-empresa', 'fil-maquina'];

async function loadFiltersAndRestore() {
  initDates();
  await loadFilters();
  autoTriggerFromURL(FILTER_IDS, queryData);
}

document.getElementById('btn-apply').addEventListener('click', () => {
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
});
document.getElementById('btn-excel').addEventListener('click', () => {
  window.location.href = '/api/tarjas/resumen-persona-tractorista/download-excel?' + currentParams();
});
document.getElementById('btn-pdf').addEventListener('click', () => {
  window.open('/api/tarjas/resumen-persona-tractorista/download-pdf?' + currentParams(), '_blank');
});

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') queryData().then(() => syncFiltersToURL(FILTER_IDS)); });
});

bindPopstate(FILTER_IDS, queryData);

loadFiltersAndRestore();

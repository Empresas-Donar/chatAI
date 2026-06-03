// tarjas_resumen_persona_tractorista.js — Tractorista worker × date pivot

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

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';

  try {
    const res = await fetch('/api/tarjas/resumen-persona-tractorista?' + params);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (!data.rows.length) {
      document.getElementById('pivot-section').style.display = 'none';
      document.getElementById('empty-state').style.display = 'block';
      setDownloadEnabled(false);
      return;
    }

    document.getElementById('empty-state').style.display = 'none';
    renderPivot(data.rows);
    document.getElementById('pivot-section').style.display = '';
    setDownloadEnabled(true);
  } catch (e) {
    console.error('Query error:', e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Consultar';
  }
}

function renderPivot(rows) {
  const dates = [...new Set(rows.map(r => r.fecha))].sort();

  // Group by worker → (maquina|horas_extras key) → { maquina, horas_extras, byDate, total }
  const workers = new Map();
  rows.forEach(r => {
    const w = r.trabajador ?? '(sin nombre)';
    const rowKey = `${r.maquina ?? ''}||${r.horas_extras ?? ''}`;
    if (!workers.has(w)) workers.set(w, new Map());
    const rowMap = workers.get(w);
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

  // Sort workers by grand total desc
  const sortedWorkers = [...workers.entries()]
    .map(([name, rowMap]) => {
      let grandTotal = 0;
      rowMap.forEach(e => { grandTotal += e.total; });
      return { name, rowMap, grandTotal };
    })
    .sort((a, b) => b.grandTotal - a.grandTotal);

  // thead
  const thead = document.getElementById('pivot-thead');
  let superHdr = '<tr class="trp-superheader">';
  superHdr += '<th class="th-empty" colspan="3"></th>';
  superHdr += `<th colspan="${dates.length}">fecha (Fecha) / total_tractor</th>`;
  superHdr += '<th class="th-empty"></th>';
  superHdr += '</tr>';

  let hdr = '<tr>';
  hdr += '<th class="th-fixed">trabajador</th>';
  hdr += '<th class="th-fixed">maquina</th>';
  hdr += '<th class="th-fixed">horas_extras</th>';
  dates.forEach(d => { hdr += `<th class="th-date">${formatShortDate(d)}</th>`; });
  hdr += '<th class="th-total">Total</th>';
  hdr += '</tr>';

  thead.innerHTML = superHdr + hdr;

  // tbody
  let html = '';
  sortedWorkers.forEach(w => {
    const entries = [...w.rowMap.values()];
    let isFirst = true;

    entries.forEach(entry => {
      const rowClass = isFirst ? 'worker-first' : '';
      const workerCell = isFirst ? esc(w.name) : '';
      isFirst = false;

      html += `<tr class="${rowClass}">`;
      html += `<td class="cell-worker" title="${esc(w.name)}">${workerCell}</td>`;
      html += `<td class="cell-tipo">${entry.maquina ? esc(entry.maquina) : '<span class="cell-null">-</span>'}</td>`;
      html += `<td class="cell-tipo">${entry.horas_extras ? esc(entry.horas_extras) : '<span class="cell-null">-</span>'}</td>`;

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

  document.getElementById('pivot-tbody').innerHTML = html;
}

function currentParams() {
  const p = new URLSearchParams({
    fecha_inicio: document.getElementById('fil-from').value,
    fecha_termino: document.getElementById('fil-to').value,
  });
  const add = (key, id) => { const el = document.getElementById(id); if (el?.value) p.append(key, el.value); };
  add('trabajador','fil-trabajador'); add('tipo_pago','fil-tipo');
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
    .map(([k,v]) => `<span class="ph-chip"><strong>${esc(k)}:</strong> ${esc(v)}</span>`)
    .join('');
  document.getElementById('print-header').innerHTML =
    `<h2>${esc(title)}</h2><div class="ph-filters">${chips}</div>`;
  window.print();
}

document.getElementById('btn-apply').addEventListener('click', queryData);
document.getElementById('btn-excel').addEventListener('click', () => {
  window.location.href = '/api/tarjas/resumen-persona-tractorista/download-excel?' + currentParams();
});
document.getElementById('btn-pdf').addEventListener('click', () => {
  const g = id => document.getElementById(id)?.value || '';
  printWithHeader('Detalle trabajador tractorista — Tarjas', {
    'Desde': g('fil-from'), 'Hasta': g('fil-to'),
    'Contratista': g('fil-contratista'), 'Trabajador': g('fil-trabajador'),
    'Tipo de pago': g('fil-tipo'), 'Máquina': g('fil-maquina'),
  });
});

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') queryData(); });
});

initDates();
loadFilters();
queryData();

// tarjas_resumen_horas.js — Worker extra-hours summary pivot table

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
    const res = await fetch('/api/tarjas/resumen-horas/filters');
    const data = await res.json();

    const sel = document.getElementById('fil-trabajador');
    sel.innerHTML = '<option value="">Todos</option>' +
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
  const vTipo = document.getElementById('fil-tipo').value;
  const vCont = document.getElementById('fil-contratista').value;
  if (vTrab) params.append('trabajador', vTrab);
  if (vTipo) params.append('tipo_pago', vTipo);
  if (vCont) params.append('contratista', vCont);
  const vEmp = document.getElementById('fil-empresa').value;
  if (vEmp) params.append('empresa', vEmp);

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';
  let _hasData = false;

  try {
    const res = await fetch('/api/tarjas/resumen-horas?' + params);
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
  const dates = [...new Set(rows.map(r => r.fecha))].sort();

  const workers = new Map();
  rows.forEach(r => {
    const w = r.trabajador ?? '(sin nombre)';
    if (!workers.has(w)) workers.set(w, new Map());
    const tipos = workers.get(w);
    if (!tipos.has(r.tipo_pago)) tipos.set(r.tipo_pago, { byDate: {}, total: 0 });
    const entry = tipos.get(r.tipo_pago);
    const hrs = Number(r.horas_trabajadas) || 0;
    entry.byDate[r.fecha] = (entry.byDate[r.fecha] || 0) + hrs;
    entry.total += hrs;
  });

  const sortedWorkers = [...workers.entries()]
    .map(([name, tipos]) => {
      let grandTotal = 0;
      tipos.forEach(e => { grandTotal += e.total; });
      return { name, tipos, grandTotal };
    })
    .sort((a, b) => b.grandTotal - a.grandTotal);

  // Thead
  const thead = document.getElementById('pivot-thead');
  let superHdr = '<tr class="trp-superheader">';
  superHdr += '<th class="th-empty" colspan="2"></th>';
  superHdr += `<th colspan="${dates.length}">fecha (Fecha) / horas_trabajadas</th>`;
  superHdr += '<th class="th-empty"></th>';
  superHdr += '</tr>';

  let hdr = '<tr>';
  hdr += '<th class="th-fixed">trabajador</th>';
  hdr += '<th class="th-fixed">tipo_pago</th>';
  dates.forEach(d => { hdr += `<th class="th-date">${formatShortDate(d)}</th>`; });
  hdr += '<th class="th-total">Total</th>';
  hdr += '</tr>';

  thead.innerHTML = superHdr + hdr;

  // Tbody
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
        const val = entry.byDate[d] || 0;
        if (val > 0) {
          html += `<td class="cell-value has-value">${val}</td>`;
        } else {
          html += '<td class="cell-zero">0</td>';
        }
      });

      html += `<td class="cell-total">${entry.total}</td>`;
      html += '</tr>';
    });
  });

  tbody.innerHTML = html;
}

// ── Download helpers ──────────────────────────────────────────────────
function currentParams() {
  const p = new URLSearchParams({
    fecha_inicio: document.getElementById('fil-from').value,
    fecha_termino: document.getElementById('fil-to').value,
  });
  const vTrab = document.getElementById('fil-trabajador').value;
  const vTipo = document.getElementById('fil-tipo').value;
  const vCont = document.getElementById('fil-contratista').value;
  if (vTrab) p.append('trabajador', vTrab);
  if (vTipo) p.append('tipo_pago', vTipo);
  if (vCont) p.append('contratista', vCont);
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

// ── Events ────────────────────────────────────────────────────────────
document.getElementById('btn-apply').addEventListener('click', queryData);
document.getElementById('btn-excel').addEventListener('click', () => {
  window.location.href = '/api/tarjas/resumen-horas/download-excel?' + currentParams();
});
document.getElementById('btn-pdf').addEventListener('click', () => {
  window.open('/api/tarjas/resumen-horas/download-pdf?' + currentParams(), '_blank');
});

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') queryData(); });
});

// ── Init ──────────────────────────────────────────────────────────────
initDates();
loadFilters();
queryData();

/* despacho_notas.js */
'use strict';

const $ = id => document.getElementById(id);

const fmt = n => {
  if (n == null || n === '') return '—';
  return '$' + Number(n).toLocaleString('es-CL', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
};

const fmtDate = iso => {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}-${m}-${y}`;
};

const isTrato = tipo =>
  tipo && ['a trato', 'trato'].includes(tipo.toLowerCase().trim());

// ── Tabs ─────────────────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.dn-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.dn-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const tab = btn.dataset.tab;
      $('tab-notas').style.display = tab === 'notas' ? '' : 'none';
      $('tab-odoo').style.display  = tab === 'odoo'  ? '' : 'none';
    });
  });
}

// ── Default dates: first and last day of current month ────────────────────────
function setDefaultDates() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const last = new Date(y, now.getMonth() + 1, 0).getDate();
  const first = `${y}-${m}-01`;
  const end   = `${y}-${m}-${String(last).padStart(2, '0')}`;
  $('fil-from').value  = first;
  $('fil-to').value    = end;
  $('odoo-from').value = first;
  $('odoo-to').value   = end;
}

// ── Load filters (notas) ──────────────────────────────────────────────────────
async function loadNotasFilters() {
  const res = await fetch('/api/despacho/notas/filters');
  if (!res.ok) return;
  const data = await res.json();

  const selCampo = $('fil-campo');
  data.campos.forEach(c => {
    const o = document.createElement('option');
    o.value = o.textContent = c;
    selCampo.appendChild(o);
  });

  const selCont = $('fil-contratista');
  data.contratistas.forEach(c => {
    const o = document.createElement('option');
    o.value = o.textContent = c;
    selCont.appendChild(o);
  });
}

// ── Load filters (odoo) ───────────────────────────────────────────────────────
async function loadOdooFilters() {
  const res = await fetch('/api/despacho/odoo/filters');
  if (!res.ok) return;
  const data = await res.json();

  const sel = $('odoo-cliente');
  data.clientes.forEach(c => {
    const o = document.createElement('option');
    o.value = o.textContent = c;
    sel.appendChild(o);
  });
}

// ── Notas: fetch & render ─────────────────────────────────────────────────────
async function fetchReport() {
  const from        = $('fil-from').value;
  const to          = $('fil-to').value;
  const campo       = $('fil-campo').value;
  const contratista = $('fil-contratista').value;

  if (!from || !to)    { alert('Selecciona fechas de inicio y término.'); return; }
  if (!contratista)    { alert('Selecciona un contratista.'); return; }

  const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to, contratista });
  if (campo) params.set('campo', campo);

  let data;
  try {
    const res = await fetch(`/api/despacho/notas?${params}`);
    if (!res.ok) throw new Error(await res.text());
    data = await res.json();
  } catch (e) {
    alert('Error al cargar datos: ' + e.message);
    return;
  }

  renderReport(data, from, to, contratista);
}

function renderReport(data, from, to, contratista) {
  const { rows, total_trato, total_aldia, total_general, nombre_campo } = data;

  $('hdr-empresa').textContent     = nombre_campo ? `AGRÍCOLA DONAR — ${nombre_campo}` : 'AGRÍCOLA DONAR UNO SPA';
  $('hdr-contratista').textContent = contratista.toUpperCase();
  $('hdr-periodo').textContent     = `Semana desde ${fmtDate(from)} al ${fmtDate(to)}`;
  $('hdr-fecha-inicio').textContent  = fmtDate(from);
  $('hdr-fecha-termino').textContent = fmtDate(to);
  $('glosa-text').textContent = `SERVICIOS DE LABORES AGRÍCOLAS ${fmtDate(from)} AL ${fmtDate(to)}`;

  $('tot-trato').textContent   = fmt(total_trato);
  $('tot-aldia').textContent   = fmt(total_aldia);
  $('tot-general').textContent = fmt(total_general);

  const tbody = $('detail-tbody');
  tbody.innerHTML = '';

  if (!rows.length) {
    $('report-section').style.display = 'none';
    $('empty-state').style.display    = '';
    $('btn-print').style.display      = 'none';
    return;
  }

  rows.forEach(r => {
    const tr = document.createElement('tr');
    tr.className = isTrato(r.tipo_pago) ? 'tipo-trato-row' : 'tipo-aldia-row';
    tr.innerHTML = `
      <td>${r.tipo_pago ?? '—'}</td>
      <td>${r.cc ?? '—'}</td>
      <td>${r.labor ?? '—'}</td>
      <td class="num">${r.jornadas ?? '—'}</td>
      <td class="num">${fmt(r.total_unitario)}</td>
      <td class="num">${fmt(r.total_pagar)}</td>
    `;
    tbody.appendChild(tr);
  });

  $('table-total').textContent = fmt(total_general);
  $('detail-count').textContent = rows.length;

  $('empty-state').style.display    = 'none';
  $('report-section').style.display = '';
  $('btn-print').style.display      = '';
}

// ── Odoo: preview ─────────────────────────────────────────────────────────────
async function fetchOdooPreview() {
  const from    = $('odoo-from').value;
  const to      = $('odoo-to').value;
  const cliente = $('odoo-cliente').value;

  if (!from || !to) { alert('Selecciona fechas.'); return; }

  const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });
  if (cliente) params.set('cliente', cliente);

  let text;
  try {
    const res = await fetch(`/api/despacho/odoo/download?${params}`);
    if (!res.ok) throw new Error(await res.text());
    text = await res.text();
  } catch (e) {
    alert('Error: ' + e.message);
    return;
  }

  const lines = text.trim().split('\n').filter(Boolean);
  if (lines.length <= 1) {
    $('odoo-preview-section').style.display = 'none';
    $('odoo-empty').style.display = '';
    return;
  }

  const dataRows = lines.slice(1); // skip header
  const tbody = $('odoo-tbody');
  tbody.innerHTML = '';

  dataRows.forEach(line => {
    const cols = parseCSVLine(line);
    const tr = document.createElement('tr');
    // Vendedor(0), Producto(1), Cantidad(2), CodDist(3), partner(6), product_id(7), analytic(9)
    tr.innerHTML = `
      <td>${cols[0] || ''}</td>
      <td>${cols[1] || ''}</td>
      <td class="num">${cols[2] || ''}</td>
      <td>${cols[3] || ''}</td>
      <td>${cols[6] || ''}</td>
      <td>${cols[7] || ''}</td>
      <td class="dn-analytic">${cols[9] || ''}</td>
    `;
    tbody.appendChild(tr);
  });

  $('odoo-count').textContent = dataRows.length;
  $('odoo-empty').style.display           = 'none';
  $('odoo-preview-section').style.display = '';
}

function parseCSVLine(line) {
  const result = [];
  let cur = '', inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') { inQ = !inQ; continue; }
    if (ch === ',' && !inQ) { result.push(cur); cur = ''; continue; }
    cur += ch;
  }
  result.push(cur);
  return result;
}

// ── Odoo: download ────────────────────────────────────────────────────────────
function downloadOdoo() {
  const from    = $('odoo-from').value;
  const to      = $('odoo-to').value;
  const cliente = $('odoo-cliente').value;

  if (!from || !to) { alert('Selecciona fechas.'); return; }

  const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });
  if (cliente) params.set('cliente', cliente);

  window.location.href = `/api/despacho/odoo/download?${params}`;
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  initTabs();
  setDefaultDates();
  await Promise.all([loadNotasFilters(), loadOdooFilters()]);

  $('btn-apply').addEventListener('click', fetchReport);
  $('btn-print').addEventListener('click', () => window.print());
  $('btn-odoo-preview').addEventListener('click', fetchOdooPreview);
  $('btn-odoo-download').addEventListener('click', downloadOdoo);
});

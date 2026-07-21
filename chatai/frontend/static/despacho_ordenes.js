/* despacho_ordenes.js */
'use strict';

const fmtN = n => n == null ? '—' : Number(n).toLocaleString('es-CL');
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function parseFecha(s) {
  if (!s) return '—';
  // source data stored as MM/DD/YYYY HH:MM:SS — reformat to DD/MM/YYYY
  const m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (m) return `${m[2]}/${m[1]}/${m[3]}`;
  // fallback: if already YYYY-MM-DD, reformat to DD/MM/YYYY
  const iso = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;
  return s;
}

async function loadFilters() {
  try {
    const res = await fetch('/api/despacho/ordenes/filters');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { clientes, productos } = await res.json();

    const selC = document.getElementById('fil-cliente');
    clientes.forEach(c => { const o = document.createElement('option'); o.value = o.textContent = c; selC.appendChild(o); });

    const selP = document.getElementById('fil-producto');
    productos.forEach(c => { const o = document.createElement('option'); o.value = o.textContent = c; selP.appendChild(o); });
  } catch (e) {
    showError('Error cargando filtros: ' + e.message);
  }
}

document.getElementById('btn-apply').addEventListener('click', fetchOrdenes);

document.getElementById('btn-download').addEventListener('click', () => {
  const cliente  = document.getElementById('fil-cliente').value;
  const producto = document.getElementById('fil-producto').value;
  const params = new URLSearchParams();
  if (cliente)  params.set('cliente', cliente);
  if (producto) params.set('producto', producto);
  window.location.href = '/api/despacho/ordenes/download?' + params;
});

async function fetchOrdenes() {
  const cliente  = document.getElementById('fil-cliente').value;
  const producto = document.getElementById('fil-producto').value;

  hideError();
  document.getElementById('kpi-bar').classList.add('hidden');
  document.getElementById('table-wrap').classList.add('hidden');
  document.getElementById('empty-box').classList.add('hidden');
  document.getElementById('btn-download').disabled = true;

  const btn = document.getElementById('btn-apply');
  btn.disabled = true; btn.textContent = 'Cargando…';

  try {
    const params = new URLSearchParams();
    if (cliente)  params.set('cliente', cliente);
    if (producto) params.set('producto', producto);

    const res = await fetch('/api/despacho/ordenes?' + params);
    if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.detail || res.statusText); }
    const data = await res.json();

    if (!data.ordenes.length) {
      document.getElementById('empty-box').classList.remove('hidden');
      return;
    }
    render(data);
    document.getElementById('btn-download').disabled = false;
  } catch (e) {
    showError('Error: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Consultar';
  }
}

function render({ ordenes, kpi }) {
  document.getElementById('kpi-ordenes').textContent  = fmtN(kpi.total_ordenes);
  document.getElementById('kpi-cantidad').textContent = fmtN(kpi.total_cantidad);
  document.getElementById('kpi-clientes').textContent = fmtN(kpi.total_clientes);
  document.getElementById('kpi-ccs').textContent      = fmtN(kpi.total_ccs);
  document.getElementById('kpi-bar').classList.remove('hidden');

  document.getElementById('row-count').textContent = `${ordenes.length} registros`;

  const tbody = document.getElementById('tbody-ordenes');
  tbody.innerHTML = '';
  ordenes.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="white-space:nowrap">${esc(parseFecha(r.fecha))}</td>
      <td>${esc(r.cliente)}</td>
      <td>${esc(r.producto)}</td>
      <td>${esc(r.descripcion)}</td>
      <td style="max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc(r.cc)}">${esc(r.cc)}</td>
      <td class="num">${fmtN(r.cantidad)}</td>
    `;
    tbody.appendChild(tr);
  });

  document.getElementById('table-wrap').classList.remove('hidden');
}

function showError(msg) { const el = document.getElementById('error-box'); el.textContent = msg; el.classList.remove('hidden'); }
function hideError()    { document.getElementById('error-box').classList.add('hidden'); }

loadFilters();
document.addEventListener('DOMContentLoaded', () => fetchOrdenes());

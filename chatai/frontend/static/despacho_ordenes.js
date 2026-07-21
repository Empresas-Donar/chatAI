/* despacho_ordenes.js */
'use strict';

const fmtN = n => n == null ? '—' : Number(n).toLocaleString('es-CL');

let _lastOrdParams = null;
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

// ── Default dates: last 90 days ───────────────────────────────────────────
function setDefaultDates() {
  const to   = new Date();
  const from = new Date(to);
  from.setDate(from.getDate() - 90);
  const fmt = d => d.toISOString().slice(0, 10);
  document.getElementById('fil-from').value = fmt(from);
  document.getElementById('fil-to').value   = fmt(to);
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

// ── URL filter sync ───────────────────────────────────────────────────────
const FILTER_IDS = ['fil-from', 'fil-to', 'fil-cliente', 'fil-producto'];

document.getElementById('btn-apply').addEventListener('click', () => {
  fetchOrdenes().then(() => syncFiltersToURL(FILTER_IDS));
});

bindPopstate(FILTER_IDS, fetchOrdenes);

document.getElementById('btn-sync-preview').addEventListener('click', () => {
  openSyncModal();
});

document.getElementById('btn-download').addEventListener('click', () => {
  const from     = document.getElementById('fil-from').value;
  const to       = document.getElementById('fil-to').value;
  const cliente  = document.getElementById('fil-cliente').value;
  const producto = document.getElementById('fil-producto').value;
  const params = new URLSearchParams();
  if (from)     params.set('fecha_inicio', from);
  if (to)       params.set('fecha_termino', to);
  if (cliente)  params.set('cliente', cliente);
  if (producto) params.set('producto', producto);
  window.location.href = '/api/despacho/ordenes/download?' + params;
});

async function fetchOrdenes() {
  const from     = document.getElementById('fil-from').value;
  const to       = document.getElementById('fil-to').value;
  const cliente  = document.getElementById('fil-cliente').value;
  const producto = document.getElementById('fil-producto').value;

  hideError();
  document.getElementById('kpi-bar').classList.add('hidden');
  document.getElementById('table-wrap').classList.add('hidden');
  document.getElementById('empty-box').classList.add('hidden');
  document.getElementById('btn-download').disabled = true;
  document.getElementById('btn-sync-preview').disabled = true;

  if (!from || !to) { showError('Selecciona un rango de fechas.'); return; }

  const btn = document.getElementById('btn-apply');
  btn.disabled = true; btn.textContent = 'Cargando…';

  try {
    const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });
    if (cliente)  params.set('cliente', cliente);
    if (producto) params.set('producto', producto);
    _lastOrdParams = params.toString();

    const res = await fetch('/api/despacho/ordenes?' + params);
    if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.detail || res.statusText); }
    const data = await res.json();

    if (!data.ordenes.length) {
      document.getElementById('empty-box').classList.remove('hidden');
      return;
    }
    render(data);
    document.getElementById('btn-download').disabled = false;
    document.getElementById('btn-sync-preview').disabled = false;
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

// Set default dates, populate selects, restore URL params, then auto-run
setDefaultDates();
loadFilters().then(() => {
  autoTriggerFromURL(FILTER_IDS, fetchOrdenes);
});

// ── CC Sync Preview Modal ─────────────────────────────────────────────────

const syncModal = {
  overlay:      () => document.getElementById('sync-modal'),
  loading:      () => document.getElementById('sync-modal-loading'),
  content:      () => document.getElementById('sync-modal-content'),
  error:        () => document.getElementById('sync-modal-error'),
  okCount:      () => document.getElementById('sync-ok-count'),
  unknownCount: () => document.getElementById('sync-unknown-count'),
  unknownChip:  () => document.getElementById('sync-unknown-chip'),
  emptyCount:   () => document.getElementById('sync-empty-count'),
  emptyChip:    () => document.getElementById('sync-empty-chip'),
  unknownAlert: () => document.getElementById('sync-unknown-alert'),
  unknownCountMsg: () => document.getElementById('sync-unknown-count-msg'),
  bqAlert:      () => document.getElementById('sync-bq-unavail-alert'),
  tbody:        () => document.getElementById('sync-preview-tbody'),
};

const STATUS_BADGE = {
  ok:       '<span class="cc-badge cc-badge-ok">OK</span>',
  unknown:  '<span class="cc-badge cc-badge-unknown">Sin mapear</span>',
  archived: '<span class="cc-badge cc-badge-archived">Archivado</span>',
  empty:    '<span class="cc-badge cc-badge-empty">Vacío</span>',
};

async function loadSyncPreview() {
  syncModal.loading().style.display = 'flex';
  syncModal.content().classList.add('hidden');
  syncModal.error().classList.add('hidden');

  try {
    const res = await fetch('/api/despacho/ordenes/sync-preview?' + (_lastOrdParams || ''));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Summary chips
    syncModal.okCount().textContent      = data.ok_count ?? 0;
    syncModal.unknownCount().textContent = data.unknown_count ?? 0;
    syncModal.emptyCount().textContent   = data.empty_count ?? 0;
    syncModal.unknownChip().style.display = (data.unknown_count > 0) ? '' : 'none';
    syncModal.emptyChip().style.display   = (data.empty_count > 0)   ? '' : 'none';

    // Alerts
    if (!data.bq_available) {
      syncModal.bqAlert().classList.remove('hidden');
      syncModal.unknownAlert().classList.add('hidden');
    } else {
      syncModal.bqAlert().classList.add('hidden');
      if (data.unknown_count > 0) {
        syncModal.unknownCountMsg().textContent = data.unknown_count;
        syncModal.unknownAlert().classList.remove('hidden');
      } else {
        syncModal.unknownAlert().classList.add('hidden');
      }
    }

    // Table rows
    const ccs = data.ccs ?? [];
    if (!ccs.length) {
      syncModal.tbody().innerHTML = '<tr><td colspan="4" style="text-align:center;color:#94a3b8;padding:24px">Sin centros de costo en este período</td></tr>';
    } else {
      syncModal.tbody().innerHTML = ccs.map(r => {
        const isProblematic = r.status !== 'ok';
        const rowCls = isProblematic ? 'cc-row-error' : '';
        const badge = STATUS_BADGE[r.status] ?? STATUS_BADGE.unknown;
        return `<tr class="${rowCls}">
          <td>${esc(r.cc)}</td>
          <td class="num">${fmtN(r.num_ordenes)}</td>
          <td class="num">${fmtN(r.total_cantidad)}</td>
          <td>${badge}</td>
        </tr>`;
      }).join('');
    }

    syncModal.loading().style.display = 'none';
    syncModal.content().classList.remove('hidden');
  } catch (e) {
    syncModal.loading().style.display = 'none';
    const el = syncModal.error();
    el.innerHTML = '<span class="cc-alert-icon">⚠️</span> Error al cargar la previa: ' + esc(e.message);
    el.classList.remove('hidden');
  }
}

function openSyncModal() {
  syncModal.overlay().classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  loadSyncPreview();
}

function closeSyncModal() {
  syncModal.overlay().classList.add('hidden');
  document.body.style.overflow = '';
}

document.getElementById('btn-sync-cancel').addEventListener('click', closeSyncModal);
document.getElementById('btn-sync-modal-close').addEventListener('click', closeSyncModal);
syncModal.overlay().addEventListener('click', e => {
  if (e.target === syncModal.overlay()) closeSyncModal();
});

/* despacho_guia.js */
'use strict';

const fmtN    = n => n == null ? '—' : Number(n).toLocaleString('es-CL');
const fmtDate = s => { if (!s) return '—'; const [y, m, d] = s.split('-'); return `${d}-${m}-${y}`; };
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

const CALIDAD_CLASS = {
  'PRIMERA SUPERMERCADO':    'cal-sup',
  'PRIMERA MERCADO INTERNO': 'cal-pri',
  'SEGUNDA MERCADO INTERNO': 'cal-seg',
  'TERCERA MERCADO INTERNO': 'cal-ter',
  'DESCARTE Y TORCIDO':      'cal-des',
};

// Abbreviate long product names keeping the code prefix
function fmtProducto(p) {
  if (!p || p === '—') return '—';
  // "594-E2-(AL)-25/26 PIM.ROJO" → code + short name
  const m = p.match(/^(\d+-\S+)-25\/26\s+(.+)$/);
  return m ? `<span style="color:var(--text-muted);font-size:11px">${esc(m[1])}</span> ${esc(m[2])}` : esc(p);
}

let _guiasData = [];

// ── Default dates: last 30 days ───────────────────────────────────────────
function setDefaultDates() {
  const to   = new Date();
  const from = new Date(to);
  from.setDate(from.getDate() - 30);
  const fmt = d => d.toISOString().slice(0, 10);
  document.getElementById('fil-from').value = fmt(from);
  document.getElementById('fil-to').value   = fmt(to);
}

// ── Load filters (reactive) ───────────────────────────────────────────────
let _updatingFilters = false;

function populate(sel, items, keep) {
  sel.innerHTML = '<option value="">Todos</option>';
  items.forEach(v => {
    const o = document.createElement('option');
    o.value = o.textContent = v;
    if (v === keep) o.selected = true;
    sel.appendChild(o);
  });
}

async function loadFilters({ cliente = '', chofer = '' } = {}) {
  _updatingFilters = true;
  try {
    const params = new URLSearchParams();
    if (cliente) params.set('cliente', cliente);
    if (chofer)  params.set('chofer',  chofer);
    const res = await fetch('/api/despacho/guia/filters?' + params);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { clientes, choferes } = await res.json();
    populate(document.getElementById('fil-cliente'), clientes, cliente);
    populate(document.getElementById('fil-chofer'),  choferes, chofer);
  } catch (e) {
    showError('Error cargando filtros: ' + e.message);
  } finally {
    _updatingFilters = false;
  }
}

document.getElementById('fil-cliente').addEventListener('change', function () {
  if (_updatingFilters) return;
  loadFilters({ cliente: this.value, chofer: document.getElementById('fil-chofer').value });
});

document.getElementById('fil-chofer').addEventListener('change', function () {
  if (_updatingFilters) return;
  loadFilters({ cliente: document.getElementById('fil-cliente').value, chofer: this.value });
});

// ── Generate ─────────────────────────────────────────────────────────────
document.getElementById('btn-apply').addEventListener('click', fetchGuias);

async function fetchGuias() {
  const from    = document.getElementById('fil-from').value;
  const to      = document.getElementById('fil-to').value;
  const cliente = document.getElementById('fil-cliente').value;
  const chofer  = document.getElementById('fil-chofer').value;

  hideError();
  document.getElementById('guias-container').innerHTML = '';
  document.getElementById('print-actions').style.display = 'none';
  document.getElementById('empty-box').classList.add('hidden');

  if (!from || !to) { showError('Selecciona un rango de fechas.'); return; }

  const btn = document.getElementById('btn-apply');
  btn.disabled = true; btn.textContent = 'Generando…';

  try {
    const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });
    if (cliente) params.set('cliente', cliente);
    if (chofer)  params.set('chofer', chofer);

    const res = await fetch('/api/despacho/guia?' + params);
    if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.detail || res.statusText); }
    const { viajes } = await res.json();

    if (!viajes.length) {
      document.getElementById('empty-box').classList.remove('hidden');
      return;
    }

    _guiasData = viajes;
    renderAll(viajes);
  } catch (e) {
    showError('Error: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Generar guías';
  }
}

// ── Render all trips ──────────────────────────────────────────────────────
function renderAll(viajes) {
  const container = document.getElementById('guias-container');
  container.innerHTML = '';
  viajes.forEach((v, i) => container.appendChild(buildGuia(v, i + 1)));

  document.getElementById('trip-count').textContent = `${viajes.length} guía${viajes.length !== 1 ? 's' : ''} generada${viajes.length !== 1 ? 's' : ''}`;
  document.getElementById('print-actions').style.display = '';
}

// ── Build a single guia document ─────────────────────────────────────────
function buildGuia(v, idx) {
  const el = document.createElement('div');
  el.className = 'guia-doc';

  const totalLineas = v.lineas.length;
  const hasOdoo = v.lineas.some(l => l.product_id);

  el.innerHTML = `
    <!-- Header -->
    <div class="guia-header">
      <div class="guia-logo-block">
        <div class="guia-logo">EMPRESAS<br>DONAR</div>
        <div class="guia-logo-label">Agrícola Donar</div>
      </div>
      <div class="guia-company">
        <div class="guia-company-name">AGRÍCOLA DONAR DOS SPA</div>
        <div class="guia-company-rut">RUT 76.123.456-7</div>
        <div class="guia-company-sub">
          Cliente: <span>${esc(v.nombre_odoo || v.cliente)}</span>
        </div>
      </div>
      <div class="guia-meta">
        <div class="guia-doc-title">GUÍA DE DESPACHO N° ${String(idx).padStart(4, '0')}</div>
        <div class="guia-meta-row">
          <span class="guia-meta-label">Fecha</span>
          <span class="guia-meta-val">${fmtDate(v.fecha)}</span>
        </div>
        <div class="guia-meta-row">
          <span class="guia-meta-label">Unidades</span>
          <span class="guia-meta-val">${fmtN(v.total_unidades)}</span>
        </div>
        <div class="guia-meta-row">
          <span class="guia-meta-label">Pallets</span>
          <span class="guia-meta-val">${v.total_pallets > 0 ? fmtN(v.total_pallets) : '—'}</span>
        </div>
      </div>
    </div>

    <!-- Transport -->
    <div class="guia-transport">
      <div class="guia-transport-cell">
        <div class="guia-transport-label">Chofer</div>
        <div class="guia-transport-val">${esc(v.chofer)}</div>
      </div>
      <div class="guia-transport-cell">
        <div class="guia-transport-label">Patente</div>
        <div class="guia-transport-val">${esc(v.patente)}</div>
      </div>
      <div class="guia-transport-cell">
        <div class="guia-transport-label">Destino</div>
        <div class="guia-transport-val">${v.destino && v.destino !== '—' ? esc(v.destino) : '—'}</div>
      </div>
      <div class="guia-transport-cell">
        <div class="guia-transport-label">Líneas</div>
        <div class="guia-transport-val">${totalLineas}</div>
      </div>
    </div>

    <!-- Table -->
    <div class="guia-table-wrap">
      <table class="guia-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Producto</th>
            <th>Calidad</th>
            <th class="num">Cajas</th>
            <th class="num">Und./Caja</th>
            <th class="num">Total Unidades</th>
            <th class="num">Pallets</th>
            <th class="num">Mallas</th>
            ${hasOdoo ? '<th>Cód. Odoo</th>' : ''}
          </tr>
        </thead>
        <tbody>
          ${v.lineas.map((l, i) => buildLinea(l, i + 1, hasOdoo)).join('')}
        </tbody>
      </table>
    </div>

    <!-- Footer -->
    <div class="guia-footer">
      <div class="guia-footer-cell">
        <div class="guia-footer-label">Total unidades</div>
        <div class="guia-footer-val highlight">${fmtN(v.total_unidades)}</div>
      </div>
      <div class="guia-footer-cell">
        <div class="guia-footer-label">Total pallets</div>
        <div class="guia-footer-val">${v.total_pallets > 0 ? fmtN(v.total_pallets) : '—'}</div>
      </div>
      <div class="guia-footer-cell">
        <div class="guia-footer-label">Firma receptor</div>
        <div class="guia-footer-val" style="border-bottom:1px solid #94a3b8;min-width:140px;height:28px"></div>
      </div>
    </div>
  `;
  return el;
}

function buildLinea(l, i, hasOdoo) {
  const calClass = CALIDAD_CLASS[l.calidad] || 'cal-other';
  const calLabel = l.calidad && l.calidad !== '—' ? l.calidad : '—';
  const odooCell = hasOdoo
    ? `<td style="font-family:monospace;font-size:11px;color:var(--text-muted)">${esc(l.product_id) || '—'}</td>`
    : '';
  return `
    <tr>
      <td style="color:var(--text-muted);font-size:12px">${i}</td>
      <td>${fmtProducto(l.producto)}</td>
      <td><span class="cal-badge ${calClass}">${esc(calLabel)}</span></td>
      <td class="num">${l.cajas > 0 ? fmtN(l.cajas) : '—'}</td>
      <td class="num">${l.unidades_caja > 0 ? fmtN(l.unidades_caja) : '—'}</td>
      <td class="num"><strong>${fmtN(l.total_unidades)}</strong></td>
      <td class="num">${l.pallets > 0 ? fmtN(l.pallets) : '—'}</td>
      <td class="num">${l.mallas > 0 ? fmtN(l.mallas) : '—'}</td>
      ${odooCell}
    </tr>
  `;
}

function showError(msg) { const el = document.getElementById('error-box'); el.textContent = msg; el.classList.remove('hidden'); }
function hideError()    { document.getElementById('error-box').classList.add('hidden'); }

// ── Init ──────────────────────────────────────────────────────────────────
setDefaultDates();
loadFilters();

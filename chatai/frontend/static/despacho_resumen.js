/* despacho_resumen.js */
'use strict';

const fmtN   = n => n == null ? '—' : Number(n).toLocaleString('es-CL');
const fmtDate = s => { if (!s) return '—'; const [y,m,d] = s.split('-'); return `${d}/${m}/${y}`; };
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

const CALIDAD_COLORS = {
  'PRIMERA SUPERMERCADO':   '#3b82f6',
  'PRIMERA MERCADO INTERNO':'#22c55e',
  'SEGUNDA MERCADO INTERNO':'#f59e0b',
  'TERCERA MERCADO INTERNO':'#f97316',
  'DESCARTE Y TORCIDO':     '#ef4444',
  'Sin calidad':            '#94a3b8',
};

let chartTendencia = null;
let chartCalidad   = null;

// ── Default dates: last 90 days ───────────────────────────────────────────
function setDefaultDates() {
  const to   = new Date();
  const from = new Date(to);
  from.setDate(from.getDate() - 90);
  const fmt = d => d.toISOString().slice(0, 10);
  document.getElementById('fil-from').value = fmt(from);
  document.getElementById('fil-to').value   = fmt(to);
}

// ── Load filter dropdowns ─────────────────────────────────────────────────
async function loadFilters() {
  try {
    const res = await fetch('/api/despacho/resumen/filters');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { clientes } = await res.json();
    const sel = document.getElementById('fil-cliente');
    clientes.forEach(c => {
      const o = document.createElement('option');
      o.value = o.textContent = c;
      sel.appendChild(o);
    });
  } catch (e) {
    showError('Error cargando filtros: ' + e.message);
  }
}

// ── Query ─────────────────────────────────────────────────────────────────
document.getElementById('btn-apply').addEventListener('click', fetchDashboard);

async function fetchDashboard() {
  const from    = document.getElementById('fil-from').value;
  const to      = document.getElementById('fil-to').value;
  const cliente = document.getElementById('fil-cliente').value;

  hideError();
  document.getElementById('dashboard').style.display = 'none';
  document.getElementById('empty-box').classList.add('hidden');

  if (!from || !to) { showError('Selecciona un rango de fechas.'); return; }

  const btn = document.getElementById('btn-apply');
  btn.disabled = true; btn.textContent = 'Cargando…';

  try {
    const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to });
    if (cliente) params.set('cliente', cliente);

    const res = await fetch('/api/despacho/resumen?' + params);
    if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.detail || res.statusText); }
    const data = await res.json();

    if (!data.kpi.total_registros) {
      document.getElementById('empty-box').classList.remove('hidden');
      return;
    }
    render(data);
  } catch (e) {
    showError('Error: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Consultar';
  }
}

// ── Render ────────────────────────────────────────────────────────────────
function render({ kpi, tendencia_semanal, top_clientes, por_calidad, top_productos, ultimos }) {
  // KPIs
  document.getElementById('kpi-unidades').textContent  = fmtN(kpi.total_unidades);
  document.getElementById('kpi-registros').textContent = `${fmtN(kpi.total_registros)} registros`;
  document.getElementById('kpi-kg').textContent        = fmtN(kpi.total_kg) + ' kg';
  document.getElementById('kpi-bins').textContent      = `${fmtN(kpi.total_bins)} bins`;
  document.getElementById('kpi-clientes').textContent  = fmtN(kpi.clientes);
  document.getElementById('kpi-dias').textContent      = `${fmtN(kpi.dias)} días con actividad`;

  // Chart: tendencia semanal
  if (chartTendencia) { chartTendencia.destroy(); }
  chartTendencia = new Chart(document.getElementById('chart-tendencia').getContext('2d'), {
    type: 'bar',
    data: {
      labels: tendencia_semanal.map(r => fmtDate(String(r.semana))),
      datasets: [
        {
          label: 'Unidades',
          data: tendencia_semanal.map(r => r.unidades),
          backgroundColor: '#3b82f6',
          borderRadius: 4,
          yAxisID: 'y',
        },
        {
          label: 'KG (lechuga)',
          data: tendencia_semanal.map(r => r.kg),
          backgroundColor: '#22c55e',
          borderRadius: 4,
          yAxisID: 'y',
        },
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'top', labels: { font: { size: 11 }, boxWidth: 12 } } },
      scales: {
        x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
        y: { ticks: { font: { size: 11 } }, beginAtZero: true },
      }
    }
  });

  // Chart: calidad (donut)
  if (chartCalidad) { chartCalidad.destroy(); }
  chartCalidad = new Chart(document.getElementById('chart-calidad').getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: por_calidad.map(r => r.calidad),
      datasets: [{
        data: por_calidad.map(r => r.unidades),
        backgroundColor: por_calidad.map(r => CALIDAD_COLORS[r.calidad] || '#94a3b8'),
        borderWidth: 2,
      }]
    },
    options: {
      cutout: '55%',
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 10 } },
        tooltip: { callbacks: { label: c => `${c.label}: ${fmtN(c.parsed)}` } },
      }
    }
  });

  // Table: top clientes
  const tbC = document.getElementById('tbody-clientes');
  tbC.innerHTML = '';
  top_clientes.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${esc(r.cliente)}</td><td class="num">${fmtN(r.unidades)}</td><td class="num">${fmtN(r.kg)}</td><td class="num">${fmtN(r.despachos)}</td>`;
    tbC.appendChild(tr);
  });

  // Table: top productos
  const tbP = document.getElementById('tbody-productos');
  tbP.innerHTML = '';
  top_productos.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${esc(r.producto)}</td><td class="num">${fmtN(r.unidades)}</td><td class="num">${fmtN(r.registros)}</td>`;
    tbP.appendChild(tr);
  });

  // Table: últimos despachos
  const tbU = document.getElementById('tbody-ultimos');
  tbU.innerHTML = '';
  ultimos.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${fmtDate(r.fecha)}</td>
      <td>${esc(r.cliente)}</td>
      <td style="max-width:220px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc(r.producto)}">${esc(r.producto)}</td>
      <td><span class="badge" style="background:${CALIDAD_COLORS[r.calidad]||'#e2e8f0'};color:#1e293b;font-size:11px">${esc(r.calidad)}</span></td>
      <td class="num">${fmtN(r.unidades) === '0' ? '—' : fmtN(r.unidades)}</td>
      <td class="num">${fmtN(r.kg) === '0' ? '—' : fmtN(r.kg)}</td>
      <td class="num">${fmtN(r.bins) === '0' ? '—' : fmtN(r.bins)}</td>
    `;
    tbU.appendChild(tr);
  });

  document.getElementById('dashboard').style.display = '';
}

function showError(msg) { const el = document.getElementById('error-box'); el.textContent = msg; el.classList.remove('hidden'); }
function hideError()    { document.getElementById('error-box').classList.add('hidden'); }

// ── Init ──────────────────────────────────────────────────────────────────
setDefaultDates();
loadFilters();
// Auto-load on page open
document.addEventListener('DOMContentLoaded', () => fetchDashboard());

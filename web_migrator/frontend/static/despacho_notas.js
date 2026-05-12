/* despacho_notas.js — Notas de crédito page logic */
'use strict';

let _lastParams = null;

const fmtCLP = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 });

function fmtDate(s) {
  if (!s) return '–';
  const [y, m, d] = s.split('-');
  return `${d}-${m}-${y}`;
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

const isTrato = tipo => tipo && ['a trato', 'trato'].includes(tipo.toLowerCase().trim());

let chartInstance = null;

// ── Default dates: first and last day of current month ────────────────────
function setDefaultDates() {
  const now  = new Date();
  const y    = now.getFullYear();
  const m    = String(now.getMonth() + 1).padStart(2, '0');
  const last = new Date(y, now.getMonth() + 1, 0).getDate();
  document.getElementById('fil-from').value = `${y}-${m}-01`;
  document.getElementById('fil-to').value   = `${y}-${m}-${String(last).padStart(2, '0')}`;
}

// ── Load filters ──────────────────────────────────────────────────────────
async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/notas/filters');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { campos, contratistas } = await res.json();

    const selC = document.getElementById('fil-contratista');
    contratistas.forEach(c => {
      const o = document.createElement('option');
      o.value = o.textContent = c;
      selC.appendChild(o);
    });

    const selF = document.getElementById('fil-campo');
    campos.forEach(c => {
      const o = document.createElement('option');
      o.value = o.textContent = c;
      selF.appendChild(o);
    });
  } catch (err) {
    showError('Error cargando filtros: ' + err.message);
  }
}

// ── Generate button ───────────────────────────────────────────────────────
document.getElementById('btn-apply').addEventListener('click', async () => {
  const contratista = document.getElementById('fil-contratista').value;
  const campo       = document.getElementById('fil-campo').value;
  const from        = document.getElementById('fil-from').value;
  const to          = document.getElementById('fil-to').value;

  hideError();
  document.getElementById('oc-document').style.display = 'none';
  document.getElementById('empty-box').classList.add('hidden');

  if (!contratista) { showError('Selecciona un contratista.'); return; }
  if (!from || !to)  { showError('Selecciona fechas de inicio y término.'); return; }
  if (from > to)     { showError('La fecha de inicio no puede ser posterior a la de término.'); return; }

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Generando…';

  try {
    const params = new URLSearchParams({ fecha_inicio: from, fecha_termino: to, contratista });
    if (campo) params.set('campo', campo);
    _lastParams = { contratista, campo, fecha_inicio: from, fecha_termino: to };

    const res = await fetch('/api/tarjas/notas?' + params);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || res.statusText);
    }
    const data = await res.json();

    if (!data.rows.length) {
      document.getElementById('empty-box').classList.remove('hidden');
      return;
    }

    renderDocument(data, from, to, contratista);
  } catch (err) {
    showError('Error al generar: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generar nota';
  }
});

// ── Render document ───────────────────────────────────────────────────────
function renderDocument(data, from, to, contratista) {
  const { rows, total_trato, total_aldia, total_general, nombre_campo } = data;

  document.getElementById('doc-company').textContent    = nombre_campo ? `AGRÍCOLA DONAR — ${nombre_campo}` : 'AGRÍCOLA DONAR UNO SPA';
  document.getElementById('doc-contractor').textContent = contratista.toUpperCase();
  document.getElementById('doc-week').textContent       = `Semana desde ${fmtDate(from)} al ${fmtDate(to)}`;
  document.getElementById('doc-date-from').textContent  = fmtDate(from);
  document.getElementById('doc-date-to').textContent    = fmtDate(to);
  document.getElementById('doc-grand-total').textContent = fmtCLP.format(total_general);

  document.getElementById('doc-glosa').textContent =
    `SERVICIOS DE LABORES AGRÍCOLAS ${fmtDate(from)} AL ${fmtDate(to)}`;

  document.getElementById('doc-total-trato').textContent = fmtCLP.format(total_trato);
  document.getElementById('doc-total-aldia').textContent = fmtCLP.format(total_aldia);
  document.getElementById('doc-total').textContent       = fmtCLP.format(total_general);

  const pctTrato = total_general ? (total_trato / total_general) * 100 : 0;
  const pctAldia = total_general ? (total_aldia / total_general) * 100 : 0;
  renderChart(pctTrato, pctAldia);

  const tbody = document.getElementById('doc-tbody');
  tbody.innerHTML = '';
  for (const row of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="badge ${isTrato(row.tipo_pago) ? 'badge-trato' : 'badge-aldia'}">${esc(row.tipo_pago)}</span></td>
      <td>${esc(row.cc)}</td>
      <td>${esc(row.labor)}</td>
      <td class="num">${row.jornadas ?? '–'}</td>
      <td class="num">${fmtCLP.format(row.total_unitario ?? 0)}</td>
      <td class="num">${fmtCLP.format(row.total_pagar ?? 0)}</td>
    `;
    tbody.appendChild(tr);
  }

  document.getElementById('oc-document').style.display = 'block';
  document.getElementById('btn-odoo-export').disabled = false;
}

function renderChart(pctTrato, pctAldia) {
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  chartInstance = new Chart(
    document.getElementById('doc-chart').getContext('2d'),
    {
      type: 'doughnut',
      data: {
        labels: ['A Trato', 'Al Día'],
        datasets: [{
          data: [pctTrato, pctAldia],
          backgroundColor: ['#3b82f6', '#22c55e'],
          borderWidth: 2,
        }]
      },
      options: {
        cutout: '60%',
        plugins: {
          legend: { position: 'right', labels: { font: { size: 11 }, boxWidth: 12 } },
          tooltip: { callbacks: { label: c => `${c.label}: ${Number(c.parsed).toFixed(1)}%` } },
        },
      }
    }
  );
}

// ── Utils ─────────────────────────────────────────────────────────────────
function showError(msg) {
  const el = document.getElementById('error-box');
  el.textContent = msg;
  el.classList.remove('hidden');
}
function hideError() {
  document.getElementById('error-box').classList.add('hidden');
}

// ── Odoo export ───────────────────────────────────────────────────────────
document.getElementById('btn-odoo-export').addEventListener('click', () => {
  if (!_lastParams) return;
  const { contratista, campo, fecha_inicio, fecha_termino } = _lastParams;
  if (!campo) { showError('Selecciona un campo específico para exportar a Odoo.'); return; }
  const params = new URLSearchParams({ contratista, campo, fecha_inicio, fecha_termino });
  const a = document.createElement('a');
  a.href = '/api/tarjas/notas/odoo-export?' + params;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
});

// ── Init ──────────────────────────────────────────────────────────────────
setDefaultDates();
loadFilters();

// purchase_orders.js — Purchase Order page logic

const fmtCLP = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 });
const fmtPct = v => (v != null ? Number(v).toFixed(1) + '%' : '–');

function fmtDate(s) {
  if (!s) return '–';
  const [y, m, d] = s.split('-');
  return `${d}-${m}-${y}`;
}

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

const PAYMENT_TYPE_LABELS = { 'trato': 'A Trato', 'Al dia': 'Al Día' };
const PAYMENT_TYPE_BADGE  = { 'trato': 'badge-trato', 'Al dia': 'badge-aldia' };

let chartInstance = null;
let _lastParams = null;

// ── Load filter dropdowns ────────────────────────────────────────────────
async function loadFilters() {
  try {
    const res = await fetch('/api/purchase-orders/filters');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { contratistas, empresas } = await res.json();

    const selC = document.getElementById('sel-contractor');
    selC.innerHTML = '<option value="">Seleccione contratista…</option>' +
      contratistas.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');

    const selE = document.getElementById('sel-company');
    selE.innerHTML = '<option value="">Seleccione empresa…</option>' +
      empresas.map(e => `<option value="${esc(e)}">${esc(e)}</option>`).join('');
  } catch (err) {
    showError('Error cargando filtros: ' + err.message);
  }
}

// ── Generate button ──────────────────────────────────────────────────────
document.getElementById('btn-generate').addEventListener('click', async () => {
  const contractor = document.getElementById('sel-contractor').value;
  const company    = document.getElementById('sel-company').value;
  const dateFrom   = document.getElementById('inp-date-from').value;
  const dateTo     = document.getElementById('inp-date-to').value;

  hideError();
  document.getElementById('oc-document').style.display = 'none';
  document.getElementById('empty-box').classList.add('hidden');

  if (!contractor || !company || !dateFrom || !dateTo) {
    showError('Complete todos los filtros antes de generar la orden.');
    return;
  }
  if (dateFrom > dateTo) {
    showError('La fecha de inicio no puede ser posterior a la fecha de término.');
    return;
  }

  const btn = document.getElementById('btn-generate');
  btn.disabled = true;
  btn.textContent = 'Generando…';

  try {
    const params = new URLSearchParams({
      contratista: contractor,
      empresa: company,
      fecha_inicio: dateFrom,
      fecha_termino: dateTo,
    });
    _lastParams = params.toString();
    const res = await fetch('/api/purchase-orders?' + params);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || res.statusText);
    }
    const { header, rows } = await res.json();

    if (!header || !rows.length) {
      document.getElementById('empty-box').classList.remove('hidden');
      return;
    }

    renderDocument(header, rows);
  } catch (err) {
    showError('Error al generar: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generar orden';
  }
});

// ── Render document ──────────────────────────────────────────────────────
function renderDocument(h, rows) {
  document.getElementById('doc-company').textContent    = h.company;
  document.getElementById('doc-contractor').textContent = h.contractor;
  document.getElementById('doc-week').textContent =
    `Semana desde ${fmtDate(h.date_from)} al ${fmtDate(h.date_to)}`;
  document.getElementById('doc-date-from').textContent = fmtDate(h.date_from);
  document.getElementById('doc-date-to').textContent   = fmtDate(h.date_to);
  document.getElementById('doc-grand-total').textContent = fmtCLP.format(h.total);

  document.getElementById('doc-glosa').textContent =
    `SERVICIOS DE LABORES AGRÍCOLAS SEMANA DEL ${fmtDate(h.date_from)} AL ${fmtDate(h.date_to)}`;

  document.getElementById('doc-total-trato').textContent = fmtCLP.format(h.total_trato);
  document.getElementById('doc-total-aldia').textContent = fmtCLP.format(h.total_al_dia);
  document.getElementById('doc-total').textContent       = fmtCLP.format(h.total);

  renderChart(h.pct_trato, h.pct_al_dia);

  const tbody = document.getElementById('doc-tbody');
  tbody.innerHTML = '';
  for (const row of rows) {
    const tipo     = row.tipo_pago || '';
    const label    = PAYMENT_TYPE_LABELS[tipo] || tipo;
    const badgeCls = PAYMENT_TYPE_BADGE[tipo]  || 'badge-aldia';
    const pctVal   = row['% Tipo de pago'];

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="badge ${badgeCls}">${esc(label)}</span></td>
      <td>${esc(String(row['CC'] ?? ''))}</td>
      <td>${esc(row['Nombre Labor'] ?? '')}</td>
      <td class="num">${row.jornadas ?? ''}</td>
      <td class="num">${fmtCLP.format(row.total_unitario ?? 0)}</td>
      <td class="num">${fmtCLP.format(row.total_labor ?? 0)}</td>
      <td class="num">${fmtPct(pctVal)}</td>
    `;
    tbody.appendChild(tr);
  }

  document.getElementById('oc-document').style.display = 'block';
  const btnExport = document.getElementById('btn-odoo-export');
  btnExport.disabled = false;
}

function renderChart(pctTrato, pctAlDia) {
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  chartInstance = new Chart(
    document.getElementById('doc-chart').getContext('2d'),
    {
      type: 'doughnut',
      data: {
        labels: ['A Trato', 'Al Día'],
        datasets: [{
          data: [pctTrato ?? 0, pctAlDia ?? 0],
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

// ── Utils ────────────────────────────────────────────────────────────────
function showError(msg) {
  const el = document.getElementById('error-box');
  el.textContent = msg;
  el.classList.remove('hidden');
}
function hideError() {
  document.getElementById('error-box').classList.add('hidden');
}

// ── Odoo export ──────────────────────────────────────────────────────────
document.getElementById('btn-odoo-export').addEventListener('click', () => {
  if (!_lastParams) return;
  const a = document.createElement('a');
  a.href = '/api/purchase-orders/odoo-export?' + _lastParams;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
});

// ── Init ─────────────────────────────────────────────────────────────────
loadFilters();

// tarjas_detail.js — Tarjas weekly detail page

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0
});
const fmtNum = new Intl.NumberFormat('es-CL');
const fmtPct = v => v != null ? Number(v).toFixed(2) + ' %' : '—';

function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toISO(d) { return d.toISOString().slice(0, 10); }

let chartTipo = null;

// Draws the % value centered on each pie slice. The screen chart previously
// only showed the percentage inside the tooltip on hover; the PDF export
// can't reproduce hover state, so both now show it as a fixed label drawn
// directly on the slice via the Canvas API (no extra dependency).
const percentLabelPlugin = {
  id: 'percentLabel',
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    const meta = chart.getDatasetMeta(0);
    const data = chart.data.datasets[0].data;
    const total = data.reduce((a, b) => a + (Number(b) || 0), 0);
    if (total <= 0) return;

    ctx.save();
    ctx.font = 'bold 12px Helvetica, Arial, sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.strokeStyle = 'rgba(0,0,0,0.55)';
    ctx.lineWidth = 3;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    meta.data.forEach((arc, i) => {
      const value = Number(data[i]) || 0;
      if (value <= 0) return;
      const pct = (value / total * 100).toFixed(1) + '%';
      const { x, y } = arc.tooltipPosition();
      ctx.strokeText(pct, x, y);
      ctx.fillText(pct, x, y);
    });
    ctx.restore();
  }
};

// ── Init dates (current week: Monday to Sunday) ─────────────────────
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

// ── Load filter dropdowns ────────────────────────────────────────────
async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/detalle/filters');
    const data = await res.json();

    fillSelect('fil-contratista', data.contratistas, 'Todos');
    fillSelect('fil-empresa', data.empresas, 'Todas');
    fillSelect('fil-cc', data.centros_costo, 'Todos');
    fillSelect('fil-labor', data.labores, 'Todas');
    fillSelect('fil-campo', data.campos, 'Todos');
  } catch (e) {
    console.error('Error loading filters:', e);
  }
}

function fillSelect(id, items, defaultLabel) {
  const sel = document.getElementById(id);
  sel.innerHTML = `<option value="">${defaultLabel}</option>` +
    items.map(i => `<option value="${esc(String(i))}">${esc(String(i))}</option>`).join('');
}

// ── Query data ───────────────────────────────────────────────────────
async function queryData() {
  const from = document.getElementById('fil-from').value;
  const to   = document.getElementById('fil-to').value;
  if (!from || !to) return;

  const params = new URLSearchParams({
    fecha_inicio: from,
    fecha_termino: to,
  });

  const add = (key, id) => {
    const v = document.getElementById(id)?.value;
    if (v) params.append(key, v);
  };
  add('contratista', 'fil-contratista');
  add('empresa', 'fil-empresa');
  add('centro_costo', 'fil-cc');
  add('tipo_pago', 'fil-tipo');
  add('labor', 'fil-labor');
  add('campo', 'fil-campo');

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';
  let _hasData = false;

  try {
    const res = await fetch('/api/tarjas/detalle?' + params);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (!data.rows.length) {
      document.getElementById('summary-section').style.display = 'none';
      document.getElementById('detail-section').style.display = 'none';
      document.getElementById('empty-state').style.display = 'block';
      return;
    }

    document.getElementById('empty-state').style.display = 'none';
    renderSummary(data.resumen, data.total, data.total_trabajado, data.jornadas);
    renderChart(data.resumen, data.total);
    renderDetail(data.rows, data.count);
    document.getElementById('summary-section').style.display = '';
    document.getElementById('detail-section').style.display = '';
    _hasData = true;
  } catch (e) {
    console.error('Query error:', e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Consultar';
    setDownloadEnabled(_hasData);
  }
}

// ── Render summary table ─────────────────────────────────────────────
function renderSummary(resumen, total, totalTrabajado, jornadas) {
  const TIPO_LABELS = { 'trato': 'Trato', 'Al dia': 'Al Día', 'Al día': 'Al Día' };
  const TIPO_CLASS  = { 'trato': 'tipo-trato', 'Al dia': 'tipo-aldia', 'Al día': 'tipo-aldia' };

  const tbody = document.getElementById('summary-tbody');
  tbody.innerHTML = resumen.map(r => {
    const label = TIPO_LABELS[r.tipo_pago] || r.tipo_pago;
    const cls = TIPO_CLASS[r.tipo_pago] || '';
    return `<tr>
      <td><span class="${cls}">${esc(label)}</span></td>
      <td class="num">${fmtCLP.format(r.total_pagar)}</td>
      <td class="num">${fmtCLP.format(r.total_trabajado)}</td>
      <td class="num">${fmtNum.format(r.jornadas)}</td>
    </tr>`;
  }).join('');

  document.getElementById('summary-total').textContent = fmtCLP.format(total);
  document.getElementById('summary-trabajado').textContent = fmtCLP.format(totalTrabajado || 0);
  document.getElementById('summary-jornadas').textContent = fmtNum.format(jornadas);
}

// ── Render pie chart ─────────────────────────────────────────────────
function renderChart(resumen, total) {
  if (chartTipo) chartTipo.destroy();

  const labels = resumen.map(r => {
    if (r.tipo_pago === 'trato') return 'Trato';
    if (r.tipo_pago === 'Al dia' || r.tipo_pago === 'Al día') return 'Al Día';
    return r.tipo_pago;
  });
  const values = resumen.map(r => r.total_pagar);
  const colors = resumen.map(r =>
    r.tipo_pago === 'trato' ? '#3b82f6' : '#f97316'
  );

  chartTipo = new Chart(document.getElementById('chart-tipo').getContext('2d'), {
    type: 'pie',
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: colors, borderWidth: 2 }]
    },
    plugins: [percentLabelPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { font: { size: 12 }, boxWidth: 14, padding: 12 }
        },
        tooltip: {
          callbacks: {
            label: c => {
              const pct = total > 0 ? (c.parsed / total * 100).toFixed(1) : 0;
              return `${c.label}: ${fmtCLP.format(c.parsed)} (${pct}%)`;
            }
          }
        }
      }
    }
  });
}

// ── Render detail table ──────────────────────────────────────────────
function renderDetail(rows, count) {
  document.getElementById('detail-count').textContent = `${count} registro${count !== 1 ? 's' : ''}`;

  const TIPO_CLASS = { 'trato': 'tipo-trato', 'Al dia': 'tipo-aldia', 'Al día': 'tipo-aldia' };
  const TIPO_LABEL = { 'trato': 'Trato', 'Al dia': 'Al Día', 'Al día': 'Al Día' };

  const tbody = document.getElementById('detail-tbody');
  tbody.innerHTML = rows.map(r => {
    const cls = TIPO_CLASS[r.tipo_pago] || '';
    const label = TIPO_LABEL[r.tipo_pago] || r.tipo_pago;
    return `<tr>
      <td><span class="${cls}">${esc(label)}</span></td>
      <td>${esc(r.labor ?? '')}</td>
      <td>${esc(String(r.centro_costo ?? ''))}</td>
      <td>${esc(r.centro_costo_nombre || '—')}</td>
      <td class="num">${r.costo_hora != null ? fmtCLP.format(r.costo_hora) : '—'}</td>
      <td class="num">${r.jornadas ?? '—'}</td>
      <td class="num">${r.total_unitario != null ? fmtCLP.format(r.total_unitario) : '—'}</td>
      <td class="num">${r.costo_total != null ? fmtCLP.format(r.costo_total) : '—'}</td>
      <td class="num">${r.total_trabajado != null ? fmtCLP.format(r.total_trabajado) : '—'}</td>
      <td class="num">${fmtPct(r.pct_pago)}</td>
    </tr>`;
  }).join('');

  const sumJornadas = rows.reduce((s, r) => s + Number(r.jornadas || 0), 0);
  const sumCosto = rows.reduce((s, r) => s + Number(r.costo_total || 0), 0);
  const sumTrab = rows.reduce((s, r) => s + Number(r.total_trabajado || 0), 0);
  document.getElementById('detail-tfoot').innerHTML = `<tr>
    <td colspan="4"><strong>Total</strong></td>
    <td></td>
    <td class="num"><strong>${fmtNum.format(sumJornadas)}</strong></td>
    <td></td>
    <td class="num"><strong>${fmtCLP.format(sumCosto)}</strong></td>
    <td class="num"><strong>${fmtCLP.format(sumTrab)}</strong></td>
    <td class="num"><strong>${sumCosto > 0 ? '100.00 %' : '—'}</strong></td>
  </tr>`;
}

// ── Download helpers ─────────────────────────────────────────────────
function currentParams() {
  const p = new URLSearchParams({
    fecha_inicio: document.getElementById('fil-from').value,
    fecha_termino: document.getElementById('fil-to').value,
  });
  const add = (key, id) => { const v = document.getElementById(id)?.value; if (v) p.append(key, v); };
  add('contratista','fil-contratista');
  add('empresa','fil-empresa');
  add('centro_costo','fil-cc');
  add('tipo_pago','fil-tipo');
  add('labor','fil-labor');
  add('campo','fil-campo');
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
const FILTER_IDS = ['fil-from', 'fil-to', 'fil-contratista', 'fil-empresa', 'fil-cc', 'fil-labor', 'fil-campo', 'fil-tipo'];

async function loadFiltersAndRestore() {
  // Set default dates first so inputs are never empty when no URL params exist
  initDates();
  // Populate dynamic selects, then restore URL params so select values find their <option>
  await loadFilters();
  autoTriggerFromURL(FILTER_IDS, queryData);
}

// ── Events ───────────────────────────────────────────────────────────
document.getElementById('btn-apply').addEventListener('click', () => {
  queryData().then(() => syncFiltersToURL(FILTER_IDS));
});
document.getElementById('btn-excel').addEventListener('click', () => {
  window.location.href = '/api/tarjas/detalle/download-excel?' + currentParams();
});
document.getElementById('btn-pdf').addEventListener('click', () => {
  window.open('/api/tarjas/detalle/download-pdf?' + currentParams(), '_blank');
});

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') queryData().then(() => syncFiltersToURL(FILTER_IDS)); });
});

bindPopstate(FILTER_IDS, queryData);

// ── Init ─────────────────────────────────────────────────────────────
loadFiltersAndRestore();

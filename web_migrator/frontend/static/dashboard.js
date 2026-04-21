// dashboard.js — Dashboard page logic

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0
});
const fmtNum = new Intl.NumberFormat('es-CL');

function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtDate(s) {
  if (!s) return '—';
  const [y, m, d] = s.split('-');
  return `${d}/${m}`;
}

function fmtDateFull(s) {
  if (!s) return '—';
  const [y, m, d] = s.split('-');
  return `${d}/${m}/${y}`;
}

function toISO(d) { return d.toISOString().slice(0, 10); }

let chartDaily = null;
let chartTipo = null;

// ── Date filter setup ────────────────────────────────────────────────
function initDateFilter() {
  const now = new Date();
  const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  document.getElementById('fil-date-from').value = toISO(firstOfMonth);
  document.getElementById('fil-date-to').value = toISO(now);
}

function getDateParams() {
  const from = document.getElementById('fil-date-from').value;
  const to   = document.getElementById('fil-date-to').value;
  if (!from || !to) return '';
  return `fecha_inicio=${from}&fecha_termino=${to}`;
}

function setPreset(days) {
  const now = new Date();
  let from;

  if (days === 30) {
    from = new Date(now.getFullYear(), now.getMonth(), 1);
  } else {
    from = new Date(now);
    from.setDate(from.getDate() - days + 1);
  }

  document.getElementById('fil-date-from').value = toISO(from);
  document.getElementById('fil-date-to').value = toISO(now);

  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
}

document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.addEventListener('click', e => {
    setPreset(parseInt(btn.dataset.days));
    loadDashboard();
  });
});

document.getElementById('btn-apply-filter').addEventListener('click', () => {
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  loadDashboard();
});

// allow Enter key on date inputs
document.querySelectorAll('#fil-date-from, #fil-date-to').forEach(el => {
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
      loadDashboard();
    }
  });
});

// ── Load dashboard data ──────────────────────────────────────────────
async function loadDashboard() {
  try {
    const params = getDateParams();
    const url = '/api/dashboard' + (params ? '?' + params : '');
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    updateRangeLabels();
    renderKPIs(data);
    renderDailyChart(data.tarjas_daily);
    renderTipoChart(data.tarjas_period);
    renderTopContratistas(data.top_contratistas);
    renderTopLabores(data.top_labores);
    renderAlerts(data.sensor_alerts, data.sensors_by_source);
  } catch(e) {
    console.error('Dashboard load error:', e);
  }
}

function updateRangeLabels() {
  const from = document.getElementById('fil-date-from').value;
  const to   = document.getElementById('fil-date-to').value;
  const label = `${fmtDateFull(from)} — ${fmtDateFull(to)}`;
  document.getElementById('badge-contratistas').textContent = label;
  document.getElementById('badge-labores').textContent = label;
  document.getElementById('chart-daily-title').textContent = `Pagos diarios`;
}

// ── KPI Cards ────────────────────────────────────────────────────────
function renderKPIs(data) {
  const tp = data.tarjas_period;
  const s = data.sensors;

  document.getElementById('kpi-total-mes').textContent = fmtCLP.format(tp.total_periodo);

  const prev = tp.total_anterior || 0;
  if (prev > 0) {
    const pctChange = ((tp.total_periodo - prev) / prev * 100).toFixed(1);
    const cls = pctChange >= 0 ? 'up' : 'down';
    const arrow = pctChange >= 0 ? '↑' : '↓';
    document.getElementById('kpi-total-trend').innerHTML =
      `<span class="${cls}">${arrow} ${Math.abs(pctChange)}%</span> vs período anterior`;
  } else {
    document.getElementById('kpi-total-trend').textContent = 'Sin datos del período anterior';
  }

  document.getElementById('kpi-contratistas').textContent = tp.contratistas_activos;
  document.getElementById('kpi-contratistas-sub').textContent =
    `en ${tp.campos_activos} campo${tp.campos_activos !== 1 ? 's' : ''}`;

  document.getElementById('kpi-jornadas').textContent = fmtNum.format(tp.jornadas_periodo);
  document.getElementById('kpi-jornadas-sub').textContent =
    `${tp.labores_distintas} labores distintas`;

  const pctOnline = s.total > 0 ? Math.round(s.online / s.total * 100) : 0;
  document.getElementById('kpi-sensors').textContent = `${s.online} / ${s.total}`;
  document.getElementById('kpi-sensors-sub').textContent =
    s.offline > 0
      ? `${s.offline} offline · ${pctOnline}% operativo`
      : `${pctOnline}% operativo · ${s.campos} campos`;
}

// ── Daily payments chart ─────────────────────────────────────────────
function renderDailyChart(daily) {
  if (chartDaily) chartDaily.destroy();
  const ctx = document.getElementById('chart-daily').getContext('2d');
  chartDaily = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: daily.map(d => fmtDate(d.dia)),
      datasets: [{
        label: 'Total diario',
        data: daily.map(d => d.total),
        backgroundColor: '#3b82f6',
        borderRadius: 4,
        barPercentage: 0.7,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: c => fmtCLP.format(c.parsed.y) }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: v => v >= 1000000 ? `$${(v/1000000).toFixed(1)}M` : `$${(v/1000).toFixed(0)}K`,
            font: { size: 11 }
          },
          grid: { color: '#f1f5f9' }
        },
        x: {
          ticks: { font: { size: 11 } },
          grid: { display: false }
        }
      }
    }
  });
}

// ── Payment type doughnut ────────────────────────────────────────────
function renderTipoChart(tp) {
  if (chartTipo) chartTipo.destroy();
  const ctx = document.getElementById('chart-tipo').getContext('2d');
  chartTipo = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['A Trato', 'Al Día'],
      datasets: [{
        data: [tp.total_trato, tp.total_al_dia],
        backgroundColor: ['#3b82f6', '#22c55e'],
        borderWidth: 2,
      }]
    },
    options: {
      cutout: '65%',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { font: { size: 12 }, boxWidth: 14, padding: 16 }
        },
        tooltip: {
          callbacks: { label: c => `${c.label}: ${fmtCLP.format(c.parsed)}` }
        }
      }
    }
  });
}

// ── Top contratistas table ───────────────────────────────────────────
function renderTopContratistas(rows) {
  const tbody = document.getElementById('tbl-contratistas');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="loading-cell">Sin datos</td></tr>';
    return;
  }
  const max = rows[0].total;
  tbody.innerHTML = rows.map(r => {
    const pct = max > 0 ? Math.round(r.total / max * 100) : 0;
    return `<tr>
      <td>
        <div style="font-weight:600">${esc(r.contratista)}</div>
        <div class="progress-bar-wrap"><div class="progress-bar" style="width:${pct}%"></div></div>
      </td>
      <td class="num">${fmtCLP.format(r.total)}</td>
    </tr>`;
  }).join('');
}

// ── Top labores table ────────────────────────────────────────────────
function renderTopLabores(rows) {
  const tbody = document.getElementById('tbl-labores');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="loading-cell">Sin datos</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r =>
    `<tr>
      <td style="font-weight:600">${esc(r.labor)}</td>
      <td class="num">${fmtNum.format(r.jornadas)}</td>
      <td class="num">${fmtCLP.format(r.total)}</td>
    </tr>`
  ).join('');
}

// ── Sensor alerts ────────────────────────────────────────────────────
function renderAlerts(alerts, sources) {
  const container = document.getElementById('sensor-alerts');

  if (!alerts.length) {
    container.innerHTML = '<div class="alert-empty">Todos los sensores operativos</div>';
  } else {
    container.innerHTML = '<div class="alert-list">' + alerts.map(a => {
      const lastSeen = a.last_seen ? fmtDate(a.last_seen) : 'sin datos';
      return `<div class="alert-item">
        <div class="alert-dot"></div>
        <span class="alert-name">${esc(a.sensor_name)}</span>
        <span style="color:var(--text-muted);font-size:12px">${esc(a.field)} · ${esc(a.source)}</span>
        <span class="alert-meta">Último: ${lastSeen}</span>
      </div>`;
    }).join('') + '</div>';
  }

  const srcContainer = document.getElementById('sensor-sources');
  srcContainer.innerHTML = sources.map(s =>
    `<div class="source-badge">
      <div class="source-dot source-dot--${esc(s.source)}"></div>
      ${esc(s.source)}: ${s.online}/${s.total} online
    </div>`
  ).join('');
}

// ── Init ─────────────────────────────────────────────────────────────
initDateFilter();
loadDashboard();

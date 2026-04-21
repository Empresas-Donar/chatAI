// sensor_status.js — Status Diario page logic

let allRows = [];

async function init() {
  await loadStatus();
}

async function loadStatus() {
  const field = document.getElementById('fil-field').value;
  const days  = document.getElementById('fil-days').value;

  const params = new URLSearchParams({ days });
  if (field) params.append('field', field);

  try {
    const res  = await fetch('/api/sensors/status?' + params);
    const data = await res.json();
    allRows = data.rows;

    const sel = document.getElementById('fil-field');
    if (sel.options.length <= 1 && data.fields.length) {
      const current = sel.value;
      sel.innerHTML = '<option value="">Todos los campos</option>' +
        data.fields.map(f => `<option value="${esc(f)}"${f === current ? ' selected' : ''}>${esc(f)}</option>`).join('');
      sel.value = current;
    }

    renderCalendar(allRows);
    renderTable(allRows);
  } catch(e) {
    document.getElementById('status-tbody').innerHTML =
      `<tr class="empty-row"><td colspan="8">Error cargando datos</td></tr>`;
    console.error(e);
  }
}

// ── Calendar heatmap ─────────────────────────────────────────────────────
function renderCalendar(rows) {
  const byField = {};
  for (const r of rows) {
    if (!byField[r.field]) byField[r.field] = {};
    byField[r.field][r.date] = r;
  }

  const days = parseInt(document.getElementById('fil-days').value);
  const dates = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    dates.push(d.toISOString().slice(0, 10));
  }

  const grid = document.getElementById('calendar-grid');
  grid.innerHTML = '';

  for (const [fieldName, dayMap] of Object.entries(byField)) {
    const row = document.createElement('div');
    row.className = 'cal-field-row';

    const label = document.createElement('div');
    label.className = 'cal-field-label';
    label.textContent = fieldName;
    row.appendChild(label);

    const daysDiv = document.createElement('div');
    daysDiv.className = 'cal-days';

    for (const date of dates) {
      const rec  = dayMap[date];
      const cell = document.createElement('div');
      const [y, m, d] = date.split('-');
      const dayNum = parseInt(d);

      let cls = 'empty';
      let tip = `${d}-${m}-${y}: sin datos`;

      if (rec) {
        cls = rec.status === 'ok' ? 'ok' : (rec.status === 'warn' ? 'warn' : 'offline');
        const wc  = rec.wc_executions  ? `WC: ${rec.wc_executions}` : '';
        const ubi = rec.ubibot_channels != null ? `Ubibot: ${rec.ubibot_channels} ch` : '';
        const tmp = rec.temp_avg != null ? `Temp: ${rec.temp_avg}°C` : '';
        tip = `${d}-${m}-${y} · ${[wc, ubi, tmp].filter(Boolean).join(' · ')}`;
        if (rec.notes) tip += `\n${rec.notes}`;
      }

      cell.className = `cal-day ${cls}`;
      cell.textContent = dayNum;

      const tooltip = document.createElement('div');
      tooltip.className = 'tooltip';
      tooltip.textContent = tip;
      cell.appendChild(tooltip);

      daysDiv.appendChild(cell);
    }
    row.appendChild(daysDiv);
    grid.appendChild(row);
  }

  if (!Object.keys(byField).length) {
    grid.innerHTML = '<span style="color:var(--text-muted);font-size:13px">Sin datos para el período seleccionado</span>';
  }
}

// ── Table ────────────────────────────────────────────────────────────────
function renderTable(rows) {
  setText('tbl-count', `${rows.length} registro${rows.length !== 1 ? 's' : ''}`);

  if (!rows.length) {
    document.getElementById('status-tbody').innerHTML =
      `<tr class="empty-row"><td colspan="8">Sin registros</td></tr>`;
    return;
  }

  const tbody = document.getElementById('status-tbody');
  tbody.innerHTML = '';

  for (const r of rows) {
    const [y, m, d] = r.date.split('-');
    const dateStr = `${d}-${m}-${y}`;

    let wcHtml = '—';
    if (r.wc_executions) {
      const parts = r.wc_executions.split('/');
      const isOk  = parts.length === 2 && parts[0] === parts[1];
      wcHtml = `<span class="wc-exec ${isOk ? 'wc-ok' : 'wc-warn'}">${esc(r.wc_executions)}</span>`;
    }

    let tempHtml = '—';
    if (r.temp_avg != null) {
      tempHtml = `<span class="temp-cell">
        <span class="temp-avg">${r.temp_avg}°</span>
        <span class="temp-min">↓${r.temp_min ?? '–'}°</span>
        <span class="temp-max">↑${r.temp_max ?? '–'}°</span>
      </span>`;
    }

    const statusCls = r.status === 'ok' ? 'badge-ok' : (r.status === 'warn' ? 'badge-warn' : 'badge-offline');
    const statusLbl = r.status === 'ok' ? 'OK' : (r.status === 'warn' ? 'Alerta' : 'Offline');
    const irrHtml   = r.irrigation_mm != null ? `${r.irrigation_mm} mm` : '—';
    const noteHtml  = r.notes ? `<span class="note-cell" title="${esc(r.notes)}">${esc(r.notes)}</span>` : '—';

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${dateStr}</strong></td>
      <td>${esc(r.field)}</td>
      <td><span class="badge ${statusCls}">${statusLbl}</span></td>
      <td class="num">${wcHtml}</td>
      <td class="num">${r.ubibot_channels != null ? r.ubibot_channels : '—'}</td>
      <td class="num">${tempHtml}</td>
      <td class="num">${irrHtml}</td>
      <td>${noteHtml}</td>
    `;
    tbody.appendChild(tr);
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Events ───────────────────────────────────────────────────────────────
document.getElementById('fil-field').addEventListener('change', loadStatus);
document.getElementById('fil-days').addEventListener('change',  loadStatus);

init();

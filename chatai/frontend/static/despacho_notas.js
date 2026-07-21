/* despacho_notas.js — Notas de crédito page logic */
'use strict';

let _lastParams   = null;
let _currentData  = null; // stores last renderDocument data for NC redistribution

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
  document.getElementById('nc-section').style.display  = 'none';
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

// ── NC Amount — proportional distribution ─────────────────────────────────

function parseCLPInput(raw) {
  // Accept "700.000", "700000", "$700.000" etc.
  const cleaned = String(raw).replace(/[$\s]/g, '').replace(/\./g, '').replace(/,/g, '.');
  const n = parseInt(cleaned, 10);
  return isNaN(n) ? null : n;
}

function distributeProportional(rows, ncTotal) {
  // Largest-remainder method so sum === ncTotal exactly
  const originalTotal = rows.reduce((s, r) => s + (r.total_pagar ?? 0), 0);
  if (!originalTotal) return rows.map(r => ({ ...r, nc_pagar: 0 }));

  const exact    = rows.map(r => (r.total_pagar ?? 0) / originalTotal * ncTotal);
  const floored  = exact.map(Math.floor);
  const remain   = ncTotal - floored.reduce((s, v) => s + v, 0);

  // Sort indices by descending fractional part
  const fracs = exact.map((v, i) => ({ i, frac: v - floored[i] }))
    .sort((a, b) => b.frac - a.frac);

  const adjusted = [...floored];
  for (let k = 0; k < remain; k++) adjusted[fracs[k].i]++;

  return rows.map((r, i) => ({ ...r, nc_pagar: adjusted[i] }));
}

function applyNC(ncTotal) {
  if (!_currentData) return;
  const { rows, total_general } = _currentData;

  const adjusted = distributeProportional(rows, ncTotal);

  const tbody = document.getElementById('doc-tbody');
  const trs   = tbody.querySelectorAll('tr');

  let ncTrato = 0, ncAldia = 0;

  adjusted.forEach((row, idx) => {
    const td = trs[idx]?.querySelectorAll('td');
    if (!td) return;
    td[5].innerHTML = `<span class="nc-val">${fmtCLP.format(row.nc_pagar)}</span>`;
    trs[idx].classList.add('nc-adjusted');
    if (isTrato(row.tipo_pago)) ncTrato += row.nc_pagar;
    else ncAldia += row.nc_pagar;
  });

  document.getElementById('doc-total-trato').textContent = fmtCLP.format(ncTrato);
  document.getElementById('doc-total-aldia').textContent = fmtCLP.format(ncAldia);
  document.getElementById('doc-total').textContent       = fmtCLP.format(ncTotal);
  document.getElementById('doc-grand-total').textContent = fmtCLP.format(ncTotal);

  const pctTrato = ncTotal ? (ncTrato / ncTotal) * 100 : 0;
  const pctAldia = ncTotal ? (ncAldia / ncTotal) * 100 : 0;
  renderChart(pctTrato, pctAldia);
}

function restoreOriginals() {
  if (!_currentData) return;
  const { rows, total_trato, total_aldia, total_general } = _currentData;

  const tbody = document.getElementById('doc-tbody');
  const trs   = tbody.querySelectorAll('tr');

  rows.forEach((row, idx) => {
    const td = trs[idx]?.querySelectorAll('td');
    if (!td) return;
    td[5].innerHTML = fmtCLP.format(row.total_pagar ?? 0);
    trs[idx].classList.remove('nc-adjusted');
  });

  document.getElementById('doc-total-trato').textContent = fmtCLP.format(total_trato);
  document.getElementById('doc-total-aldia').textContent = fmtCLP.format(total_aldia);
  document.getElementById('doc-total').textContent       = fmtCLP.format(total_general);
  document.getElementById('doc-grand-total').textContent = fmtCLP.format(total_general);

  const pctTrato = total_general ? (total_trato / total_general) * 100 : 0;
  const pctAldia = total_general ? (total_aldia / total_general) * 100 : 0;
  renderChart(pctTrato, pctAldia);
}

// NC input wiring
document.getElementById('nc-amount').addEventListener('input', function () {
  const val = parseCLPInput(this.value);
  const msg = document.getElementById('nc-validation');
  const clearBtn = document.getElementById('nc-clear');

  if (!this.value.trim()) {
    msg.textContent = '';
    msg.className   = 'nc-validation';
    clearBtn.style.display = 'none';
    restoreOriginals();
    return;
  }

  if (val === null || val <= 0) {
    msg.textContent = '⚠ Ingresa un monto válido (ej: 700.000)';
    msg.className   = 'nc-validation err';
    clearBtn.style.display = 'none';
    return;
  }

  applyNC(val);
  msg.textContent = `✓ Distribuido: ${fmtCLP.format(val)}`;
  msg.className   = 'nc-validation ok';
  clearBtn.style.display = 'inline';
});

document.getElementById('nc-clear').addEventListener('click', function () {
  document.getElementById('nc-amount').value = '';
  document.getElementById('nc-validation').textContent = '';
  document.getElementById('nc-validation').className   = 'nc-validation';
  this.style.display = 'none';
  restoreOriginals();
});

// ── Render document ───────────────────────────────────────────────────────
function renderDocument(data, from, to, contratista) {
  _currentData = data; // save for NC redistribution
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

  // show NC section and reset it
  const ncSection = document.getElementById('nc-section');
  ncSection.style.display = 'flex';
  document.getElementById('nc-amount').value = '';
  document.getElementById('nc-validation').textContent = '';
  document.getElementById('nc-validation').className   = 'nc-validation';
  document.getElementById('nc-clear').style.display    = 'none';

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

// ── CC Sync Modal ─────────────────────────────────────────────────────────

const ccModal = {
  overlay:      () => document.getElementById('cc-sync-modal'),
  loading:      () => document.getElementById('cc-modal-loading'),
  content:      () => document.getElementById('cc-modal-content'),
  error:        () => document.getElementById('cc-modal-error'),
  lastSync:     () => document.getElementById('cc-last-sync'),
  archivedAlert:() => document.getElementById('cc-archived-alert'),
  exclCountMsg: () => document.getElementById('cc-excluded-count-msg'),
  bqAlert:      () => document.getElementById('cc-bq-unavail-alert'),
  rowsCount:    () => document.getElementById('cc-rows-count'),
  exclCount:    () => document.getElementById('cc-excluded-count'),
  exclChip:     () => document.getElementById('cc-excluded-chip'),
  previewTbody: () => document.getElementById('cc-preview-tbody'),
  previewTfoot: () => document.getElementById('cc-preview-tfoot'),
  btnSync:      () => document.getElementById('btn-cc-do-sync'),
  btnProceed:   () => document.getElementById('btn-cc-proceed'),
};

function formatSyncDate(isoStr) {
  if (!isoStr) return 'Nunca';
  try {
    const d = new Date(isoStr + 'Z');
    const diff = Math.floor((Date.now() - d) / 60000);
    if (diff < 1)  return 'Hace un momento';
    if (diff < 60) return `Hace ${diff} minutos`;
    const h = Math.floor(diff / 60);
    if (h < 24)   return `Hace ${h} hora${h > 1 ? 's' : ''}`;
    const days = Math.floor(h / 24);
    return `Hace ${days} día${days > 1 ? 's' : ''} — ${d.toLocaleDateString('es-CL', { day:'numeric', month:'short', year:'numeric' })}`;
  } catch {
    return isoStr;
  }
}

async function loadExportPreview() {
  ccModal.loading().style.display = 'flex';
  ccModal.content().classList.add('hidden');
  ccModal.error().classList.add('hidden');

  try {
    // Preview endpoint uses 'empresa' for nombre_campo — map 'campo' to it
    const { contratista, campo, fecha_inicio, fecha_termino } = _lastParams;
    const previewParams = new URLSearchParams({
      contratista,
      empresa: campo,
      fecha_inicio,
      fecha_termino,
    });
    const res = await fetch('/api/tarjas/export-preview?' + previewParams);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    ccModal.lastSync().textContent = formatSyncDate(data.last_sync);

    const okRows   = data.rows     ?? [];
    const exclRows = data.excluded ?? [];
    const totalRows = okRows.length + exclRows.length;

    ccModal.rowsCount().textContent = okRows.length;
    ccModal.exclCount().textContent = exclRows.length;
    ccModal.exclChip().style.display = exclRows.length > 0 ? '' : 'none';

    if (!data.bq_available) {
      ccModal.bqAlert().classList.remove('hidden');
      ccModal.archivedAlert().classList.add('hidden');
      ccModal.btnSync().disabled = true;
    } else {
      ccModal.bqAlert().classList.add('hidden');
      if (exclRows.length > 0) {
        ccModal.exclCountMsg().textContent = exclRows.length;
        ccModal.archivedAlert().classList.remove('hidden');
        ccModal.btnSync().disabled = false;
      } else {
        ccModal.archivedAlert().classList.add('hidden');
        ccModal.btnSync().disabled = true;
      }
    }

    function renderAnalytic(raw, archivedIds) {
      if (!raw || raw === '–') return '–';
      const archived = new Set(archivedIds ?? []);
      try {
        const obj = JSON.parse(raw);
        return Object.entries(obj).map(([id, pct]) => {
          const val = `"${id}": ${Number(pct).toFixed(2)}`;
          return archived.has(id)
            ? `<span class="cc-id-error" title="CC archivado">${esc(val)}</span>`
            : esc(val);
        }).join(', ');
      } catch {
        return esc(raw);
      }
    }

    let totalQty = 0, totalAmt = 0;

    const okHtml = okRows.map(r => {
      totalQty += r.qty ?? 0;
      totalAmt += r.total ?? 0;
      return `<tr>
        <td>${esc(r.product_id ?? '–')}</td>
        <td class="num">${r.qty ?? 0}</td>
        <td class="cc-analytic">{${renderAnalytic(r.analytic_distribution, [])}}</td>
        <td class="num">${Number(r.price_unit ?? 0).toLocaleString('es-CL')}</td>
        <td><span class="cc-badge cc-badge-ok">OK</span></td>
      </tr>`;
    }).join('');

    const exclHtml = exclRows.map(r => `<tr class="cc-row-error">
      <td>${esc(r.product_id ?? '–')}</td>
      <td class="num">${r.qty ?? 0}</td>
      <td class="cc-analytic">{${renderAnalytic(r.analytic_distribution, r.archived_ids ?? [])}}</td>
      <td class="num">${Number(r.price_unit ?? 0).toLocaleString('es-CL')}</td>
      <td><span class="cc-badge cc-badge-archived" title="${esc(r.reason ?? '')}">⚠ Incompleta</span></td>
    </tr>`).join('');

    if (totalRows === 0) {
      ccModal.previewTbody().innerHTML = '<tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:24px">Sin líneas para este período</td></tr>';
      ccModal.previewTfoot().innerHTML = '';
    } else {
      ccModal.previewTbody().innerHTML = okHtml + exclHtml;
      ccModal.previewTfoot().innerHTML = `<tr>
        <td><strong>Total exportable</strong></td>
        <td class="num">${totalQty}</td>
        <td></td><td></td><td></td>
      </tr>`;
    }

    ccModal.loading().style.display = 'none';
    ccModal.content().classList.remove('hidden');
  } catch (e) {
    ccModal.loading().style.display = 'none';
    const el = ccModal.error();
    el.innerHTML = '<span class="cc-alert-icon">⚠️</span> Error al cargar vista previa: ' + esc(e.message);
    el.classList.remove('hidden');
  }
}

function openCCModal() {
  ccModal.overlay().classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  loadExportPreview();
}

function closeCCModal() {
  ccModal.overlay().classList.add('hidden');
  document.body.style.overflow = '';
}

ccModal.btnSync().addEventListener('click', async () => {
  const btn = ccModal.btnSync();
  btn.disabled = true;
  btn.textContent = 'Sincronizando…';
  ccModal.error().classList.add('hidden');
  try {
    const res = await fetch('/api/tarjas/sync-cc', { method: 'POST' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || res.statusText);
    }
    const data = await res.json();
    await loadExportPreview();
    if (data.fixed > 0) {
      const successEl = document.createElement('div');
      successEl.className = 'cc-alert cc-alert-success';
      successEl.innerHTML = `<span class="cc-alert-icon">✅</span><div>${data.message}</div>`;
      ccModal.content().insertBefore(successEl, ccModal.content().firstChild);
      setTimeout(() => successEl.remove(), 6000);
    }
  } catch (e) {
    const el = ccModal.error();
    el.textContent = '⚠️ Error en la sincronización: ' + e.message;
    el.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Sincronizar CCs con Odoo';
  }
});

ccModal.btnProceed().addEventListener('click', async () => {
  closeCCModal();
  await doOdooExport();
});

document.getElementById('btn-cc-cancel').addEventListener('click', closeCCModal);
document.getElementById('btn-cc-modal-close').addEventListener('click', closeCCModal);
ccModal.overlay().addEventListener('click', e => {
  if (e.target === ccModal.overlay()) closeCCModal();
});

// ── Odoo export ───────────────────────────────────────────────────────────

async function doOdooExport() {
  if (!_lastParams) return;
  const { contratista, campo, fecha_inicio, fecha_termino } = _lastParams;

  const btn = document.getElementById('btn-odoo-export');
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Generando archivo…';

  try {
    const params = new URLSearchParams({ contratista, campo, fecha_inicio, fecha_termino });
    const ncVal = parseCLPInput(document.getElementById('nc-amount').value);
    if (ncVal && ncVal > 0) params.set('nc_total', ncVal);

    const res = await fetch('/api/tarjas/notas/odoo-export?' + params);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || res.statusText);
    }

    const excludedAmount = parseInt(res.headers.get('X-Excluded-Amount') || '0');
    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : 'odoo-nota.xlsx';

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    if (excludedAmount > 0) {
      alert(`⚠️ Advertencia: ${fmtCLP.format(excludedAmount)} fueron excluidos del archivo porque hay labores o centros de costo sin mapear en Odoo.`);
    }
  } catch (e) {
    showError('Error al exportar: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

document.getElementById('btn-odoo-export').addEventListener('click', () => {
  if (!_lastParams) return;
  if (!_lastParams.campo) { showError('Selecciona un campo específico para exportar a Odoo.'); return; }
  openCCModal();
});

document.getElementById('btn-print-pdf').addEventListener('click', () => {
  if (!_lastParams) return;
  const { contratista, campo, fecha_inicio, fecha_termino } = _lastParams;
  const params = new URLSearchParams({ contratista, campo, fecha_inicio, fecha_termino });
  const ncVal = parseCLPInput(document.getElementById('nc-amount').value);
  if (ncVal && ncVal > 0) params.set('nc_total', ncVal);
  window.open('/api/tarjas/notas/print-pdf?' + params, '_blank');
});

// ── URL filter sync ───────────────────────────────────────────────────────
const FILTER_IDS = ['fil-from', 'fil-to', 'fil-contratista', 'fil-campo'];

// Sync URL when user clicks "Generar nota" (secondary listener stacks on the primary above)
document.getElementById('btn-apply').addEventListener('click', () => {
  // Sync only if minimum required field is filled (avoid polluting URL on empty-click)
  if (document.getElementById('fil-contratista').value) {
    syncFiltersToURL(FILTER_IDS);
  }
});

// ── Init ──────────────────────────────────────────────────────────────────
setDefaultDates();
// Restore URL params after selects are populated; no auto-trigger (document requires deliberate action)
loadFilters().then(() => loadFiltersFromURL(FILTER_IDS));

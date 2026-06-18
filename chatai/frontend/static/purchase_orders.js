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

// ── CC Sync Modal ────────────────────────────────────────────────────────

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
  okWrap:       () => document.getElementById('cc-ok-wrap'),
  okLabel:      () => document.getElementById('cc-label-ok'),
  okTbody:      () => document.getElementById('cc-ok-tbody'),
  okTfoot:      () => document.getElementById('cc-ok-tfoot'),
  exclWrap:     () => document.getElementById('cc-excl-wrap'),
  exclLabel:    () => document.getElementById('cc-label-excl'),
  exclTbody:    () => document.getElementById('cc-excl-tbody'),
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
    const res = await fetch('/api/tarjas/export-preview?' + _lastParams);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Last sync
    ccModal.lastSync().textContent = formatSyncDate(data.last_sync);

    // Summary chips
    ccModal.rowsCount().textContent = data.rows_count ?? 0;
    ccModal.exclCount().textContent = data.excluded_count ?? 0;
    ccModal.exclChip().style.display = (data.excluded_count > 0) ? '' : 'none';

    // Alerts
    if (!data.bq_available) {
      ccModal.bqAlert().classList.remove('hidden');
      ccModal.archivedAlert().classList.add('hidden');
      ccModal.btnSync().disabled = true;
    } else {
      ccModal.bqAlert().classList.add('hidden');
      if (data.excluded_count > 0) {
        ccModal.exclCountMsg().textContent = data.excluded_count;
        ccModal.archivedAlert().classList.remove('hidden');
        ccModal.btnSync().disabled = false;
      } else {
        ccModal.archivedAlert().classList.add('hidden');
        ccModal.btnSync().disabled = true;
      }
    }

    // Ok rows table
    const okRows = data.rows ?? [];
    ccModal.okLabel().style.display = '';
    ccModal.okWrap().style.display = '';
    if (okRows.length) {
      let totalQty = 0, totalAmt = 0;
      ccModal.okTbody().innerHTML = okRows.map(r => {
        totalQty += r.qty ?? 0;
        totalAmt += r.total ?? 0;
        return `<tr>
          <td>${esc(r.product_id ?? '–')}</td>
          <td>${esc(r.cc_display ?? '–')}</td>
          <td class="num">${r.qty ?? 0}</td>
          <td class="num">${fmtCLP.format(r.price_unit ?? 0)}</td>
          <td class="num">${fmtCLP.format(r.total ?? 0)}</td>
        </tr>`;
      }).join('');
      ccModal.okTfoot().innerHTML = `<tr>
        <td colspan="2"><strong>Total</strong></td>
        <td class="num">${totalQty}</td>
        <td class="num">–</td>
        <td class="num">${fmtCLP.format(totalAmt)}</td>
      </tr>`;
    } else {
      ccModal.okTbody().innerHTML = '<tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:20px">Sin líneas a exportar</td></tr>';
      ccModal.okTfoot().innerHTML = '';
    }

    // Excluded rows table
    const exclRows = data.excluded ?? [];
    if (exclRows.length) {
      ccModal.exclTbody().innerHTML = exclRows.map(r => `<tr class="cc-excl-row">
        <td>${esc(r.product_id ?? '–')}</td>
        <td>${esc(r.cc_display ?? '–')}</td>
        <td class="cc-excl-reason">${esc(r.reason ?? '')}</td>
        <td class="num">${fmtCLP.format(r.total ?? 0)}</td>
      </tr>`).join('');
      ccModal.exclLabel().style.display = '';
      ccModal.exclWrap().style.display = '';
    } else {
      ccModal.exclLabel().style.display = 'none';
      ccModal.exclWrap().style.display = 'none';
    }

    ccModal.loading().style.display = 'none';
    ccModal.content().classList.remove('hidden');
  } catch (e) {
    ccModal.loading().style.display = 'none';
    const el = ccModal.error();
    el.innerHTML = '<span class="cc-alert-icon">⚠️</span> Error al verificar los CCs: ' + esc(e.message);
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

// Sync now button
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
    // Refresh preview after sync
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
    btn.textContent = 'Sincronizar ahora';
  }
});

// Proceed with export
ccModal.btnProceed().addEventListener('click', async () => {
  closeCCModal();
  await doOdooExport();
});

// Close modal
document.getElementById('btn-cc-cancel').addEventListener('click', closeCCModal);
document.getElementById('btn-cc-modal-close').addEventListener('click', closeCCModal);
ccModal.overlay().addEventListener('click', e => {
  if (e.target === ccModal.overlay()) closeCCModal();
});

// ── Odoo export ──────────────────────────────────────────────────────────

async function doOdooExport() {
  if (!_lastParams) return;
  const btn = document.getElementById('btn-odoo-export');
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Generando archivo…';
  try {
    const res = await fetch('/api/purchase-orders/odoo-export?' + _lastParams);
    if (!res.ok) throw new Error('Error al generar el archivo');
    const excludedAmount = parseInt(res.headers.get('X-Excluded-Amount') || '0');
    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : 'odoo-export.xlsx';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    if (excludedAmount > 0) {
      const fmt = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 });
      alert(`⚠️ Advertencia: ${fmt.format(excludedAmount)} fueron excluidos del archivo porque hay labores o centros de costo sin mapear en Odoo.`);
    }
  } catch (e) {
    alert('Error al exportar: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

document.getElementById('btn-odoo-export').addEventListener('click', () => {
  if (!_lastParams) return;
  openCCModal();
});

// ── Init ─────────────────────────────────────────────────────────────────
loadFilters();

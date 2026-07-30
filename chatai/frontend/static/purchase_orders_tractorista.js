// purchase_orders_tractorista.js — Odoo purchase order page for tractoristas

const fmtCLP = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 });
const fmtNum2 = new Intl.NumberFormat('es-CL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function fmtDate(s) {
  if (!s) return '–';
  const [y, m, d] = s.split('-');
  return `${d}/${m}/${y}`;
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let _lastParams = null;

// ── Load filter dropdowns ────────────────────────────────────────────────
async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/tractorista/filters');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { contratistas, campos } = await res.json();

    const selC = document.getElementById('sel-contractor');
    selC.innerHTML = '<option value="">Seleccione contratista…</option>' +
      contratistas.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');

    const selCampo = document.getElementById('sel-campo');
    selCampo.innerHTML = '<option value="">Seleccione campo…</option>' +
      campos.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
  } catch (err) {
    showError('Error cargando filtros: ' + err.message);
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────
function showError(msg) {
  const box = document.getElementById('error-box');
  box.textContent = msg;
  box.classList.remove('hidden');
}

function hideError() {
  document.getElementById('error-box').classList.add('hidden');
}

// ── Generate button ───────────────────────────────────────────────────────
document.getElementById('btn-generate').addEventListener('click', async () => {
  const contractor = document.getElementById('sel-contractor').value;
  const campo      = document.getElementById('sel-campo').value;
  const dateFrom   = document.getElementById('inp-date-from').value;
  const dateTo     = document.getElementById('inp-date-to').value;

  hideError();
  document.getElementById('oc-document').style.display = 'none';

  if (!contractor || !campo || !dateFrom || !dateTo) {
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
      contratista:    contractor,
      campo:          campo,
      fecha_inicio:   dateFrom,
      fecha_termino:  dateTo,
    });
    _lastParams = params.toString();

    const res = await fetch('/api/tarjas/tractorista/preview?' + params);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || res.statusText);
    }
    const data = await res.json();

    if (!data.rows.length) {
      document.getElementById('oc-document').style.display = 'block';
      document.getElementById('doc-tbody').innerHTML = '';
      document.getElementById('doc-tfoot').innerHTML = '';
      document.getElementById('empty-state').classList.remove('hidden');
      document.getElementById('btn-odoo-export').disabled = true;
      return;
    }

    renderDocument(data);
  } catch (err) {
    showError('Error al generar: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generar orden';
  }
});

// ── Render preview document ───────────────────────────────────────────────
function renderDocument(data) {
  document.getElementById('doc-contractor').textContent = data.contratista;
  document.getElementById('doc-campo').textContent      = data.campo;
  document.getElementById('doc-week').textContent       =
    `${fmtDate(data.fecha_inicio)} — ${fmtDate(data.fecha_termino)}`;
  document.getElementById('doc-date-from').textContent  = fmtDate(data.fecha_inicio);
  document.getElementById('doc-date-to').textContent    = fmtDate(data.fecha_termino);
  document.getElementById('doc-grand-total').textContent = fmtCLP.format(data.total_monto);

  // Group rows by CC
  const groups = [];
  let currentCC = null, currentGroup = null;
  for (const r of data.rows) {
    if (r.cc !== currentCC) {
      currentCC = r.cc;
      currentGroup = { cc: r.cc, rows: [] };
      groups.push(currentGroup);
    }
    currentGroup.rows.push(r);
  }

  const container = document.getElementById('cc-sections');
  container.innerHTML = '';

  for (const g of groups) {
    const ccTotal    = g.rows.reduce((s, r) => s + (r.total ?? 0), 0);
    const ccJornadas = g.rows.reduce((s, r) => s + (r.horas ?? 0), 0);

    let rowsHtml = g.rows.map(r => `<tr>
      <td>${fmtDate(r.fecha)}</td>
      <td>${esc(r.labor ?? '')}</td>
      <td class="num">${r.precio_hora != null ? fmtCLP.format(r.precio_hora) : '—'}</td>
      <td class="num">${r.horas != null ? fmtNum2.format(r.horas) : '—'}</td>
      <td class="num">${r.total != null ? fmtCLP.format(r.total) : '—'}</td>
    </tr>`).join('');

    const section = document.createElement('div');
    section.className = 'cc-section';
    section.dataset.cc = g.cc;
    section.innerHTML = `
      <div class="cc-section-header">
        <span class="cc-section-title">CC ${esc(String(g.cc ?? ''))}</span>
        <div class="cc-section-total">${fmtCLP.format(ccTotal)}</div>
        <button class="btn btn-secondary btn-cc-pdf" data-cc="${esc(String(g.cc ?? ''))}">
          ↓ Descargar PDF
        </button>
      </div>
      <div class="oc-table-wrap">
        <table class="oc-table">
          <thead><tr>
            <th>Fecha</th>
            <th>Labor</th>
            <th class="num">Valor unitario</th>
            <th class="num">Jornadas</th>
            <th class="num">Total a pagar</th>
          </tr></thead>
          <tbody>${rowsHtml}</tbody>
          <tfoot><tr>
            <td colspan="2"><strong>Total CC ${esc(String(g.cc ?? ''))}</strong></td>
            <td></td>
            <td class="num"><strong>${fmtNum2.format(ccJornadas)}</strong></td>
            <td class="num"><strong>${fmtCLP.format(ccTotal)}</strong></td>
          </tr></tfoot>
        </table>
      </div>`;
    container.appendChild(section);
  }

  // Wire PDF buttons
  container.querySelectorAll('.btn-cc-pdf').forEach(btn => {
    btn.addEventListener('click', () => downloadCCPdf(btn.dataset.cc, btn));
  });

  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('btn-odoo-export').disabled = false;
  document.getElementById('oc-document').style.display = 'block';
}

async function downloadCCPdf(cc, btn) {
  if (!_lastParams) return;
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Generando…';
  try {
    const params = _lastParams + '&cc=' + encodeURIComponent(cc);
    const res = await fetch('/api/tarjas/tractorista/download-pdf?' + params);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tractorista_cc${cc}_${_lastParams.replace(/[^a-z0-9_]/gi, '_')}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    showError('Error al generar PDF: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

// ── Export modal ──────────────────────────────────────────────────────────
const ccModal = {
  overlay:      () => document.getElementById('cc-sync-modal'),
  loading:      () => document.getElementById('cc-modal-loading'),
  content:      () => document.getElementById('cc-modal-content'),
  error:        () => document.getElementById('cc-modal-error'),
  rowsCount:    () => document.getElementById('cc-rows-count'),
  exclCount:    () => document.getElementById('cc-excluded-count'),
  exclChip:     () => document.getElementById('cc-excluded-chip'),
  exclCountMsg: () => document.getElementById('cc-excluded-count-msg'),
  archivedAlert:() => document.getElementById('cc-archived-alert'),
  previewTbody: () => document.getElementById('cc-preview-tbody'),
  previewTfoot: () => document.getElementById('cc-preview-tfoot'),
};

async function loadExportPreview() {
  ccModal.loading().style.display = 'flex';
  ccModal.content().classList.add('hidden');
  ccModal.error().classList.add('hidden');
  try {
    const res = await fetch('/api/tarjas/tractorista/export-preview?' + _lastParams);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const okRows   = data.rows     ?? [];
    const exclRows = data.excluded ?? [];

    ccModal.rowsCount().textContent = okRows.length;
    ccModal.exclCount().textContent = exclRows.length;
    ccModal.exclChip().style.display = exclRows.length > 0 ? '' : 'none';
    if (exclRows.length > 0) {
      ccModal.exclCountMsg().textContent = exclRows.length;
      ccModal.archivedAlert().classList.remove('hidden');
    } else {
      ccModal.archivedAlert().classList.add('hidden');
    }

    let totalQty = 0;
    const okHtml = okRows.map(r => {
      totalQty += r.qty ?? 0;
      return `<tr>
        <td>${esc(r.product_id ?? '–')}</td>
        <td class="num">${fmtNum2.format(r.qty ?? 0)}</td>
        <td class="cc-analytic">${esc(r.analytic_distribution ?? '–')}</td>
        <td class="num">${fmtCLP.format(r.price_unit ?? 0)}</td>
        <td><span class="cc-badge cc-badge-ok">OK</span></td>
      </tr>`;
    }).join('');
    const exclHtml = exclRows.map(r => `<tr class="cc-row-error">
      <td>${esc(r.product_id ?? '–')}</td>
      <td class="num">${fmtNum2.format(r.qty ?? 0)}</td>
      <td class="cc-analytic">${esc(r.analytic_distribution ?? '–')}</td>
      <td class="num">${fmtCLP.format(r.price_unit ?? 0)}</td>
      <td><span class="cc-badge cc-badge-archived" title="${esc(r.reason ?? '')}">⚠ Sin mapeo</span></td>
    </tr>`).join('');

    if (okRows.length + exclRows.length === 0) {
      ccModal.previewTbody().innerHTML = '<tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:24px">Sin líneas para este período</td></tr>';
      ccModal.previewTfoot().innerHTML = '';
    } else {
      ccModal.previewTbody().innerHTML = okHtml + exclHtml;
      ccModal.previewTfoot().innerHTML = `<tr><td><strong>Total exportable</strong></td><td class="num">${fmtNum2.format(totalQty)}</td><td></td><td></td><td></td></tr>`;
    }

    ccModal.loading().style.display = 'none';
    ccModal.content().classList.remove('hidden');
  } catch (e) {
    ccModal.loading().style.display = 'none';
    const el = ccModal.error();
    el.innerHTML = '<span>⚠️</span> Error al cargar vista previa: ' + esc(e.message);
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

document.getElementById('btn-odoo-export').addEventListener('click', () => {
  if (!_lastParams) return;
  openCCModal();
});

document.getElementById('btn-cc-cancel').addEventListener('click', closeCCModal);
document.getElementById('btn-cc-modal-close').addEventListener('click', closeCCModal);
ccModal.overlay().addEventListener('click', e => { if (e.target === ccModal.overlay()) closeCCModal(); });

document.getElementById('btn-cc-proceed').addEventListener('click', async () => {
  closeCCModal();
  const btn = document.getElementById('btn-odoo-export');
  btn.disabled = true;
  btn.textContent = 'Generando archivo…';
  try {
    const res = await fetch('/api/tarjas/tractorista/odoo-export?' + _lastParams);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || res.statusText);
    }
    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : 'odoo-tractorista.xlsx';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    showError('Error al exportar: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Exportar archivo Odoo';
  }
});


// ── Init ──────────────────────────────────────────────────────────────────
loadFilters();

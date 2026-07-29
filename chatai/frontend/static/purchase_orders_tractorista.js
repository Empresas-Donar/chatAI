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

  const tbody = document.getElementById('doc-tbody');
  tbody.innerHTML = data.rows.map(r => {
    const missingProduct = !r.product_id || r.product_id === '(sin mapeo)';
    const rowClass = missingProduct ? ' style="background:var(--error-bg,#fff5f5)"' : '';
    return `<tr${rowClass}>
      <td>${esc(String(r.cc ?? ''))}</td>
      <td>${esc(r.labor ?? '')}</td>
      <td class="num">${r.horas != null ? fmtNum2.format(r.horas) : '—'}</td>
      <td class="num">${r.precio_hora != null ? fmtCLP.format(r.precio_hora) : '—'}</td>
      <td class="num">${r.total != null ? fmtCLP.format(r.total) : '—'}</td>
      <td>${missingProduct ? '<span style="color:var(--error,#c00)">' + esc(r.product_id ?? '(sin mapeo)') + '</span>' : esc(r.product_id)}</td>
    </tr>`;
  }).join('');

  const tfoot = document.getElementById('doc-tfoot');
  tfoot.innerHTML = `<tr>
    <td colspan="2"><strong>Total</strong></td>
    <td class="num"><strong>${fmtNum2.format(data.total_horas)}</strong></td>
    <td></td>
    <td class="num"><strong>${fmtCLP.format(data.total_monto)}</strong></td>
    <td></td>
  </tr>`;

  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('btn-odoo-export').disabled = false;
  document.getElementById('oc-document').style.display = 'block';
}

// ── Odoo export button ────────────────────────────────────────────────────
document.getElementById('btn-odoo-export').addEventListener('click', async () => {
  if (!_lastParams) return;

  const btn = document.getElementById('btn-odoo-export');
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Generando archivo…';

  try {
    const res = await fetch('/api/tarjas/tractorista/odoo-export?' + _lastParams);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || res.statusText);
    }

    const excludedAmount = parseInt(res.headers.get('X-Excluded-Amount') || '0');
    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : 'odoo-tractorista.xlsx';

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    if (excludedAmount > 0) {
      alert(`Advertencia: ${fmtCLP.format(excludedAmount)} fueron excluidos del archivo porque hay labores o centros de costo sin mapear en Odoo.`);
    }
  } catch (e) {
    showError('Error al exportar: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
});

// ── Init ──────────────────────────────────────────────────────────────────
loadFilters();

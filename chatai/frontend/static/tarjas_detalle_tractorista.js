// tarjas_detalle_tractorista.js — Weekly tractorista detail

const fmtCLP = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', maximumFractionDigits: 0
});
const fmtCLPDec = new Intl.NumberFormat('es-CL', {
  style: 'currency', currency: 'CLP', minimumFractionDigits: 2, maximumFractionDigits: 2
});
const fmtNum = new Intl.NumberFormat('es-CL');

function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toISO(d) { return d.toISOString().slice(0, 10); }

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

async function loadFilters() {
  try {
    const res = await fetch('/api/tarjas/detalle-tractorista/filters');
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
  add('labor', 'fil-labor');
  add('campo', 'fil-campo');

  const btn = document.getElementById('btn-apply');
  btn.disabled = true;
  btn.textContent = 'Cargando…';

  try {
    const res = await fetch('/api/tarjas/detalle-tractorista?' + params);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (!data.rows.length) {
      document.getElementById('summary-section').style.display = 'none';
      document.getElementById('detail-section').style.display = 'none';
      document.getElementById('empty-state').style.display = 'block';
      setDownloadEnabled(false);
      return;
    }

    document.getElementById('empty-state').style.display = 'none';
    renderSummary(data.resumen_contratista, data.total, data.jornadas);
    renderDetail(data.rows, data.count);
    document.getElementById('summary-section').style.display = '';
    document.getElementById('detail-section').style.display = '';
    setDownloadEnabled(true);
  } catch (e) {
    console.error('Query error:', e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Consultar';
  }
}

function renderSummary(rows, total, jornadas) {
  const tbody = document.getElementById('summary-tbody');
  tbody.innerHTML = rows.map(r => {
    const tp = esc(r.tipo_pago ?? '');
    const tot = r.total_pagar != null ? fmtCLP.format(r.total_pagar) : '—';
    return `<tr>
      <td>${tp}</td>
      <td class="cell-contractor" title="${esc(r.contratista)}">${esc(r.contratista ?? '')}</td>
      <td class="num">${tot}</td>
      <td class="num">${fmtNum.format(r.jornadas)}</td>
    </tr>`;
  }).join('');

  document.getElementById('summary-total').textContent = fmtCLP.format(total);
  document.getElementById('summary-jornadas').textContent = fmtNum.format(jornadas);
}

function renderDetail(rows, count) {
  document.getElementById('detail-count').textContent = `${count} registro${count !== 1 ? 's' : ''}`;

  const tbody = document.getElementById('detail-tbody');
  tbody.innerHTML = rows.map(r => `<tr>
      <td>${esc(r.tipo_pago ?? '')}</td>
      <td>${esc(String(r.centro_costo ?? ''))}</td>
      <td>${esc(r.labor ?? '')}</td>
      <td class="num">${r.total_unitario != null ? fmtCLPDec.format(r.total_unitario) : '—'}</td>
      <td class="num">${r.jornadas ?? '—'}</td>
      <td class="num">${r.costo_total != null ? fmtCLP.format(r.costo_total) : '—'}</td>
    </tr>`).join('');
}

function currentParams() {
  const p = new URLSearchParams({
    fecha_inicio: document.getElementById('fil-from').value,
    fecha_termino: document.getElementById('fil-to').value,
  });
  const add = (key, id) => { const v = document.getElementById(id)?.value; if (v) p.append(key, v); };
  add('contratista','fil-contratista');
  add('empresa','fil-empresa');
  add('centro_costo','fil-cc');
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
    .map(([k,v]) => `<span class="ph-chip"><strong>${esc(k)}:</strong> ${esc(v)}</span>`)
    .join('');
  const now = new Date().toLocaleDateString('es-CL', { day:'2-digit', month:'long', year:'numeric' });
  document.getElementById('print-header').innerHTML = `
    <div class="ph-top">
      <img class="ph-logo" src="/static/img/donar_logo.png" alt="Empresas Donar" />
      <div class="ph-title-block">
        <h2>${esc(title)}</h2>
        <p class="ph-subtitle">Generado el ${now}</p>
      </div>
    </div>
    <div class="ph-filters">${chips}</div>
  `;
  window.print();
}:</strong> ${esc(v)}</span>`)
    .join('');
  document.getElementById('print-header').innerHTML =
    `<h2>${esc(title)}</h2><div class="ph-filters">${chips}</div>`;
  window.print();
}

document.getElementById('btn-apply').addEventListener('click', queryData);
document.getElementById('btn-excel').addEventListener('click', () => {
  window.location.href = '/api/tarjas/detalle-tractorista/download-excel?' + currentParams();
});
document.getElementById('btn-pdf').addEventListener('click', () => {
  const g = id => document.getElementById(id)?.value || '';
  printWithHeader('Detalle tractorista — Tarjas', {
    'Desde': g('fil-from'), 'Hasta': g('fil-to'),
    'Contratista': g('fil-contratista'),
    'Empresa': g('fil-empresa'), 'Campo': g('fil-campo'),
    'CC': g('fil-cc'), 'Labor': g('fil-labor'),
  });
});

document.querySelectorAll('#fil-from, #fil-to').forEach(el => {
  el.addEventListener('keydown', e => { if (e.key === 'Enter') queryData(); });
});

initDates();
loadFilters();
queryData();

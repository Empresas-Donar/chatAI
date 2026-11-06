// Catalog of appsheet.tarjas_cc: the tarjas app cost-center list.

const form = document.getElementById('cc-form');
const empty = document.getElementById('cc-empty');
const errorEl = document.getElementById('cc-error');
const pageError = document.getElementById('cc-page-error');
const saveBtn = document.getElementById('cc-save');
const cancelBtn = document.getElementById('cc-cancel');
const addBtn = document.getElementById('cc-add');
const card = document.getElementById('cc-card');
const tbody = document.getElementById('cc-body');
const codeInput = document.getElementById('cc-codigo');
const nameInput = document.getElementById('cc-nombre');
const campoInput = document.getElementById('cc-campo');
const queryInput = document.getElementById('cc-q');
const campoFilter = document.getElementById('cc-fil-campo');
const panel = document.getElementById('cc-panel');
const overlay = document.getElementById('cc-overlay');
const panelTitle = document.getElementById('cc-panel-title');
const panelSub = document.getElementById('cc-panel-sub');
const linesEl = document.getElementById('cc-lines');
const totalEl = document.getElementById('cc-dist-total');
const cuentasList = document.getElementById('cc-cuentas');
const addLineBtn = document.getElementById('cc-add-line');

let editingId = null;
let rows = [];
let cuentas = [];

function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function norm(value) {
  return String(value ?? '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '');
}

function showError(message) {
  errorEl.textContent = message || '';
  errorEl.hidden = !message;
}

function detailMessage(data) {
  const detail = data && data.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(item => item.msg || '').filter(Boolean).join(' ');
  }
  return '';
}

function cuentaLabel(cuenta) {
  const name = cuenta.cultivo && cuenta.cultivo !== cuenta.id_cc
    ? `${cuenta.id_cc} · ${cuenta.cultivo}`
    : cuenta.id_cc;
  return cuenta.campo ? `${name} (${cuenta.campo})` : name;
}

function labelForOdoo(odooId) {
  const match = cuentas.find(cuenta => cuenta.odoo_id === String(odooId));
  return match ? cuentaLabel(match) : String(odooId ?? '');
}

function resolveCuenta(text) {
  const value = String(text || '').trim();
  if (!value) return null;
  const byLabel = cuentas.find(cuenta => cuentaLabel(cuenta) === value);
  if (byLabel) return byLabel.odoo_id;
  const byCode = cuentas.find(cuenta => cuenta.id_cc === value);
  if (byCode) return byCode.odoo_id;
  if (/^\d{1,12}$/.test(value)) return value;
  return null;
}

function fillCuentas(list) {
  cuentas = list || [];
  cuentasList.innerHTML = cuentas.map(cuenta =>
    `<option value="${esc(cuentaLabel(cuenta))}"></option>`
  ).join('');
}

function cents(value) {
  const text = String(value ?? '').trim().replace(',', '.');
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  const [whole, frac = ''] = text.split('.');
  return Number(whole) * 100 + Number(frac.padEnd(2, '0'));
}

function paintTotal() {
  const values = [...linesEl.querySelectorAll('.cc-line-pct')];
  if (!values.length) {
    totalEl.textContent = 'Sin líneas';
    totalEl.className = '';
    return;
  }
  let sum = 0;
  let valid = true;
  values.forEach(input => {
    const amount = cents(input.value);
    if (amount == null) valid = false;
    else sum += amount;
  });
  if (!valid) {
    totalEl.textContent = 'Porcentaje inválido';
    totalEl.className = 'cc-dist-total--bad';
    return;
  }
  const shown = (sum / 100).toFixed(2);
  totalEl.textContent = `Total ${shown}`;
  totalEl.className = sum === 10000 ? 'cc-dist-total--ok' : 'cc-dist-total--bad';
}

function addLine(odooId, porcentaje) {
  const line = document.createElement('div');
  line.className = 'cc-line';
  line.innerHTML = `
    <input class="cc-line-cuenta" list="cc-cuentas" placeholder="Código o id Odoo" autocomplete="off" value="${esc(labelForOdoo(odooId))}" />
    <input class="cc-line-pct" inputmode="decimal" placeholder="%" value="${esc(porcentaje || '')}" />
    <button type="button" class="cc-line-remove" aria-label="Quitar línea">×</button>
  `;
  linesEl.appendChild(line);
  paintTotal();
}

function setLines(distribucion) {
  linesEl.innerHTML = '';
  (distribucion || []).forEach(line => addLine(line.odoo_id, line.porcentaje));
  paintTotal();
}

function readLines() {
  const lines = [];
  let unknown = null;
  linesEl.querySelectorAll('.cc-line').forEach(line => {
    const text = line.querySelector('.cc-line-cuenta').value.trim();
    const porcentaje = line.querySelector('.cc-line-pct').value.trim().replace(',', '.');
    if (!text && !porcentaje) return;
    const odooId = resolveCuenta(text);
    if (text && !odooId) unknown = text;
    lines.push({ odoo_id: odooId || '', porcentaje });
  });
  return { lines, unknown };
}

function payload() {
  return {
    id_cc: codeInput.value,
    cultivo: nameInput.value,
    id_campo: Number(campoInput.value),
    distribucion: readLines().lines,
  };
}

function fillCampoOptions(select, campos, placeholder) {
  const current = select.value;
  select.innerHTML = `<option value="">${esc(placeholder)}</option>` +
    campos.map(campo =>
      `<option value="${esc(campo.id_campo)}">${esc(campo.nombre)}</option>`
    ).join('');
  if ([...select.options].some(option => option.value === current)) {
    select.value = current;
  }
}

function openPanel() {
  panel.hidden = false;
  overlay.hidden = false;
  document.body.style.overflow = 'hidden';
}

function closePanel() {
  editingId = null;
  panel.hidden = true;
  overlay.hidden = true;
  document.body.style.overflow = '';
  form.reset();
  codeInput.disabled = false;
  setLines([]);
  showError('');
  render();
}

function openCreate() {
  editingId = null;
  form.reset();
  codeInput.disabled = false;
  saveBtn.textContent = 'Agregar';
  panelTitle.textContent = 'Nuevo centro de costo';
  panelSub.textContent = 'El código es el que se elige al registrar una tarja.';
  showError('');
  setLines([]);
  openPanel();
  render();
  codeInput.focus();
}

function openEdit(row) {
  editingId = row.id_cc;
  codeInput.value = row.id_cc || '';
  codeInput.disabled = true;
  nameInput.value = row.cultivo || '';
  campoInput.value = row.id_campo == null ? '' : String(row.id_campo);
  saveBtn.textContent = 'Guardar';
  panelTitle.textContent = 'Editar centro de costo';
  panelSub.textContent = 'El código no se cambia: las tarjas ya lo usan.';
  showError('');
  setLines(row.distribucion || []);
  openPanel();
  render();
  nameInput.focus();
}

function visibleRows() {
  const q = norm(queryInput.value.trim());
  const campo = campoFilter.value;
  return rows.filter(row => {
    if (campo && String(row.id_campo) !== campo) return false;
    if (!q) return true;
    return norm(row.id_cc).includes(q) || norm(row.cultivo).includes(q);
  });
}

function render() {
  const shown = visibleRows();
  empty.hidden = shown.length > 0;
  empty.textContent = rows.length
    ? 'Ningún centro de costo coincide con el filtro.'
    : 'Todavía no hay centros de costo.';
  card.hidden = shown.length === 0;
  document.getElementById('cc-count').textContent =
    shown.length === rows.length
      ? String(rows.length)
      : `${shown.length} de ${rows.length}`;
  tbody.innerHTML = shown.map(row => `<tr class="${row.id_cc === editingId ? 'is-open' : ''}">
    <td>${esc(row.id_cc)}</td>
    <td>${esc(row.cultivo || '—')}</td>
    <td>${esc(row.campo || '—')}</td>
    <td class="num">${row.distribucion && row.distribucion.length ? row.distribucion.length : '—'}</td>
    <td class="num">${row.registros}</td>
    <td class="cc-actions">
      <button type="button" class="btn btn-secondary btn-sm" data-edit="${esc(row.id_cc)}">Editar</button>
      <button type="button" class="btn btn-danger btn-sm" data-delete="${esc(row.id_cc)}">Borrar</button>
    </td>
  </tr>`).join('');
}

async function load() {
  const res = await fetch('/api/centros-costo');
  if (res.status === 403) {
    empty.hidden = false;
    empty.textContent = 'Solo un administrador puede ver este catálogo.';
    card.hidden = true;
    return;
  }
  if (!res.ok) {
    empty.hidden = false;
    empty.textContent = 'No se pudo cargar el catálogo.';
    card.hidden = true;
    return;
  }
  const data = await res.json();
  rows = data.centros || [];
  const campos = data.campos || [];
  fillCampoOptions(campoInput, campos, 'Seleccione');
  fillCampoOptions(campoFilter, campos, 'Todos');
  fillCuentas(data.cuentas || []);
  addBtn.disabled = false;
  render();
}

async function remove(id) {
  if (!window.confirm(
    '¿Borrar este centro de costo? Si tiene registros, no se borra. Si sigue activo en Odoo, la sincronización lo vuelve a crear.'
  )) return;
  pageError.hidden = true;
  const res = await fetch('/api/centros-costo/' + encodeURIComponent(id), { method: 'DELETE' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    pageError.textContent = detailMessage(data) || 'No se pudo borrar.';
    pageError.hidden = false;
    return;
  }
  if (editingId === id) closePanel();
  await load();
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  showError('');
  const entered = readLines();
  if (entered.unknown) {
    showError(`No reconozco la cuenta «${entered.unknown}». Elige una de la lista o escribe el id numérico de Odoo.`);
    return;
  }
  if (entered.lines.some(line => !line.odoo_id)) {
    showError('Cada línea necesita una cuenta.');
    return;
  }
  saveBtn.disabled = true;
  const creating = !editingId;
  const url = creating
    ? '/api/centros-costo'
    : '/api/centros-costo/' + encodeURIComponent(editingId);
  try {
    const res = await fetch(url, {
      method: creating ? 'POST' : 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload()),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showError(detailMessage(data) || 'No se pudo guardar.');
      return;
    }
    closePanel();
    await load();
  } finally {
    saveBtn.disabled = false;
  }
});

addLineBtn.addEventListener('click', () => {
  addLine('', '');
  const inputs = linesEl.querySelectorAll('.cc-line-cuenta');
  inputs[inputs.length - 1].focus();
});
linesEl.addEventListener('input', paintTotal);
linesEl.addEventListener('click', event => {
  const removeBtn = event.target.closest('.cc-line-remove');
  if (!removeBtn) return;
  removeBtn.closest('.cc-line').remove();
  paintTotal();
});
addBtn.addEventListener('click', openCreate);
cancelBtn.addEventListener('click', closePanel);
document.getElementById('cc-panel-close').addEventListener('click', closePanel);
overlay.addEventListener('click', closePanel);
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !panel.hidden) closePanel();
});
queryInput.addEventListener('input', render);
campoFilter.addEventListener('change', render);
tbody.addEventListener('click', event => {
  const editBtn = event.target.closest('[data-edit]');
  if (editBtn) {
    const row = rows.find(item => item.id_cc === editBtn.dataset.edit);
    if (row) openEdit(row);
    return;
  }
  const deleteBtn = event.target.closest('[data-delete]');
  if (deleteBtn) remove(deleteBtn.dataset.delete);
});

load();

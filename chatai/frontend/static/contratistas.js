// intranet contractor master. Does not write AppSheet catalogs.

const form = document.getElementById('ct-form');
const empty = document.getElementById('ct-empty');
const errorEl = document.getElementById('ct-error');
const saveBtn = document.getElementById('ct-save');
const cancelBtn = document.getElementById('ct-cancel');
const activeCard = document.getElementById('ct-active-card');
const quietCard = document.getElementById('ct-quiet-card');
const activeBody = document.getElementById('ct-active-body');
const quietBody = document.getElementById('ct-quiet-body');

let editingId = null;

function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function showError(message) {
  errorEl.textContent = message || '';
  errorEl.hidden = !message;
}

function payload() {
  return {
    nombre: document.getElementById('ct-nombre').value,
    nombre_corto: document.getElementById('ct-corto').value,
    rut: document.getElementById('ct-rut').value,
    activo: document.getElementById('ct-activo').value === '1',
  };
}

function resetForm() {
  editingId = null;
  form.reset();
  document.getElementById('ct-activo').value = '1';
  saveBtn.textContent = 'Agregar';
  cancelBtn.hidden = true;
  showError('');
}

function fillForm(row) {
  editingId = row.id_intranet;
  document.getElementById('ct-nombre').value = row.nombre || '';
  document.getElementById('ct-corto').value = row.nombre_corto || '';
  document.getElementById('ct-rut').value = row.rut || '';
  document.getElementById('ct-activo').value = row.activo ? '1' : '0';
  saveBtn.textContent = 'Guardar';
  cancelBtn.hidden = false;
  showError('');
  document.getElementById('ct-nombre').focus();
}

function rowHtml(row) {
  return `<tr>
    <td>${esc(row.nombre)}</td>
    <td>${esc(row.nombre_corto || '—')}</td>
    <td>${esc(row.rut || '—')}</td>
    <td>${row.activo ? 'Sí' : 'No'}</td>
    <td class="num">${row.enlaces_tarjas}</td>
    <td class="num">${row.enlaces_cosecha}</td>
    <td>
      <button type="button" class="btn btn-secondary btn-sm" data-edit="${esc(row.id_intranet)}">Editar</button>
      <button type="button" class="btn btn-danger btn-sm" data-delete="${esc(row.id_intranet)}">Borrar</button>
    </td>
  </tr>`;
}

function fillSection(card, tbody, countEl, rows, label) {
  card.hidden = rows.length === 0;
  countEl.textContent = label;
  tbody.innerHTML = rows.map(rowHtml).join('');
}

function render(rows, desde) {
  const activos = rows.filter(row => row.con_actividad);
  const sin = rows.filter(row => !row.con_actividad);
  empty.hidden = rows.length > 0;
  empty.textContent = 'Todavía no hay contratistas en el maestro.';
  fillSection(
    activeCard,
    activeBody,
    document.getElementById('ct-active-count'),
    activos,
    desde ? `${activos.length} · desde el ${desde}` : String(activos.length),
  );
  fillSection(
    quietCard,
    quietBody,
    document.getElementById('ct-quiet-count'),
    sin,
    String(sin.length),
  );
  document.querySelectorAll('#ct-active-body [data-edit], #ct-quiet-body [data-edit]').forEach(btn => {
    btn.addEventListener('click', () => {
      const row = rows.find(item => item.id_intranet === btn.dataset.edit);
      if (row) fillForm(row);
    });
  });
  document.querySelectorAll('#ct-active-body [data-delete], #ct-quiet-body [data-delete]').forEach(btn => {
    btn.addEventListener('click', () => remove(btn.dataset.delete));
  });
}

async function load() {
  const res = await fetch('/api/contratistas');
  if (res.status === 403) {
    empty.hidden = false;
    empty.textContent = 'Solo un administrador puede ver este catálogo.';
    return;
  }
  if (!res.ok) {
    empty.hidden = false;
    empty.textContent = 'No se pudo cargar el catálogo.';
    return;
  }
  const data = await res.json();
  render(data.contratistas || [], data.actividad_desde);
}

async function remove(id) {
  if (!window.confirm('¿Borrar este contratista del maestro? La fila de la app queda, y el enlace pasa a vacío.')) return;
  showError('');
  const res = await fetch('/api/contratistas/' + encodeURIComponent(id), { method: 'DELETE' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    showError(data.detail || 'No se pudo borrar.');
    return;
  }
  if (editingId === id) resetForm();
  await load();
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  showError('');
  saveBtn.disabled = true;
  const creating = !editingId;
  const url = creating ? '/api/contratistas' : '/api/contratistas/' + encodeURIComponent(editingId);
  try {
    const res = await fetch(url, {
      method: creating ? 'POST' : 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload()),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showError(data.detail || 'No se pudo guardar.');
      return;
    }
    resetForm();
    await load();
  } finally {
    saveBtn.disabled = false;
  }
});

cancelBtn.addEventListener('click', resetForm);
load();

// Fleet catalog. Kept off the global scope so it does not collide with base.html.
(function () {

const form = document.getElementById('tr-form');
const empty = document.getElementById('tr-empty');
const errorEl = document.getElementById('tr-error');
const pageError = document.getElementById('tr-page-error');
const addBtn = document.getElementById('tr-add');
const card = document.getElementById('tr-card');
const tbody = document.getElementById('tr-body');
const queryInput = document.getElementById('tr-q');
const campoFilter = document.getElementById('tr-fil-campo');
const habFilter = document.getElementById('tr-fil-hab');
const estadoFilter = document.getElementById('tr-fil-estado');
const panel = document.getElementById('tr-panel');
const overlay = document.getElementById('tr-overlay');
const panelTitle = document.getElementById('tr-panel-title');
const patenteInput = document.getElementById('tr-patente');
const modeloInput = document.getElementById('tr-modelo');
const maquinaInput = document.getElementById('tr-maquina');
const anioInput = document.getElementById('tr-anio');
const fechaInput = document.getElementById('tr-fecha');
const antiguedadEl = document.getElementById('tr-antiguedad');
const cumpleInput = document.getElementById('tr-cumple');
const colorInput = document.getElementById('tr-color');
const chasisInput = document.getElementById('tr-chasis');
const tractoristaInput = document.getElementById('tr-tractorista');
const camposBox = document.getElementById('tr-campos');
const habilitadoInput = document.getElementById('tr-habilitado');
const saveBtn = document.getElementById('tr-save');
const usoBox = document.getElementById('tr-uso');
const usoTexto = document.getElementById('tr-uso-texto');
const detalle = document.getElementById('tr-detalle');
const conductoresTabla = document.getElementById('tr-conductores-mini');
const avisosEl = document.getElementById('tr-avisos');
const costCard = document.getElementById('tr-cost-card');
const costBody = document.getElementById('tr-cost-body');
const tarifaNote = document.getElementById('tr-tarifa-note');

let rows = [];
let campos = [];
let tarifa = null;
let conductores = [];
let tab = 'flota';
let editingPerfil = null;
let sugerido9 = null;
let sugerido75 = null;

const flota = document.getElementById('tr-flota');
const conductoresView = document.getElementById('tr-conductores');
const cdBody = document.getElementById('cd-body');
const cdCard = document.getElementById('cd-card');
const cdEmpty = document.getElementById('cd-empty');
const cdQuery = document.getElementById('cd-q');
const cdPanel = document.getElementById('cd-panel');
const cdOverlay = document.getElementById('cd-overlay');
const cdForm = document.getElementById('cd-form');
const cdNombre = document.getElementById('cd-nombre');
const cdCarnet = document.getElementById('cd-carnet');
const cdOperador = document.getElementById('cd-operador');
const cdHorario = document.getElementById('cd-horario');
const cdDesde = document.getElementById('cd-desde');
const cdHasta = document.getElementById('cd-hasta');
const cdCosto9 = document.getElementById('cd-costo-9');
const cdCosto75 = document.getElementById('cd-costo-75');
const cdCampo9 = document.getElementById('cd-campo-9');
const cdError = document.getElementById('cd-error');
const cdTitle = document.getElementById('cd-panel-title');
let editingId = null;
let editingPatente = null;
let editingNombre = null;

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

function parseAnio(raw) {
  const text = String(raw || '').trim();
  if (!text) return null;
  let day;
  let month;
  let year;
  const full = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  const bare = text.match(/^(\d{4})$/);
  if (full) {
    day = Number(full[1]);
    month = Number(full[2]);
    year = Number(full[3]);
  } else if (bare) {
    day = 1;
    month = 1;
    year = Number(bare[1]);
  } else {
    return null;
  }
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return date;
}

function ageLabel(raw) {
  const date = parseAnio(raw);
  if (!date) return raw && String(raw).trim() ? 'Fecha no válida' : 'Sin año';
  const today = new Date();
  let years = today.getFullYear() - date.getFullYear();
  const before = (today.getMonth() < date.getMonth())
    || (today.getMonth() === date.getMonth() && today.getDate() < date.getDate());
  if (before) years -= 1;
  if (years <= 0) return 'Este año';
  if (years === 1) return '1 año';
  return years + ' años';
}

function clp(value) {
  const amount = Number(value || 0);
  return '$' + amount.toLocaleString('es-CL');
}

function campoTexto(row) {
  if (!row.campos || !row.campos.length) return '—';
  return row.campos.map(campo => campo.nombre).join(', ');
}

function cumpleTexto(value) {
  if (value === 'SI') return 'Sí, −10%';
  if (value === 'NO') return 'No';
  return '—';
}

function fillCampoOptions(select, list, placeholder) {
  const current = select.value;
  select.innerHTML = `<option value="">${esc(placeholder)}</option>` +
    list.map(campo =>
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
  showError('');
}

function paintUso(row) {
  if (!row || !row.ultima_tarja) {
    usoBox.hidden = true;
    usoTexto.textContent = '';
    return;
  }
  const quien = [row.trabajador, row.contratista].filter(Boolean).join(' · ');
  const donde = row.campo_tarja ? ` en ${row.campo_tarja}` : '';
  usoTexto.textContent = `${row.ultima_tarja}${donde}. ${quien}.`;
  usoBox.hidden = false;
}

function precioJornada(persona) {
  if (!tarifa) return '—';
  if (persona.licencia === 'Sin operador') return clp(tarifa.sin_operador_9h);
  if (persona.licencia === 'Sin carnet') return clp(tarifa.sin_carnet_9h);
  return clp(tarifa.con_carnet_9h);
}

function renderTarifa() {
  if (!tarifa) {
    costCard.hidden = true;
    return;
  }
  costCard.hidden = false;
  costBody.innerHTML = `
    <tr>
      <td>Jornada de 9 h</td>
      <td class="num">${esc(clp(tarifa.con_carnet_9h))}</td>
      <td class="num">${esc(clp(tarifa.sin_carnet_9h))}</td>
    </tr>
    <tr>
      <td>Jornada de 7,5 h</td>
      <td class="num">${esc(clp(tarifa.con_carnet_75))}</td>
      <td class="num">${esc(clp(tarifa.sin_carnet_75))}</td>
    </tr>`;
  tarifaNote.textContent =
    `El carnet suma ${clp(tarifa.carnet)} y solo entra en esta jornada, si el conductor va con operador. ` +
    `Sin operador, la jornada de 9 h es ${clp(tarifa.sin_operador_9h)} y no lleva carnet. ` +
    `Cumple: el tractor tiene más de 5 años y por eso se descuenta el 10%.`;
}

function paintDetalle(row) {
  const personas = (row && row.conductores) || [];
  const avisos = (row && row.avisos) || [];
  if (!personas.length) {
    detalle.hidden = true;
    return;
  }
  conductoresTabla.innerHTML = `<tr><th>Nombre</th><th>Licencia</th><th class="num">Jornada de 9 h</th></tr>` +
    personas.map(persona => `<tr>
      <td>${esc(persona.nombre)}</td>
      <td>${esc(persona.licencia)}</td>
      <td class="num">${esc(precioJornada(persona))}</td>
    </tr>`).join('');
  avisosEl.innerHTML = avisos.map(aviso => `<li>${esc(aviso)}</li>`).join('');
  detalle.hidden = false;
}

function fillCampoChecks(selected) {
  const picked = new Set((selected || []).map(id => String(id)));
  camposBox.innerHTML = campos.map(campo => `
    <label class="tr-check">
      <input type="checkbox" name="campo" value="${esc(campo.id_campo)}" ${picked.has(String(campo.id_campo)) ? 'checked' : ''} />
      ${esc(campo.nombre)}
    </label>`).join('');
}

function checkedCampos() {
  return [...camposBox.querySelectorAll('input:checked')].map(input => Number(input.value));
}

function edadFuente() {
  const fecha = fechaInput.value.trim();
  if (fecha) return fecha;
  return anioInput.value.trim();
}

function openCreate() {
  editingId = null;
  editingPatente = null;
  editingNombre = null;
  form.reset();
  habilitadoInput.checked = true;
  fillCampoChecks([]);
  panelTitle.textContent = 'Nuevo tractor';
  antiguedadEl.textContent = 'Sin año';
  usoBox.hidden = true;
  detalle.hidden = true;
  showError('');
  openPanel();
  modeloInput.focus();
}

function openEdit(row) {
  editingId = row.id;
  editingPatente = row.patente || null;
  editingNombre = row.en_catalogo && !row.patente ? row.maquina : null;
  modeloInput.value = row.modelo || '';
  maquinaInput.value = row.maquina || '';
  anioInput.value = row.anio_modelo || (/^\d{4}$/.test(row.anio || '') ? row.anio : '');
  fechaInput.value = row.fecha_partida || ((row.anio || '').includes('/') ? row.anio : '');
  antiguedadEl.textContent = ageLabel(fechaInput.value || anioInput.value);
  cumpleInput.value = row.cumple || '';
  colorInput.value = row.color || '';
  chasisInput.value = row.chasis || '';
  tractoristaInput.value = row.tractorista || '';
  habilitadoInput.checked = row.habilitado !== false;
  fillCampoChecks((row.campos || []).map(campo => campo.id_campo));
  patenteInput.value = row.patente || '';
  panelTitle.textContent = row.patente || row.modelo || row.maquina || 'Tractor';
  paintUso(row);
  paintDetalle(row);
  showError('');
  openPanel();
  modeloInput.focus();
}

function anioTexto(row) {
  if (row.anio_modelo) return String(row.anio_modelo);
  if (/^\d{4}$/.test(row.anio || '')) return row.anio;
  return '—';
}

function visibleRows() {
  const q = norm(queryInput.value.trim());
  const campo = campoFilter.value;
  const estado = estadoFilter.value;
  const hab = habFilter.value;
  return rows.filter(row => {
    if (hab === '1' && !row.habilitado) return false;
    if (hab === '0' && row.habilitado) return false;
    if (estado && row.estado !== estado) return false;
    if (campo && !(row.campos || []).some(item => String(item.id_campo) === campo)) return false;
    if (!q) return true;
    const blob = [row.patente, row.modelo, row.maquina, row.chasis, row.tractorista, row.contratista, row.trabajador]
      .concat((row.conductores || []).map(persona => persona.nombre))
      .map(norm).join(' ');
    return blob.includes(q);
  });
}

function render() {
  const shown = visibleRows();
  empty.hidden = shown.length > 0;
  empty.textContent = rows.length
    ? 'Ningún tractor coincide con el filtro.'
    : 'Todavía no hay tractores.';
  if (rows.length && habFilter.value === '1' && shown.length === 0 && !queryInput.value && !campoFilter.value && !estadoFilter.value) {
    empty.textContent = 'No hay tractores habilitados.';
  }
  card.hidden = shown.length === 0;
  document.getElementById('tr-count').textContent =
    shown.length === rows.length ? String(rows.length) : `${shown.length} de ${rows.length}`;
  tbody.innerHTML = shown.map(row => {
    const titulo = row.modelo || row.maquina || '—';
    const app = row.modelo && row.maquina && row.modelo !== row.maquina
      ? `<div class="tr-sub">${esc(row.maquina)}</div>` : '';
    const extra = row.en_catalogo ? '' : ' <span class="tr-pill tr-pill--sin_tarjas">Solo tarjas</span>';
    const off = row.habilitado ? '' : ' <span class="tr-pill tr-pill--quieto">No habilitado</span>';
    return `<tr>
    <td>${esc(row.patente || '—')}</td>
    <td>${esc(titulo)}${app}${extra}${off}</td>
    <td>${esc(row.chasis || '—')}</td>
    <td>${esc(row.tractorista || '—')}</td>
    <td>${esc(campoTexto(row))}</td>
    <td>${esc(anioTexto(row))}</td>
    <td>${esc(row.fecha_partida || '—')}</td>
    <td>${esc(row.antiguedad || '—')}</td>
    <td class="tr-cumple--${esc(row.cumple || '')}">${esc(cumpleTexto(row.cumple))}</td>
    <td>${esc(row.ultima_tarja || '—')}</td>
    <td class="tr-estado">
      <span class="tr-pill tr-pill--${esc(row.estado)}">${esc(row.estado_label)}</span>
      <span class="tr-sub">${esc(row.estado_motivo || '')}</span>
    </td>
    <td class="tr-actions">
      <button type="button" class="btn btn-secondary btn-sm" data-edit="${esc(row.id)}">Editar</button>
    </td>
  </tr>`;
  }).join('');
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  showError('');
  const maquina = maquinaInput.value.trim();
  if (!maquina) {
    showError('El nombre en la app es obligatorio.');
    return;
  }
  const patente = patenteInput.value.trim().toUpperCase();
  if (!/^[A-Z0-9]{4,12}$/.test(patente)) {
    showError('La patente tiene letras y números, sin espacios.');
    return;
  }
  const anio = anioInput.value.trim();
  if (anio && !/^\d{4}$/.test(anio)) {
    showError('El año tiene 4 dígitos.');
    return;
  }
  const fecha = fechaInput.value.trim();
  if (fecha && ageLabel(fecha) === 'Fecha no válida') {
    showError('La fecha de partida es DD/MM/YYYY.');
    return;
  }
  const elegidos = checkedCampos();
  if (!elegidos.length) {
    showError('Elige al menos un campo.');
    return;
  }
  const payload = {
    patente,
    modelo: modeloInput.value.trim() || null,
    maquina,
    color: colorInput.value.trim() || null,
    chasis: chasisInput.value.trim() || null,
    anio: anio || null,
    fecha_partida: fecha || null,
    tractorista: tractoristaInput.value.trim() || null,
    cumple: cumpleInput.value || null,
    campos: elegidos,
    habilitado: habilitadoInput.checked,
    reemplaza: editingNombre,
  };
  const creating = !editingPatente;
  saveBtn.disabled = true;
  const res = await fetch(creating ? '/api/tractores' : '/api/tractores/' + encodeURIComponent(editingPatente), {
    method: creating ? 'POST' : 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  saveBtn.disabled = false;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail;
    showError(typeof detail === 'string' ? detail : 'No se pudo guardar el tractor.');
    return;
  }
  closePanel();
  pageError.hidden = true;
  await load();
});

anioInput.addEventListener('input', () => {
  antiguedadEl.textContent = ageLabel(edadFuente());
});
fechaInput.addEventListener('input', () => {
  antiguedadEl.textContent = ageLabel(edadFuente());
});
function hoy() {
  const now = new Date();
  return String(now.getDate()).padStart(2, '0') + '/' +
    String(now.getMonth() + 1).padStart(2, '0') + '/' + now.getFullYear();
}

function estandar(carnet, operador, horario) {
  if (!tarifa) return [null, null];
  if (horario === 'lun_sab') {
    if (!operador) return [tarifa.sin_operador_9h, tarifa.sin_operador_sab];
    if (carnet) return [tarifa.con_carnet_9h, tarifa.con_carnet_sab];
    return [tarifa.sin_carnet_9h, tarifa.sin_carnet_sab];
  }
  if (!operador) return [tarifa.sin_operador_9h, tarifa.sin_operador_75];
  if (carnet) return [tarifa.con_carnet_9h, tarifa.con_carnet_75];
  return [tarifa.sin_carnet_9h, tarifa.sin_carnet_75];
}

function aplicarSugerido() {
  const [p9, p75] = estandar(cdCarnet.value === 'si', cdOperador.value === 'si', cdHorario.value);
  cdCampo9.hidden = cdHorario.value === 'lun_sab';
  const actual9 = Number(cdCosto9.value.replace(/\D/g, ''));
  const actual75 = Number(cdCosto75.value.replace(/\D/g, ''));
  if (cdCosto9.value === '' || actual9 === sugerido9) cdCosto9.value = p9 == null ? '' : String(p9);
  if (cdCosto75.value === '' || actual75 === sugerido75) cdCosto75.value = p75 == null ? '' : String(p75);
  sugerido9 = p9;
  sugerido75 = p75;
}

function showTab(name) {
  tab = name;
  document.querySelectorAll('.tr-tab').forEach(btn => {
    const on = btn.dataset.tab === name;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  flota.hidden = name !== 'flota';
  conductoresView.hidden = name !== 'conductores';
  addBtn.textContent = name === 'conductores' ? 'Agregar conductor' : 'Agregar';
}

function renderConductores() {
  const q = norm(cdQuery.value.trim());
  const shown = conductores.filter(row => !q || norm(row.trabajador).includes(q));
  cdEmpty.hidden = shown.length > 0;
  cdEmpty.textContent = conductores.length
    ? 'Ningún conductor coincide.'
    : 'No hay conductores.';
  cdCard.hidden = shown.length === 0;
  document.getElementById('cd-count').textContent = String(shown.length);
  cdBody.innerHTML = shown.map(row => `<tr>
    <td>${esc(row.trabajador)}${row.en_ficha ? '' : ' <span class="tr-pill tr-pill--quieto">Sin ficha</span>'}</td>
    <td>${esc(row.licencia)}</td>
    <td>${esc(row.horario)}</td>
    <td class="num">${row.esquema === 'lun_sab' ? '—' : esc(clp(row.jornada_9h))}</td>
    <td class="num">${esc(clp(row.jornada_75))}</td>
    <td>${esc(row.desde || '—')}</td>
    <td class="tr-actions">
      <button type="button" class="btn btn-secondary btn-sm" data-nombre="${esc(row.trabajador)}">${row.en_ficha ? 'Editar' : 'Crear ficha'}</button>
    </td>
  </tr>`).join('');
}

function openPerfil(row) {
  editingPerfil = row && row.en_ficha ? row.id : null;
  cdNombre.value = row ? row.trabajador : '';
  cdNombre.disabled = !!(row && row.en_ficha);
  cdTitle.textContent = row && row.en_ficha ? row.trabajador : 'Nuevo conductor';
  cdOperador.value = !row || row.con_operador !== false ? 'si' : 'no';
  cdCarnet.value = row && row.carnet === false ? 'no' : 'si';
  cdHorario.value = row && row.esquema ? row.esquema : 'lun_vie';
  cdDesde.value = row && row.desde ? row.desde : hoy();
  cdHasta.value = row && row.hasta ? row.hasta : '';
  const [p9, p75] = estandar(cdCarnet.value === 'si', cdOperador.value === 'si', cdHorario.value);
  sugerido9 = p9;
  sugerido75 = p75;
  cdCampo9.hidden = cdHorario.value === 'lun_sab';
  cdCosto9.value = row && row.en_ficha ? String(row.jornada_9h) : String(p9);
  cdCosto75.value = row && row.en_ficha ? String(row.jornada_75) : String(p75);
  cdError.hidden = true;
  cdPanel.hidden = false;
  cdOverlay.hidden = false;
  document.body.style.overflow = 'hidden';
  if (!cdNombre.disabled) cdNombre.focus();
}

function closePerfil() {
  editingPerfil = null;
  cdPanel.hidden = true;
  cdOverlay.hidden = true;
  if (panel.hidden) document.body.style.overflow = '';
}

function monto(input) {
  const digits = input.value.replace(/\D/g, '');
  return digits === '' ? null : Number(digits);
}

addBtn.addEventListener('click', () => {
  if (tab === 'conductores') openPerfil(null);
  else openCreate();
});
document.getElementById('tr-cancel').addEventListener('click', closePanel);
document.getElementById('tr-panel-close').addEventListener('click', closePanel);
overlay.addEventListener('click', closePanel);
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (!cdPanel.hidden) closePerfil();
  else if (!panel.hidden) closePanel();
});
document.querySelectorAll('.tr-tab').forEach(btn => {
  btn.addEventListener('click', () => showTab(btn.dataset.tab));
});
cdCarnet.addEventListener('change', aplicarSugerido);
cdOperador.addEventListener('change', aplicarSugerido);
cdHorario.addEventListener('change', aplicarSugerido);
cdQuery.addEventListener('input', renderConductores);
document.getElementById('cd-cancel').addEventListener('click', closePerfil);
document.getElementById('cd-panel-close').addEventListener('click', closePerfil);
cdOverlay.addEventListener('click', closePerfil);
cdBody.addEventListener('click', event => {
  const btn = event.target.closest('[data-nombre]');
  if (!btn) return;
  const row = conductores.find(item => item.trabajador === btn.dataset.nombre);
  if (row) openPerfil(row);
});
cdForm.addEventListener('submit', async event => {
  event.preventDefault();
  cdError.hidden = true;
  const payload = {
    trabajador: cdNombre.value,
    carnet: cdCarnet.value === 'si',
    con_operador: cdOperador.value === 'si',
    esquema: cdHorario.value,
    desde: cdDesde.value,
    hasta: cdHasta.value || null,
    costo_9h: cdHorario.value === 'lun_sab' ? null : monto(cdCosto9),
    costo_75: monto(cdCosto75),
  };
  const creating = !editingPerfil;
  const res = await fetch(creating ? '/api/conductores' : '/api/conductores/' + encodeURIComponent(editingPerfil), {
    method: creating ? 'POST' : 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data && data.detail;
    cdError.textContent = typeof detail === 'string' ? detail : 'No se pudo guardar la ficha.';
    cdError.hidden = false;
    return;
  }
  closePerfil();
  await load();
  showTab('conductores');
});
queryInput.addEventListener('input', render);
campoFilter.addEventListener('change', render);
habFilter.addEventListener('change', render);
estadoFilter.addEventListener('change', render);
tbody.addEventListener('click', event => {
  const editBtn = event.target.closest('[data-edit]');
  if (!editBtn) return;
  const row = rows.find(item => item.id === editBtn.dataset.edit);
  if (row) openEdit(row);
});

async function load() {
  const res = await fetch('/api/tractores');
  if (res.status === 403) {
    empty.hidden = false;
    empty.textContent = 'Solo un administrador puede ver la flota.';
    card.hidden = true;
    return;
  }
  if (!res.ok) {
    empty.hidden = false;
    empty.textContent = 'No se pudo cargar la flota.';
    card.hidden = true;
    return;
  }
  const data = await res.json();
  rows = data.tractores || [];
  campos = data.campos || [];
  tarifa = data.tarifa || null;
  renderTarifa();
  fillCampoOptions(campoFilter, campos, 'Todos');
  if (!panel.hidden) fillCampoChecks(checkedCampos());
  addBtn.disabled = false;
  render();
  const perfiles = await fetch('/api/conductores');
  if (!perfiles.ok) {
    cdEmpty.hidden = false;
    cdEmpty.textContent = 'No se pudo cargar los conductores.';
    cdCard.hidden = true;
    return;
  }
  const dataPerfiles = await perfiles.json();
  conductores = dataPerfiles.conductores || [];
  if (!tarifa && dataPerfiles.tarifa) tarifa = dataPerfiles.tarifa;
  renderConductores();
}

load();

})();

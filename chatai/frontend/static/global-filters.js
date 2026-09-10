// global-filters.js — Persist Empresa / Contratista / date range across report pages
// Canonical store: localStorage. URL query params win per-key on load (shareable links).
// Depends on url-filters.js (loaded first) for URL sync helpers.
//
// Public:
//   GLOBAL_FILTER_IDS, STORAGE_KEY
//   getGlobalFilters(), saveGlobalFilters()
//   window.globalFiltersReady — Promise resolved after selects are populated

'use strict';

const GLOBAL_FILTER_IDS = ['fil-from', 'fil-to', 'fil-empresa', 'fil-contratista'];
const STORAGE_KEY = 'donar.globalFilters';
const FILTERS_ENDPOINT = '/api/tarjas/general/filters';

function _toLocalISO(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function currentWeekRange() {
  const now = new Date();
  const day = now.getDay();
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  monday.setDate(monday.getDate() - (day === 0 ? 6 : day - 1));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  return { from: _toLocalISO(monday), to: _toLocalISO(sunday) };
}

function _readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const data = JSON.parse(raw);
    return data && typeof data === 'object' ? data : {};
  } catch (_) {
    return {};
  }
}

function _urlValue(id) {
  if (typeof _paramsWithAliases === 'function') {
    const params = _paramsWithAliases();
    return params.has(id) ? params.get(id) : null;
  }
  const params = new URLSearchParams(location.search);
  return params.has(id) ? params.get(id) : null;
}

function _el(id) {
  return document.getElementById(id);
}

function getGlobalFilters() {
  const out = {};
  GLOBAL_FILTER_IDS.forEach(id => {
    const el = _el(id);
    out[id] = el ? el.value : '';
  });
  return out;
}

function saveGlobalFilters() {
  const bar = document.getElementById('global-filter-bar');
  if (!bar) return;
  const data = getGlobalFilters();
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch (_) { /* quota / private mode */ }
}

function _applyValue(id, value) {
  const el = _el(id);
  if (!el || value == null) return;
  el.value = value;
}

function _hydrateDates() {
  const stored = _readStored();
  const week = currentWeekRange();

  const fromUrl = _urlValue('fil-from');
  const toUrl = _urlValue('fil-to');
  _applyValue('fil-from', fromUrl !== null ? fromUrl : (stored['fil-from'] || week.from));
  _applyValue('fil-to', toUrl !== null ? toUrl : (stored['fil-to'] || week.to));
}

function _hydrateSelects() {
  const stored = _readStored();
  GLOBAL_FILTER_IDS.slice(2).forEach(id => {
    const fromUrl = _urlValue(id);
    const val = fromUrl !== null ? fromUrl : (stored[id] || '');
    _applyValue(id, val);
  });
}

function _fillSelect(id, items, emptyLabel) {
  const sel = _el(id);
  if (!sel) return;
  const keep = sel.value;
  const list = Array.isArray(items) ? items : [];
  sel.innerHTML = `<option value="">${emptyLabel}</option>` +
    list.map(v => {
      const s = String(v);
      const safe = s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      return `<option value="${safe}">${safe}</option>`;
    }).join('');
  if (keep) sel.value = keep;
}

async function _loadEmpresaContratista() {
  const selE = _el('fil-empresa');
  const selC = _el('fil-contratista');
  if (!selE || !selC) return;
  try {
    const res = await fetch(FILTERS_ENDPOINT);
    if (!res.ok) return;
    const data = await res.json();
    _fillSelect('fil-empresa', data.empresas, 'Todas');
    _fillSelect('fil-contratista', data.contratistas, 'Todos');
  } catch (_) { /* non-fatal — empty dropdowns remain */ }
  _hydrateSelects();
}

function _bindPersistence() {
  const bar = document.getElementById('global-filter-bar');
  if (!bar) return;
  bar.addEventListener('change', saveGlobalFilters);
  bar.addEventListener('input', evt => {
    if (evt.target && (evt.target.id === 'fil-from' || evt.target.id === 'fil-to')) {
      saveGlobalFilters();
    }
  });
}

async function initGlobalFilters() {
  const bar = document.getElementById('global-filter-bar');
  if (!bar) return;
  _hydrateDates();
  _bindPersistence();
  saveGlobalFilters();
  await _loadEmpresaContratista();
  saveGlobalFilters();
}

// Expose for page scripts (presets, calendario panel sync, url-filters hooks)
window.GLOBAL_FILTER_IDS = GLOBAL_FILTER_IDS;
window.STORAGE_KEY = STORAGE_KEY;
window.getGlobalFilters = getGlobalFilters;
window.saveGlobalFilters = saveGlobalFilters;
window.currentWeekRange = currentWeekRange;
window.globalFiltersReady = initGlobalFilters();

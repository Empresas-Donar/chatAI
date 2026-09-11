// global-filters.js — Persist Empresa / Contratista / date range across report pages
// Canonical store: localStorage. URL query params win per-key on load (shareable links).
// Nav links to report pages are rewritten with the current globals so they survive navigation.
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
const REPORT_PREFIXES = ['/tarjas', '/dashboard', '/reportes', '/odoo', '/despacho'];

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

function _desired(id) {
  const fromUrl = _urlValue(id);
  if (fromUrl !== null) return fromUrl;
  const stored = _readStored()[id];
  return stored != null ? stored : '';
}

function _fold(s) {
  return String(s).normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

function _setSelectValue(el, val) {
  if (!el) return;
  if (val == null || val === '') {
    el.value = '';
    return;
  }
  const raw = String(val);
  const nfc = raw.normalize('NFC');
  const opts = Array.from(el.options);
  let match = opts.find(o => o.value === raw || o.value.normalize('NFC') === nfc);
  if (!match) {
    const folded = _fold(nfc);
    match = opts.find(o => _fold(o.value) === folded);
  }
  if (match) {
    el.value = match.value;
    return;
  }
  const opt = document.createElement('option');
  opt.value = raw;
  opt.textContent = raw;
  el.appendChild(opt);
  el.value = raw;
}

function _applyValue(id, value) {
  const el = _el(id);
  if (!el || value == null) return;
  if (el.tagName === 'SELECT') _setSelectValue(el, value);
  else el.value = value;
}

function getGlobalFilters() {
  const out = {};
  GLOBAL_FILTER_IDS.forEach(id => {
    const el = _el(id);
    out[id] = el ? el.value : '';
  });
  return out;
}

function _isReportPath(path) {
  return REPORT_PREFIXES.some(p => path === p || path.startsWith(p + '/'));
}

function decorateNavLinks() {
  const values = {};
  GLOBAL_FILTER_IDS.forEach(id => {
    const el = _el(id);
    const live = el ? el.value : '';
    values[id] = live || _readStored()[id] || '';
  });
  document.querySelectorAll('a[href]').forEach(a => {
    const href = a.getAttribute('href');
    if (!href || !href.startsWith('/') || href.startsWith('//')) return;
    let url;
    try {
      url = new URL(href, location.origin);
    } catch (_) {
      return;
    }
    if (!_isReportPath(url.pathname)) return;
    GLOBAL_FILTER_IDS.forEach(id => {
      if (values[id]) url.searchParams.set(id, values[id]);
      else url.searchParams.delete(id);
    });
    const qs = url.searchParams.toString();
    const next = url.pathname + (qs ? '?' + qs : '');
    if (href !== next) a.setAttribute('href', next);
  });
}

function _syncUrlFromGlobals() {
  const params = new URLSearchParams(location.search);
  GLOBAL_FILTER_IDS.forEach(id => {
    const el = _el(id);
    const val = el ? el.value : '';
    if (val) params.set(id, val);
    else params.delete(id);
  });
  const qs = params.toString();
  const newUrl = qs ? `${location.pathname}?${qs}` : location.pathname;
  const current = location.pathname + location.search;
  if (current !== newUrl) history.replaceState(null, '', newUrl);
}

function saveGlobalFilters() {
  const bar = document.getElementById('global-filter-bar');
  if (!bar) return;
  const stored = _readStored();
  const data = getGlobalFilters();
  GLOBAL_FILTER_IDS.forEach(id => {
    const el = _el(id);
    if (!el || el.tagName !== 'SELECT') return;
    if (el.value) return;
    const prev = stored[id];
    if (!prev) return;
    const hasOption = Array.from(el.options).some(o => o.value === prev);
    if (!hasOption) data[id] = prev;
  });
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch (_) { /* quota / private mode */ }
  decorateNavLinks();
  _syncUrlFromGlobals();
}

function _hydrateDates() {
  const week = currentWeekRange();
  const from = _desired('fil-from') || week.from;
  const to = _desired('fil-to') || week.to;
  _applyValue('fil-from', from);
  _applyValue('fil-to', to);
}

function _hydrateSelects() {
  GLOBAL_FILTER_IDS.slice(2).forEach(id => {
    _applyValue(id, _desired(id));
  });
}

function _fillSelect(id, items, emptyLabel) {
  const sel = _el(id);
  if (!sel) return;
  const preferred = _desired(id) || sel.value;
  const list = Array.isArray(items) ? items : [];
  sel.innerHTML = `<option value="">${emptyLabel}</option>` +
    list.map(v => {
      const s = String(v);
      const safe = s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      return `<option value="${safe}">${safe}</option>`;
    }).join('');
  _setSelectValue(sel, preferred);
}

async function _loadEmpresaContratista() {
  const selE = _el('fil-empresa');
  const selC = _el('fil-contratista');
  if (!selE || !selC) return;
  _hydrateSelects();
  try {
    const res = await fetch(FILTERS_ENDPOINT);
    if (!res.ok) return;
    const data = await res.json();
    _fillSelect('fil-empresa', data.empresas, 'Todas');
    _fillSelect('fil-contratista', data.contratistas, 'Todos');
  } catch (_) { /* non-fatal — placeholder options remain */ }
  _hydrateSelects();
}

function _bindPersistence() {
  const bar = document.getElementById('global-filter-bar');
  if (!bar) return;
  bar.addEventListener('change', () => {
    saveGlobalFilters();
    window.dispatchEvent(new CustomEvent('global-filters-change'));
  });
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
  await _loadEmpresaContratista();
  _bindPersistence();
  saveGlobalFilters();
}

// Expose for page scripts (presets, calendario panel sync, url-filters hooks)
window.GLOBAL_FILTER_IDS = GLOBAL_FILTER_IDS;
window.STORAGE_KEY = STORAGE_KEY;
window.getGlobalFilters = getGlobalFilters;
window.saveGlobalFilters = saveGlobalFilters;
window.currentWeekRange = currentWeekRange;
window.decorateNavLinks = decorateNavLinks;
window.globalFiltersReady = initGlobalFilters();

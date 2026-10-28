// global-filters.js — Persist dates / empresa / contratista across report pages.
// Dates lead. Empresa lists campos with tarjas in that range, then contratista
// lists whoever worked in the chosen campo.
// Empresa/contratista: localStorage. Dates: sessionStorage (custom range lasts the tab).
// URL query params win per-key on load (shareable links).
// Nav links to report pages are rewritten with the current globals so they survive navigation.
// Depends on url-filters.js (loaded first) for URL sync helpers.
//
// Default dates: last completed Wednesday–Tuesday (company close week).
//   Fri 11 Sep 2026 → 2026-09-02 .. 2026-09-08
//   Wed 16 Sep 2026 → 2026-09-09 .. 2026-09-15
//
// Public:
//   GLOBAL_FILTER_IDS, STORAGE_KEY
//   getGlobalFilters(), saveGlobalFilters(), currentWeekRange()
//   window.globalFiltersReady — Promise resolved after selects are populated

'use strict';

const GLOBAL_FILTER_IDS = ['fil-from', 'fil-to', 'fil-empresa', 'fil-contratista'];
const DATE_IDS = ['fil-from', 'fil-to'];
const STORAGE_KEY = 'donar.globalFilters';
const DATE_SESSION_KEY = 'donar.globalFilterDates';
const FILTERS_ENDPOINT = '/api/tarjas/general/filters';
const REPORT_PREFIXES = ['/tarjas', '/dashboard', '/reportes', '/odoo', '/despacho', '/cosecha'];

function _toLocalISO(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function currentWeekRange(now) {
  const today = now instanceof Date ? now : new Date();
  const d = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  d.setDate(d.getDate() - 1);
  while (d.getDay() !== 2) d.setDate(d.getDate() - 1);
  const tuesday = d;
  const wednesday = new Date(tuesday);
  wednesday.setDate(tuesday.getDate() - 6);
  return { from: _toLocalISO(wednesday), to: _toLocalISO(tuesday) };
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

function _readSessionDates() {
  try {
    const raw = sessionStorage.getItem(DATE_SESSION_KEY);
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
  if (DATE_IDS.includes(id)) {
    const sess = _readSessionDates()[id];
    return sess != null ? sess : '';
  }
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
    values[id] = el ? el.value : (_desired(id) || '');
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
    sessionStorage.setItem(DATE_SESSION_KEY, JSON.stringify({
      'fil-from': data['fil-from'] || '',
      'fil-to': data['fil-to'] || '',
    }));
  } catch (_) { /* quota / private mode */ }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      'fil-empresa': data['fil-empresa'] || '',
      'fil-contratista': data['fil-contratista'] || '',
    }));
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

function _matchItem(items, preferred) {
  if (!preferred) return '';
  const raw = String(preferred);
  const nfc = raw.normalize('NFC');
  const folded = _fold(nfc);
  const hit = (items || []).find(value => {
    const text = String(value);
    return text === raw || text.normalize('NFC') === nfc || _fold(text) === folded;
  });
  return hit == null ? '' : String(hit);
}

function _writeSelect(id, items, emptyLabel, preferred) {
  const sel = _el(id);
  if (!sel) return '';
  const list = Array.isArray(items) ? items : [];
  const chosen = _matchItem(list, preferred);
  sel.innerHTML = `<option value="">${emptyLabel}</option>` +
    list.map(value => {
      const text = String(value);
      const safe = text.replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      return `<option value="${safe}">${safe}</option>`;
    }).join('');
  sel.value = chosen;
  return chosen;
}

function _scopeParams(empresa) {
  const params = new URLSearchParams();
  const from = _el('fil-from')?.value || '';
  const to = _el('fil-to')?.value || '';
  if (from && to) {
    params.set('fecha_inicio', from);
    params.set('fecha_termino', to);
  }
  if (empresa) params.set('empresa', empresa);
  return params;
}

let _scopeGen = 0;

async function _fetchScope(empresa) {
  const params = _scopeParams(empresa);
  const qs = params.toString();
  const res = await fetch(FILTERS_ENDPOINT + (qs ? '?' + qs : ''));
  if (!res.ok) return null;
  return res.json();
}

function _usesDateCascade() {
  return !location.pathname.startsWith('/cosecha');
}

async function _loadScopedOptions(reloadEmpresas) {
  const gen = ++_scopeGen;
  const wanted = reloadEmpresas
    ? (_el('fil-empresa')?.value || _desired('fil-empresa') || '')
    : (_el('fil-empresa')?.value || '');
  let data;
  try {
    data = await _fetchScope(wanted);
  } catch (_) {
    return;
  }
  if (!data || gen !== _scopeGen) return;
  let empresa = wanted;
  if (reloadEmpresas) {
    empresa = _writeSelect('fil-empresa', data.empresas, 'Todas', wanted);
  }
  let contratistas = data.contratistas || [];
  if (reloadEmpresas && _fold(empresa) !== _fold(wanted)) {
    try {
      data = await _fetchScope(empresa);
    } catch (_) {
      return;
    }
    if (!data || gen !== _scopeGen) return;
    contratistas = data.contratistas || [];
  }
  _writeSelect(
    'fil-contratista',
    contratistas,
    'Todos',
    _el('fil-contratista')?.value || _desired('fil-contratista') || '',
  );
}

function _bindPersistence() {
  const bar = document.getElementById('global-filter-bar');
  if (!bar) return;
  bar.addEventListener('change', async evt => {
    const id = evt.target && evt.target.id;
    // Empresa and dates reload the lists before the report runs. Cover the
    // previous report for that whole wait, not only once the query starts.
    const cover = _usesDateCascade() && (id === 'fil-from' || id === 'fil-to' || id === 'fil-empresa');
    if (cover && typeof showReportLoading === 'function') showReportLoading();
    try {
      if (_usesDateCascade() && (id === 'fil-from' || id === 'fil-to')) {
        await _loadScopedOptions(true);
      } else if (_usesDateCascade() && id === 'fil-empresa') {
        await _loadScopedOptions(false);
      }
      saveGlobalFilters();
      window.dispatchEvent(new CustomEvent('global-filters-change'));
    } finally {
      if (cover && typeof hideReportLoading === 'function') hideReportLoading();
    }
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
  await _loadScopedOptions(true);
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

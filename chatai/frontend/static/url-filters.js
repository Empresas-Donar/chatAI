// url-filters.js — Shared utility: persist report filter state in URL query params
// Usage:
//   syncFiltersToURL(ids)              — call after a successful query to push current filter values to URL
//   loadFiltersFromURL(ids)            — call after dynamic selects are populated; returns true if any param was found
//   autoTriggerFromURL(ids, triggerFn) — restore filters then always run the report (do not wait for Consultar)
//   runReportQuery(fn)                 — overlay spinner while fn's promise settles (Odoo generate, etc.)
//   bindPopstate(ids, triggerFn)       — wire browser back/forward to restore filters and re-run the query
//
// id array entries: strings matching element IDs on the page.
// Empty values are omitted from the URL.
// Global IDs (fil-from, fil-to, fil-empresa, fil-contratista) are always merged in.
// Legacy aliases (inp-date-*, sel-contractor, sel-company, fil-date-*) map onto canonical IDs.

'use strict';

const _GLOBAL_FILTER_IDS = ['fil-from', 'fil-to', 'fil-empresa', 'fil-contratista'];

const FILTER_ALIASES = {
  'inp-date-from': 'fil-from',
  'inp-date-to': 'fil-to',
  'sel-contractor': 'fil-contratista',
  'sel-company': 'fil-empresa',
  'fil-date-from': 'fil-from',
  'fil-date-to': 'fil-to',
  'inp-contratista': 'fil-contratista',
  'inp-empresa': 'fil-empresa',
};

function _mergeFilterIds(ids) {
  const extra = Array.isArray(ids) ? ids : [];
  return [...new Set([..._GLOBAL_FILTER_IDS, ...extra])];
}

function _paramsWithAliases() {
  const params = new URLSearchParams(location.search);
  Object.keys(FILTER_ALIASES).forEach(alias => {
    const canonical = FILTER_ALIASES[alias];
    if (!params.has(canonical) && params.has(alias)) {
      params.set(canonical, params.get(alias));
    }
  });
  return params;
}

const _LOADING_ID = 'report-inline-loading';
let _loadingDepth = 0;

function _positionLoader(el) {
  const bar = document.getElementById('global-filter-bar');
  const nav = document.querySelector('.navbar');
  const top = bar ? bar.getBoundingClientRect().bottom
    : (nav ? nav.getBoundingClientRect().bottom : 58);
  el.style.top = Math.round(top) + 'px';
}

function showReportLoading() {
  const el = document.getElementById(_LOADING_ID);
  if (!el) return;
  _loadingDepth += 1;
  _positionLoader(el);
  el.hidden = false;
}

function _revealLoaderIfAuto() {
  const bar = document.getElementById('global-filter-bar');
  if (!bar || bar.hasAttribute('data-skip-auto-report')) return;
  const el = document.getElementById(_LOADING_ID);
  if (!el) return;
  _positionLoader(el);
  el.hidden = false;
}

function hideReportLoading() {
  _loadingDepth = Math.max(0, _loadingDepth - 1);
  if (_loadingDepth > 0) return;
  const el = document.getElementById(_LOADING_ID);
  if (el) el.hidden = true;
}

/** Show the overlay while fn runs. New pages should not call this — autoTriggerFromURL covers it. */
function runReportQuery(fn) {
  showReportLoading();
  try {
    const result = fn();
    if (result && typeof result.finally === 'function') {
      return result.finally(hideReportLoading);
    }
  } catch (err) {
    hideReportLoading();
    throw err;
  }
  hideReportLoading();
}

window.showReportLoading = showReportLoading;
window.hideReportLoading = hideReportLoading;
window.runReportQuery = runReportQuery;

_revealLoaderIfAuto();

window.addEventListener('resize', () => {
  const el = document.getElementById(_LOADING_ID);
  if (el && !el.hidden) _positionLoader(el);
});

/**
 * Read current values from elements and push them to the URL as query params.
 * Uses history.pushState so each Consultar click creates a back/forward entry.
 * @param {string[]} ids - Element IDs to serialize
 */
function syncFiltersToURL(ids) {
  ids = _mergeFilterIds(ids);
  const params = new URLSearchParams();
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el && el.value) {
      params.set(id, el.value);
    }
  });
  const qs = params.toString();
  const newUrl = qs ? `${location.pathname}?${qs}` : location.pathname;
  history.pushState(null, '', newUrl);
  if (typeof saveGlobalFilters === 'function') saveGlobalFilters();
}

/**
 * Read URL query params and restore matching element values.
 * For selects whose options may not exist yet, the value is still assigned —
 * browsers silently ignore invalid select values, so call this AFTER options
 * are populated via API when possible.
 * @param {string[]} ids - Element IDs to restore
 * @returns {boolean} true if at least one param was found and applied
 */
function _foldAccent(s) {
  return String(s).normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

function _setFilterValue(el, val) {
  if (!el) return;
  if (el.tagName !== 'SELECT') {
    el.value = val;
    return;
  }
  const raw = String(val);
  const nfc = raw.normalize('NFC');
  const opts = Array.from(el.options);
  let match = opts.find(o => o.value === raw || o.value.normalize('NFC') === nfc);
  if (!match) {
    const folded = _foldAccent(nfc);
    match = opts.find(o => _foldAccent(o.value) === folded);
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

function loadFiltersFromURL(ids) {
  ids = _mergeFilterIds(ids);
  const params = _paramsWithAliases();
  let found = false;
  ids.forEach(id => {
    const val = params.get(id);
    if (val !== null) {
      const el = document.getElementById(id);
      if (el) {
        _setFilterValue(el, val);
        found = true;
      }
    }
  });
  if (found && typeof saveGlobalFilters === 'function') saveGlobalFilters();
  return found;
}

/**
 * Restore filters then always run the report query (navigation must not wait for Consultar).
 * Also re-runs when the global filter bar changes.
 * Inline loading in the table slot hides when triggerFn's promise settles.
 */
let _autoQueryFn = null;
let _autoQueryIds = null;

function _runAutoQuery() {
  if (typeof _autoQueryFn !== 'function') return Promise.resolve();
  return Promise.resolve(runReportQuery(_autoQueryFn));
}

function _bindQueryButtons() {
  ['btn-apply', 'btn-apply-filter'].forEach(id => {
    const btn = document.getElementById(id);
    if (!btn || btn.dataset.gfBound) return;
    btn.dataset.gfBound = '1';
    btn.addEventListener('click', ev => {
      if (typeof _autoQueryFn !== 'function') return;
      if (id === 'btn-apply-filter') {
        document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
      }
      ev.preventDefault();
      ev.stopImmediatePropagation();
      _runAutoQuery().then(() => {
        if (typeof syncFiltersToURL === 'function' && _autoQueryIds) {
          syncFiltersToURL(_autoQueryIds);
        }
      });
    }, true);
  });
}

function autoTriggerFromURL(ids, triggerFn) {
  ids = _mergeFilterIds(ids);
  loadFiltersFromURL(ids);
  _autoQueryIds = ids;
  _autoQueryFn = triggerFn;
  _bindQueryButtons();
  _runAutoQuery();
}

window.addEventListener('global-filters-change', () => {
  if (typeof _autoQueryFn !== 'function') return;
  _runAutoQuery();
});

/**
 * Wire browser back/forward (popstate) to restore filter state and re-run the query.
 * @param {string[]} ids - Element IDs to restore
 * @param {Function} triggerFn - The query function to call after restoring
 */
function bindPopstate(ids, triggerFn) {
  ids = _mergeFilterIds(ids);
  window.addEventListener('popstate', () => {
    loadFiltersFromURL(ids);
    _autoQueryIds = ids;
    _autoQueryFn = triggerFn;
    _runAutoQuery();
  });
}

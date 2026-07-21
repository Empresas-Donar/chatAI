// url-filters.js — Shared utility: persist report filter state in URL query params
// Usage:
//   syncFiltersToURL(ids)              — call after a successful query to push current filter values to URL
//   loadFiltersFromURL(ids)            — call after dynamic selects are populated; returns true if any param was found
//   autoTriggerFromURL(ids, triggerFn) — load filters from URL and, if found, show a loading banner then call triggerFn
//   bindPopstate(ids, triggerFn)       — wire browser back/forward to restore filters and re-run the query
//
// id array entries: strings matching element IDs on the page.
// Empty values are omitted from the URL.

'use strict';

const _BANNER_ID = 'url-load-banner';

function _showLoadingBanner() {
  if (document.getElementById(_BANNER_ID)) return;
  const el = document.createElement('div');
  el.id = _BANNER_ID;
  el.setAttribute('aria-live', 'polite');
  el.style.cssText = [
    'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:9999',
    'display:flex', 'align-items:center', 'justify-content:center', 'gap:10px',
    'padding:10px 20px',
    'background:var(--terra,#C4503A)', 'color:#fff',
    'font-size:0.875rem', 'font-weight:500', 'letter-spacing:0.01em',
    'box-shadow:0 2px 8px rgba(0,0,0,0.18)',
    'transition:opacity 0.3s',
  ].join(';');
  el.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
    style="animation:url-spin 0.9s linear infinite;flex-shrink:0">
    <circle cx="12" cy="12" r="10" stroke-opacity="0.3"/>
    <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/>
  </svg>Cargando datos del enlace…`;

  const style = document.createElement('style');
  style.textContent = '@keyframes url-spin{to{transform:rotate(360deg)}}';
  document.head.appendChild(style);
  document.body.prepend(el);
}

function _hideLoadingBanner() {
  const el = document.getElementById(_BANNER_ID);
  if (!el) return;
  el.style.opacity = '0';
  setTimeout(() => el.remove(), 320);
}

/**
 * Read current values from elements and push them to the URL as query params.
 * Uses history.pushState so each Consultar click creates a back/forward entry.
 * @param {string[]} ids - Element IDs to serialize
 */
function syncFiltersToURL(ids) {
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
}

/**
 * Read URL query params and restore matching element values.
 * For selects whose options may not exist yet, the value is still assigned —
 * browsers silently ignore invalid select values, so call this AFTER options
 * are populated via API when possible.
 * @param {string[]} ids - Element IDs to restore
 * @returns {boolean} true if at least one param was found and applied
 */
function loadFiltersFromURL(ids) {
  const params = new URLSearchParams(location.search);
  let found = false;
  ids.forEach(id => {
    const val = params.get(id);
    if (val !== null) {
      const el = document.getElementById(id);
      if (el) {
        el.value = val;
        found = true;
      }
    }
  });
  return found;
}

/**
 * Load filters from URL and, if any params are found, show a loading banner and call triggerFn.
 * The banner auto-hides when triggerFn's promise resolves/rejects.
 * If triggerFn is not async, the banner hides immediately after the call.
 * @param {string[]} ids - Element IDs to restore
 * @param {Function} triggerFn - The query function to call (may return a Promise)
 */
function autoTriggerFromURL(ids, triggerFn) {
  if (!loadFiltersFromURL(ids)) return;
  _showLoadingBanner();
  const result = triggerFn();
  if (result && typeof result.finally === 'function') {
    result.finally(_hideLoadingBanner);
  } else {
    _hideLoadingBanner();
  }
}

/**
 * Wire browser back/forward (popstate) to restore filter state and re-run the query.
 * @param {string[]} ids - Element IDs to restore
 * @param {Function} triggerFn - The query function to call after restoring
 */
function bindPopstate(ids, triggerFn) {
  window.addEventListener('popstate', () => {
    loadFiltersFromURL(ids);
    triggerFn();
  });
}

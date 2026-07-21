// url-filters.js — Shared utility: persist report filter state in URL query params
// Usage:
//   syncFiltersToURL(ids)          — call after a successful query to push current filter values to URL
//   loadFiltersFromURL(ids)        — call after dynamic selects are populated; returns true if any param was found
//   bindPopstate(ids, triggerFn)   — wire browser back/forward to restore filters and re-run the query
//
// id array entries: strings matching element IDs on the page.
// Empty values are omitted from the URL.

'use strict';

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

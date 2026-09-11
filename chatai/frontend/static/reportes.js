/* reportes.js — Bulk PDF download page */

(function () {
  'use strict';

  // ── DOM refs ──────────────────────────────────────────────────────────────
  const filFrom     = document.getElementById('fil-from');
  const filTo       = document.getElementById('fil-to');
  const filEmpresa      = document.getElementById('fil-empresa');
  const filContratista  = document.getElementById('fil-contratista');
  const btnDownload = document.getElementById('btn-download');
  const btnSelectAll = document.getElementById('btn-select-all');
  const btnClearAll  = document.getElementById('btn-clear-all');
  const repCount    = document.getElementById('rep-count');
  const loadingEl   = document.getElementById('rep-loading');

  // ── Default dates: owned by global bar (closed Wed–Tue week) ─────────────
  function setDefaultDates() {
    const fromEl = document.getElementById('fil-from');
    const toEl = document.getElementById('fil-to');
    if (fromEl && fromEl.value && toEl && toEl.value) return;
    if (typeof currentWeekRange === 'function') {
      const w = currentWeekRange();
      fromEl.value = w.from;
      toEl.value = w.to;
    }
  }

  async function loadFilters() {
    if (window.globalFiltersReady) await window.globalFiltersReady;
    setDefaultDates();
  }

  // ── Checkbox / card selection ─────────────────────────────────────────────
  function getCheckboxes() {
    return Array.from(document.querySelectorAll('.rep-checkbox'));
  }

  function getSelected() {
    return getCheckboxes().filter(cb => cb.checked).map(cb => cb.value);
  }

  function updateState() {
    const selected = getSelected();
    const count = selected.length;
    repCount.textContent = count === 1 ? '1 reporte seleccionado' : `${count} reportes seleccionados`;
    btnDownload.disabled = count === 0 || !filFrom.value || !filTo.value;
  }

  function initCards() {
    document.querySelectorAll('.rep-card').forEach(card => {
      const cb = card.querySelector('.rep-checkbox');
      card.addEventListener('click', () => {
        cb.checked = !cb.checked;
        card.classList.toggle('selected', cb.checked);
        updateState();
      });
    });
  }

  btnSelectAll.addEventListener('click', () => {
    getCheckboxes().forEach(cb => {
      cb.checked = true;
      cb.closest('.rep-card').classList.add('selected');
    });
    updateState();
  });

  btnClearAll.addEventListener('click', () => {
    getCheckboxes().forEach(cb => {
      cb.checked = false;
      cb.closest('.rep-card').classList.remove('selected');
    });
    updateState();
  });

  filFrom.addEventListener('change', updateState);
  filTo.addEventListener('change', updateState);

  // ── Download ──────────────────────────────────────────────────────────────
  btnDownload.addEventListener('click', async () => {
    const selected = getSelected();
    if (!selected.length) return;

    const from = filFrom.value;
    const to   = filTo.value;
    if (!from || !to) return;

    const params = new URLSearchParams({
      reports: selected.join(','),
      fecha_inicio: from,
      fecha_termino: to,
    });
    if (filEmpresa.value) params.set('empresa', filEmpresa.value);
    if (filContratista.value) params.set('contratista', filContratista.value);

    loadingEl.style.display = 'flex';
    btnDownload.disabled = true;

    try {
      const res = await fetch(`/api/reportes/bulk-pdf?${params}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error desconocido' }));
        alert('Error al generar el PDF: ' + (err.detail || res.statusText));
        return;
      }
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `reportes_${from}_${to}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('Error de conexión al servidor.');
    } finally {
      loadingEl.style.display = 'none';
      updateState();
    }
  });

  // ── URL filter sync ───────────────────────────────────────────────────────
  const FILTER_IDS = ['fil-from', 'fil-to', 'fil-empresa', 'fil-contratista'];

  // Sync URL when user clicks download (secondary listener on btnDownload)
  btnDownload.addEventListener('click', () => {
    syncFiltersToURL(FILTER_IDS);
  });

  // ── Init ──────────────────────────────────────────────────────────────────
  loadFilters().then(() => {
    // Restore URL params after selects are populated; no auto-trigger (download is manual)
    loadFiltersFromURL(FILTER_IDS);
    updateState();
  });
  initCards();
  updateState();
})();

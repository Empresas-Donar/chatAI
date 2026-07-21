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

  // ── Default dates: current week Mon–Sun ───────────────────────────────────
  function setDefaultDates() {
    const today = new Date();
    const day = today.getDay();
    const diffMon = (day === 0 ? -6 : 1 - day);
    const mon = new Date(today);
    mon.setDate(today.getDate() + diffMon);
    const sun = new Date(mon);
    sun.setDate(mon.getDate() + 6);

    filFrom.value = mon.toISOString().slice(0, 10);
    filTo.value   = sun.toISOString().slice(0, 10);
  }

  // ── Load empresas ─────────────────────────────────────────────────────────
  async function loadFilters() {
    try {
      const res = await fetch('/api/tarjas/general/filters');
      if (!res.ok) return;
      const data = await res.json();
      (data.empresas || []).forEach(e => {
        const opt = document.createElement('option');
        opt.value = e; opt.textContent = e;
        filEmpresa.appendChild(opt);
      });
      (data.contratistas || []).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c; opt.textContent = c;
        filContratista.appendChild(opt);
      });
    } catch (_) { /* non-fatal */ }
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
  setDefaultDates();
  loadFilters().then(() => {
    // Restore URL params after selects are populated; no auto-trigger (download is manual)
    loadFiltersFromURL(FILTER_IDS);
    updateState();
  });
  initCards();
  updateState();
})();

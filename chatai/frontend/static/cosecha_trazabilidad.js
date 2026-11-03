(function () {
  const form = document.getElementById('traza-form');
  const input = document.getElementById('traza-q');
  const list = document.getElementById('traza-list');
  const error = document.getElementById('traza-error');
  const empty = document.getElementById('traza-empty');
  const matches = document.getElementById('traza-matches');
  const detail = document.getElementById('traza-detail');
  let current = [];
  let catalog = [];
  let shown = [];
  let active = -1;
  let browsing = false;
  let pickedQuery = '';
  let catalogGen = 0;

  function fold(value) {
    return (value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  }

  function money(value) {
    return '$' + Number(value || 0).toLocaleString('es-CL');
  }

  function slash(iso) {
    if (!iso || iso.length < 10) return iso || '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return d + '/' + m + '/' + y;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function showError(message) {
    error.hidden = !message;
    error.textContent = message || '';
  }

  async function search(q) {
    showError('');
    empty.hidden = true;
    matches.hidden = true;
    detail.hidden = true;
    clear(matches);
    clear(detail);
    if (window.showReportLoading) window.showReportLoading();
    try {
      const params = filters();
      params.set('q', q);
      const res = await fetch('/api/cosecha/trazabilidad?' + params);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        showError(body.detail || 'No se pudo buscar');
        return;
      }
      current = body.personas || [];
      if (!current.length) {
        empty.hidden = false;
        return;
      }
      renderMatches();
      showPerson(0);
      if (current.length === 1) input.value = current[0].nombre;
      const url = new URL(window.location.href);
      url.searchParams.set('q', q);
      window.history.replaceState(null, '', url);
    } finally {
      if (window.hideReportLoading) window.hideReportLoading();
    }
  }

  function renderMatches() {
    clear(matches);
    if (current.length < 2) {
      matches.hidden = true;
      return;
    }
    matches.hidden = false;
    current.forEach((person, index) => {
      const button = el('button', 'traza-match');
      button.type = 'button';
      button.appendChild(el('strong', '', person.nombre));
      const meta = [person.rut, (person.contratistas || []).join(', '), person.capachos + ' capachos']
        .filter(Boolean)
        .join(' · ');
      button.appendChild(el('small', '', meta));
      button.addEventListener('click', () => showPerson(index));
      matches.appendChild(button);
    });
  }

  function showPerson(index) {
    Array.from(matches.children).forEach((button, i) => {
      button.classList.toggle('is-active', i === index);
    });
    const person = current[index];
    clear(detail);
    detail.hidden = false;

    const head = el('div', 'traza-head');
    const titles = el('div');
    titles.appendChild(el('h2', '', person.nombre));
    const bits = [
      person.rut,
      (person.contratistas || []).join(', '),
      (person.cuadrillas || []).map(n => 'cuadrilla ' + n).join(', '),
      person.capachos + ' capachos',
      (person.dias_trabajados || (person.dias || []).length) + ' días',
    ];
    if (person.desde) bits.push(slash(person.desde) + ' – ' + slash(person.hasta));
    titles.appendChild(el('p', '', bits.filter(Boolean).join(' · ')));
    head.appendChild(titles);
    head.appendChild(el(
      'span',
      person.credencial_vigente ? 'traza-badge traza-badge--ok' : 'traza-badge traza-badge--warn',
      person.credencial_vigente ? 'Credencial vigente' : 'Sin credencial vigente'
    ));
    detail.appendChild(head);

    if (person.alertas && person.alertas.length) {
      const list = el('ul', 'traza-alerts');
      person.alertas.forEach(note => list.appendChild(el('li', '', note)));
      detail.appendChild(list);
    }

    const cards = el('div', 'summary-grid');
    cards.appendChild(summaryCard('QR usados', String(person.qrs_usados || 0)));
    cards.appendChild(summaryCard('Cuadrillas', String(person.cuadrillas_trabajadas || 0)));
    cards.appendChild(summaryCard('Días', String(person.dias_trabajados || (person.dias || []).length)));
    cards.appendChild(summaryCard('Capachos', String(person.capachos || 0)));
    detail.appendChild(cards);

    if (person.qrs && person.qrs.length) {
      detail.appendChild(tableCard(
        'Credenciales usadas',
        ['Código', 'Capachos', 'Cuadrillas', 'Desde', 'Hasta', 'Estado'],
        person.qrs.map(qr => [
          qr.codigo_qr,
          String(qr.capachos),
          (qr.cuadrillas || []).join(', '),
          slash(qr.desde),
          slash(qr.hasta),
          qr.estado,
        ]),
        [1]
      ));
    }

    if (person.por_cuadrilla && person.por_cuadrilla.length) {
      detail.appendChild(tableCard(
        'Cuadrillas',
        ['Cuadrilla', 'Contratista', 'Capachos', 'QR', 'Desde', 'Hasta'],
        person.por_cuadrilla.map(crew => [
          crew.cuadrilla,
          (crew.contratistas || []).join(', '),
          String(crew.capachos),
          String(crew.qrs),
          slash(crew.desde),
          slash(crew.hasta),
        ]),
        [0, 2, 3]
      ));
    }

    if (person.fichas && person.fichas.length) {
      detail.appendChild(tableCard(
        'Credencial en el catálogo',
        ['Código', 'Nombre', 'RUT', 'Contratista', 'Cuadrilla'],
        person.fichas.map(ficha => [
          ficha.codigo_qr, ficha.trabajador, ficha.rut, ficha.contratista, ficha.cuadrilla,
        ])
      ));
    }

    if (person.dias && person.dias.length) {
      detail.appendChild(tableCard(
        'Por día',
        ['Fecha', 'Horario', 'Contratista', 'Cuadrilla', 'Cuartel', 'Capachos', 'Trato', 'Piso', 'A pagar'],
        person.dias.map(day => [
          slash(day.fecha),
          day.desde + '–' + day.hasta,
          (day.contratistas || []).join(', '),
          (day.cuadrillas || []).join(', '),
          (day.cuarteles || []).join(', '),
          String(day.capachos),
          money(day.trato),
          money(day.piso),
          money(day.a_pagar),
        ]),
        [5, 6, 7, 8]
      ));
    }

    if (person.escaneos && person.escaneos.length) {
      detail.appendChild(tableCard(
        'Capachos',
        ['Fecha', 'Hora', 'Contratista', 'Cuadrilla', 'Bin', 'Cuartel', 'Precio', 'Credencial'],
        person.escaneos.map(scan => [
          slash(scan.fecha),
          scan.hora,
          scan.contratista,
          scan.cuadrilla,
          scan.bins,
          scan.cuartel,
          money(scan.precio),
          scan.codigo_qr,
        ]),
        [6]
      ));
    }
  }

  function summaryCard(label, value) {
    const card = el('div', 'summary-card');
    card.appendChild(el('div', 'card-label', label));
    card.appendChild(el('div', 'card-main', value));
    return card;
  }

  function tableCard(title, headers, rows, numericCols) {
    const card = el('div', 'table-card');
    const header = el('div', 'table-header');
    header.appendChild(el('span', '', title));
    header.appendChild(el('span', 'count', String(rows.length)));
    card.appendChild(header);
    const wrap = el('div');
    wrap.style.overflowX = 'auto';
    const table = el('table', 'tbl');
    const thead = el('thead');
    const headRow = el('tr');
    headers.forEach((label, i) => {
      headRow.appendChild(el('th', (numericCols || []).includes(i) ? 'num' : '', label));
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = el('tbody');
    rows.forEach(values => {
      const tr = el('tr');
      values.forEach((value, i) => {
        const cell = el('td', (numericCols || []).includes(i) ? 'num' : '', value);
        tr.appendChild(cell);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    card.appendChild(wrap);
    return card;
  }

  function closeList() {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    active = -1;
  }

  function openList() {
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  }

  function workerQuery(worker) {
    return (worker.rut || worker.nombre || '').trim();
  }

  function workerMeta(worker) {
    return [worker.rut, worker.contratista, worker.cuadrilla ? 'cuadrilla ' + worker.cuadrilla : '', worker.capachos + ' capachos', (worker.dias_trabajados || 0) + ' días']
      .filter(Boolean)
      .join(' · ');
  }

  function filters() {
    const params = new URLSearchParams();
    const from = document.getElementById('fil-from')?.value || '';
    const to = document.getElementById('fil-to')?.value || '';
    const empresa = document.getElementById('fil-empresa')?.value || '';
    const contratista = document.getElementById('fil-contratista')?.value || '';
    if (from) params.set('fecha_inicio', from);
    if (to) params.set('fecha_termino', to);
    if (empresa) params.set('empresa', empresa);
    if (contratista) params.set('contratista', contratista);
    return params;
  }

  function renderList() {
    clear(list);
    const raw = browsing ? '' : input.value.trim();
    const tokens = fold(raw).split(/\s+/).filter(part => part.length >= 1);
    shown = catalog.filter(worker => {
      if (!tokens.length) return true;
      const haystack = fold([worker.nombre, worker.rut, worker.contratista, worker.cuadrilla].join(' '));
      return tokens.every(token => haystack.includes(token));
    });
    if (!shown.length) {
      list.appendChild(el(
        'li',
        'traza-option traza-option--empty',
        catalog.length ? 'Nadie coincide con la búsqueda' : 'Nadie cosechó en este filtro'
      ));
      active = -1;
      openList();
      return;
    }
    shown.forEach((worker, index) => {
      const item = el('li', 'traza-option');
      item.setAttribute('role', 'option');
      item.appendChild(el('strong', '', worker.nombre));
      item.appendChild(el('small', '', workerMeta(worker)));
      item.addEventListener('mousedown', event => {
        event.preventDefault();
        choose(index);
      });
      list.appendChild(item);
    });
    const currentIndex = shown.findIndex(worker => workerQuery(worker) === pickedQuery);
    active = currentIndex >= 0 ? currentIndex : 0;
    markActive();
    openList();
  }

  function markActive() {
    Array.from(list.children).forEach((item, index) => {
      const on = index === active;
      item.classList.toggle('is-active', on);
      if (on) item.scrollIntoView({ block: 'nearest' });
    });
  }

  function choose(index) {
    const worker = shown[index];
    if (!worker) return;
    input.value = worker.nombre;
    pickedQuery = workerQuery(worker);
    browsing = true;
    closeList();
    search(pickedQuery);
  }

  input.addEventListener('input', () => {
    browsing = false;
    pickedQuery = '';
    renderList();
  });
  input.addEventListener('focus', () => {
    browsing = true;
    renderList();
    input.select();
  });
  input.addEventListener('keydown', event => {
    if (list.hidden) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      active = Math.min(active + 1, shown.length - 1);
      markActive();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      active = Math.max(active - 1, 0);
      markActive();
    } else if (event.key === 'Enter' && active >= 0) {
      event.preventDefault();
      choose(active);
    } else if (event.key === 'Escape') {
      closeList();
    }
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.traza-combo')) closeList();
  });

  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!list.hidden && active >= 0) {
      choose(active);
      return;
    }
    const q = input.value.trim();
    if (q.length < 3) {
      showError('Escribe al menos 3 letras o el RUT');
      return;
    }
    closeList();
    search(q);
  });

  async function loadCatalog() {
    const gen = ++catalogGen;
    const res = await fetch('/api/cosecha/trazabilidad/trabajadores?' + filters());
    if (gen !== catalogGen) return;
    const body = res.ok ? await res.json().catch(() => ({})) : {};
    catalog = body.trabajadores || [];
    if (!list.hidden) renderList();
  }

  async function applyFilters() {
    await loadCatalog();
    if (pickedQuery) await search(pickedQuery);
  }

  async function start() {
    pickedQuery = new URLSearchParams(window.location.search).get('q') || '';
    if (pickedQuery) input.value = pickedQuery;
    if (window.globalFiltersReady) await window.globalFiltersReady;
    const ids = ['fil-from', 'fil-to', 'fil-empresa', 'fil-contratista'];
    autoTriggerFromURL(ids, applyFilters);
    bindPopstate(ids, applyFilters);
  }

  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start);
})();

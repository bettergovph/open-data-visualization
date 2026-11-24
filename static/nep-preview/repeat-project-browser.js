(() => {
  'use strict';
  const browser = document.getElementById('repeat-project-browser');
  if (!browser) return;
  const get = name => browser.querySelector('.repeat-browser-' + name);
  const timeline = get('years'), record = get('record'), photoStage = get('photo-stage');
  const photoLabel = get('photo-label'), photoSource = get('photo-source');
  const photoControls = get('photo-controls'), photoSelect = photoControls.querySelector('select');
  const previous = get('prev'), next = get('next'), retry = get('retry'), position = get('position');
  const filters = [...browser.querySelectorAll('[data-repeat-filter]')];
  const periodFilters = [...browser.querySelectorAll('[data-repeat-period]')];
  const search = get('title-search')?.querySelector('input');
  const places = [...browser.querySelectorAll('[data-repeat-place]')], clearPlace = get('clear-place');
  const locationLinks = get('location') || element('div', '', 'repeat-browser-location');
  if (!locationLinks.isConnected) get('stats').after(locationLinks);
  const number = value => Number(value).toLocaleString('en-PH');
  const peso = value => '₱' + number(value);
  const currentStages = ['2027 SCR', '2027 HGAB', '2027 NEP'];
  const pages = new Map();
  let index, project, category = 'all', current = 0, selected, activePhoto = -1;
  let period = periodFilters.length ? '2027' : 'all', linked2027 = new Set();
  let geography = new Map(), results = null, requestId = 0;
  let titles, titleRequest;
  const searchKey = title => title.trim().toLowerCase().replace(/\s+/g, ' ');

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function link(text, href) {
    const node = element('a', text);
    node.href = href;
    node.target = '_blank';
    node.rel = 'noopener';
    return node;
  }

  function showPhoto(index) {
    if (index === activePhoto) return;
    activePhoto = index;
    const attachment = project.photos?.[index];
    if (!attachment) {
      photoStage.replaceChildren(element('p', 'No linked photo attachment in the current records.'));
      photoLabel.textContent = 'Project photo evidence';
      photoSource.hidden = true;
      return;
    }
    const label = attachment.label + (attachment.preview ? ' · photo preview' : '');
    photoLabel.textContent = attachment.projectTitle ? label + ' · ' + attachment.projectTitle : label;
    photoSource.hidden = false;
    photoSource.href = attachment.url;
    photoSource.textContent = attachment.format === 'pdf' ? 'Open photo PDF ↗' : 'Open photo source ↗';
    photoSelect.value = String(index);
    if (attachment.preview || attachment.format === 'image') {
      const img = element('img');
      img.alt = attachment.label + ' photo evidence for ' + (attachment.projectTitle || project.title);
      img.decoding = 'async';
      img.onerror = () => {
        if (photoStage.contains(img)) showPdfOrFallback(attachment);
      };
      img.src = attachment.preview || attachment.url;
      photoStage.replaceChildren(img);
    } else {
      showPdfOrFallback(attachment);
    }
  }

  function showPdfOrFallback(attachment) {
    if (attachment.format !== 'pdf' || navigator.pdfViewerEnabled === false) {
      photoStage.replaceChildren(element('p', 'Open the source link to view this photo attachment.'));
      return;
    }
    const frame = element('iframe');
    frame.title = attachment.label + ' photo attachment';
    frame.loading = 'lazy';
    frame.referrerPolicy = 'no-referrer';
    frame.src = attachment.url + '#page=1&toolbar=0&view=Fit';
    photoStage.replaceChildren(frame);
  }

  function showLocation(item) {
    const records = [...project.stages, ...project.years.flatMap(([, rows]) => rows)];
    const route = item.points?.length === 2 ? item : records.find(row => row.points?.length === 2);
    const location = item.points?.length ? item : route || records.find(row => row.points?.length);
    const reported = new Map();
    for (const row of records) {
      for (const point of row.points || []) {
        if (!reported.has(point.join(','))) reported.set(point.join(','), row.stage);
      }
    }
    const comparison = !route && reported.size === 2 ? [...reported.keys()] : null;
    const endpoints = route?.points.map(point => point.join(',')) || comparison;
    const pins = comparison || location?.points.map(point => point.join(','));
    const links = [];
    if (pins) {
      for (const [i, point] of pins.entries()) {
        const label = pins.length === 1 ? 'Google Maps ↗' : 'Google Maps · point ' + (i + 1) + ' ↗';
        const params = new URLSearchParams({api: '1', query: point});
        links.push(link(label, 'https://www.google.com/maps/search/?' + params));
      }
    } else {
      const params = new URLSearchParams({api: '1', query: project.title});
      links.push(link('Search Google Maps ↗', 'https://www.google.com/maps/search/?' + params));
    }
    if (endpoints) {
      const [origin, destination] = endpoints;
      const params = new URLSearchParams({api: '1', origin, destination});
      const directions = link('Route ↗', 'https://www.google.com/maps/dir/?' + params);
      directions.className = 'repeat-browser-route';
      directions.title = 'Directions between reported points';
      links.push(directions);
    }
    const context = location ? 'Map points from ' + location.stage : 'Search by project title';
    let details = context;
    if (comparison) details = 'Route between reported locations · ' + comparison.map(point => reported.get(point)).join(' / ');
    else if (route && route !== location) details += ' · Route points from ' + route.stage;
    else if (!route) details += ' · Route unavailable';
    locationLinks.replaceChildren(...links, element('span', details));
    locationLinks.hidden = false;
  }

  function select(item, button) {
    if (selected) selected.setAttribute('aria-pressed', 'false');
    selected = button;
    selected.setAttribute('aria-pressed', 'true');
    const heading = element('p');
    heading.append(element('strong', item.stage), document.createTextNode(' · ' + item.title));
    const details = [item.status, item.source].filter(Boolean).join(' · ');
    const sourceLinks = element('p', '', 'repeat-browser-record-links');
    if (item.url) sourceLinks.append(link(item.url.includes('project-documents.html') ? 'Open project documents ↗' : 'Open budget source ↗', item.url));
    record.replaceChildren(heading);
    if (details) record.append(element('p', details));
    if (sourceLinks.childElementCount) record.append(sourceLinks);
    showLocation(item);
    const photos = project.photos || [];
    const preferred = item.stage === '2027 HGAB' ? 'HGAB' : item.stage === '2027 NEP' ? 'Proposal' : '';
    const match = preferred ? photos.findIndex(photo => photo.stage === preferred) : -1;
    if (match >= 0 || activePhoto < 0) showPhoto(match >= 0 ? match : photos.length ? 0 : -2);
  }

  function stageGroup(label, items) {
    const group = element('div', '', 'repeat-browser-year');
    if (!items.length) {
      const missing = element('div', '', 'repeat-browser-missing');
      missing.append(element('strong', label), element('span', 'No linked row'));
      group.append(missing);
    }
    for (const [index, item] of items.entries()) {
      const button = element('button');
      button.type = 'button';
      button.setAttribute('aria-pressed', 'false');
      button.title = item.title;
      button.append(element('strong', label + (items.length > 1 ? ' · ' + (index + 1) : '')),
        element('span', item.status === 'Removed' ? 'Removed' : item.pesos == null ? 'Amount unavailable' : peso(item.pesos)));
      button.onclick = () => select(item, button);
      group.append(button);
    }
    return group;
  }

  function stat(value, label) {
    const node = element('span');
    node.append(element('strong', value), document.createTextNode(' ' + label));
    return node;
  }

  function render() {
    get('title').textContent = project.title;
    get('office').textContent = project.office;
    const total = resultCount();
    position.textContent = 'Project ' + number(current + 1) + ' of ' + number(total);
    const repeated = index.mode === '2027' ? 'FY2027 candidate pair' : 'matched GAA line';
    get('stats').replaceChildren(stat(number(project.repeatCount), repeated + (project.repeatCount === 1 ? '' : 's')),
      stat(peso(project.total), project.totalLabel || 'combined GAA allocation'));
    get('stats').hidden = false;
    get('body').hidden = false;
    previous.disabled = current === 0;
    next.disabled = current === total - 1;
    timeline.replaceChildren();
    selected = null;
    activePhoto = -1;
    photoSelect.replaceChildren();
    for (const [i, attachment] of (project.photos || []).entries()) {
      const option = element('option', attachment.label + ' · ' + (i + 1));
      option.value = String(i);
      photoSelect.append(option);
    }
    photoControls.hidden = photoSelect.length < 2;
    const groups = [
      ...currentStages.map(stage => [stage, project.stages.filter(item => item.stage === stage)]),
      ...project.years.map(([year, rows]) => [year + ' GAA', rows]),
    ];
    let defaultButton, routeButton, pointButton;
    for (const [label, rows] of groups) {
      const group = stageGroup(label, rows);
      timeline.append(group);
      const buttons = group.querySelectorAll('button');
      for (const [i, item] of rows.entries()) {
        defaultButton ??= buttons[i];
        if (item.points?.length === 2) routeButton ??= buttons[i];
        if (item.points?.length) pointButton ??= buttons[i];
      }
    }
    (routeButton || pointButton || defaultButton).click();
    timeline.scrollTop = 0;
  }

  async function fetchJson(url) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch(url, {signal: controller.signal});
      if (!response.ok) throw Error('HTTP ' + response.status);
      return await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }

  function showError(message, restart, error) {
    position.textContent = message;
    retry.onclick = restart;
    retry.hidden = false;
    console.warn('Historical project browser unavailable:', error);
  }

  function resultCount() {
    return results?.length ?? index.total;
  }

  function optionsFor(level) {
    const region = places[0].value, province = places[1].value, town = places[2].value;
    return [...geography.values()].filter(place => {
      if (place.level !== level) return false;
      if (level === 'region') return true;
      if (level === 'province') return region && place.parent === region;
      if (level === 'barangay') return town && place.parent === town;
      if (province) return place.parent === province;
      return region && (place.parent === region || geography.get(place.parent)?.parent === region);
    }).sort((a, b) => a.name.localeCompare(b.name));
  }

  function fillPlaces(changed = -1) {
    for (const [i, select] of places.entries()) {
      const keep = i <= changed ? select.value : '';
      const options = optionsFor(select.dataset.repeatPlace);
      const names = new Map();
      for (const place of options) names.set(place.name, (names.get(place.name) || 0) + 1);
      select.replaceChildren(select.options[0], ...options.map(place => {
        const parent = names.get(place.name) > 1 && geography.get(place.parent);
        return new Option(parent ? place.name + ' · ' + parent.name : place.name, place.code);
      }));
      select.value = options.some(place => place.code === keep) ? keep : '';
      select.disabled = options.length === 0;
    }
    if (clearPlace) clearPlace.disabled = !places.some(select => select.value);
  }

  function applyFilters() {
    const query = searchKey(search?.value || '');
    const place = places.reduce((code, select) => select.value || code, '');
    const ranked = category === 'all' ? null : (index.filters?.[category] || []);
    const atPlace = geography.get(place)?.offsets;
    if (ranked && atPlace) {
      const available = new Set(atPlace);
      results = ranked.filter(offset => available.has(offset));
    } else {
      results = ranked || atPlace || null;
    }
    if (period === '2027') {
      results = results ? results.filter(offset => linked2027.has(offset)) : index.linked2027;
    }
    for (const button of periodFilters) {
      button.setAttribute('aria-pressed', String(button.dataset.repeatPeriod === period));
    }
    for (const button of filters) {
      const key = button.dataset.repeatFilter;
      button.disabled = key !== 'all' && !index.filters?.[key]?.length;
      button.setAttribute('aria-pressed', String(key === category));
    }
    const ticket = ++requestId;
    current = 0;
    retry.hidden = true;
    get('title').textContent = '';
    get('office').textContent = '';
    get('stats').hidden = get('body').hidden = locationLinks.hidden = true;
    photoStage.replaceChildren();
    if (query && !titles) {
      position.textContent = 'Loading project titles…';
      loadTitles().then(() => {
        if (ticket === requestId) applyFilters();
      }).catch(error => {
        if (ticket === requestId) showError('Could not load project titles.', applyFilters, error);
      });
      return;
    }
    if (query) {
      results = Array.from(results ?? titles.keys()).filter(offset => titles[offset].includes(query));
    }
    if (resultCount()) openProject(0);
    else position.textContent = period === '2027'
      ? 'No FY2027-linked projects match these filters.'
      : 'No projects match these filters.';
  }

  function loadTitles() {
    titleRequest ??= fetchJson(index.titleIndex).then(rows => {
      if (!Array.isArray(rows) || rows.length !== index.total) throw Error('Incomplete title index');
      titles = rows.map(searchKey);
    }).catch(error => {
      titleRequest = undefined;
      throw error;
    });
    return titleRequest;
  }

  async function openProject(target) {
    if (target < 0 || target >= resultCount()) return;
    const ticket = ++requestId;
    const focusedArrow = document.activeElement;
    const offset = results ? results[target] : target;
    const page = Math.floor(offset / index.pageSize);
    retry.hidden = true;
    try {
      let part = pages.get(page);
      if (!Array.isArray(part)) {
        position.textContent = 'Loading project ' + number(target + 1) + '…';
        if (!part) {
          part = fetchJson(index.pages[page - 1]).then(rows => {
            pages.set(page, rows);
            return rows;
          }).catch(error => {
            pages.delete(page);
            throw error;
          });
          pages.set(page, part);
        }
        part = await part;
      }
      if (ticket !== requestId) return;
      const entry = part[offset % index.pageSize];
      if (!entry) throw Error('Project record is missing');
      project = entry;
      current = target;
      render();
      if (focusedArrow === previous && previous.disabled) next.focus();
      if (focusedArrow === next && next.disabled) previous.focus();
    } catch (error) {
      if (ticket !== requestId) return;
      pages.delete(page);
      showError('Could not load project ' + number(target + 1) + '.', () => openProject(target), error);
    }
  }

  const move = delta => openProject(current + delta);
  previous.onclick = () => move(-1);
  next.onclick = () => move(1);
  if (search) search.oninput = applyFilters;
  for (const button of periodFilters) {
    button.onclick = () => {
      const key = button.dataset.repeatPeriod;
      if (key === period) return;
      period = key;
      applyFilters();
    };
  }
  for (const button of filters) {
    button.onclick = () => {
      const key = button.dataset.repeatFilter;
      if (key === category) return;
      category = key;
      applyFilters();
    };
  }
  for (const [i, select] of places.entries()) {
    select.onchange = () => {
      fillPlaces(i);
      applyFilters();
    };
  }
  if (clearPlace) clearPlace.onclick = () => {
    fillPlaces();
    places[0]?.focus();
    applyFilters();
  };
  photoSelect.onchange = () => showPhoto(Number(photoSelect.value));
  browser.addEventListener('keydown', event => {
    if (event.target !== previous && event.target !== next) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      move(event.key === 'ArrowLeft' ? -1 : 1);
    }
  });
  async function load() {
    retry.hidden = true;
    position.textContent = 'Loading ranked projects…';
    try {
      index = await fetchJson(browser.dataset.source);
      if (!index.first?.length) throw Error('No project records');
      linked2027 = new Set(index.linked2027);
      pages.set(0, index.first);
      geography = new Map((index.geography || []).map(([code, name, level, parent, offsets]) =>
        [code, {code, name, level, parent, offsets}]));
      fillPlaces();
      if (search) search.disabled = false;
      for (const button of periodFilters) button.disabled = false;
      applyFilters();
    } catch (error) {
      showError('Could not load the project browser.', load, error);
    }
  }
  load();
})();

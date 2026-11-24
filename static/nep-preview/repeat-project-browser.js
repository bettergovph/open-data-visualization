(() => {
  'use strict';
  const browser = document.getElementById('repeat-project-browser');
  if (!browser) return;
  const get = name => browser.querySelector('.repeat-browser-' + name);
  const timeline = get('years'), record = get('record'), photoStage = get('photo-stage');
  const photoLabel = get('photo-label'), photoSource = get('photo-source');
  const photoControls = get('photo-controls'), photoSelect = photoControls.querySelector('select');
  const previous = get('prev'), next = get('next'), retry = get('retry'), position = get('position');
  const number = value => Number(value).toLocaleString('en-PH');
  const peso = value => '₱' + number(value);
  const currentStages = ['2027 SCR', '2027 HGAB', '2027 NEP'];
  const pages = new Map();
  let index, project, current = 0, selected, activePhoto = -1, moving = false;

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
    photoLabel.textContent = attachment.label + (attachment.preview ? ' · photo preview' : '');
    photoSource.hidden = false;
    photoSource.href = attachment.url;
    photoSource.textContent = attachment.format === 'pdf' ? 'Open photo PDF ↗' : 'Open photo source ↗';
    photoSelect.value = String(index);
    if (attachment.preview || attachment.format === 'image') {
      const img = element('img');
      img.alt = attachment.label + ' photo evidence for ' + project.title;
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

  function mapLinks(points) {
    const links = points.map((point, index) => link(
      points.length === 1 ? 'Google Maps ↗' : 'Google Maps · point ' + (index + 1) + ' ↗',
      'https://www.google.com/maps/search/?' + new URLSearchParams({api: '1', query: point.join(',')})
    ));
    if (points.length === 2) {
      const params = new URLSearchParams({api: '1', origin: points[0].join(','), destination: points[1].join(',')});
      links.push(link('Directions between points ↗', 'https://www.google.com/maps/dir/?' + params));
    }
    return links;
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
    if (item.points?.length) sourceLinks.append(...mapLinks(item.points));
    record.replaceChildren(heading);
    if (details) record.append(element('p', details));
    if (sourceLinks.childElementCount) record.append(sourceLinks);
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
    position.textContent = 'Project ' + number(current + 1) + ' of ' + number(index.total);
    get('stats').replaceChildren(stat(String(project.repeatCount), project.repeatCount === 1 ? 'matched GAA line' : 'matched GAA lines'),
      stat(peso(project.total), 'combined GAA allocation'));
    get('stats').hidden = false;
    get('body').hidden = false;
    previous.disabled = current === 0;
    next.disabled = current === index.total - 1;
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

  async function move(delta) {
    const target = current + delta;
    if (moving || target < 0 || target >= index.total) return;
    const focusedArrow = document.activeElement;
    const page = Math.floor(target / index.pageSize);
    retry.hidden = true;
    moving = true;
    try {
      if (!pages.has(page)) {
        position.textContent = 'Loading project ' + number(target + 1) + '…';
        pages.set(page, await fetchJson(index.pages[page - 1]));
      }
      const entry = pages.get(page)[target % index.pageSize];
      if (!entry) throw Error('Project record is missing');
      project = entry;
      current = target;
      render();
      if (focusedArrow === previous && previous.disabled) next.focus();
      if (focusedArrow === next && next.disabled) previous.focus();
    } catch (error) {
      pages.delete(page);
      showError('Could not load project ' + number(target + 1) + '.', () => move(delta), error);
    } finally {
      moving = false;
    }
  }

  previous.onclick = () => move(-1);
  next.onclick = () => move(1);
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
      pages.set(0, index.first);
      project = index.first[0];
      render();
    } catch (error) {
      showError('Could not load the project browser.', load, error);
    }
  }
  load();
})();

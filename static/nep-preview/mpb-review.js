(() => {
  const params = new URLSearchParams(location.search);
  const hash = params.get('hash') || '';
  const access = document.getElementById('access-message');
  const workspace = document.getElementById('workspace');
  const indexView = document.getElementById('project-index');
  const reviewView = document.getElementById('project-review');
  const projectRows = document.getElementById('project-rows');
  const meta = document.getElementById('project-meta');
  const status = document.getElementById('status');
  const rowsRoot = document.getElementById('rows');
  const projects = [];
  let current = null;
  let currentPdfPage = null;
  let projectPage = 0;
  const projectPageSize = 10;
  const apiBase = location.hostname === 'research.bettergov.ph' ? 'https://visualizations.bettergov.ph' : '';
  const allocationFormat = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP', maximumFractionDigits: 0 });

  const api = async (path, options = {}) => {
    const response = await fetch(`${apiBase}/api/mpb-review/${path}?hash=${encodeURIComponent(hash)}`, {
      cache: 'no-store',
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || payload.detail || `HTTP ${response.status}`);
    return payload;
  };
  const addText = (parent, tag, text, className = '') => {
    const element = document.createElement(tag);
    element.textContent = text ?? '';
    if (className) element.className = className;
    parent.append(element);
    return element;
  };
  const setPage = (view, code, pdfPage) => {
    indexView.hidden = view !== 'index';
    reviewView.hidden = view !== 'review';
    const next = new URL(location.href);
    if (code) next.searchParams.set('project', code);
    else next.searchParams.delete('project');
    if (pdfPage != null) next.searchParams.set('pdfPage', String(pdfPage));
    else next.searchParams.delete('pdfPage');
    history.replaceState(null, '', next);
  };

  function annotationPairs(row) {
    const values = row.keyValues && typeof row.keyValues === 'object' ? row.keyValues : {};
    return Object.entries(values).map(([key, value]) => ({ key, value: String(value ?? '') }));
  }

  function renderProjectList() {
    projectRows.replaceChildren();
    projects.sort((a, b) => (Number(b.allocationPesos) || 0) - (Number(a.allocationPesos) || 0) || a.code.localeCompare(b.code));
    const pageCount = Math.max(1, Math.ceil(projects.length / projectPageSize));
    projectPage = Math.min(projectPage, pageCount - 1);
    const visibleProjects = projects.slice(projectPage * projectPageSize, (projectPage + 1) * projectPageSize);
    for (const project of visibleProjects) {
      const tr = document.createElement('tr');
      addText(tr, 'td', project.name, 'project-name');
      addText(tr, 'td', project.allocationPesos == null ? '—' : allocationFormat.format(project.allocationPesos));
      addText(tr, 'td', project.office || '—');
      addText(tr, 'td', project.pageCount);
      addText(tr, 'td', project.rowCount);
      addText(tr, 'td', project.powStatus);
      const action = document.createElement('td');
      const button = addText(action, 'button', 'Review rows');
      button.type = 'button';
      button.addEventListener('click', () => selectProject(project.code));
      tr.append(action);
      projectRows.append(tr);
    }
    document.getElementById('project-count').textContent = `${projects.length.toLocaleString()} parsed MPB POW records.`;
    document.getElementById('project-page').textContent = `Page ${projectPage + 1} of ${pageCount} · showing ${visibleProjects.length}`;
    document.getElementById('project-prev').disabled = projectPage === 0;
    document.getElementById('project-next').disabled = projectPage + 1 >= pageCount;
  }

  function renderProject(project, desiredPage = null) {
    current = project;
    rowsRoot.replaceChildren();
    status.classList.remove('error');
    meta.textContent = `${project.code} · ${project.name} · ${project.office} · ${project.region} · ${project.pageCount} PDF page(s) · ${project.rows.length} extracted table rows`;
    const annotated = project.rows.filter(row => annotationPairs(row).length).length;
    status.textContent = `${annotated} of ${project.rows.length} rows have key/value annotations. POW status: ${project.powStatus}.`;
    const pageNumbers = [...new Set(project.rows.map(row => row.page))].sort((a, b) => a - b);
    const firstIncompletePage = pageNumbers.find(page => project.rows.some(row => row.page === page && !annotationPairs(row).length));
    currentPdfPage = desiredPage != null && pageNumbers.includes(Number(desiredPage))
      ? Number(desiredPage)
      : firstIncompletePage ?? pageNumbers[pageNumbers.length - 1] ?? null;
    setPage('review', project.code, currentPdfPage);
    document.getElementById('scan-page-label').textContent = currentPdfPage == null
      ? 'No scanned rows'
      : `PDF page ${currentPdfPage} · ${project.rows.filter(row => row.page === currentPdfPage && annotationPairs(row).length).length}/${project.rows.filter(row => row.page === currentPdfPage).length} rows annotated`;
    document.getElementById('previous-page').disabled = currentPdfPage == null || !pageNumbers.some(page => page < currentPdfPage);
    document.getElementById('next-page').disabled = currentPdfPage == null || !pageNumbers.some(page => page > currentPdfPage);

    if (!project.rows.length) {
      addText(rowsRoot, 'p', 'No extracted table rows were found for this scanned POW.');
      return;
    }
    for (const row of project.rows.filter(item => item.page === currentPdfPage)) {
      const card = document.createElement('article');
      card.className = `row-card${annotationPairs(row).length ? ' annotated' : ''}`;
      const heading = document.createElement('div');
      heading.className = 'row-head';
      addText(heading, 'span', `POW source page ${row.page} · parsed row ${row.row}`);
      addText(heading, 'span', `HGAB file ${project.code}`);
      card.append(heading);
      addText(card, 'pre', row.rawText);
      const pairList = document.createElement('div');
      const pairs = annotationPairs(row);
      const addPair = (key = '', value = '') => {
        const line = document.createElement('div');
        line.className = 'pair';
        const keyInput = document.createElement('input');
        keyInput.value = key;
        keyInput.placeholder = 'Key';
        keyInput.setAttribute('aria-label', `Annotation key for row ${row.row}`);
        const valueInput = document.createElement('input');
        valueInput.value = value;
        valueInput.placeholder = 'Value';
        valueInput.setAttribute('aria-label', `Annotation value for row ${row.row}`);
        const remove = addText(line, 'button', 'Remove', 'secondary');
        remove.type = 'button';
        remove.addEventListener('click', () => line.remove());
        line.prepend(keyInput, valueInput);
        pairList.append(line);
      };
      for (const pair of pairs) addPair(pair.key, pair.value);
      if (!pairs.length) addPair();
      card.append(pairList);
      const actions = document.createElement('div');
      actions.className = 'row-actions';
      const add = addText(actions, 'button', 'Add key:value');
      add.type = 'button';
      add.className = 'secondary';
      add.addEventListener('click', () => addPair());
      const save = addText(actions, 'button', 'Save annotations');
      save.type = 'button';
      const saveStatus = addText(actions, 'span', '', 'save-status');
      save.addEventListener('click', async () => {
        const keyValues = {};
        let invalid = false;
        for (const line of pairList.querySelectorAll('.pair')) {
          const [keyInput, valueInput] = line.querySelectorAll('input');
          const key = keyInput.value.trim();
          const value = valueInput.value.trim();
          if (!key && !value) continue;
          if (!key) { invalid = true; keyInput.focus(); break; }
          keyValues[key] = value;
        }
        if (invalid) {
          saveStatus.textContent = 'Enter a key for each value.';
          saveStatus.classList.add('error');
          return;
        }
        save.disabled = true;
        saveStatus.textContent = 'Saving…';
        saveStatus.classList.remove('error');
        try {
          await api('annotations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_code: project.code, row_id: row.rowId, key_values: keyValues }),
          });
          row.keyValues = keyValues;
          saveStatus.textContent = 'Saved';
          card.classList.toggle('annotated', annotationPairs(row).length > 0);
          const count = project.rows.filter(item => annotationPairs(item).length).length;
          status.textContent = `${count} of ${project.rows.length} rows have key/value annotations. POW status: ${project.powStatus}.`;
          const pageNumbers = [...new Set(project.rows.map(item => item.page))].sort((a, b) => a - b);
          const pageRows = project.rows.filter(item => item.page === currentPdfPage);
          document.getElementById('scan-page-label').textContent = `PDF page ${currentPdfPage} · ${pageRows.filter(item => annotationPairs(item).length).length}/${pageRows.length} rows annotated`;
          if (project.rows.filter(item => item.page === currentPdfPage).every(item => annotationPairs(item).length)) {
            const nextPage = pageNumbers.find(page => page > currentPdfPage);
            if (nextPage != null) {
              renderProject(project, nextPage);
              status.textContent = `All rows on PDF page ${row.page} are annotated. Moved to page ${nextPage}.`;
            }
          }
        } catch (error) {
          saveStatus.textContent = error.message;
          saveStatus.classList.add('error');
        } finally {
          save.disabled = false;
        }
      });
      card.append(actions);
      rowsRoot.append(card);
    }
  }

  async function selectProject(code, desiredPage = null) {
    if (!code) return;
    setPage('review', code);
    status.textContent = 'Loading scanned POW rows…';
    rowsRoot.replaceChildren();
    try {
      const project = await api(`projects/${encodeURIComponent(code)}`);
      renderProject(project, desiredPage);
      const index = projects.findIndex(item => item.code === code);
      document.getElementById('previous-project').disabled = index <= 0;
      document.getElementById('next-project').disabled = index < 0 || index >= projects.length - 1;
    } catch (error) {
      status.textContent = error.message;
      status.classList.add('error');
    }
  }

  document.getElementById('back-to-projects').addEventListener('click', () => setPage('index'));
  document.getElementById('project-prev').addEventListener('click', () => { projectPage -= 1; renderProjectList(); });
  document.getElementById('project-next').addEventListener('click', () => { projectPage += 1; renderProjectList(); });
  document.getElementById('previous-page').addEventListener('click', () => {
    const previous = [...new Set(current?.rows.map(row => row.page) || [])].sort((a, b) => a - b).filter(page => page < currentPdfPage).pop();
    if (previous != null) renderProject(current, previous);
  });
  document.getElementById('next-page').addEventListener('click', () => {
    const next = [...new Set(current?.rows.map(row => row.page) || [])].sort((a, b) => a - b).find(page => page > currentPdfPage);
    if (next != null) renderProject(current, next);
  });
  document.getElementById('previous-project').addEventListener('click', () => {
    const index = projects.findIndex(item => item.code === current?.code);
    if (index > 0) selectProject(projects[index - 1].code);
  });
  document.getElementById('next-project').addEventListener('click', () => {
    const index = projects.findIndex(item => item.code === current?.code);
    if (index >= 0 && index < projects.length - 1) selectProject(projects[index + 1].code);
  });
  document.getElementById('export-project').addEventListener('click', () => {
    if (!current) return;
    const output = {
      project: { code: current.code, name: current.name, office: current.office, powUrl: current.powUrl },
      exportedAt: new Date().toISOString(),
      rows: current.rows.map(row => ({ rowId: row.rowId, page: row.page, table: row.table, row: row.row, parsedText: row.rawText, sourceRow: row.sourceRow, annotations: row.keyValues || {} })),
    };
    const blob = new Blob([JSON.stringify(output, null, 2)], { type: 'application/json' });
    const href = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = href;
    link.download = `${current.code}-mpb-pow-annotations.json`;
    link.click();
    URL.revokeObjectURL(href);
  });

  if (!/^[0-9a-f]{64}$/i.test(hash)) {
    access.textContent = 'Admin access required. Open this page using the same hash-protected link used for connectivity review.';
    access.classList.add('error');
    return;
  }
  api('projects').then(payload => {
    projects.push(...payload.projects);
    if (!projects.length) throw new Error('No scanned MPB POWs were found in the local document cache.');
    renderProjectList();
    access.textContent = `${projects.length} scanned MPB POWs available for review.`;
    workspace.hidden = false;
    const initial = params.get('project');
    if (projects.some(project => project.code === initial)) selectProject(initial, params.get('pdfPage'));
    else setPage('index');
  }).catch(error => {
    access.textContent = error.message;
    access.classList.add('error');
  });
})();

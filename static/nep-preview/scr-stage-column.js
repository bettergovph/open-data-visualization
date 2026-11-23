/* Add a sourced Senate Committee Report disposition beside reliably matched
 * project rows. SCR status is stage evidence, not an automatic finding. */
(() => {
  'use strict';

  const PAGE_PROGRAMS = {
    'documents.html': ['dpwh'],
    'dpwh.html': ['dpwh'],
    'fmr.html': ['fmr'],
    'nia.html': ['nia'],
    'dpwh-transparency.html': ['dpwh'],
    'repeats.html': ['dpwh', 'fmr', 'nia', 'hfep'],
    'out-of-place.html': ['dpwh'],
    'congress.html': ['dpwh', 'fmr', 'nia', 'hfep'],
    'flags.html': ['dpwh', 'fmr', 'nia', 'hfep'],
    'undocumented-hgab.html': ['dpwh'],
    'cost-per-km.html': ['dpwh', 'fmr'],
    'pccp-cost-per-unit.html': ['dpwh'],
    'cost-per-unit.html': ['dpwh'],
    'cmpd-cost-per-unit.html': ['dpwh'],
    'expectation-vs-reality.html': ['dpwh'],
    'rcs.html': ['dpwh'],
    'mpb.html': ['dpwh'],
    'barangay.html': ['dpwh'],
  };
  const filename = decodeURIComponent(location.pathname.split('/').pop() || '');
  const programs = PAGE_PROGRAMS[filename];
  if (!programs) return;
  const dataUrl = document.body.dataset.scrDataUrl || 'scr-data.json';

  const style = document.createElement('style');
  style.textContent = `
    th.scr-stage-heading{min-width:190px;background:#EAF0FF!important;color:#00246A!important}
    td.scr-stage-cell{min-width:190px;vertical-align:top}
    .scr-stage-badge{display:inline-block;padding:3px 8px;border:1px solid #BDBDBD;border-radius:999px;background:#F5F5F5;color:#212121;font-size:12px;font-weight:750;line-height:1.35}
    .scr-stage-badge.is-green{border-color:#9ac6a5;background:#edf7ef;color:#21633a}
    .scr-stage-badge.is-red{border-color:#e0aaaa;background:#fff0f0;color:#9b1c1c}
    .scr-stage-badge.is-blue{border-color:#b8c9ee;background:#EAF0FF;color:#0038A8}
    .scr-stage-badge.is-amber{border-color:#e8cc7a;background:#fff8df;color:#725000}
    .scr-stage-note{display:block;margin-top:4px;color:#52616d;font-size:12px;line-height:1.4}
    .scr-stage-cell a,.scr-stage-review a{display:inline-block;margin-top:4px;color:#0038A8;font-size:12px;font-weight:650}
    .scr-stage-unmatched{color:#697782;font-size:12px}
    .scr-stage-item+.scr-stage-item{margin-top:9px;padding-top:9px;border-top:1px solid #E0E0E0}
    .scr-stage-title{display:block;margin-bottom:4px;color:#212121;font-size:12px;font-weight:700}
    .scr-stage-review{margin:14px 0;padding:12px;border:1px solid #BDBDBD;border-left:4px solid #FCD116;border-radius:8px;background:#F5F5F5}
    .scr-page-summary{box-sizing:border-box;margin:12px 0 20px;padding:14px 18px;border:1px solid #BDBDBD;border-left:5px solid #FCD116;border-radius:10px;background:#EAF0FF;color:#212121}
    .scr-page-summary h2{margin:0 0 5px;color:#00246A;font-size:16px}
    .scr-page-summary p{margin:4px 0;font-size:13px;line-height:1.45}
    .scr-page-summary strong{color:#00246A}
  `;
  document.head.append(style);

  const normalize = value => String(value || '')
    .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/&amp;/g, 'and').replace(/[^a-z0-9]+/g, ' ').trim();
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[ch]);
  const amount = value => {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };
  const peso = value => value == null ? '' : `₱${Math.abs(value).toLocaleString('en-PH')}`;

  function buildTitleIndex(rows) {
    const index = new Map();
    for (const row of rows) {
      if (!programs.includes(row.program)) continue;
      const keys = new Set([normalize(row.house_title), normalize(row.title)]);
      for (const key of keys) {
        if (key.length < 18) continue;
        if (!index.has(key)) index.set(key, []);
        const list = index.get(key);
        if (!list.some(item => item.id === row.id)) list.push(row);
      }
    }
    const buckets = new Map();
    for (const [key, records] of index) {
      const prefix = key.split(' ').slice(0, 3).join(' ');
      if (!buckets.has(prefix)) buckets.set(prefix, []);
      buckets.get(prefix).push({key, records});
    }
    for (const aliases of buckets.values()) aliases.sort((a, b) => b.key.length - a.key.length);
    return {buckets, records: new Map(rows.map(row => [row.id, row]))};
  }

  function matchRow(tr, titleIndex) {
    const cells = [...tr.cells].filter(cell => cell.tagName === 'TD' && !cell.hasAttribute('colspan'));
    if (!cells.length) return [];
    const texts = cells.map(cell => normalize(cell.innerText || cell.textContent));
    const visible = texts.filter(text => text.length >= 18 && text.length <= 600);
    const rowText = texts.join(' ');
    const amounts = new Set([...rowText.matchAll(/(?:₱|php\s*)?\b([\d,]{5,})\b/g)].map(m => m[1].replace(/,/g, '')));
    const matches = new Map();
    for (const text of visible) {
      const prefix = text.split(' ').slice(0, 3).join(' ');
      const aliases = (titleIndex.buckets.get(prefix) || []).filter(alias => text === alias.key || text.startsWith(alias.key + ' '));
      if (!aliases.length) continue;
      const maxLength = aliases.reduce((maximum, alias) => Math.max(maximum, alias.key.length), 0);
      let candidates = [...new Map(aliases.filter(alias => alias.key.length === maxLength)
        .flatMap(alias => alias.records).map(row => [row.id, row])).values()];
      if (candidates.length > 1) {
        const amountMatches = candidates.filter(row => [amount(row.house_php), amount(row.senate_php)]
          .some(n => n != null && amounts.has(String(n))));
        if (amountMatches.length === 1) candidates = amountMatches;
      }
      if (candidates.length === 1) matches.set(candidates[0].id, candidates[0]);
    }
    return [...matches.values()];
  }

  function statusView(row) {
    const senate = amount(row.senate_php);
    const house = amount(row.house_php);
    const diff = senate != null && house != null ? senate - house : null;
    if (row.status === 'cut') return {
      cls: 'is-green', label: 'Removed in SCR',
      note: 'Potentially resolves a presence-based HGAB flag; check the original claim.',
    };
    if (row.status === 'raised') return {
      cls: 'is-red', label: `Increased in SCR${diff > 0 ? ` · +${peso(diff)}` : ''}`,
      note: 'Review whether the increase worsens a flag under the original rule.',
    };
    if (row.status === 'added' || row.status === 'restored') return {
      cls: 'is-red', label: `${row.status === 'restored' ? 'Restored' : 'Added'} in SCR${senate != null ? ` · ${peso(senate)}` : ''}`,
      note: 'New Senate-stage row; assess against the relevant flag rule.',
    };
    if (row.status === 'reduced') return {
      cls: 'is-blue', label: `Reduced in SCR${diff < 0 ? ` · −${peso(diff)}` : ''}`,
      note: 'Compare the revised amount with the earlier finding and its threshold.',
    };
    if (row.status === 'renamed') return {
      cls: 'is-amber', label: 'Renamed in SCR',
      note: 'Review whether the revision resolves or changes a title, scope, or location flag.',
    };
    if (row.status === 'unchanged') return {cls: '', label: 'Unchanged in SCR', note: 'House amount and project line retained.'};
    return {cls: '', label: 'Not listed in SCR schedule', note: 'This NEP row has no corresponding line in the House or SCR project schedule.'};
  }

  function makeCell(rows) {
    const cell = document.createElement('td');
    cell.className = 'scr-stage-cell';
    cell.dataset.scrStageCell = 'true';
    if (!rows.length) {
      cell.innerHTML = '<span class="scr-stage-unmatched">No reliable SCR row match</span>';
      return cell;
    }
    cell.dataset.scrRowIds = rows.map(row => row.id).join(' ');
    cell.innerHTML = rows.map(row => {
      const view = statusView(row);
      const title = rows.length > 1 ? `<span class="scr-stage-title">${esc(row.title || row.house_title)}</span>` : '';
      const senatePdfUrl = row.senate_pdf_url || (row.senate_doc
        ? `https://budget-assets.bettergov.ph/senate/2027/pdf/${encodeURIComponent(row.senate_doc)}.pdf${row.senate_page ? `#page=${encodeURIComponent(row.senate_page)}` : ''}`
        : '');
      const link = senatePdfUrl
        ? `<a href="${esc(senatePdfUrl)}" target="_blank" rel="noopener">SCR p. ${esc(row.senate_page || 'open')} ↗</a>`
        : '';
      return `<div class="scr-stage-item">${title}<span class="scr-stage-badge ${view.cls}">${esc(view.label)}</span><span class="scr-stage-note">${esc(view.note)}</span>${link}</div>`;
    }).join('');
    return cell;
  }

  function isProjectTable(table) {
    if (!table.tHead) return false;
    const headers = [...table.tHead.rows].flatMap(row => [...row.cells]).map(cell => normalize(cell.innerText || cell.textContent));
    return headers.some(label => /\bproject\b/.test(label) &&
      !/\b(?:projects|project folders?|project rows?|project details|project list|project count|assigned projects)\b/.test(label) &&
      /\b(?:project|title|line|item|source|name|candidate|office)\b/.test(label));
  }

  function enhanceTable(table, titleIndex) {
    if (!table.tHead) return;
    const pageTables = [...document.querySelectorAll('table')];
    const tableIndex = pageTables.indexOf(table);
    const forceNiaProjectTable = filename === 'nia.html' && tableIndex >= 0 && tableIndex < 2;
    const bodyRows = [...table.querySelectorAll('tbody tr')];
    if (!bodyRows.length) return;
    const matched = bodyRows.map(row => ({row, records: matchRow(row, titleIndex)}));
    const headRow = table.tHead.rows[table.tHead.rows.length - 1];
    if (!headRow) return;
    let heading = [...headRow.cells].find(cell => cell.dataset.scrStageHeading === 'true');
    if (!heading && !matched.some(item => item.records.length) && !forceNiaProjectTable && !isProjectTable(table)) return;
    if (!heading) {
      heading = document.createElement('th');
      heading.scope = 'col';
      heading.className = 'scr-stage-heading';
      heading.dataset.scrStageHeading = 'true';
      heading.textContent = 'SCR stage / flag review';
      headRow.append(heading);
    }
    for (const {row, records} of matched) {
      if (!row.querySelector(':scope > td[data-scr-stage-cell]') && row.cells.length && !row.cells[row.cells.length - 1].hasAttribute('colspan')) row.append(makeCell(records));
    }
    table.dataset.scrStageTable = 'true';
  }

  function enhanceOutOfPlaceCard(card, titleIndex) {
    if (filename !== 'out-of-place.html' || card.querySelector('[data-scr-stage-review]')) return;
    const title = card.querySelector('h2');
    if (!title || !clean(title.textContent)) return;
    const pseudo = document.createElement('tr');
    const titleCell = document.createElement('td');
    titleCell.textContent = clean(title.textContent);
    const amountCell = document.createElement('td');
    amountCell.textContent = card.querySelector('dl')?.innerText || '';
    pseudo.append(titleCell, amountCell);
    const records = matchRow(pseudo, titleIndex);
    if (!records.length) return;
    const review = document.createElement('div');
    review.className = 'scr-stage-review';
    review.dataset.scrStageReview = 'true';
    review.setAttribute('role', 'note');
    review.innerHTML = '<strong>SCR stage / flag review</strong>' + makeCell(records).innerHTML;
    title.after(review);
  }

  function summaryHtml(summary) {
    const matched = Number(summary.matchedCount || 0);
    const examined = Number(summary.sourceRows ?? matched);
    const unmatched = Math.max(0, examined - matched);
    return `<h2>${esc(summary.title)}</h2><p><strong>${Number(summary.removedCount).toLocaleString('en-PH')} of ${matched.toLocaleString('en-PH')} matched rows</strong> in this page-specific review are labeled Removed in SCR.${unmatched ? ` ${unmatched.toLocaleString('en-PH')} listed rows had no reliable SCR match and are excluded.` : ''}</p><p><strong>${esc(summary.valueLabel)}: ${peso(summary.removedGross)}</strong> in House allocations.</p><p>${esc(summary.note)}</p>`;
  }

  function addSummary(summary) {
    if (!summary || document.querySelector('[data-scr-page-summary]')) return;
    const hero = document.querySelector('.repeat-hero, .hgab-coverage-hero, .out-of-place-overview, #report-hero, .mpb-hero, .page-hero, .unit-hero, .history-hero');
    const target = hero || document.querySelector('main')?.firstElementChild;
    if (!target) return;
    const panel = document.createElement('section');
    panel.className = 'scr-page-summary';
    panel.dataset.scrPageSummary = 'true';
    panel.setAttribute('aria-label', 'Senate Committee Report comparison summary');
    panel.innerHTML = summaryHtml(summary);
    target.insertAdjacentElement('afterend', panel);
  }

  function addPageTableSummary(titleIndex, hasSpecificSummary) {
    if (hasSpecificSummary) return;
    const tables = [...document.querySelectorAll('table[data-scr-stage-table]')];
    if (!tables.length) return;
    const rows = tables.flatMap(table => [...table.querySelectorAll('tbody tr')]);
    const matched = new Map();
    for (const row of rows) {
      const cell = row.querySelector(':scope > td[data-scr-stage-cell]');
      for (const id of (cell?.dataset.scrRowIds || '').split(/\s+/).filter(Boolean)) {
        const record = titleIndex.records.get(id);
        if (record) matched.set(id, record);
      }
    }
    const records = [...matched.values()];
    const removed = records.filter(row => row.status === 'cut');
    const summary = {
      title: 'SCR · project rows on this page',
      sourceRows: rows.length,
      matchedCount: records.length,
      removedCount: removed.length,
      removedGross: removed.reduce((sum, row) => sum + Math.abs(Number(row.house_php) || 0), 0),
      valueLabel: 'Gross House allocation on rows Removed in SCR',
      note: 'Counts unique SCR rows matched to project rows in this page’s tables. Rows without a reliable title-and-amount match are excluded; a project shown in multiple tables is counted once. Gross House allocations are not net or realized savings.',
    };
    let panel = document.querySelector('[data-scr-dynamic-summary]');
    if (!panel) {
      addSummary(summary);
      panel = document.querySelector('[data-scr-page-summary]');
      if (panel) panel.dataset.scrDynamicSummary = 'true';
    } else {
      panel.innerHTML = summaryHtml(summary);
    }
  }

  fetch(dataUrl).then(response => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }).then(data => {
    const titleIndex = buildTitleIndex(data.rows || []);
    const dataSummaryExists = Boolean(data.pageSummaries?.[filename]);
    addSummary(data.pageSummaries?.[filename]);
    const scan = node => {
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      if (node.matches('table')) enhanceTable(node, titleIndex);
      node.querySelectorAll('table').forEach(table => enhanceTable(table, titleIndex));
      if (filename === 'out-of-place.html') {
        const card = document.getElementById('project-card');
        if (card && (node === card || card.contains(node) || node.contains(card))) enhanceOutOfPlaceCard(card, titleIndex);
      }
    };
    scan(document.body);
    addPageTableSummary(titleIndex, dataSummaryExists);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        if (record.target.closest?.('.scr-page-summary')) continue;
        const added = [...record.addedNodes];
        if (added.length && added.every(node => node.nodeType === Node.ELEMENT_NODE &&
          (node.matches('[data-scr-stage-cell], [data-scr-stage-heading]')))) continue;
        const table = record.target.closest && record.target.closest('table');
        if (table) enhanceTable(table, titleIndex);
        for (const node of added) scan(node);
      }
      addPageTableSummary(titleIndex, dataSummaryExists);
    });
    observer.observe(document.body, {childList: true, subtree: true});
  }).catch(error => console.warn('SCR stage comparison unavailable:', error));
})();

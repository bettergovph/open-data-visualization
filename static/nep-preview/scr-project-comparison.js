(() => {
  const $ = id => document.getElementById(id);
  const section = $('scr-project-comparison');
  const status = $('count');
  const retry = $('scr-retry');
  const filters = [$('q'), $('program'), $('status')];
  const [search, schedule, disposition] = filters;
  const previous = $('prev'), next = $('next');
  const fmt = v => v === '' || v == null ? '—' : '₱' + Number(v).toLocaleString('en-US');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const size = 50;
  let rows = [], filtered = [], page = 0;

  function render() {
    const total = filtered.length;
    const pages = Math.max(1, Math.ceil(total / size));
    const start = page * size;
    const shown = filtered.slice(start, start + size);
    status.textContent = total.toLocaleString() + ' matching rows';
    $('page').textContent = `Page ${page + 1} of ${pages}`;
    $('range').textContent = total ? `${start + 1}–${start + shown.length} of ${total.toLocaleString()}` : '0';
    $('rows').innerHTML = shown.map(row => `<tr>
      <td><strong>${esc(row.program.toUpperCase())}</strong><br><span class="pill ${esc(row.status)}">${esc(row.status_label||row.status)}</span><br><span class="small">${esc(row.id)}</span></td>
      <td>${esc(row.title)}</td>
      <td>${esc(row.house_title||'—')}</td>
      <td>${esc(row.office||'—')}<br>${esc(row.region||'')}</td>
      <td class="amount">${fmt(row.nep_php)}</td>
      <td class="amount">${fmt(row.house_php)}</td>
      <td class="amount">${fmt(row.senate_php)}</td>
      <td class="amount">${row.status==='cut'?fmt(row.house_php):'—'}</td>
      <td>${esc(row.check_note||row.matched_by||'—')}${row.senate_pdf_url?`<br><a href="${esc(row.senate_pdf_url)}" target="_blank" rel="noopener">SCR p. ${esc(row.senate_page||'open')}</a>`:''}</td>
      <td>${row.nep_pdf_url?`<a href="${esc(row.nep_pdf_url)}" target="_blank" rel="noopener">NEP p. ${esc(row.nep_page||'open')}</a>`:''} ${row.house_pdf_url?`<br><a href="${esc(row.house_pdf_url)}" target="_blank" rel="noopener">House p. ${esc(row.house_page||'open')}</a>`:''} ${row.page_url?`<br><a href="${esc(row.page_url)}" target="_blank" rel="noopener">BetterGov row</a>`:''}</td>
    </tr>`).join('') || '<tr><td colspan="10">No projects match these filters.</td></tr>';
    previous.disabled = page === 0;
    next.disabled = page >= pages - 1;
  }

  function filter() {
    const q = search.value.trim().toLowerCase(), program = schedule.value, stage = disposition.value;
    filtered = rows.filter(row => {
      if (program && row.program !== program) return false;
      if (stage === 'changed' && ['unchanged', 'nep_only'].includes(row.status)) return false;
      if (stage !== 'all' && stage !== 'changed' && row.status !== stage) return false;
      if (!q) return true;
      row.searchText ??= [row.id, row.house_id, row.title, row.house_title, row.office, row.region,
        row.pap, row.check_note].join(' ').toLowerCase();
      return row.searchText.includes(q);
    });
    page = 0;
    render();
  }

  async function load() {
    retry.hidden = true;
    status.textContent = 'Loading SCR project rows…';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(section.dataset.source, {signal: controller.signal});
      if (!response.ok) throw Error(`HTTP ${response.status}`);
      const {columns, values, rows: packed} = await response.json();
      rows = packed.map(record => Object.fromEntries(columns.map((key, index) => [key, values[record[index]]])));
      filters.forEach(control => { control.disabled = false; });
      filter();
    } catch (error) {
      status.textContent = 'SCR project rows could not be loaded.';
      retry.hidden = false;
      console.warn('SCR project rows unavailable:', error);
    } finally {
      clearTimeout(timeout);
    }
  }

  filters.forEach(control => control.addEventListener('input', filter));
  previous.onclick = () => { page--; render(); };
  next.onclick = () => { page++; render(); };
  retry.onclick = load;
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      load();
    }, {rootMargin: '400px'});
    observer.observe(section);
  } else load();
})();

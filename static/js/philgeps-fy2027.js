(() => {
  'use strict';
  const get = id => document.getElementById(id);
  const node = (tag, value, className) => {
    const element = document.createElement(tag);
    if (value) element.textContent = value;
    if (className) element.className = className;
    return element;
  };
  const number = new Intl.NumberFormat('en-PH');
  const pesos = new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP' });
  const displayDate = value => new Intl.DateTimeFormat('en-PH', {
    year: 'numeric', month: 'long', day: 'numeric', timeZone: 'Asia/Manila',
  }).format(new Date(value + 'T00:00:00+08:00'));
  const stages = [
    ['NEP', 'National Expenditure Program'],
    ['HGAB', 'House third reading'],
    ['SCR', 'Senate Committee Report'],
  ];
  const research = 'https://research.bettergov.ph/static/nep-preview/';

  function source(text, path) {
    if (!path) return node('span', text);
    const url = new URL(path, research);
    if (url.protocol !== 'https:') return node('span', text);
    const link = node('a', text);
    link.href = url;
    return link;
  }

  function noticeCard(notice) {
    const card = node('details');
    const contract = notice.title.startsWith(notice.contract) ? notice.title : notice.contract + ' · ' + notice.title;
    card.append(
      node('summary', contract),
      node('small', [notice.office, notice.status, notice.abc == null ? null : 'ABC ' + pesos.format(notice.abc)]
        .filter(Boolean).join(' · ')),
    );
    const links = node('ul');
    const original = node('li');
    original.append(source('PhilGEPS notice ' + notice.reference, notice.url));
    links.append(original);
    for (const line of notice.budget) {
      const item = node('li');
      const amount = line.amount == null ? '' : ' · ' + pesos.format(line.amount);
      item.append(source(line.stage + amount, line.url));
      links.append(item);
    }
    card.append(links);
    if (!notice.budget.length && notice.basis) card.append(node('small', notice.basis));
    if (notice.flags.length) {
      const flags = node('ul');
      for (const flag of notice.flags) {
        const item = node('li');
        item.append(source(flag.label, flag.url));
        if (flag.evidence) item.append(document.createTextNode(' · ' + flag.evidence));
        flags.append(item);
      }
      card.append(flags);
    }
    return card;
  }

  function render(data) {
    const notices = data.notices.map(notice => ({ ...notice, stages: new Set(notice.budget.map(line => line.stage)) }));
    if (!notices.length) throw new Error('No notice records.');
    const total = notices.length;
    const matched = notices.filter(notice => notice.stages.size).length;
    const sourceCount = new Set(notices.map(notice => notice.url)).size;
    get('match-count').textContent = number.format(matched);
    get('contract-count').textContent = 'of ' + number.format(total) + ' contracts';
    get('source-count').textContent = number.format(sourceCount) + ' official PhilGEPS sources';
    if (data.asOf) get('snapshot-date').textContent = 'Public notices screened through ' + displayDate(data.asOf) + '.';

    const grid = get('contract-grid');
    grid.setAttribute('aria-label', matched + ' contracts with a budget match out of ' + total);
    grid.replaceChildren(...Array.from({ length: total }, (_, i) => node('span', '', i >= matched ? 'unmatched' : 'matched')));

    const filter = get('flag-filter');
    const labels = [...new Set(notices.flatMap(notice => notice.flags.map(flag => flag.label)))].sort((a, b) => a.localeCompare(b));
    for (const label of labels) filter.add(new Option(label, label));
    const chart = get('stage-chart');
    const reset = get('reset-stage');
    let selectedStage = '';

    for (const [stage, label] of stages) {
      const count = notices.filter(notice => notice.stages.has(stage)).length;
      const bar = node('button', '', 'stage-bar');
      bar.type = 'button';
      bar.dataset.stage = stage;
      bar.setAttribute('aria-controls', 'notice-results');
      const head = node('span', '', 'stage-bar-head');
      head.append(node('span', stage + ' · ' + label), node('span', number.format(count)));
      const track = node('span', '', 'stage-track');
      track.setAttribute('aria-hidden', 'true');
      const fill = node('span');
      fill.style.width = (count / total * 100) + '%';
      track.append(fill);
      bar.append(head, track);
      bar.onclick = () => {
        selectedStage = selectedStage === stage ? '' : stage;
        showMatches();
      };
      chart.append(bar);
    }

    function showMatches() {
      for (const bar of chart.querySelectorAll('button')) {
        bar.setAttribute('aria-pressed', String(bar.dataset.stage === selectedStage));
      }
      reset.disabled = !selectedStage && !filter.value;
      const filtered = notices.filter(notice =>
        (!selectedStage || notice.stages.has(selectedStage)) &&
        (!filter.value || notice.flags.some(flag => flag.label === filter.value))
      );
      get('results-count').textContent = 'Showing ' + filtered.length + ' of ' + total + ' contracts' +
        (selectedStage ? ' · ' + selectedStage : '') + '.';
      const results = get('notice-results');
      results.replaceChildren(...(filtered.length ? filtered.map(noticeCard) :
        [node('p', 'No contracts match these filters.', 'philgeps-caption')]));
      results.scrollTop = 0;
    }

    reset.onclick = () => {
      selectedStage = '';
      filter.value = '';
      showMatches();
      chart.querySelector('button').focus();
    };
    filter.onchange = showMatches;
    showMatches();
    get('philgeps-dashboard').hidden = false;
    get('philgeps-status').hidden = true;
  }

  try {
    render(JSON.parse(get('philgeps-data').textContent));
  } catch (error) {
    console.error('PhilGEPS visualization:', error);
    get('philgeps-status').textContent = 'The notice figures could not be loaded. See the research report below.';
  }
})();

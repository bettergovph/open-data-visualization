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

  function chartBar(label) {
    const button = node('button', '', 'stage-bar');
    button.type = 'button';
    button.setAttribute('aria-controls', 'notice-results');
    const title = node('span', '', 'stage-bar-head');
    const value = node('span');
    title.append(node('span', label), value);
    const track = node('span', '', 'stage-track');
    track.setAttribute('aria-hidden', 'true');
    const fill = node('span');
    track.append(fill);
    button.append(title, track);
    return { button, setCount(count, total) {
      value.textContent = number.format(count);
      fill.style.width = (total ? count / total * 100 : 0) + '%';
    } };
  }

  function countFlags(notices) {
    const counts = new Map();
    for (const notice of notices) {
      for (const flag of notice.flagLabels) counts.set(flag, (counts.get(flag) || 0) + 1);
    }
    return counts;
  }

  function render(records, asOf) {
    const notices = records.map(notice => ({
      ...notice,
      stages: new Set(notice.budget.map(line => line.stage)),
      flagLabels: new Set(notice.flags.map(flag => flag.label)),
    }));
    if (!notices.length) throw new Error('No notice records.');
    const total = notices.length;
    const matched = notices.filter(notice => notice.stages.size).length;
    const sourceCount = new Set(notices.map(notice => notice.url)).size;
    const hero = document.querySelector('.topic-hero');
    if (hero) {
      hero.querySelector('.topic-hero-deck').textContent =
        `${number.format(sourceCount)} official PhilGEPS sources list ${number.format(total)} contracts citing FY2027 funds. ${number.format(matched)} have a budget match in the available schedules.`;
      if (asOf && !hero.querySelector('.topic-hero-meta')) {
        const badge = node('div', '', 'topic-hero-meta');
        badge.append(node('span', 'Public notices screened through ' + asOf));
        hero.querySelector('.topic-hero-inner').append(badge);
      }
    }
    get('match-count').textContent = number.format(matched);
    get('contract-count').textContent = 'of ' + number.format(total) + ' contracts';
    get('source-count').textContent = number.format(sourceCount) + ' official PhilGEPS sources';

    const grid = get('contract-grid');
    grid.setAttribute('aria-label', matched + ' contracts with a budget match out of ' + total);
    grid.replaceChildren(...Array.from({ length: total }, (_, i) => node('span', '', i >= matched ? 'unmatched' : 'matched')));

    const filter = get('flag-filter');
    const allFlags = countFlags(notices);
    const labels = [...allFlags.keys()].sort((a, b) => a.localeCompare(b));
    for (const label of labels) filter.add(new Option(label, label));
    const chart = get('stage-chart');
    const reset = get('reset-stage');
    let selectedStage = '';

    for (const [stage, label] of stages) {
      const count = notices.filter(notice => notice.stages.has(stage)).length;
      const bar = chartBar(stage + ' · ' + label);
      bar.button.dataset.stage = stage;
      bar.setCount(count, total);
      bar.button.onclick = () => {
        selectedStage = selectedStage === stage ? '' : stage;
        showMatches();
      };
      chart.append(bar.button);
    }

    const flagChart = get('flag-chart');
    const flagScope = get('flag-chart-scope');
    const flagBars = new Map();
    if (flagChart) {
      const extraChart = get('extra-flag-chart');
      const more = get('more-flags');
      const order = [...labels].sort((a, b) => allFlags.get(b) - allFlags.get(a) || a.localeCompare(b));
      for (const [index, label] of order.entries()) {
        const bar = chartBar(label);
        bar.button.onclick = () => {
          filter.value = filter.value === label ? '' : label;
          showMatches();
        };
        flagBars.set(label, bar);
        (index < 5 ? flagChart : extraChart).append(bar.button);
      }
      more.hidden = labels.length <= 5;
    }

    function showMatches() {
      for (const bar of chart.querySelectorAll('button')) {
        bar.setAttribute('aria-pressed', String(bar.dataset.stage === selectedStage));
      }
      reset.disabled = !selectedStage && !filter.value;
      const scoped = selectedStage ? notices.filter(notice => notice.stages.has(selectedStage)) : notices;
      if (flagScope) {
        flagScope.textContent = `Among ${number.format(scoped.length)} ${selectedStage ? selectedStage + ' matches' : 'contracts'}. A contract may have multiple flags. Select a flag to filter the records.`;
      }
      const counts = selectedStage ? countFlags(scoped) : allFlags;
      for (const [label, bar] of flagBars) {
        const count = counts.get(label) || 0;
        const selected = label === filter.value;
        bar.setCount(count, scoped.length);
        bar.button.setAttribute('aria-pressed', String(selected));
        bar.button.disabled = !count && !selected;
      }
      const filtered = filter.value ? scoped.filter(notice => notice.flagLabels.has(filter.value)) : scoped;
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
    const data = JSON.parse(get('philgeps-data').textContent);
    render(Array.isArray(data) ? data : data.notices, data.asOf);
  } catch (error) {
    console.error('PhilGEPS visualization:', error);
    get('philgeps-status').textContent = 'The notice figures could not be loaded. See the research report below.';
  }
})();

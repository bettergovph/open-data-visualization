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

  const flagBuckets = [
    { label: '0 flags', color: 'flag-none', includes: notice => notice.flagLabels.size === 0 },
    { label: '1–2 flags', color: 'flag-low', includes: notice => [1, 2].includes(notice.flagLabels.size) },
    { label: '3–4 flags', color: 'flag-mid', includes: notice => [3, 4].includes(notice.flagLabels.size) },
    { label: '5+ flags', color: 'flag-high', includes: notice => notice.flagLabels.size >= 5 },
  ];

  function chartBar(label, count) {
    const button = node('button', '', 'stage-bar');
    button.type = 'button';
    button.setAttribute('aria-controls', 'notice-results');
    const title = node('span', '', 'stage-bar-head');
    title.append(node('span', label), node('span', number.format(count)));
    const track = node('span', '', 'stage-track');
    track.setAttribute('aria-hidden', 'true');
    const breakdown = node('span', '', 'stage-breakdown');
    button.append(title, track, breakdown);
    return { button, track, breakdown };
  }

  function keyLabel(bucket, count) {
    const label = node('span');
    const marker = node('i', '', bucket.color);
    marker.setAttribute('aria-hidden', 'true');
    label.append(marker, document.createTextNode(count === undefined ? bucket.label :
      bucket.label + ': ' + number.format(count)));
    return label;
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
    const flagCounts = new Map();
    for (const notice of notices) {
      for (const flag of notice.flagLabels) flagCounts.set(flag, (flagCounts.get(flag) || 0) + 1);
    }
    const flags = [...flagCounts].sort(([a, left], [b, right]) => right - left || a.localeCompare(b));
    for (const [label, count] of flags) filter.add(new Option(`${label} (${number.format(count)})`, label));
    const chart = get('stage-chart');
    const legend = get('stage-legend');
    const reset = get('reset-stage');
    const bars = new Map();
    let selectedStage = '';

    for (const [stage, label] of stages) {
      const stageNotices = notices.filter(notice => notice.stages.has(stage));
      const bar = chartBar(stage + ' · ' + label, stageNotices.length);
      bar.button.dataset.stage = stage;
      bar.button.onclick = () => {
        selectedStage = selectedStage === stage ? '' : stage;
        showMatches();
      };
      bars.set(stage, { ...bar, notices: stageNotices });
      chart.append(bar.button);
    }

    function showMatches() {
      const selectedFlag = filter.value;
      const buckets = selectedFlag ? [
        { label: 'With selected flag', color: 'flag-selected', includes: notice => notice.flagLabels.has(selectedFlag) },
        { label: 'Other stage matches', color: 'other-matches', includes: notice => !notice.flagLabels.has(selectedFlag) },
      ] : flagBuckets;
      legend?.replaceChildren(...buckets.map(bucket => keyLabel(bucket)));
      for (const [stage, bar] of bars) {
        bar.button.setAttribute('aria-pressed', String(stage === selectedStage));
        const counts = buckets.map(bucket => bar.notices.filter(bucket.includes).length);
        bar.track.replaceChildren(...buckets.map((bucket, i) => {
          const segment = node('span', '', bucket.color);
          segment.style.width = (counts[i] / total * 100) + '%';
          return segment;
        }));
        bar.breakdown.replaceChildren(...buckets.map((bucket, i) => keyLabel(bucket, counts[i])));
      }
      reset.disabled = !selectedStage && !selectedFlag;
      const scoped = selectedStage ? bars.get(selectedStage).notices : notices;
      const filtered = selectedFlag ? scoped.filter(notice => notice.flagLabels.has(selectedFlag)) : scoped;
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

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
  const stages = [
    ['NEP', 'National Expenditure Program'],
    ['HGAB', 'House third reading'],
    ['SCR', 'Senate Committee Report'],
  ];
  const flagBuckets = [
    { label: '0 flags', color: 'flag-none', includes: notice => notice.flagLabels.size === 0 },
    { label: '1–2 flags', color: 'flag-low', includes: notice => [1, 2].includes(notice.flagLabels.size) },
    { label: '3–4 flags', color: 'flag-mid', includes: notice => [3, 4].includes(notice.flagLabels.size) },
    { label: '5+ flags', color: 'flag-high', includes: notice => notice.flagLabels.size >= 5 },
  ];

  function chartBar(label, count) {
    const row = node('div', '', 'stage-bar');
    const title = node('span', '', 'stage-bar-head');
    title.append(node('span', label), node('span', number.format(count)));
    const track = node('span', '', 'stage-track');
    track.setAttribute('aria-hidden', 'true');
    const breakdown = node('span', '', 'stage-breakdown');
    row.append(title, track, breakdown);
    return { row, track, breakdown };
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
      url: notice.url,
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
    const bars = [];

    for (const [stage, label] of stages) {
      const stageNotices = notices.filter(notice => notice.stages.has(stage));
      const bar = chartBar(stage + ' · ' + label, stageNotices.length);
      bar.row.dataset.stage = stage;
      bars.push({ ...bar, notices: stageNotices });
      chart.append(bar.row);
    }

    function drawStacks() {
      const selectedFlag = filter.value;
      const buckets = selectedFlag ? [
        { label: 'With selected flag', color: 'flag-selected', includes: notice => notice.flagLabels.has(selectedFlag) },
        { label: 'Other stage matches', color: 'other-matches', includes: notice => !notice.flagLabels.has(selectedFlag) },
      ] : flagBuckets;
      legend?.replaceChildren(...buckets.map(bucket => keyLabel(bucket)));
      for (const bar of bars) {
        const counts = buckets.map(bucket => bar.notices.filter(bucket.includes).length);
        bar.track.replaceChildren(...buckets.map((bucket, i) => {
          const segment = node('span', '', bucket.color);
          segment.style.width = (counts[i] / total * 100) + '%';
          return segment;
        }));
        bar.breakdown.replaceChildren(...buckets.map((bucket, i) => keyLabel(bucket, counts[i])));
      }
    }

    filter.onchange = drawStacks;
    drawStacks();
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

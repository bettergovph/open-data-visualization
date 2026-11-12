(() => {
  const materialSelect = document.querySelector('#material');
  const searchInput = document.querySelector('#search');
  const rowsBody = document.querySelector('#rows');
  const ratesBody = document.querySelector('#rates');
  const summary = document.querySelector('#summary');
  const errorBox = document.querySelector('#load-error');
  const boxplotPanel = document.querySelector('#boxplot-panel');
  const boxplot = document.querySelector('#boxplot');

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
  const aliases = {
    'common borrow': ['common borrow'],
    'selected borrow': ['selected borrow'],
    'aggregate subbase course': ['aggregate subbase', 'subbase course'],
    'aggregate base course': ['aggregate base course', 'base course'],
    'cement concrete pavement': ['cement concrete pavement', 'pccp'],
    'asphalt concrete': ['asphalt concrete', 'hot laid asphalt'],
    'portland cement': ['portland cement'],
    'fine aggregate sand': ['fine aggregate', 'concrete sand'],
    'concrete hollow blocks': ['concrete hollow block', 'chb'],
    'reinforcing steel': ['reinforcing steel', 'deformed bars', 'reinforcing bars'],
    'ready mix concrete': ['ready mix concrete', 'ready mixed concrete'],
    gravel: ['gravel']
  };
  const normalized = value => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const termsFor = name => {
    const key = normalized(name);
    return Object.entries(aliases).find(([alias]) => key.includes(alias))?.[1] || [key];
  };
  const unitKey = unit => {
    const key = String(unit || '').toLowerCase().replace(/m³/g, 'm3').replace(/m²/g, 'm2')
      .replace(/\s+/g, '').replace(/\./g, '');
    return ({
      cum: 'm3', cubicmeter: 'm3', cubicmeters: 'm3', m3: 'm3',
      sqm: 'm2', squaremeter: 'm2', squaremeters: 'm2', m2: 'm2',
      kg: 'kg', kgs: 'kg', kilogram: 'kg', kilograms: 'kg',
      m: 'm', meter: 'm', meters: 'm', ltr: 'l', liter: 'l', liters: 'l',
      l: 'l', gal: 'gal', gallon: 'gal', gallons: 'gal', bag: 'bag',
      ea: 'each', pc: 'each', each: 'each'
    })[key] || key;
  };
  const peso = value => value == null || !Number.isFinite(Number(value))
    ? '—'
    : '₱' + Number(value).toLocaleString('en-PH', { maximumFractionDigits: 2 });
  const sourceRegion = region => {
    const value = String(region || '');
    if (value === 'NCR' || value === 'CAR') return value;
    return /^Region I\b/i.test(value) ? 'Region I' : '';
  };
  const powUnit = unit => ({ 'cu.m': 'cum', 'sq.m': 'sqm', kg: 'kg', m: 'm', l: 'ltr' })[String(unit || '').toLowerCase()] || String(unit || '').toLowerCase();
  const median = values => {
    const middle = Math.floor(values.length / 2);
    return values.length % 2 ? values[middle] : (values[middle - 1] + values[middle]) / 2;
  };
  const quantile = (values, fraction) => {
    const position = (values.length - 1) * fraction;
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    return values[lower] + (values[upper] - values[lower]) * (position - lower);
  };
  const formatCost = value => '₱' + Number(value).toLocaleString('en-PH', { maximumFractionDigits: 2 });

  function drawBoxplot(items) {
    const groups = new Map();
    items.forEach(item => {
      const value = Number(item.unitCost);
      if (!Number.isFinite(value) || value <= 0) return;
      const unit = unitKey(item.unit) || String(item.unit || 'Unit unavailable');
      if (!groups.has(unit)) groups.set(unit, { label: item.unit || unit, values: [] });
      groups.get(unit).values.push(value);
    });
    const rows = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
    boxplotPanel.hidden = items.length === 0;
    if (!items.length) {
      boxplot.innerHTML = '';
      return;
    }
    if (!rows.length) {
      boxplot.innerHTML = '<p class="cmpd-boxplot-empty">Matched POW rows were found, but none has a usable positive unit cost for a box plot.</p>';
      return;
    }

    boxplot.innerHTML = rows.map(([, group]) => {
      const values = group.values.sort((a, b) => a - b);
      const q1 = quantile(values, 0.25);
      const q2 = median(values);
      const q3 = quantile(values, 0.75);
      const iqr = q3 - q1;
      const lowerFence = q1 - 1.5 * iqr;
      const upperFence = q3 + 1.5 * iqr;
      const inRange = values.filter(value => value >= lowerFence && value <= upperFence);
      const low = inRange[0];
      const high = inRange[inRange.length - 1];
      const outliers = values.filter(value => value < lowerFence || value > upperFence);
      const axisMax = Math.max(high, ...outliers, 1) * 1.04;
      const x = value => 44 + (Math.max(0, value) / axisMax) * 620;
      const boxX = x(q1);
      const boxWidth = Math.max(2, x(q3) - boxX);
      const shownOutliers = outliers.length > 100
        ? outliers.filter((_, index) => index % Math.ceil(outliers.length / 100) === 0)
        : outliers;
      const outlierDots = shownOutliers.map((value, index) =>
        '<circle class="cmpd-boxplot-outlier" cx="' + x(value).toFixed(1) +
        '" cy="' + (30 + (index % 5) * 5) + '" r="3"><title>' + formatCost(value) + '</title></circle>'
      ).join('');
      const ticks = [0, axisMax / 2, axisMax].map(value =>
        '<g><line class="cmpd-boxplot-axis" x1="' + x(value).toFixed(1) +
        '" y1="61" x2="' + x(value).toFixed(1) + '" y2="66"></line><text class="cmpd-boxplot-tick" x="' +
        x(value).toFixed(1) + '" y="82" text-anchor="middle">' +
        escapeHtml(formatCost(value)) + '</text></g>'
      ).join('');
      return '<div class="cmpd-boxplot-row"><div class="cmpd-boxplot-unit"><strong>' +
        escapeHtml(group.label) + '</strong><small>n = ' + values.length.toLocaleString('en-PH') +
        ' · median ' + escapeHtml(formatCost(q2)) + '<br>IQR ' + escapeHtml(formatCost(q1)) +
        '–' + escapeHtml(formatCost(q3)) + (outliers.length ? '<br>' + outliers.length.toLocaleString('en-PH') +
        ' outside 1.5×IQR' : '') + '</small></div><div class="cmpd-boxplot-chart"><svg viewBox="0 0 700 92" role="img" aria-label="' +
        escapeHtml(group.label) + ' unit-cost box plot, ' + values.length + ' matched POW costs, median ' +
        escapeHtml(formatCost(q2)) + '"><title>' + escapeHtml(group.label) + ' POW unit-cost distribution</title>' +
        '<line class="cmpd-boxplot-axis" x1="44" y1="61" x2="664" y2="61"></line>' + ticks +
        '<line class="cmpd-boxplot-whisker" x1="' + x(low).toFixed(1) + '" y1="41" x2="' +
        x(high).toFixed(1) + '" y2="41"></line><line class="cmpd-boxplot-whisker" x1="' +
        x(low).toFixed(1) + '" y1="34" x2="' + x(low).toFixed(1) + '" y2="48"></line><line class="cmpd-boxplot-whisker" x1="' +
        x(high).toFixed(1) + '" y1="34" x2="' + x(high).toFixed(1) + '" y2="48"></line><rect class="cmpd-boxplot-box" x="' +
        boxX.toFixed(1) + '" y="25" width="' + boxWidth.toFixed(1) + '" height="32" rx="3"></rect><line class="cmpd-boxplot-median" x1="' +
        x(q2).toFixed(1) + '" y1="24" x2="' + x(q2).toFixed(1) + '" y2="58"></line>' +
        outlierDots + '</svg></div></div>';
    }).join('');
    const omitted = rows.reduce((sum, [, group]) => {
      const sorted = group.values.sort((a, b) => a - b);
      const q1 = quantile(sorted, 0.25);
      const q3 = quantile(sorted, 0.75);
      const iqr = q3 - q1;
      const outlierCount = sorted.filter(value => value < q1 - 1.5 * iqr || value > q3 + 1.5 * iqr).length;
      return sum + Math.max(0, outlierCount - 100);
    }, 0);
    if (omitted > 0) {
      boxplot.insertAdjacentHTML('beforeend', '<p class="cmpd-boxplot-note">' +
        omitted.toLocaleString('en-PH') + ' outlier markers are omitted for readability; counts beside each unit include every value outside 1.5×IQR.</p>');
    }
  }

  function draw(data) {
    const name = materialSelect.value;
    const rates = data.rates.filter(rate => rate.description === name);
    const terms = termsFor(name);
    const knownUnits = new Set(['m3', 'm2', 'kg', 'm', 'l', 'gal', 'bag', 'each']);
    const referenceUnits = new Set(rates.map(rate => unitKey(rate.unit)).filter(unit => knownUnits.has(unit)));
    const search = normalized(searchInput.value);
    const found = data.candidates.filter(item =>
      terms.some(term => normalized(item.description).includes(term)) &&
      (!referenceUnits.size || referenceUnits.has(unitKey(item.unit))) &&
      (!search || normalized([item.project, item.description, item.office, item.region].join(' ')).includes(search))
    );
    const code = rates[0]?.code || '—';
    summary.textContent = name + ' · ' + (rates[0]?.unit || 'unit unavailable') + ' · ' +
      found.length.toLocaleString('en-PH') + ' matched POW rows · material code ' + code;
    drawBoxplot(found);

    rowsBody.innerHTML = found.map(item => {
      const region = sourceRegion(item.region);
      const comparable = rates.find(rate =>
        rate.region === region && unitKey(rate.unit) === unitKey(powUnit(item.unit))
      );
      const cmpdPrice = comparable
        ? peso(comparable.average) + '<small>' + escapeHtml(comparable.region) + ' · CMPD p. ' + escapeHtml(comparable.page) + '</small>'
        : 'No comparable regional rate<small>Region/unit not available in supplied extract</small>';
      const powUrl = escapeHtml(item.powUrl);
      const source = item.powUrl
        ? '<a href="' + powUrl + '#page=' + encodeURIComponent(item.page) + '" target="_blank" rel="noopener">POW p. ' + escapeHtml(item.page) + ' ↗</a>'
        : 'POW p. ' + escapeHtml(item.page);
      return '<tr><td>' + escapeHtml(item.itemCode) + '<small>' + escapeHtml(item.description) + '</small></td>' +
        '<td>' + escapeHtml(item.unit) + '</td><td>' + cmpdPrice + '</td><td>' + peso(item.unitCost) + '</td>' +
        '<td>' + escapeHtml(item.project) + '<small>' + escapeHtml(item.office) + ' · ' +
        escapeHtml(item.region) + ' · ' + source + '</small></td></tr>';
    }).join('') || '<tr><td class="cmpd-empty" colspan="5">No matching POW rows for this material and search.</td></tr>';

    ratesBody.innerHTML = rates.map(rate => '<tr><td>' + escapeHtml(rate.code) + '</td><td>' +
      escapeHtml(rate.description) + '</td><td>' + escapeHtml(rate.unit) + '</td><td>' +
      escapeHtml(rate.region) + '</td><td>' + (rate.average == null ? 'OCR review needed' : peso(rate.average)) +
      '</td><td>CMPD p. ' + escapeHtml(rate.page) + '</td></tr>').join('') ||
      '<tr><td class="cmpd-empty" colspan="6">No reference rates are available for this material.</td></tr>';
  }

  fetch('cmpd-cost-per-unit-data.json')
    .then(response => {
      if (!response.ok) throw new Error('Source data returned HTTP ' + response.status);
      return response.json();
    })
    .then(data => {
      const materials = [...new Set(data.rates.map(rate => rate.description))]
        .filter(name => data.candidates.some(item => termsFor(name).some(term => normalized(item.description).includes(term))))
        .sort((a, b) => a.localeCompare(b));
      if (!materials.length) throw new Error('No matching CMPD materials were found in the supplied data.');
      materialSelect.innerHTML = materials.map(name =>
        '<option value="' + escapeHtml(name) + '">' + escapeHtml(name) + '</option>'
      ).join('');
      materialSelect.addEventListener('change', () => draw(data));
      searchInput.addEventListener('input', () => draw(data));
      draw(data);
    })
    .catch(error => {
      errorBox.hidden = false;
      errorBox.textContent = 'Data unavailable: ' + error.message;
      summary.textContent = 'The CMPD and POW comparison data could not be loaded.';
      boxplotPanel.hidden = true;
      boxplot.innerHTML = '';
      rowsBody.innerHTML = '<tr><td class="cmpd-empty" colspan="5">Data unavailable.</td></tr>';
      ratesBody.innerHTML = '<tr><td class="cmpd-empty" colspan="6">Data unavailable.</td></tr>';
    });
})();

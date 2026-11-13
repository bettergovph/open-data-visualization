(() => {
  const materialSelect = document.querySelector('#material');
  const searchInput = document.querySelector('#search');
  const rowsBody = document.querySelector('#rows');
  const ratesBody = document.querySelector('#rates');
  const summary = document.querySelector('#summary');
  const errorBox = document.querySelector('#load-error');
  const boxplotPanel = document.querySelector('#boxplot-panel');
  const boxplot = document.querySelector('#boxplot');
  const pageLoading = document.querySelector('#page-loading');

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
  const normalized = value => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const materialLabel = name => /\bchb\b|concrete hollow blocks?/i.test(name)
    ? 'CONCRETE HOLLOW BLOCK (CHB)'
    : name;
  const isChbMaterial = name => materialLabel(name) === 'CONCRETE HOLLOW BLOCK (CHB)';
  const materialCategory = name => {
    if (isChbMaterial(name)) return 'concrete hollow blocks';
    const key = normalized(name);
    return ['cement concrete pavement', 'asphalt concrete', 'aggregate subbase',
      'aggregate base course', 'common borrow', 'selected borrow', 'reinforcing steel',
      'portland cement', 'ready mix concrete', 'fine aggregate sand', 'gravel']
      .find(category => key.includes(category)) || key;
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
    const value = normalized(region);
    const aliases = [
      ['NIR', ['negros island region', 'nir']],
      ['IV-A', ['calabarzon', 'region iv a', 'region 4 a', 'iv a']],
      ['IV-B', ['mimaropa', 'region iv b', 'region 4 b', 'iv b']],
      ['XIII', ['region xiii', 'region 13', 'caraga', 'region xiii']],
      ['VIII', ['region viii', 'region 8', 'eastern visayas']],
      ['VII', ['region vii', 'region 7', 'central visayas']],
      ['VI', ['region vi', 'region 6', 'western visayas']],
      ['III', ['region iii', 'region 3', 'central luzon']],
      ['II', ['region ii', 'region 2', 'cagayan valley']],
      ['XII', ['region xii', 'region 12', 'soccsksargen']],
      ['XI', ['region xi', 'region 11', 'davao region']],
      ['X', ['region x', 'region 10', 'northern mindanao']],
      ['IX', ['region ix', 'region 9', 'zamboanga peninsula']],
      ['CAR', ['cordillera administrative region', 'car']],
      ['NCR', ['national capital region', 'metro manila', 'ncr']],
      ['XIII', ['caraga']],
      ['V', ['region v', 'region 5', 'bicol region']],
      ['IV-A', ['calabarzon']],
      ['I', ['region i', 'region 1', 'ilocos region']],
      ['IV-B', ['mimaropa']],
      ['VI', ['western visayas']],
      ['VII', ['central visayas']],
      ['VIII', ['eastern visayas']],
      ['IX', ['zamboanga peninsula']],
      ['X', ['northern mindanao']],
      ['XI', ['davao region']],
      ['XII', ['soccsksargen']]
    ];
    for (const [code, names] of aliases) {
      if (names.some(name => value === normalized(name) || value.includes(normalized(name)))) return code;
    }
    return '';
  };
  const powUnit = unit => ({ 'cu.m': 'cum', 'sq.m': 'sqm', kg: 'kg', m: 'm', l: 'ltr' })[String(unit || '').toLowerCase()] || String(unit || '').toLowerCase();
  const cmpdRateFor = (item, rates) => {
    const region = sourceRegion(item.region);
    const unit = unitKey(powUnit(item.unit));
    const sameUnit = rates.filter(rate =>
      unitKey(rate.unit) === unit && rate.regionalAverage != null && Number.isFinite(Number(rate.regionalAverage))
    );
    const regional = sameUnit.find(rate => rate.region === region);
    if (regional) return { rate: regional, referencePrice: Number(regional.regionalAverage), estimated: false };
    const highestAvailable = [...sameUnit].sort((a, b) => Number(b.regionalAverage) - Number(a.regionalAverage))[0];
    return highestAvailable
      ? { rate: highestAvailable, referencePrice: Number(highestAvailable.regionalAverage), estimated: true }
      : null;
  };
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
      groups.get(unit).values.push({ value, item });
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
      const records = group.values.sort((a, b) => a.value - b.value);
      const values = records.map(record => record.value);
      const q1 = quantile(values, 0.25);
      const q2 = median(values);
      const q3 = quantile(values, 0.75);
      const iqr = q3 - q1;
      const lowerFence = q1 - 1.5 * iqr;
      const upperFence = q3 + 1.5 * iqr;
      const inRange = records.filter(record => record.value >= lowerFence && record.value <= upperFence);
      const low = inRange[0].value;
      const high = inRange[inRange.length - 1].value;
      const outliers = records.filter(record => record.value < lowerFence || record.value > upperFence);
      const axisMax = Math.max(high, ...outliers.map(record => record.value), 1) * 1.04;
      const logMax = Math.log1p(axisMax);
      const x = value => 44 + (Math.log1p(Math.max(0, value)) / logMax) * 620;
      const boxX = x(q1);
      const boxWidth = Math.max(2, x(q3) - boxX);
      const shownOutliers = outliers.length > 100
        ? outliers.filter((_, index) => index % Math.ceil(outliers.length / 100) === 0)
        : outliers;
      const outlierDots = shownOutliers.map((record, index) => {
        const item = record.item;
        const tooltip = [
          formatCost(record.value) + ' per ' + (item.unit || group.label),
          item.description,
          item.project,
          [item.office, item.region].filter(Boolean).join(' · '),
          'POW p. ' + (item.page || 'unknown')
        ].filter(Boolean).join(' | ');
        return '<circle class="cmpd-boxplot-outlier" cx="' + x(record.value).toFixed(1) +
          '" cy="' + (30 + (index % 5) * 5) + '" r="4" tabindex="0" aria-label="' +
          escapeHtml(tooltip) + '"><title>' + escapeHtml(tooltip) + '</title></circle>';
      }
      ).join('');
      const tickValues = [0];
      for (let power = 10; power <= axisMax; power *= 10) tickValues.push(power);
      const lastPower = tickValues[tickValues.length - 1];
      if (axisMax / lastPower > 2) tickValues.push(axisMax);
      const ticks = tickValues.map(value =>
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
      const sorted = group.values.map(record => record.value).sort((a, b) => a - b);
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
    const usableCosts = rows.reduce((sum, [, group]) => sum + group.values.length, 0);
    const omittedCosts = items.length - usableCosts;
    if (omittedCosts > 0) {
      boxplot.insertAdjacentHTML('beforeend', '<p class="cmpd-boxplot-note">' +
        omittedCosts.toLocaleString('en-PH') + ' matched rows have zero or missing POW unit costs and are omitted from the logarithmic plot.</p>');
    }
    pageLoading.hidden = true;
  }

  function draw({ rates, candidates, material }) {
    const name = material.description;
    const search = normalized(searchInput.value);
    const found = candidates.filter(item =>
      normalized(item.material) === materialCategory(name) &&
      (!search || normalized([item.project, item.description, item.office, item.region].join(' ')).includes(search))
    );
    const matchedPow = found.map(item => ({ item, match: cmpdRateFor(item, rates) }))
      .filter(entry => entry.match);
    const estimatedCount = matchedPow.filter(entry => entry.match.estimated).length;
    const code = rates[0]?.code || '—';
    summary.textContent = name + ' · ' + (rates[0]?.unit || 'unit unavailable') + ' · ' +
      found.length.toLocaleString('en-PH') + ' text-matched POW rows · ' +
      matchedPow.length.toLocaleString('en-PH') + ' with a CMPD reference (' +
      estimatedCount.toLocaleString('en-PH') + ' estimates) · material code ' + code;
    drawBoxplot(matchedPow.map(entry => entry.item));

    rowsBody.innerHTML = found.map(item => {
      const match = cmpdRateFor(item, rates);
      const cmpdPrice = match
      ? peso(match.referencePrice) + (match.estimated
          ? '<small><strong>Estimate only</strong> · highest available same-unit rate (' +
            escapeHtml(match.rate.regionName) + ' regional average · CMPD source row ' + escapeHtml(match.rate.sourceRow) +
            '). No CMPD rate for ' + escapeHtml(item.region || 'this region') + '.</small>'
          : '<small>' + escapeHtml(match.rate.regionName) + ' regional average</small>')
        : 'No same-unit CMPD rate available<small>No published reference for this unit in the supplied extract.</small>';
      const powUrl = escapeHtml(item.powUrl);
      const source = item.powUrl
        ? '<a href="' + powUrl + '#page=' + encodeURIComponent(item.page) + '" target="_blank" rel="noopener">POW p. ' + escapeHtml(item.page) + ' ↗</a>'
        : 'POW p. ' + escapeHtml(item.page);
      return '<tr><td>' + escapeHtml(item.itemCode) + '<small>' + escapeHtml(item.description) + '</small></td>' +
        '<td>' + escapeHtml(item.unit) + '</td><td>' + cmpdPrice + '</td><td>' + peso(item.unitCost) + '</td>' +
        '<td>' + escapeHtml(item.project) + '<small>' + escapeHtml(item.office) + ' · ' +
        escapeHtml(item.region) + ' · ' + source + '</small></td></tr>';
    }).join('') || '<tr><td class="cmpd-empty" colspan="5">No matching POW rows for this material and search.</td></tr>';

    ratesBody.innerHTML = rates.map(rate => {
      const officePrice = rate.average == null
        ? 'Not listed' + (rate.priceStatus ? '<small>Status: ' + escapeHtml(rate.priceStatus) + '</small>' : '')
        : peso(rate.average);
      const categorySource = [rate.priceCategory, rate.priceSource].filter(Boolean).map(escapeHtml).join(' · ') || '—';
      const notes = rate.notes ? '<small>' + escapeHtml(rate.notes) + '</small>' : '';
      return '<tr><td>' + escapeHtml(rate.code) + '</td><td>' + escapeHtml(rate.description) +
        '</td><td>' + escapeHtml(rate.unit) + '</td><td>' + escapeHtml(rate.regionName) +
        '</td><td>' + escapeHtml(rate.office) + '</td><td>' + officePrice +
        '</td><td>' + peso(rate.regionalAverage) + '</td><td>' + categorySource + notes +
        '<small>Source row ' + escapeHtml(rate.sourceRow) + '</small></td></tr>';
    }).join('') ||
      '<tr><td class="cmpd-empty" colspan="8">No office rates are available for this material.</td></tr>';
  }

  const dataVersion = document.querySelector('meta[name="cmpd-data-version"]')?.content || '';
  fetch('cmpd-cost-per-unit-data.json?v=' + encodeURIComponent(dataVersion))
    .then(response => {
      if (!response.ok) throw new Error('Source data returned HTTP ' + response.status);
      return response.json();
    })
    .then(data => {
      const candidateCategories = new Set(Object.keys(data.candidateShards || {}));
      const materials = data.materials.filter(material =>
        candidateCategories.has(materialCategory(materialLabel(material.description)))
      );
      if (!materials.length) throw new Error('No matching CMPD materials were found in the supplied data.');
      materialSelect.innerHTML = materials.map(material =>
        '<option value="' + escapeHtml(material.code) + '">' + escapeHtml(material.description) + '</option>'
      ).join('');
      const candidateCache = new Map();
      const rateCache = new Map();
      const showError = error => {
        pageLoading.hidden = true;
        errorBox.hidden = false;
        errorBox.textContent = 'Data unavailable: ' + error.message;
        summary.textContent = 'The CMPD and POW comparison data could not be loaded.';
        boxplotPanel.hidden = true;
        boxplot.innerHTML = '';
        rowsBody.innerHTML = '<tr><td class="cmpd-empty" colspan="5">Data unavailable.</td></tr>';
        ratesBody.innerHTML = '<tr><td class="cmpd-empty" colspan="8">Data unavailable.</td></tr>';
      };
      const drawSelected = async () => {
        const material = data.materials.find(entry => entry.code === materialSelect.value);
        if (!material) throw new Error('Selected CMPD material was not found.');
        const category = materialCategory(materialLabel(material.description));
        let rates = rateCache.get(material.code);
        let candidates = candidateCache.get(category);
        if (!rates || !candidates) {
          pageLoading.hidden = false;
          summary.textContent = 'Loading ' + material.description + ' CMPD rates and POW matches…';
          const requests = [];
          if (!rates) {
            const name = data.rateShards[material.code];
            if (!name) throw new Error('CMPD office-rate shard is missing.');
            requests.push(fetch(name + '?v=' + encodeURIComponent(data.version)).then(response => {
              if (!response.ok) throw new Error('CMPD office rates returned HTTP ' + response.status);
              return response.json();
            }).then(value => { rates = value; rateCache.set(material.code, value); }));
          }
          if (!candidates) {
            const shardNames = data.candidateShards[category] || [];
            requests.push(Promise.all(shardNames.map(name =>
            fetch(name + '?v=' + encodeURIComponent(data.version)).then(response => {
              if (!response.ok) throw new Error('POW data shard returned HTTP ' + response.status);
              return response.json();
            })
            )).then(shards => { candidates = shards.flat(); candidateCache.set(category, candidates); }));
          }
          await Promise.all(requests);
        }
        draw({ rates, candidates, material });
        pageLoading.hidden = true;
      };
      materialSelect.addEventListener('change', () => drawSelected().catch(showError));
      searchInput.addEventListener('input', () => {
        const material = data.materials.find(entry => entry.code === materialSelect.value);
        const candidates = candidateCache.get(material ? materialCategory(materialLabel(material.description)) : '') || [];
        const rates = material ? rateCache.get(material.code) || [] : [];
        if (material) draw({ rates, candidates, material });
      });
      return drawSelected();
    })
    .catch(error => {
      pageLoading.hidden = true;
      errorBox.hidden = false;
      errorBox.textContent = 'Data unavailable: ' + error.message;
      summary.textContent = 'The CMPD and POW comparison data could not be loaded.';
      boxplotPanel.hidden = true;
      boxplot.innerHTML = '';
      rowsBody.innerHTML = '<tr><td class="cmpd-empty" colspan="5">Data unavailable.</td></tr>';
      ratesBody.innerHTML = '<tr><td class="cmpd-empty" colspan="8">Data unavailable.</td></tr>';
    });
})();

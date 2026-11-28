'use strict';
const search = document.querySelector('#search');
const contractors = document.querySelector('#contractors');
const selection = document.querySelector('#selection');
const table = document.querySelector('#events');
const download = document.querySelector('#download');
const directory = document.querySelector('#contractor-directory');
const directoryStatus = document.querySelector('#directory-status');
const historyHeading = document.querySelector('#history-heading');
const awardChart = document.querySelector('#contractor-workload-chart');
const awardDate = document.querySelector('#award-workload-date');
const awardValues = document.querySelector('#award-workload-values');
let awardSnapshots = [];
const number = new Intl.NumberFormat('en-PH');
const currency = new Intl.NumberFormat('en-PH', {style: 'currency', currency: 'PHP', maximumFractionDigits: 0});
const folder = 'contractor-workload/';
const shards = new Map();
let index = new Map();
let quarterSources = {};
let blacklisting = null;
const flaggedOnly = document.querySelector('#blacklisting-only');

function flaggedActivity(id) {
    return blacklisting?.contractors[id]?.activity.filter(event => event.windows.length) || [];
}

function sourceLink(label, url) {
    const link = document.createElement('a');
    link.textContent = label;
    link.href = url;
    return link;
}

function periodLabel(period) {
    return period.type + ' · ' + period.agency + ' · ' + period.start +
        (period.end ? ' to ' + period.end : ' onward') + (period.order ? ' · Order ' + period.order : '');
}

function renderBlacklisting() {
    const rows = [];
    let flaggedContractors = 0;
    for (const [id, record] of Object.entries(blacklisting.contractors)) {
        const events = flaggedActivity(id);
        if (events.length) flaggedContractors++;
        for (const event of events) {
            const row = document.createElement('tr');
            const name = cell('');
            const label = document.createElement('strong');
            label.className = 'blacklisting-overlap';
            label.textContent = record.periods[0].name + ' · ' + id;
            name.append(label);
            const activity = cell(event.type + ' · ' + event.date);
            const contract = cell(event.title + ' · ' + event.agency + ' · ');
            contract.append(sourceLink(event.source, event.url));
            const period = cell(event.windows.map(i => periodLabel(record.periods[i])).join(' | ') + ' · ');
            period.append(sourceLink('GPPB report', blacklisting.source));
            row.append(name, activity, contract, period);
            rows.push({row, day: event.date});
        }
    }
    rows.sort((a, b) => b.day.localeCompare(a.day));
    document.querySelector('#blacklisting-overlaps').replaceChildren(...rows.map(item => item.row));
    document.querySelector('#blacklisting-status').textContent =
        `${number.format(rows.length)} dated overlaps across ${number.format(flaggedContractors)} contractors. ` +
        `The GPPB snapshot was checked on ${blacklisting.snapshot}. The screen covers the retained PhilGEPS extracts and the reviewed World Bank procurement notices for the DA Philippine Rural Development Project Scale-up.`;
}

function renderContractorBlacklisting(id) {
    const container = document.querySelector('#contractor-blacklisting');
    container.replaceChildren();
    const record = blacklisting?.contractors[id];
    if (!record) return;
    for (const period of record.periods) {
        const paragraph = document.createElement('p');
        paragraph.append(periodLabel(period) + ' · ', sourceLink('GPPB report', blacklisting.source));
        container.append(paragraph);
    }
    for (const event of record.activity) {
        const paragraph = document.createElement('p');
        if (event.windows.length) paragraph.className = 'blacklisting-overlap';
        const timing = event.windows.length ? ' · During published blacklisting' :
            event.temporaryRemoval ? ' · Temporary removal requires date review' : ' · Outside recorded blacklisting periods';
        paragraph.append(event.type + ' · ' + event.date + ' · ' + event.title + timing + ' · ',
            sourceLink(event.source, event.url));
        container.append(paragraph);
    }
}

async function read(path) {
    const response = await fetch(folder + path);
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
}

function cell(value) {
    const td = document.createElement('td');
    td.textContent = value;
    return td;
}

function earlierCounts(event) {
    return {
        completed: event.priorCompleted,
        spanning: event.priorOverlap + event.priorOngoing,
        unclear: event.priorUnknown,
    };
}

function showWorkloadChart(records) {
    const dates = new Map();
    for (const event of records) {
        if (!dates.has(event.award)) {
            dates.set(event.award, {date: event.award, time: Date.parse(event.award), awards: 0, ...earlierCounts(event)});
        }
        dates.get(event.award).awards++;
    }
    awardSnapshots = [...dates.values()].sort((a, b) => a.time - b.time);
    awardDate.replaceChildren(...[...awardSnapshots].reverse().map(day =>
        new Option(`${day.date} · ${day.awards} ${day.awards === 1 ? 'award' : 'awards'}`, day.date)));
    awardChart.hidden = !awardSnapshots.length;
    drawWorkloadChart();
}

function drawWorkloadChart() {
    if (awardChart.hidden || !awardSnapshots.length) return;
    const selected = awardSnapshots.find(day => day.date === awardDate.value);
    if (!selected) return;
    awardValues.textContent = `${selected.date} · ${number.format(selected.completed)} completed · ` +
        `${number.format(selected.spanning)} spanning award · ${number.format(selected.unclear)} earlier status unclear`;
    const first = awardSnapshots[0];
    const last = awardSnapshots.at(-1);
    for (const canvas of awardChart.querySelectorAll('canvas')) {
        const key = canvas.dataset.series;
        const {clientWidth: width, clientHeight: height} = canvas;
        const density = window.devicePixelRatio || 1;
        canvas.width = Math.round(width * density);
        canvas.height = Math.round(height * density);
        const ctx = canvas.getContext('2d');
        ctx.scale(density, density);
        ctx.font = '11px system-ui';
        const max = Math.max(1, ...awardSnapshots.map(day => day[key]));
        const left = Math.max(30, ctx.measureText(number.format(max)).width + 9);
        const right = width - 16;
        const top = 10;
        const bottom = height - 23;
        const x = day => first.time === last.time ? (left + right) / 2 :
            left + (day.time - first.time) / (last.time - first.time) * (right - left);
        const y = day => bottom - day[key] / max * (bottom - top);
        ctx.strokeStyle = '#c7d1dc';
        ctx.beginPath();
        for (const level of [top, bottom]) {
            ctx.moveTo(left, level);
            ctx.lineTo(right, level);
        }
        ctx.stroke();
        ctx.fillStyle = '#35485d';
        ctx.fillText(number.format(max), 2, top + 4);
        ctx.fillText('0', 2, bottom + 4);
        ctx.fillText(first.date, left, height - 6);
        if (first !== last && width > left + 155) {
            ctx.textAlign = 'right';
            ctx.fillText(last.date, right, height - 6);
            ctx.textAlign = 'left';
        }
        ctx.strokeStyle = '#9aaab9';
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(x(selected), top);
        ctx.lineTo(x(selected), bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.strokeStyle = '#0038a8';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        awardSnapshots.forEach((day, i) => {
            if (i === 0) ctx.moveTo(x(day), y(day));
            else ctx.lineTo(x(day), y(day));
        });
        ctx.stroke();
        ctx.fillStyle = '#0038a8';
        for (const day of awardSnapshots) {
            ctx.beginPath();
            ctx.arc(x(day), y(day), day === selected ? 4 : 1.5, 0, 2 * Math.PI);
            ctx.fill();
        }
    }
}

awardDate.addEventListener('change', drawWorkloadChart);
window.addEventListener('resize', drawWorkloadChart);

function drawEvent(event, history, id) {
    const row = document.createElement('tr');
    const project = cell(event.award + ' · ');
    const link = document.createElement('a');
    link.href = 'https://transparency.dpwh.gov.ph/?project=' + encodeURIComponent(event.id);
    link.textContent = event.id + ' · ' + event.title;
    const metadata = document.createElement('small');
    metadata.textContent = [event.office, currency.format(event.amount), event.jointVenture ? 'Joint venture' : ''].filter(Boolean).join(' · ');
    project.append(link, metadata);
    if (flaggedActivity(id).some(flag => flag.type === 'Award' && flag.date === event.award && flag.reference === event.id)) {
        const evidence = sourceLink('Award during published blacklisting', '#blacklisting-check');
        evidence.className = 'blacklisting-overlap';
        project.append(evidence);
    }
    if (event.awardReferences.length) {
        const references = document.createElement('small');
        references.textContent = 'PhilGEPS award reference · ' + event.awardReferences.join(', ');
        project.append(references);
    }
    if (event.offlineSource) {
        const source = document.createElement('small');
        source.textContent = 'Included in the offline PhilGEPS contracts archive';
        project.append(source);
    }
    for (const key of event.quarterSources || []) {
        const link = document.createElement('a');
        link.href = quarterSources[key].url;
        link.textContent = 'PhilGEPS quarterly file · ' + key;
        project.append(document.createElement('br'), link);
    }
    for (const ref of event.liveReferences || []) {
        const link = document.createElement('a');
        link.href = 'https://philgeps.gov.ph/Indexes/viewAwardNotice/' + encodeURIComponent(ref);
        link.textContent = 'Official award notice ' + ref;
        project.append(document.createElement('br'), link);
    }
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Earlier contracts at this award';
    details.append(summary);
    details.addEventListener('toggle', () => {
        if (!details.open || details.childNodes.length > 1) return;
        const counts = document.createElement('p');
        counts.textContent = [
            `${number.format(event.priorCompleted)} completed before award (${number.format(event.priorLong)} took over 365 days, ${number.format(event.priorBeyondEnd || 0)} finished after the posted end)`,
            `${number.format(event.priorOverlap)} completed on or after this award date`,
            `${number.format(event.priorOngoing)} still listed as ongoing at the archive snapshot`,
            `${number.format(event.priorUnknown)} with unclear earlier status`,
        ].join(' · ');
        details.append(counts);
        const list = document.createElement('ul');
        for (const [id, start, completion, status, postedEnd] of history) {
            if (start >= event.award || id === event.id) continue;
            const item = document.createElement('li');
            const source = document.createElement('a');
            source.href = 'https://transparency.dpwh.gov.ph/?project=' + encodeURIComponent(id);
            source.textContent = id;
            const state = completion
                ? (completion < event.award ? 'Completed before award' : 'Completion on or after award') + ' · ' + completion
                : 'Snapshot status · ' + status;
            item.append(source, ' · Started ' + start + ' · ' + state);
            if (postedEnd) item.append(' · PhilGEPS posted end ' + postedEnd);
            list.append(item);
        }
        details.append(list.childElementCount ? list : document.createTextNode('No earlier dated records in the archive.'));
    });
    project.append(details);
    row.append(project,
        cell([event.status, event.start && 'Started ' + event.start, event.completion && 'Completed ' + event.completion, event.postedEnd && 'PhilGEPS posted end ' + event.postedEnd].filter(Boolean).join(' · ')));
    return row;
}

function renderDirectory() {
    const filter = search.value.trim().toLowerCase();
    const records = [...index.values()].filter(row =>
        (row.name + ' ' + row.id).toLowerCase().includes(filter) && (!flaggedOnly.checked || flaggedActivity(row.id).length));
    const selected = contractors.value;
    contractors.replaceChildren(new Option('Choose a contractor', ''));
    for (const row of records) {
        contractors.add(new Option(row.name + ' · ' + row.id + ' · ' + row.awards + ' awards', row.id));
    }
    directory.replaceChildren(...records.map(record => {
        const row = document.createElement('tr');
        const name = document.createElement('th');
        name.scope = 'row';
        const button = document.createElement('button');
        button.type = 'button';
        const overlaps = flaggedActivity(record.id);
        button.textContent = record.name;
        if (overlaps.length) button.className = 'blacklisting-overlap';
        button.addEventListener('click', () => {
            contractors.value = record.id;
            showAwards();
            historyHeading.focus();
        });
        name.append(button);
        if (overlaps.length) {
            const note = document.createElement('small');
            note.className = 'blacklisting-overlap';
            note.textContent = overlaps.length + ' dated overlaps';
            name.append(note);
        }
        row.append(name, cell(record.id), cell(number.format(record.awards)),
            cell(number.format(record.withOverlap)), cell(record.latest));
        return row;
    }));
    directoryStatus.textContent = records.length ? number.format(records.length) + ' contractor licenses' : 'No contractors match this search.';
    if (records.some(record => record.id === selected)) {
        contractors.value = selected;
    } else {
        contractors.value = records[0]?.id || '';
        showAwards();
    }
}

search.addEventListener('input', renderDirectory);
flaggedOnly.addEventListener('change', renderDirectory);
contractors.addEventListener('change', showAwards);

async function showAwards() {
    const id = contractors.value;
    renderContractorBlacklisting(id);
    const contractor = index.get(id);
    historyHeading.classList.toggle('blacklisting-overlap', flaggedActivity(id).length > 0);
    table.replaceChildren();
    awardChart.hidden = true;
    download.hidden = true;
    if (!contractor) {
        historyHeading.textContent = 'Award history';
        selection.textContent = index.size ? 'Select a contractor to see their awards.' : 'No award records are available.';
        return;
    }
    historyHeading.textContent = contractor.name + ' · License ' + contractor.id;
    selection.textContent = 'Loading award records…';
    try {
        if (!shards.has(contractor.shard)) {
            const request = read(contractor.shard + '.json');
            shards.set(contractor.shard, request);
            request.catch(() => shards.delete(contractor.shard));
        }
        const {awards: records, history} = (await shards.get(contractor.shard))[id];
        if (contractors.value !== id) return;
        table.replaceChildren(...records.map(event => drawEvent(event, history, id)));
        showWorkloadChart(records);
        selection.textContent = number.format(records.length) + ' matched awards. ' +
            number.format(contractor.withOverlap) + ' had earlier work spanning the award date.';
        if (download.href) URL.revokeObjectURL(download.href);
        download.href = URL.createObjectURL(new Blob([JSON.stringify({awards: records, history}, null, 2)], {type: 'application/json'}));
        download.download = 'contractor-' + id + '-awards.json';
        download.hidden = false;
    } catch {
        if (contractors.value === id) selection.textContent = 'Could not load this contractor’s awards. Select the contractor again to retry.';
    }
}

read('index.json').then(data => {
    index = new Map(data.contractors.map(row => [row.id, row]));
    const c = data.coverage;
    document.querySelector('#coverage').textContent =
        number.format(c.awardObservations) + ' matched award records across ' + number.format(index.size) +
        ' contractor licenses. Earlier work spanned the award date in ' + number.format(c.withOverlap) +
        ' records. In ' + number.format(c.afterLongProject) +
        ' records, the contractor had already completed a project that took over 365 days.';
    quarterSources = data.quarterSources;
    for (const [key, source] of Object.entries(quarterSources)) {
        const row = document.createElement('tr');
        const label = cell('');
        const link = document.createElement('a');
        link.href = source.url;
        link.textContent = key;
        label.append(link);
        row.append(label, cell(number.format(source.rows)), cell(number.format(source.datedAwardRows)), cell(number.format(source.identifiedRows)));
        document.querySelector('#quarter-rows').append(row);
    }
    document.querySelector('#posted-ends').textContent =
        `In ${number.format(c.afterPriorBeyondEnd)} new awards, the contractor had at least one earlier completed contract whose recorded completion fell after its PhilGEPS posted end. Both dates were available for ${number.format(c.withBothDates)} matched award–license pairs, of which ${number.format(c.afterPostedEnd)} finished after the posted end. Approved extensions and the awarding office’s knowledge remain unverified.`;
    const live = data.live.listingPages
        ? ` The modern award board search screened ${number.format(data.live.listedNotices)} notices from ${data.live.from} through ${data.live.to} and contributed ${number.format(c.liveAwardPairs || 0)} matched pairs.`
        : ' Live coverage after the quarterly files is pending.';
    document.querySelector('#crawl-coverage').textContent =
        `The offline contracts archive supports ${number.format(c.offlineAwardPairs || 0)} matched award–license pairs, including ${number.format(c.offlineOnlyPairs || 0)} unique to that archive. PhilGEPS v2 supports ${number.format(c.v2AwardPairs || 0)}. Eight official exports from Q4 2025 through Q3 2026 support ${number.format(c.quarterAwardPairs || 0)}. Those counts can overlap. Conflicting award dates excluded ${number.format(c.conflictingDateObservations)} award–license pairs.` + live;
    window.drawQuestionBars?.('workload-chart', Object.entries(data.workloadBands).map(([band, counts]) => [band, counts.awards]));
    for (const [band, counts] of Object.entries(data.workloadBands)) {
        const row = document.createElement('tr');
        row.append(cell(band), cell(number.format(counts.awards)), cell(number.format(counts.afterLongProject)));
        document.querySelector('#workload-bands').append(row);
    }
    const p = data.comparison;
    if (p.overlap) {
        const difference = p.differencePercentagePoints;
        const direction = difference < 0 ? 'lower' : 'higher';
        document.querySelector('#comparison').textContent =
            'Across ' + number.format(p.groups) + ' comparable groups and ' +
            number.format(p.overlap + p.noOverlap) + ' awards, completion within a year was ' +
            Math.abs(difference).toFixed(2) + ' percentage points ' + direction +
            ' for contractors with recorded overlap, weighting groups by their overlap awards.';
    }
    renderDirectory();
}).catch(() => {
    const message = 'Could not load the award analysis. Reload the page to retry.';
    document.querySelector('#coverage').textContent = message;
    directoryStatus.textContent = message;
    selection.textContent = message;
});

read('sanctions.json').then(data => {
    blacklisting = data;
    flaggedOnly.disabled = false;
    renderBlacklisting();
    if (index.size) {
        renderDirectory();
        showAwards();
    }
}).catch(() => {
    document.querySelector('#blacklisting-status').textContent = 'Could not load the blacklisting overlaps. Reload to retry.';
});

const liveNotices = document.querySelector('#live-notices');
async function loadLiveNotices() {
    if (!liveNotices.open || liveNotices.dataset.loaded) return;
    const status = document.querySelector('#live-notice-status');
    try {
        const notices = await read('live-notices.json');
        notices.sort((a, b) => b.award_date.localeCompare(a.award_date) || a.contract_no.localeCompare(b.contract_no));
        const rows = notices.map(notice => {
            const row = document.createElement('tr');
            const linkCell = cell('');
            const link = document.createElement('a');
            link.href = 'https://philgeps.gov.ph/Indexes/viewAwardNotice/' + encodeURIComponent(notice.award_reference_no);
            link.textContent = notice.award_reference_no + ' · ' + notice.award_notice_status;
            linkCell.append(link);
            row.append(cell(notice.award_date), cell(notice.contract_no), cell(notice.awardee_organization_name),
                cell(notice.contract_end_date || 'Unlisted'), linkCell);
            return row;
        });
        document.querySelector('#live-notice-rows').replaceChildren(...rows);
        status.textContent = number.format(rows.length) + ' verified notices';
        liveNotices.dataset.loaded = 'true';
    } catch {
        status.textContent = 'Could not load the notices. Reopen this section to retry.';
    }
}
liveNotices.addEventListener('toggle', loadLiveNotices);
loadLiveNotices();

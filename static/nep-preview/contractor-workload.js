'use strict';
const search = document.querySelector('#search');
const contractors = document.querySelector('#contractors');
const selection = document.querySelector('#selection');
const table = document.querySelector('#events');
const download = document.querySelector('#download');
const directory = document.querySelector('#contractor-directory');
const directoryStatus = document.querySelector('#directory-status');
const historyHeading = document.querySelector('#history-heading');
const number = new Intl.NumberFormat('en-PH');
const currency = new Intl.NumberFormat('en-PH', {style: 'currency', currency: 'PHP', maximumFractionDigits: 0});
const folder = 'contractor-workload/';
const shards = new Map();
let index = new Map();
let quarterSources = {};

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

function drawEvent(event, history) {
    const row = document.createElement('tr');
    const project = cell(event.award + ' · ');
    const link = document.createElement('a');
    link.href = 'https://transparency.dpwh.gov.ph/?project=' + encodeURIComponent(event.id);
    link.textContent = event.id + ' · ' + event.title;
    const metadata = document.createElement('small');
    metadata.textContent = [event.office, currency.format(event.amount), event.jointVenture ? 'Joint venture' : ''].filter(Boolean).join(' · ');
    project.append(link, metadata);
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
    summary.textContent = 'Earlier contract records';
    details.append(summary);
    details.addEventListener('toggle', () => {
        if (!details.open || details.childNodes.length > 1) return;
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
        cell(event.priorCompleted + ' completed · ' + event.priorLong + ' took over 365 days · ' + event.priorBeyondEnd + ' finished after posted end'),
        cell(event.priorOverlap + ' completed later or same day · ' + event.priorOngoing + ' still ongoing at snapshot'),
        cell(event.priorUnknown),
        cell([event.status, event.start && 'Started ' + event.start, event.completion && 'Completed ' + event.completion, event.postedEnd && 'PhilGEPS posted end ' + event.postedEnd].filter(Boolean).join(' · ')));
    return row;
}

function renderDirectory() {
    const filter = search.value.trim().toLowerCase();
    const records = [...index.values()].filter(row => (row.name + ' ' + row.id).toLowerCase().includes(filter));
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
        button.textContent = record.name;
        button.addEventListener('click', () => {
            contractors.value = record.id;
            showAwards();
            historyHeading.focus();
        });
        name.append(button);
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
contractors.addEventListener('change', showAwards);

async function showAwards() {
    const id = contractors.value;
    const contractor = index.get(id);
    table.replaceChildren();
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
        table.replaceChildren(...records.map(event => drawEvent(event, history)));
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

'use strict';
const search = document.querySelector('#search');
const contractors = document.querySelector('#contractors');
const selection = document.querySelector('#selection');
const table = document.querySelector('#events');
const download = document.querySelector('#download');
const number = new Intl.NumberFormat('en-PH');
const currency = new Intl.NumberFormat('en-PH', {style: 'currency', currency: 'PHP', maximumFractionDigits: 0});
const folder = 'contractor-workload/';
const shards = new Map();
let index = new Map();

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
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Earlier contract records';
    details.append(summary);
    details.addEventListener('toggle', () => {
        if (!details.open || details.childNodes.length > 1) return;
        const list = document.createElement('ul');
        for (const [id, start, completion, status] of history) {
            if (start >= event.award || id === event.id) continue;
            const item = document.createElement('li');
            const source = document.createElement('a');
            source.href = 'https://transparency.dpwh.gov.ph/?project=' + encodeURIComponent(id);
            source.textContent = id;
            const state = completion
                ? (completion < event.award ? 'Completed before award' : 'Completion on or after award') + ' · ' + completion
                : 'Snapshot status · ' + status;
            item.append(source, ' · Started ' + start + ' · ' + state);
            list.append(item);
        }
        details.append(list.childElementCount ? list : document.createTextNode('No earlier dated records in the archive.'));
    });
    project.append(details);
    row.append(project,
        cell(event.priorCompleted + ' completed · ' + event.priorLong + ' took over 365 days'),
        cell(event.priorOverlap + ' completed later or same day · ' + event.priorOngoing + ' still ongoing at snapshot'),
        cell(event.priorUnknown),
        cell([event.status, event.start && 'Started ' + event.start, event.completion && 'Completed ' + event.completion].filter(Boolean).join(' · ')));
    return row;
}

search.addEventListener('input', () => {
    const filter = search.value.trim().toLowerCase();
    contractors.replaceChildren(new Option('Choose a contractor', ''));
    table.replaceChildren();
    selection.textContent = '';
    download.hidden = true;
    for (const row of index.values()) {
        if ((row.name + ' ' + row.id).toLowerCase().includes(filter)) {
            contractors.add(new Option(row.name + ' · ' + row.id + ' · ' + row.awards + ' awards', row.id));
        }
    }
});

contractors.addEventListener('change', async () => {
    const id = contractors.value;
    const contractor = index.get(id);
    table.replaceChildren();
    download.hidden = true;
    if (!contractor) {
        selection.textContent = '';
        return;
    }
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
});

read('index.json').then(data => {
    index = new Map(data.contractors.map(row => [row.id, row]));
    const c = data.coverage;
    document.querySelector('#coverage').textContent =
        number.format(c.awardObservations) + ' matched award records across ' + number.format(index.size) +
        ' contractor licenses. Earlier work spanned the award date in ' + number.format(c.withOverlap) +
        ' records. In ' + number.format(c.afterLongProject) +
        ' records, the contractor had already completed a project that took over 365 days.';
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
    search.dispatchEvent(new Event('input'));
}).catch(() => {
    document.querySelector('#coverage').textContent = 'Could not load the award analysis. Reload the page to retry.';
});

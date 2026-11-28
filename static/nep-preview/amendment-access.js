'use strict';

const origin = document.querySelector('#origin');
const wait = document.querySelector('#wait');
const status = document.querySelector('#route-status');
const number = new Intl.NumberFormat('en-PH');
const minutes = value => `${Math.round(value)} min`;
const pesos = value => `₱${number.format(value)}`;
const distance = value => `${value.toFixed(1)} km`;

function element(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
}

function budgetCell(label, url, className) {
    const cell = element('td', '', className);
    const link = element('a', label);
    link.href = url;
    cell.append(link);
    return cell;
}

function draw(canvas, data, row, mode) {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const density = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * density);
    canvas.height = Math.round(height * density);
    const ctx = canvas.getContext('2d');
    ctx.scale(density, density);
    const center = [16.345, 119.920];
    const lonScale = Math.cos(center[0] * Math.PI / 180);
    const scale = Math.min((width - 44) / .106, (height - 54) / .169);
    const project = ([lat, lon]) => [
        width / 2 + (lon - center[1]) * scale * lonScale,
        height / 2 - (lat - center[0]) * scale,
    ];

    function paint(lines, color, weight, dash = []) {
        ctx.strokeStyle = color;
        ctx.lineWidth = weight;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.setLineDash(dash);
        ctx.beginPath();
        for (const line of lines) {
            for (let i = 0; i < line.length; i++) {
                const [x, y] = project(line[i]);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
        }
        ctx.stroke();
        ctx.setLineDash([]);
    }

    function label(text, point, color, offset = [8, -7]) {
        const [x, y] = project(point);
        ctx.font = '600 12px system-ui, sans-serif';
        const left = Math.min(Math.max(8, x + offset[0]), width - ctx.measureText(text).width - 8);
        ctx.strokeStyle = '#f2f8fc';
        ctx.lineWidth = 4;
        ctx.strokeText(text, left, y + offset[1]);
        ctx.fillStyle = color;
        ctx.fillText(text, left, y + offset[1]);
    }

    function point(place, color) {
        const [x, y] = project(place);
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
    }

    paint(data.shoreline, '#9cbccf', 1.2);
    paint(data.roads, '#c4d3dc', .7);
    const [first, crossing, last] = row[mode].legs;
    paint([first, last], '#075394', 3);
    paint([crossing], mode === 'ferry' ? '#93491c' : '#08746c', 4, [5, 4]);
    label('Santiago Island', [16.430, 119.901], '#465e70');
    label('Bolinao mainland', [16.321, 119.913], '#465e70');
    point(row.point, '#075394');
    point(data.hospital, '#075394');
    label(row.name, row.point, '#082a57');
    label('Bolinao Community Hospital', data.hospital, '#082a57');
    ctx.fillStyle = '#465e70';
    ctx.font = '12px system-ui, sans-serif';
    ctx.fillText('↑ N', 13, 18);
}

function showCorridor(projects) {
    const filter = document.querySelector('#corridor-kind');
    for (const kind of new Set(projects.map(project => project.kind))) filter.add(new Option(kind));
    function renderProjects() {
        const selected = projects.filter(project => !filter.value || project.kind === filter.value);
        document.querySelector('#corridor-result').textContent = `${selected.length} budget lines in view.`;
        document.querySelector('#corridor-projects').replaceChildren(...selected.map(project => {
            const row = document.createElement('tr');
            const heading = element('th', project.title);
            heading.scope = 'row';
            const budget = project.gaa2026
                ? budgetCell(`FY2026 GAA · ${pesos(project.gaa2026)}`, project.sourceUrl)
                : budgetCell(`House · ${pesos(project.house)}`, project.houseUrl);
            if (!project.gaa2026) {
                const senate = element('a', `Senate committee · ${pesos(project.senate)}`);
                senate.href = project.senateUrl;
                budget.append(document.createElement('br'), senate);
                if (project.nep !== null) budget.append(document.createElement('br'), `NEP · ${pesos(project.nep)}`);
            }
            const note = element('td', project.note);
            if (project.routeDistancesMeters.length) {
                const offsets = project.routeDistancesMeters.map(meters => `${number.format(meters)} m`);
                note.append(element('small', `Endpoint distances to modeled road points · ${offsets.join(' and ')}`));
            }
            row.append(heading, element('td', project.kind), budget, note);
            return row;
        }));
    }
    filter.addEventListener('change', renderProjects);
    renderProjects();
}

function setup(data) {
    showCorridor(data.corridorProjects);
    const projectTypes = new Map();
    for (const project of data.corridorProjects) {
        projectTypes.set(project.kind, (projectTypes.get(project.kind) || 0) + 1);
    }
    drawQuestionBars('corridor-chart', [...projectTypes].sort((a, b) => b[1] - a[1]));
    const rows = data.origins;
    const population = rows.reduce((sum, row) => sum + row.population, 0);
    const house = data.budget.reduce((sum, row) => sum + row.house, 0);
    bolinaoSummary[0][0] = `${number.format(rows.length)} barangays`;
    bolinaoSummary[1][0] = `${number.format(population)} residents`;
    bolinaoSummary[2][0] = house % 1e6 ? pesos(house) : `₱${number.format(house / 1e6)} million`;
    if (bridgeSelect.value === 'bolinao') renderProjectSummary();
    document.querySelector('#budget-ratio').textContent =
        `The two House lines equal about ${pesos(Math.round(house / population))} per resident across the seven barangays. This compares the proposed lines with the population in reach of the modeled route. Total construction and operating costs are separate.`;
    const [islandGap, mainlandGap] = data.bridgeSnapMeters;
    document.querySelector('#bridge-method').textContent =
        `The approximate modeled connection is ${distance(data.bridgeKm)}, including road tie-ins of ${islandGap} m on the island and ${mainlandGap} m on the mainland. Map snapshot retrieved ${data.snapshotDate}.`;
    for (const line of data.budget) {
        const row = document.createElement('tr');
        const heading = element('th', line.title);
        heading.scope = 'row';
        row.append(heading, budgetCell(line.nep === null ? 'No counterpart identified' : pesos(line.nep), data.nepUrl),
            budgetCell(pesos(line.house), line.houseUrl, 'num'), budgetCell(pesos(line.senate), line.senateUrl, 'num'));
        document.querySelector('#budget-rows').append(row);
    }
    for (const row of rows) origin.append(new Option(row.name, row.name));
    origin.value = 'Salud';
    origin.disabled = wait.disabled = false;

    function redraw() {
        if (document.querySelector('#bolinao-routes').hidden) return;
        const row = rows.find(item => item.name === origin.value);
        for (const mode of ['ferry', 'bridge']) draw(document.querySelector(`#${mode}-map`), data, row, mode);
    }

    function update() {
        const delay = Number(wait.value);
        const selected = rows.find(row => row.name === origin.value);
        const ferryTime = selected.ferry.minutes + delay;
        const weightedSaving = rows.reduce((total, r) =>
            total + r.population * (r.ferry.minutes + delay - r.bridge.minutes), 0) / population;
        document.querySelector('#population-time').textContent =
            `Across the seven barangays, the model saves ${weightedSaving.toFixed(1)} minutes per one-way hospital trip at this ferry wait, weighting each barangay by its population. Actual trip frequency is unknown.`;
        drawQuestionBars('route-chart', rows.map(row =>
            [row.name, row.ferry.minutes + delay - row.bridge.minutes]), ' min');
        document.querySelector('#wait-value').textContent = minutes(delay);
        status.textContent = `${selected.name} to Bolinao Community Hospital · About ${minutes(ferryTime)} by ferry, ${minutes(selected.bridge.minutes)} via the completed bridge.`;
        document.querySelector('#ferry-label').textContent =
            `${distance(selected.ferry.roadKm)} on roads, ${minutes(data.ferryMinutes)} on the ferry, ${minutes(delay)} assumed wait`;
        document.querySelector('#bridge-label').textContent =
            `${distance(selected.bridge.roadKm)} on roads, including the modeled connection`;
        document.querySelector('#comparison').replaceChildren(...rows.map(row => {
            const tr = document.createElement('tr');
            const th = element('th', row.name);
            th.scope = 'row';
            tr.append(th, ...[number.format(row.population), minutes(row.ferry.minutes + delay),
                minutes(row.bridge.minutes), minutes(row.ferry.minutes + delay - row.bridge.minutes)]
                .map(value => element('td', value, 'num')));
            return tr;
        }));
    }

    origin.addEventListener('change', () => { update(); redraw(); });
    wait.addEventListener('input', update);
    window.addEventListener('resize', redraw);
    update();
    redraw();
}

fetch('amendment-access-data.json')
    .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    })
    .then(setup)
    .catch(() => {
        status.textContent = 'The route data could not be loaded. Reload the page to try again.';
    });

const national = document.querySelector('#national-fmrs');
const serviceFilter = document.querySelector('#service-filter');
let nationalData;
let connectivityRequest;
function readConnectivityData() {
    if (!connectivityRequest) {
        connectivityRequest = fetchCritiqueData('connectivity-data.json').catch(error => {
            connectivityRequest = undefined;
            throw error;
        });
    }
    return connectivityRequest;
}
function renderNational() {
    const selected = nationalData.projects.filter(row => !serviceFilter.value || row.nearbyPublicServices[serviceFilter.value]);
    document.querySelector('#national-count').textContent = number.format(selected.length) + ' matching proposals';
    document.querySelector('#national-projects').replaceChildren(...selected.map(project => {
        const row = document.createElement('tr');
        const services = element('td', '');
        const evidence = project.nearbyPublicServiceEvidence.filter(site => !serviceFilter.value || site.type === serviceFilter.value);
        for (const site of evidence) {
            const link = element('a', site.name + ' · ' + number.format(site.distanceMeters) + ' m');
            link.href = site.sourceUrl;
            services.append(link, document.createElement('br'));
        }
        if (!evidence.length) services.textContent = project.coordinateQualityFlag ? 'Coordinates require review' : 'No mapped service recorded';
        row.append(element('th', project.title), element('td', project.nearestDistanceMeters == null ? project.result : number.format(project.nearestDistanceMeters) + ' m'), services);
        return row;
    }));
}
async function loadNational() {
    if (!national.open || nationalData) return;
    const message = document.querySelector('#national-count');
    message.textContent = 'Loading project records…';
    try {
        nationalData = await readConnectivityData();
        renderNational();
    } catch {
        message.textContent = 'Could not load the proposals. Reopen this section to retry.';
    }
}
national.addEventListener('toggle', loadNational);
loadNational();
serviceFilter.addEventListener('change', () => { if (nationalData) renderNational(); });

const bridgeSelect = document.querySelector('#bridge-scenario');
const bridgeOrigin = document.querySelector('#bridge-origin');
const bridgeCoverage = document.querySelector('#bridge-coverage');
const routeData = {};
const routeScenarios = new Map();
const detourMinutes = value => number.format(Math.round(Math.max(0, value) * 10) / 10) + ' min';
const routeDelta = trip => trip.closed ? trip.closed.minutes - trip.open.minutes : null;
const fasterDetour = trip => trip.closed && routeDelta(trip) < 0;

function timeChange(delta) {
    if (delta === 0) return 'same travel time';
    const duration = Math.abs(delta) < .05 ? 'under 0.1 min' : detourMinutes(Math.abs(delta));
    return `${duration} ${delta < 0 ? 'faster' : 'longer'}`;
}

const summaryIds = ['covered', 'population', 'budget-summary'];
const bolinaoSummary = summaryIds.map(id =>
    [document.getElementById(id).textContent, document.getElementById(id + '-label').textContent]);

function renderProjectSummary(scenario) {
    let stats = bolinaoSummary;
    if (scenario) {
        const paving = scenario.kind === 'road' && scenario.mode !== 'closure';
        const trips = scenario.origins;
        const withAlternative = trips.filter(trip => trip.closed);
        const noDetour = trips.length - withAlternative.length;
        const flagged = paving ? 0 : withAlternative.filter(fasterDetour).length;
        const changes = withAlternative.map(trip => paving ? -routeDelta(trip) : routeDelta(trip))
            .filter(delta => delta >= 0);
        let timeRange = flagged ? 'Check modeled routes' : 'No local detour';
        if (changes.length) {
            const min = detourMinutes(Math.min(...changes));
            const max = detourMinutes(Math.max(...changes));
            timeRange = min === max ? max : `${min.replace(' min', '')}–${max}`;
        }
        const kind = scenario.kind === 'road' ? 'road' : 'bridge';
        const budgetLines = routeData[kind].projects.filter(row => row.scenario === bridgeSelect.value);
        const amount = budgetLines.reduce((sum, row) => sum + row.amount, 0);
        stats = [
            [`${number.format(trips.length)} ${trips.length === 1 ? 'settlement' : 'settlements'}`,
                'Sampled starting points for hospital trips. Population unavailable.'],
            [timeRange,
                paving ? 'Modeled time saved after paving' : [
                    changes.length ? `Extra travel time if the ${kind} closes.` : '',
                    noDetour ? `${number.format(noDetour)} of ${number.format(trips.length)} trips had no local detour.` : '',
                    flagged ? `Check ${number.format(flagged)} ${flagged === 1 ? 'trip' : 'trips'} with a faster modeled detour.` : '',
                ].filter(Boolean).join(' ')],
            [budgetLines.length ? pesos(amount) : 'Budget unavailable',
                budgetLines.length === 1 ? 'FY2027 House proposal for this project'
                    : `${number.format(budgetLines.length)} matched FY2027 House budget lines`],
        ];
    }
    summaryIds.forEach((id, i) => {
        const [value, label] = stats[i];
        document.getElementById(id).textContent = value;
        document.getElementById(id + '-label').textContent = label;
    });
}


function drawDetour(canvas, trip, span, mode, paving, destinationLabel = 'Hospital') {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const density = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * density);
    canvas.height = Math.round(height * density);
    const ctx = canvas.getContext('2d');
    ctx.scale(density, density);
    const all = [...trip.open.points, ...(trip.closed?.points || []), ...span.flat(), trip.point, trip.hospital];
    const latitudes = all.map(p => p[0]);
    const longitudes = all.map(p => p[1]);
    const lat = (Math.min(...latitudes) + Math.max(...latitudes)) / 2;
    const lon = (Math.min(...longitudes) + Math.max(...longitudes)) / 2;
    const lonScale = Math.cos(lat * Math.PI / 180);
    const scale = Math.min((width - 48) / Math.max(.001, (Math.max(...longitudes) - Math.min(...longitudes)) * lonScale),
        (height - 48) / Math.max(.001, Math.max(...latitudes) - Math.min(...latitudes)));
    const project = ([y, x]) => [width / 2 + (x - lon) * scale * lonScale, height / 2 - (y - lat) * scale];
    function paint(points, color, weight, dash = []) {
        ctx.beginPath();
        points.forEach((point, index) => {
            const [x, y] = project(point);
            if (index === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.strokeStyle = color;
        ctx.lineWidth = weight;
        ctx.lineJoin = 'round';
        ctx.setLineDash(dash);
        ctx.stroke();
    }
    if (trip[mode]) paint(trip[mode].points, '#075394', 3);
    for (const points of span) paint(points, mode === 'closed' && !paving ? '#a13721' : '#08746c', 5, mode === 'closed' && !paving ? [4, 3] : []);
    for (const [point, label] of [[trip.point, 'Start'], [trip.hospital, destinationLabel]]) {
        const [x, y] = project(point);
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#082a57';
        ctx.fill();
        ctx.font = '600 12px system-ui';
        const left = Math.min(x + 8, width - ctx.measureText(label).width - 8);
        ctx.fillText(label, left, y - 7);
    }
}

function redrawOtherBridge() {
    const scenario = routeScenarios.get(bridgeSelect.value);
    if (!scenario) return;
    const trip = scenario.origins[bridgeOrigin.value];
    if (!trip) return;
    const road = scenario.kind === 'road';
    const paving = road && scenario.mode !== 'closure';
    const crossing = road ? 'road' : 'bridge';
    const start = `${trip.name} to ${trip.hospitalName} · ${detourMinutes(trip.open.minutes)}`;
    const result = trip.closed
        ? `${detourMinutes(trip.closed.minutes)} via the detour if the ${crossing} closes (${timeChange(routeDelta(trip))})`
        : 'no alternate road route found in the modeled window';
    const routeStatus = document.querySelector('#bridge-route-status');
    routeStatus.textContent = paving
        ? `${start} before paving, ${detourMinutes(trip.closed.minutes)} after paving (${timeChange(routeDelta(trip))}).`
        : `${start} with the ${crossing} open, ${result}.`;
    if (!paving && fasterDetour(trip)) {
        routeStatus.append(' ', element('strong', 'Check route: the modeled detour is faster.', 'route-review-flag'));
    }
    for (const mode of ['open', 'closed']) drawDetour(document.querySelector(`#${mode}-map`), trip, scenario.span, mode, paving);
}

function showBridgeSelection() {
    const scenario = routeScenarios.get(bridgeSelect.value);
    renderProjectSummary(scenario);
    document.querySelector('#bolinao-routes').hidden = Boolean(scenario);
    document.querySelector('#other-bridge-routes').hidden = !scenario;
    if (!scenario) {
        window.dispatchEvent(new Event('resize'));
        return;
    }
    const road = scenario.kind === 'road';
    const paving = road && scenario.mode !== 'closure';
    const before = paving ? 'Before paving' : road ? 'Road open' : 'Bridge open';
    const after = paving ? 'After paving' : road ? 'Road closed' : 'Bridge closed';
    document.querySelector('#scenario-method').textContent = paving
        ? `This scenario raises the assumed driving speed to 30 km/h along ${scenario.length} km of mapped unpaved road. Both trips use the same starting point and hospital.`
        : road
            ? `This scenario removes ${scenario.length} km of mapped road between the printed endpoints. The mapped path approximates the project alignment.`
            : 'The closure scenario removes the matched OpenStreetMap way. Bridges mapped as multiple carriageways require separate review.';
    for (const id of ['open-map-title', 'route-before-col']) document.getElementById(id).textContent = before;
    for (const id of ['closed-map-title', 'route-after-col']) document.getElementById(id).textContent = after;
    document.querySelector('#route-change-col').textContent = paving ? 'Minutes saved' : 'Travel-time change';
    document.querySelector('#detour-chart-title').textContent = paving
        ? 'Modeled minutes saved after paving' : 'Modeled detour minutes for trips with a local alternate route';
    document.querySelector('#before-legend').textContent = paving ? 'Paving segment' : road ? 'Open road segment' : 'Open bridge span';
    document.querySelector('#after-legend').textContent = road ? 'Closed road segment' : 'Closed bridge span';
    document.querySelector('#after-legend').hidden = paving;
    bridgeOrigin.replaceChildren(...scenario.origins.map((row, i) => new Option(row.name, i)));
    const chart = scenario.origins.filter(trip => trip.closed)
        .map(trip => [trip.name, paving ? -routeDelta(trip) : routeDelta(trip)])
        .filter(([, delta]) => delta >= 0);
    document.querySelector('#detour-chart').closest('figure').hidden = !chart.length;
    if (chart.length) drawQuestionBars('detour-chart', chart, ' min');
    const source = document.querySelector('#mapped-span');
    source.href = road ? scenario.url : `https://www.openstreetmap.org/way/${scenario.bridgeWay}`;
    source.textContent = road ? 'View the House budget line' : 'View the matched bridge in OpenStreetMap';
    document.querySelector('#bridge-route-comparison').replaceChildren(...scenario.origins.map(trip => {
        const row = document.createElement('tr');
        const change = element('td', trip.closed
            ? paving && routeDelta(trip) <= 0 ? detourMinutes(-routeDelta(trip)) : timeChange(routeDelta(trip))
            : '—');
        if (!paving && fasterDetour(trip)) {
            change.append(element('strong', 'Check route', 'route-review-flag'));
        }
        row.append(element('th', trip.name), element('td', trip.hospitalName), element('td', detourMinutes(trip.open.minutes)),
            element('td', trip.closed ? detourMinutes(trip.closed.minutes) : 'No local detour found'), change);
        return row;
    }));
    redrawOtherBridge();
}

function showRouteInventory(kind) {
    const data = routeData[kind];
    if (!data || !document.getElementById(kind + '-research').open) return;
    const term = document.getElementById(kind + '-search').value.trim().toLowerCase();
    const filter = document.getElementById(kind + '-filter').value;
    const projects = data.projects.filter(row => (!filter || filter === row.status) &&
        (!term || [row.title, row.region, row.bridgeId].join(' ').toLowerCase().includes(term)));
    document.getElementById(kind + '-list-count').textContent = `${number.format(projects.length)} budget lines`;
    document.getElementById(kind + '-inventory').replaceChildren(...projects.map(project => {
        const row = document.createElement('tr');
        const result = element('td', project.status);
        if (project.scenario) {
            const button = element('button', 'Compare routes');
            button.type = 'button';
            button.addEventListener('click', () => {
                bridgeSelect.value = project.scenario;
                showBridgeSelection();
                bridgeSelect.focus();
            });
            result.append(document.createElement('br'), button);
        }
        row.append(budgetCell(project.title, project.url), element('td', project.region));
        if (kind === 'bridge') row.append(element('td', project.bridgeId || '—'));
        row.append(element('td', pesos(project.amount)), result);
        return row;
    }));
}

bridgeSelect.addEventListener('change', showBridgeSelection);
bridgeOrigin.addEventListener('change', redrawOtherBridge);
window.addEventListener('resize', redrawOtherBridge);

async function loadRouteScenarios(kind, label) {
    const research = document.getElementById(kind + '-research');
    const filter = document.getElementById(kind + '-filter');
    research.addEventListener('toggle', () => showRouteInventory(kind));
    document.getElementById(kind + '-search').addEventListener('input', () => showRouteInventory(kind));
    filter.addEventListener('change', () => showRouteInventory(kind));
    try {
        const response = await fetch(kind + '-hospital-routes.json');
        if (!response.ok) throw new Error(String(response.status));
        const data = await response.json();
        const group = element('optgroup');
        group.label = label;
        const scenarios = Object.entries(data.scenarios).sort(([, a], [, b]) => a.name.localeCompare(b.name));
        for (const [id, scenario] of scenarios) {
            routeScenarios.set(id, scenario);
            group.append(new Option(kind === 'bridge' ? `${scenario.name} (${id})` : `${scenario.name} · ${scenario.mode === 'closure' ? 'closure' : 'paving'}`, id));
        }
        bridgeSelect.append(group);
        routeData[kind] = data;
        for (const state of [...new Set(data.projects.map(row => row.status))].sort()) filter.add(new Option(state));
        showRouteInventory(kind);
        return `${number.format(scenarios.length)} ${label.toLowerCase()}`;
    } catch {
        const message = `${label} could not be loaded.`;
        document.getElementById(kind + '-list-count').textContent = message;
        return message;
    }
}

const hospitalRoutes = Promise.all([loadRouteScenarios('bridge', 'Existing bridges'), loadRouteScenarios('road', 'Farm-to-market roads')])
    .then(results => { bridgeCoverage.textContent = results.join(' · '); });

const critiqueSignals = {
    faster: 'Existing drive beats the road benchmark',
    detour: 'Hospital detour adds at most 5 minutes',
    inconsistency: 'Hospital detour models a faster trip',
    paving: 'Modeled paving saves at most 1 minute',
    endpoints: 'Printed coordinates need review',
    uses: 'Shoreline, venue or land-use review',
    connectivity: 'Far from mapped cropland and national road',
};
const critiqueManualFlags = {
    'section2-coordinate-quality': 'Reviewer flagged the printed coordinates for checking.',
    'baywalk-shoreline-review': 'The title identifies a baywalk. Check which farms it serves and review the shoreline design.',
    'section2-visitor-venue': 'The review found a mapped visitor venue nearby. Check whether the route also serves farms and where it connects to the road network.',
    'section2-private-property-cue': 'The map review found a possible private-site connection. Check public access and the farms served.',
};
const critiqueProjects = [];
const fmrHouseSchedule = 'https://budget-assets.bettergov.ph/hgab/2027/pdf/hb10858-3r-vol-ib.pdf';
const fmrBudgetEntry = row => ({
    id: row.id, title: row.title, region: row.region, amount: row.amountPesos,
    url: fmrHouseSchedule + '#page=' + row.sourcePage,
});
let facilityProjects = [];
const critiqueFilter = document.querySelector('#critique-filter');
const critiqueSearch = document.querySelector('#critique-search');
const critiqueDirection = document.querySelector('#critique-direction');
const critiqueFacility = document.querySelector('#critique-facility');
const facilityLabels = {school: 'Schools', hospital: 'Hospitals', evacuation: 'Possible evacuation sites'};
let assessedFacilities;
let facilitiesByProject;
let critiqueExample;

function recordCritique(raw, status, note) {
    let entry = critiqueProjects.find(item => item.id === raw.id);
    if (!entry) {
        entry = {...raw, notes: new Map()};
        critiqueProjects.push(entry);
    }
    if (raw.scenario) entry.scenario = raw.scenario;
    const notes = entry.notes.get(status) || [];
    entry.notes.set(status, [...notes, note]);
    return entry;
}

function readCritiqueRoads(rows, alternatives) {
    for (const row of rows) {
        const project = fmrBudgetEntry(row);
        const alternative = alternatives[row.id];
        if (alternative) {
            const best = alternative.routes.reduce((a, b) => a.existingMinutes < b.existingMinutes ? a : b);
            const entry = recordCritique(project, 'faster',
                `${best.direction} takes ${detourMinutes(best.existingMinutes)} on mapped roads. The straight-line benchmark at 30 km/h is ${detourMinutes(alternative.benchmarkMinutes)}. ${alternative.routes.length === 2 ? 'Both directions beat the benchmark.' : 'Only this direction passed the faster-route screen.'}`);
            entry.alternative = alternative;
            entry.endpoints = [[row.startLatitude, row.startLongitude], [row.endLatitude, row.endLongitude]];
        }
        if (row.coordinateQualityFlag) {
            recordCritique(project, 'endpoints',
                `The printed endpoints are ${distance(row.coordinateGapMeters / 1000)} apart. Verify the coordinates before assessing the corridor.`);
        } else if (row.coordinateBasis === 'Single coordinate; no route line') {
            recordCritique(project, 'endpoints', 'Only one distinct coordinate is available. The route cannot be located from the budget entry.');
        }
        for (const flag of row.manualRedReasons || []) {
            if (flag === 'section2-coordinate-quality' && (row.coordinateQualityFlag || row.coordinateBasis === 'Single coordinate; no route line')) continue;
            const note = critiqueManualFlags[flag];
            if (note) recordCritique(project, flag === 'section2-coordinate-quality' ? 'endpoints' : 'uses', note);
        }
        if (row.coordinateBasis === 'Printed start/end pair' && row.connectivityClass.startsWith('Double Flag FMR') &&
            !row.exemptionReasons.length && !row.manualGreenReasons.length) {
            const cropland = row.farmDistanceMeters === null
                ? 'the cropland screen found no nearby annual cropland' : `the nearer endpoint is ${number.format(row.farmDistanceMeters)} m from mapped annual cropland`;
            recordCritique(project, 'connectivity',
                `The nearer endpoint is ${number.format(row.nearestDistanceMeters)} m from the national road layer. In the cropland layer, ${cropland}. Verify farm and local-road connections on the ground.`);
        }
    }
}

function readCritiqueHospitalRoutes(data) {
    for (const project of data.projects) {
        const scenario = data.scenarios[project.scenario];
        if (!scenario?.origins.length) continue;
        const paving = scenario.mode === 'paving';
        const changes = scenario.origins.map(routeDelta);
        const faster = paving ? [] : scenario.origins.filter(fasterDetour);
        if (faster.length) {
            const trips = faster.map(trip => `${trip.name} (${detourMinutes(trip.open.minutes)} open, ${detourMinutes(trip.closed.minutes)} via detour)`);
            recordCritique(project, 'inconsistency', `${trips.join(', ')}. Check routing inputs and access restrictions.`);
        }
        if (changes.some(change => change === null)) continue;
        const note = paving ? 'paving' : 'detour';
        const inRange = paving
            ? changes.every(change => change < 0 && change >= -1)
            : changes.every(change => change >= 0 && change <= 5);
        if (!inRange) continue;
        const upper = detourMinutes(Math.max(...changes.map(Math.abs)));
        const tripCount = number.format(changes.length);
        recordCritique(project, note, paving
            ? `At most ${upper} saved across ${tripCount} modeled hospital trips, even with the paving speed assumption.`
            : `All ${tripCount} sampled hospital trips have a mapped detour. The largest added time is ${upper}.`);
    }
}

function drawCritiqueExample() {
    if (!critiqueExample) return;
    const {alternative, endpoints} = critiqueExample;
    const route = alternative.routes[Number(critiqueDirection.value)];
    const points = route.direction === 'End to start' ? [...endpoints].reverse() : endpoints;
    const example = {open: {points: [points[0], ...route.points, points[1]]}, closed: null,
        point: points[0], hospital: points[1]};
    drawDetour(document.querySelector('#critique-map'), example, [points], 'open', true, 'End');
    drawQuestionBars('critique-example-chart', [
        ['Existing mapped road', route.existingMinutes], ['Straight line at 30 km/h', alternative.benchmarkMinutes],
    ], ' min');
    document.querySelector('#critique-example-detail').textContent =
        `${route.direction} · ${distance(route.existingKm)} on the mapped route. ${detourMinutes(alternative.benchmarkMinutes - route.existingMinutes)} faster than the straight-line benchmark.`;
}

function selectCritiqueExample(project) {
    critiqueExample = project;
    document.querySelector('#critique-example').hidden = false;
    document.querySelector('#critique-example-title').textContent = project.title;
    document.querySelector('#critique-example-source').href = project.url;
    critiqueDirection.replaceChildren(...project.alternative.routes.map((route, i) => new Option(route.direction, i)));
    drawCritiqueExample();
}

function critiqueFacilities(project) {
    const cell = document.createElement('td');
    if (!assessedFacilities) {
        cell.textContent = 'Facility data unavailable';
        return cell;
    }
    if (!assessedFacilities.has(project.id)) {
        cell.textContent = 'No usable alignment for the facility check';
        return cell;
    }
    const facilities = facilitiesByProject[project.id];
    if (!facilities) {
        cell.textContent = 'No mapped match within 500 m';
        return cell;
    }
    for (const [kind, {count, nearest}] of Object.entries(facilities)) {
        cell.append(element('strong', `${facilityLabels[kind]} (${number.format(count)})`));
        const list = document.createElement('ul');
        for (const {name, meters, point: [lat, lon]} of nearest) {
            const item = document.createElement('li');
            const link = element('a', name);
            link.href = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`;
            item.append(link, ` · ${number.format(meters)} m`);
            list.append(item);
        }
        cell.append(list);
    }
    return cell;
}

function renderCritiqueProjects() {
    const filter = critiqueFilter.value;
    const term = critiqueSearch.value.trim().toLowerCase();
    const facility = critiqueFacility.value;
    const candidates = facility && !filter ? facilityProjects : critiqueProjects;
    const items = candidates.filter(row => (!filter || row.notes.has(filter)) &&
        (!facility || facilitiesByProject?.[row.id]?.[facility]) &&
        (!term || [row.title, row.region, row.bridgeId].join(' ').toLowerCase().includes(term)));
    const scope = facility && !filter ? 'matching projects, including rows without a review signal' : 'projects in view';
    document.querySelector('#critique-count').textContent = `${number.format(items.length)} ${scope}`;
    document.querySelector('#critique-rows').replaceChildren(...items.map(project => {
        const row = document.createElement('tr');
        const reason = element('td', '');
        if (!project.notes.size) reason.textContent = 'No signal from these checks';
        for (const [key, notes] of project.notes) {
            const label = element('strong', critiqueSignals[key]);
            reason.append(label, element('p', notes.join(' ')));
        }
        if (project.alternative) {
            const button = element('button', 'View existing route');
            button.type = 'button';
            button.addEventListener('click', () => {
                selectCritiqueExample(project);
                critiqueDirection.focus();
            });
            reason.append(button);
        }
        if (routeScenarios.has(project.scenario)) {
            const button = element('button', 'Compare hospital trips');
            button.type = 'button';
            button.addEventListener('click', () => {
                bridgeSelect.value = project.scenario;
                showBridgeSelection();
                bridgeSelect.focus();
            });
            reason.append(button);
        }
        row.append(budgetCell(project.title, project.url), element('td', pesos(project.amount)), reason, critiqueFacilities(project));
        return row;
    }));
}

critiqueFilter.addEventListener('change', renderCritiqueProjects);
critiqueSearch.addEventListener('input', renderCritiqueProjects);
critiqueFacility.addEventListener('change', renderCritiqueProjects);
critiqueDirection.addEventListener('change', drawCritiqueExample);
window.addEventListener('resize', drawCritiqueExample);

async function fetchCritiqueData(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
}

Promise.allSettled([
    readConnectivityData(), fetchCritiqueData('fmr-route-alternatives.json'), hospitalRoutes,
    fetchCritiqueData('amendment-access-facilities.json'),
]).then(([roads, alternatives, , facilities]) => {
    if (facilities.status === 'fulfilled') {
        assessedFacilities = new Set(facilities.value.assessed);
        facilitiesByProject = facilities.value.results;
        critiqueFacility.disabled = false;
    }
    if (roads.status === 'fulfilled') {
        readCritiqueRoads(roads.value.projects, alternatives.value?.results || {});
    }
    for (const data of Object.values(routeData)) readCritiqueHospitalRoutes(data);
    critiqueProjects.sort((a, b) => Number(Boolean(b.alternative)) - Number(Boolean(a.alternative)) ||
        Number(b.notes.has('detour')) - Number(a.notes.has('detour')) || b.amount - a.amount);
    if (facilitiesByProject) {
        const flagged = new Set(critiqueProjects.map(project => project.id));
        const allProjects = [
            ...(roads.value?.projects || []).map(fmrBudgetEntry), ...(routeData.bridge?.projects || []),
        ];
        facilityProjects = [
            ...critiqueProjects,
            ...allProjects.filter(project => !flagged.has(project.id) && facilitiesByProject[project.id])
                .map(project => ({...project, notes: new Map()})),
        ];
    }
    const insights = Object.entries(critiqueSignals).map(([key, label]) => {
        critiqueFilter.add(new Option(label, key));
        return [label, critiqueProjects.filter(row => row.notes.has(key)).length];
    });
    drawQuestionBars('critique-chart', insights);
    document.querySelector('#critique-figure').hidden = false;
    const message = alternatives.status === 'fulfilled'
        ? `${number.format(alternatives.value.screened)} farm-to-market road endpoint pairs screened. `
        : 'The existing-drive comparisons could not be loaded. ';
    document.querySelector('#critique-status').textContent =
        message + `${number.format(critiqueProjects.length)} bridge or road projects with a review signal.` +
        (roads.status === 'rejected' ? ' The FMR location flags could not be loaded.' : '') +
        (!routeData.bridge || !routeData.road ? ' Some hospital-route results could not be loaded.' : '') +
        (facilities.status === 'rejected' ? ' The MPB facility data could not be loaded.' : '');
    const example = critiqueProjects.find(project => project.alternative);
    if (example) selectCritiqueExample(example);
    renderCritiqueProjects();
});

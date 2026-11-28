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
    document.querySelector('#covered').textContent = `${rows.length} barangays`;
    document.querySelector('#population').textContent = `${number.format(population)} residents`;
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
    .catch(() => { status.textContent = 'The route data could not be loaded. Reload the page to try again.'; });

const national = document.querySelector('#national-fmrs');
const serviceFilter = document.querySelector('#service-filter');
let nationalData;
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
        const response = await fetch('connectivity-data.json');
        if (!response.ok) throw new Error(String(response.status));
        nationalData = await response.json();
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
const bridgeResearch = document.querySelector('#bridge-research');
const bridgeCoverage = document.querySelector('#bridge-coverage');
let bridgeData;
const detourMinutes = value => number.format(Math.round(Math.max(0, value) * 10) / 10) + ' min';

function drawDetour(canvas, trip, span, mode) {
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
    for (const points of span) paint(points, mode === 'closed' ? '#a13721' : '#08746c', 5, mode === 'closed' ? [4, 3] : []);
    for (const [point, label] of [[trip.point, 'Start'], [trip.hospital, 'Hospital']]) {
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
    const scenario = bridgeData?.scenarios[bridgeSelect.value];
    if (!scenario) return;
    const trip = scenario.origins[bridgeOrigin.value];
    if (!trip) return;
    const result = trip.closed
        ? `with a ${detourMinutes(trip.closed.minutes - trip.open.minutes)} detour if the bridge closes`
        : 'with no alternate road route found in the modeled window';
    document.querySelector('#bridge-route-status').textContent =
        `${trip.name} to ${trip.hospitalName} · ${detourMinutes(trip.open.minutes)} with the bridge open, ${result}.`;
    for (const mode of ['open', 'closed']) drawDetour(document.querySelector(`#${mode}-map`), trip, scenario.span, mode);
}

function showBridgeSelection() {
    const scenario = bridgeData?.scenarios[bridgeSelect.value];
    document.querySelector('#bolinao-routes').hidden = Boolean(scenario);
    document.querySelector('#other-bridge-routes').hidden = !scenario;
    if (!scenario) {
        window.dispatchEvent(new Event('resize'));
        return;
    }
    bridgeOrigin.replaceChildren(...scenario.origins.map((row, i) => new Option(row.name, i)));
    const chart = scenario.origins.filter(trip => trip.closed)
        .map(trip => [trip.name, Math.max(0, trip.closed.minutes - trip.open.minutes)]);
    document.querySelector('#detour-chart').closest('figure').hidden = !chart.length;
    if (chart.length) drawQuestionBars('detour-chart', chart, ' min');
    document.querySelector('#mapped-span').href = `https://www.openstreetmap.org/way/${scenario.bridgeWay}`;
    document.querySelector('#bridge-route-comparison').replaceChildren(...scenario.origins.map(trip => {
        const row = document.createElement('tr');
        row.append(element('th', trip.name), element('td', trip.hospitalName), element('td', detourMinutes(trip.open.minutes)),
            element('td', trip.closed ? detourMinutes(trip.closed.minutes) : 'No local detour found'),
            element('td', trip.closed ? detourMinutes(trip.closed.minutes - trip.open.minutes) : '—'));
        return row;
    }));
    redrawOtherBridge();
}

function showBridgeInventory() {
    if (!bridgeData || !bridgeResearch.open) return;
    const term = document.querySelector('#bridge-search').value.trim().toLowerCase();
    const filter = document.querySelector('#bridge-filter').value;
    const projects = bridgeData.projects.filter(row => (!filter || filter === row.status) &&
        (!term || [row.title, row.region, row.bridgeId].join(' ').toLowerCase().includes(term)));
    document.querySelector('#bridge-list-count').textContent = `${number.format(projects.length)} budget lines`;
    document.querySelector('#bridge-inventory').replaceChildren(...projects.map(project => {
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
        row.append(budgetCell(project.title, project.url), element('td', project.region),
            element('td', project.bridgeId || '—'), element('td', pesos(project.amount)), result);
        return row;
    }));
}

bridgeSelect.addEventListener('change', showBridgeSelection);
bridgeOrigin.addEventListener('change', redrawOtherBridge);
window.addEventListener('resize', redrawOtherBridge);
bridgeResearch.addEventListener('toggle', showBridgeInventory);
document.querySelector('#bridge-search').addEventListener('input', showBridgeInventory);
document.querySelector('#bridge-filter').addEventListener('change', showBridgeInventory);
fetch('bridge-hospital-routes.json').then(response => {
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
}).then(data => {
    bridgeData = data;
    const scenarios = Object.entries(data.scenarios).sort(([, a], [, b]) => a.name.localeCompare(b.name));
    for (const [id, scenario] of scenarios) bridgeSelect.add(new Option(`${scenario.name} (${id})`, id));
    const filter = document.querySelector('#bridge-filter');
    for (const state of [...new Set(data.projects.map(row => row.status))].sort()) filter.add(new Option(state));
    bridgeCoverage.textContent =
        `${number.format(scenarios.length)} existing bridges have modeled hospital routes with the span open and closed, in addition to the Bolinao proposal. The nationwide screen covers ${number.format(data.projects.length)} House budget lines.`;
    showBridgeInventory();
}).catch(() => { bridgeCoverage.textContent = 'The nationwide bridge screen could not be loaded.'; });

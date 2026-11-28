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

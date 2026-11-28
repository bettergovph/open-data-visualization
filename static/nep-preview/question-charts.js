'use strict';

function drawQuestionBars(id, entries, unit = '') {
    const container = document.getElementById(id);
    const max = Math.max(1, ...entries.map(([, value]) => value));
    const rows = entries.map(([label, value]) => {
        const row = document.createElement('div');
        row.className = 'answer-bar';
        const name = document.createElement('span');
        name.textContent = label;
        const bar = document.createElement('i');
        bar.style.width = (100 * value / max) + '%';
        bar.setAttribute('aria-hidden', 'true');
        const count = document.createElement('strong');
        count.textContent = value.toLocaleString('en-PH', {maximumFractionDigits: container.id === 'hearing-budget-chart' ? 3 : 1}) + unit;
        row.append(name, bar, count);
        return row;
    });
    container.replaceChildren(...rows);
}

for (const chart of document.querySelectorAll('[data-bars]')) {
    drawQuestionBars(chart.id, JSON.parse(chart.dataset.bars));
}

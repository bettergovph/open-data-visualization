function renderRankingTable() {
    const tbody = document.getElementById('rankingTableBody');
    tbody.innerHTML = '';

    // Sort
    globalMatrixData.sort((a, b) => {
        let valA, valB;
        if (sortKey === 'rank') {
            // Default Sort: Count Desc, then Amount Desc
            if (a.project_count !== b.project_count) return a.project_count - b.project_count;
            return a.total_amount - b.total_amount;
        }

        if (sortKey === 'congressman') {
            valA = a.congressman.toLowerCase();
            valB = b.congressman.toLowerCase();
            return sortDesc ? valB.localeCompare(valA) : valA.localeCompare(valB);
        } else {
            valA = a[sortKey];
            valB = b[sortKey];
            return sortDesc ? valB - valA : valA - valB;
        }
    });

    // Fix "Rank" handling: if sorting by Rank, we revert to default high-priority sort
    if (sortKey === 'rank') {
        // Default Sort: Count Desc, then Amount Desc
        globalMatrixData.sort((a, b) => {
            if (b.project_count !== a.project_count) return b.project_count - a.project_count;
            return b.total_amount - a.total_amount;
        });
        if (!sortDesc) globalMatrixData.reverse();
    }

    // Update Headers
    ['rank', 'congressman', 'project_count', 'total_amount'].forEach(k => {
        const el = document.getElementById(`sort-${k}`);
        if (k === sortKey) {
            el.textContent = sortDesc ? '↓' : '↑';
            el.classList.remove('opacity-0');
        } else {
            el.classList.add('opacity-0');
        }
    });

    globalMatrixData.forEach((item, index) => {
        const row = document.createElement('tr');
        row.className = "hover:bg-slate-50 transition-colors group";

        const projectsPreview = item.projects.slice(0, 3).map(p =>
            `<div class="text-xs truncate max-w-xs text-slate-600 mb-1" title="${p.name}">• ${p.name}</div>`
        ).join('');

        const moreCount = item.projects.length - 3;
        const moreTag = moreCount > 0 ?
            `<button onclick="openProjectModal(${index})" class="text-xs text-indigo-500 font-medium hover:text-indigo-700 hover:underline focus:outline-none transition-colors">+${moreCount} more</button>`
            : '';

        row.innerHTML = `
                    <td class="px-6 py-4 text-slate-400 font-mono text-sm">#${index + 1}</td>
                    <td class="px-6 py-4">
                        <div class="font-bold text-slate-800">${item.congressman}</div>
                        <div class="text-xs text-slate-500 bg-slate-100 inline-block px-2 py-0.5 rounded mt-1">${item.district}
                            ${item.province && item.province !== 'Unknown' ? `<span class="text-slate-400 mx-1">•</span>${item.province}` : ''}
                        </div>
                    </td>
                    <td class="px-6 py-4 text-right font-medium text-slate-700">${item.project_count}</td>
                    <td class="px-6 py-4 text-right font-mono text-slate-700">₱ ${(item.total_amount / 1e6).toFixed(1)} M</td>
                    <td class="px-6 py-4">
                        ${projectsPreview}
                        ${moreTag}
                    </td>
                `;
        tbody.appendChild(row);
    });
}

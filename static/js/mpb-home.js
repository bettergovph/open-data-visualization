(() => {
    const list = document.getElementById('mpb-story-list');
    if (!list) return;
    const researchBase = 'https://research.bettergov.ph/static/nep-preview/';

    const chartPlans = [
        { title: 'First-time and returning recipient barangays', note: 'FY2027 recipient barangays, classified by whether an earlier MPB record was found.', href: '/static/nep-preview/mpb.html#fy2027-mpb-history', link: 'Review FY2027 recipient history', chart: (d) => waffle(d.recipientBarangays2027, [['Returning','#0038A8'],['First-time','#FCD116']]) },
        { title: 'How many FY2027 rows meet the document threshold?', note: 'Distribution by matched document types. Complete means at least four of five named types were matched to the project row.', href: '/static/nep-preview/mpb.html#fy2027-mpb-documents', link: 'Review document coverage', chart: (d) => documentDistribution(d.documents2027) },
        { title: 'How many 2027 recipient barangays have multiple project titles?', note: 'The title match count is a record comparison; multiple titles do not necessarily mean multiple completed buildings.', href: '/static/nep-preview/mpb-barangay.html', link: 'Explore barangay records', chart: (d) => donut(d.coverage2027.barangaysWithOneTitle,d.coverage2027.barangaysWithMultipleTitles,'one title','multiple titles') },
        { title: 'Historical records across all official barangays', note: 'Each bar counts barangays with exactly that many distinct MPB title matches from FY2015–FY2026. No mapped match does not establish that a barangay has no building or received no funding.', href: '/static/nep-preview/mpb-regional-province.html', link: 'Explore historical distribution', chart: (d) => historicalMultiplicityChart(d.historicalMultiplicity) },
        { title: 'Poverty and allocation per barangay', note: 'Each dot is a province. The line is a descriptive linear fit; it does not show that poverty determines allocations.', href: '/static/nep-preview/mpb-regional-province.html', link: 'Review the poverty comparison and methods', chart: (d) => scatter(d.provincePovertyPoints) },
        { title: 'Top, middle and bottom provinces by poverty incidence', note: 'Ranked by 2023 poverty incidence among families. Allocation per official barangay is shown beside poverty on a consistent province-wide scale; row counts and total mapped allocations remain context.', href: '/static/nep-preview/mpb-regional-province.html', link: 'Explore all province rankings and methods', chart: (d) => provinceRankings(d.provincePovertyPoints) },
        { title: 'MPB records and public schools by region', note: 'Each tile shows public-school records relative to MPB project rows in that region. These are regional totals, not matched projects and schools.', href: '/static/nep-preview/education-health.html#data-coverage', link: 'Review school coverage and counts', chart: (d) => regionalTiles(d.educationRows,'depedPublicSchoolCount','schools per 100 MPB rows') },
        { title: 'Reported hospital beds relative to MPB records', note: 'Each dot is a region; the vertical position compares reported government hospital beds with MPB project rows. This does not match projects to hospitals or beds.', href: '/static/nep-preview/education-health.html#data-coverage', link: 'Review hospital and bed coverage', chart: (d) => regionScatter(d.educationRows,'philhealthGovernmentHospitalBeds','Reported hospital beds') }
    ];

    const fmt = (n) => Number(n || 0).toLocaleString('en-PH');
    const peso = (n) => '₱' + Number(n || 0).toLocaleString('en-PH', { maximumFractionDigits: 0 });
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const svgWrap = (content, label, viewBox = '0 0 680 250') => `<svg viewBox="${viewBox}" role="img" aria-label="${esc(label)}" xmlns="http://www.w3.org/2000/svg">${content}</svg>`;

    function bars(rows, total) {
        const max = Math.max(...rows.map((r) => Number(r[1] || 0)), 1);
        return `<div class="chart-bars">${rows.map(([label, value, color]) => `<div class="bar-row"><span class="bar-label">${esc(label)}</span><span class="bar-track" role="img" aria-label="${esc(label)}: ${fmt(value)}"><i class="bar-fill ${color || ''}" style="width:${Math.max(1, 100 * Number(value || 0) / max)}%"></i></span><span class="bar-value">${fmt(value)}</span></div>`).join('')}</div><div class="chart-legend"><span>Total: ${fmt(total)}</span></div>`;
    }

    function stacked(rows, total) {
        const pct = rows.map((r) => 100 * Number(r[1] || 0) / total);
        return `<div class="callout-stat"><strong>${pct[0].toFixed(1)}%</strong><span>of FY2027 project rows meet the document threshold</span></div><div class="bar-track" role="img" aria-label="${fmt(rows[0][1])} complete and ${fmt(rows[1][1])} incomplete of ${fmt(total)} project rows"><i class="bar-fill" style="width:${pct[0]}%"></i><i class="bar-fill gold" style="width:${pct[1]}%"></i></div><div class="chart-legend"><span><i class="legend-dot"></i>${esc(rows[0][0])}: ${fmt(rows[0][1])} (${pct[0].toFixed(1)}%)</span><span><i class="legend-dot gold"></i>${esc(rows[1][0])}: ${fmt(rows[1][1])} (${pct[1].toFixed(1)}%)</span><span>Total: ${fmt(total)}</span></div>`;
    }

    function waffle(data, groups) {
        const total=Number(data.total)||1, first=Math.round(100*Number(data.returning)/total), cells=Array.from({length:100},(_,i)=>`<rect x="${(i%10)*19}" y="${Math.floor(i/10)*19}" width="15" height="15" rx="3" fill="${i<first?groups[0][1]:groups[1][1]}"/>`).join('');
        return `<div class="callout-stat"><strong>${(100*data.returning/total).toFixed(1)}%</strong><span>of recipient barangays had an earlier MPB record</span></div>${svgWrap(cells,'100 squares showing the share of returning and first-time recipient barangays','0 0 205 190')}<div class="chart-legend"><span><i class="legend-dot"></i>Returning ${fmt(data.returning)}</span><span><i class="legend-dot gold"></i>First-time ${fmt(data.firstTime)}</span><span>Total ${fmt(data.total)}</span></div>`;
    }
    function documentDistribution(d) {
        const rows=d.countsByMatchedTypeCount||[], max=Math.max(...rows.map(x=>Number(x.projectRows||x.rows||x.count||0)),1), vals=rows.map(x=>Number(x.projectRows||x.rows||x.count||0));
        const W=500,H=210,L=38,B=38,T=12, step=(W-L-12)/Math.max(rows.length,1), bars=rows.map((x,i)=>{const n=vals[i],h=(H-T-B)*n/max, label=x.matchedTypeCount??x.count??i;return `<rect x="${L+i*step+8}" y="${H-B-h}" width="${step-16}" height="${h}" rx="4" fill="${Number(label)>=4?'#0038A8':'#FCD116'}"><title>${label} matched types: ${fmt(n)} rows</title></rect><text x="${L+i*step+step/2}" y="${H-B+17}" text-anchor="middle" fill="#46564c" font-size="12">${label}</text>`}).join('');
        return `<div class="chart-legend"><span>Rows by number of the 5 document types matched</span><span>Threshold: 4 or 5 types</span></div>${svgWrap(`<line x1="${L}" y1="${H-B}" x2="${W}" y2="${H-B}" stroke="#89968d"/>${bars}`,'Distribution of FY2027 rows by number of matched document types',`0 0 ${W} ${H}`)}<div class="chart-legend"><span>${fmt(d.completeDocumentProjectRows)} rows meet threshold · ${Number(d.completeDocumentProjectRowsPct).toFixed(1)}%</span><span>${fmt(d.denominatorProjectRows)} rows assessed</span></div>`;
    }
    function donut(a,b,labelA,labelB) {
        const total=Number(a)+Number(b)||1, pct=Number(a)/total, r=58,c=2*Math.PI*r, dash=c*pct;
        return `<div class="donut-wrap">${svgWrap(`<circle cx="100" cy="100" r="${r}" fill="none" stroke="#FCD116" stroke-width="22"/><circle cx="100" cy="100" r="${r}" fill="none" stroke="#0038A8" stroke-width="22" stroke-dasharray="${dash} ${c-dash}" transform="rotate(-90 100 100)"/><text x="100" y="96" text-anchor="middle" fill="#0038A8" font-size="22" font-weight="700">${fmt(total)}</text><text x="100" y="116" text-anchor="middle" fill="#647268" font-size="11">recipient</text>`,'One-title and multiple-title barangays','0 0 200 200')}${svgWrap(`<text x="0" y="22" fill="#0038A8" font-size="13" font-weight="700">${fmt(a)} · ${labelA}</text><text x="0" y="52" fill="#647268" font-size="12">${(pct*100).toFixed(1)}% of recipients</text><text x="0" y="104" fill="#8b6800" font-size="13" font-weight="700">${fmt(b)} · ${labelB}</text><text x="0" y="134" fill="#647268" font-size="12">${((1-pct)*100).toFixed(1)}% of recipients</text>`,'Title multiplicity labels','0 0 210 160')}</div>`;
    }
    function historicalMultiplicityChart(d) {
        if (!d || !d.counts) return '<p>Exact historical repeat counts are unavailable.</p>';
        const W=680,H=260,L=58,R=12,T=24,B=48, total=Number(d.officialBarangays)||1;
        const bins=['0','1','2','3','4','5','6','7','8','9+'];
        const vals=bins.map(k=>Number(d.counts[k]||0));
        const max=Math.max(...vals,1), scale=v=>Math.log1p(v)/Math.log1p(max);
        const step=(W-L-R)/bins.length, bw=step*.56, base=H-B, plotH=H-T-B;
        let content='';
        [1,10,100,1000,10000].forEach(v=>{const y=base-scale(v)*plotH;if(y>=T-1)content+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="#E0E6DF"/><text x="${L-8}" y="${y+3}" text-anchor="end" fill="#647268" font-size="10">${v.toLocaleString('en-PH')}</text>`;});
        content+=`<line x1="${L}" y1="${T}" x2="${L}" y2="${base}" stroke="#89968D"/><line x1="${L}" y1="${base}" x2="${W-R}" y2="${base}" stroke="#89968D"/>`;
        bins.forEach((bin,i)=>{const value=vals[i],height=scale(value)*plotH,x=L+i*step+(step-bw)/2,y=base-height,color=bin==='0'?'#AAB6C8':bin==='9+'?'#B58600':'#0038A8';content+=`<rect x="${x}" y="${y}" width="${bw}" height="${height}" rx="3" fill="${color}"><title>${bin} matches: ${fmt(value)} barangays</title></rect><text x="${x+bw/2}" y="${Math.max(T-7,y-5)}" text-anchor="middle" fill="#344054" font-size="9">${fmt(value)}</text><text x="${x+bw/2}" y="${base+18}" text-anchor="middle" fill="#46564C" font-size="11">${bin}</text>`;});
        content+=`<text x="${(L+W-R)/2}" y="${H-8}" text-anchor="middle" fill="#46564c" font-size="11">Distinct historical title matches per barangay · ${esc(d.period)}</text>`;
        return svgWrap(content,'Number of barangays by exact count of historical MPB title matches; vertical axis is logarithmic',`0 0 ${W} ${H}`)+`<div class="chart-legend"><span>Log scale · exact counts shown above bars</span><span>9+ is the only overflow category</span><span>${fmt(total)} official barangays</span></div>`;
    }
    function regionalTiles(rows,key,caption) {
        const data=(rows||[]).filter(x=>x.level==='region'&&Number(x.mpbRows)>0).map(x=>({...x,rate:100*Number(x[key]||0)/Number(x.mpbRows)})).sort((a,b)=>b.rate-a.rate), max=Math.max(...data.map(x=>x.rate),1);
        return `<div class="tile-grid">${data.map(x=>`<div class="region-tile" style="--tile:${(0.15+.85*x.rate/max).toFixed(2)}" title="${esc(x.name)}: ${x.rate.toFixed(1)} schools per 100 MPB rows"><b>${esc(x.region.replace(/ Region|Administrative Region| Region \(.*\)/g,''))}</b><strong>${x.rate.toFixed(1)}</strong></div>`).join('')}</div><div class="chart-legend"><span>${caption}</span><span>Color intensity scales to the highest regional rate</span></div>`;
    }
    function regionScatter(rows,key,label) {
        const data=(rows||[]).filter(x=>x.level==='region'&&Number(x.mpbRows)>0&&Number(x[key])>0), xmax=Math.max(...data.map(x=>x.mpbRows),1),ymax=Math.max(...data.map(x=>x[key]),1), W=500,H=240,L=48,R=14,T=14,B=40;
        const pts=data.map(x=>{const cx=L+x.mpbRows/xmax*(W-L-R),cy=T+(1-x[key]/ymax)*(H-T-B);return `<circle cx="${cx}" cy="${cy}" r="4"><title>${esc(x.region)} · ${fmt(x.mpbRows)} MPB rows · ${fmt(x[key])} ${label.toLowerCase()}</title></circle>`}).join('');
        return svgWrap(`<line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" stroke="#89968d"/><line x1="${L}" y1="${T}" x2="${L}" y2="${H-B}" stroke="#89968d"/>${pts}<text x="${W/2}" y="${H-8}" text-anchor="middle" fill="#46564c" font-size="12">MPB project rows</text><text transform="translate(14 ${H/2}) rotate(-90)" text-anchor="middle" fill="#46564c" font-size="12">${esc(label)}</text>`,'Regional MPB project rows compared with reported hospital beds',`0 0 ${W} ${H}`);
    }

    function scatter(points) {
        const rows = points.filter((p) => p.povertyPct != null && p.allocationPerBarangayPesos != null && Number.isFinite(Number(p.povertyPct)) && Number.isFinite(Number(p.allocationPerBarangayPesos)));
        if (!rows.length) return '<p>Province comparison data is unavailable.</p>';
        const W = 680, H = 330, L = 68, R = 20, T = 18, B = 58;
        const xMax = Math.max(40, Math.ceil(Math.max(...rows.map((p) => Number(p.povertyPct))) / 10) * 10);
        const yMax = Math.ceil(Math.max(...rows.map((p) => Number(p.allocationPerBarangayPesos))) / 5000000) * 5000000;
        const X = (v) => L + (Number(v) / xMax) * (W - L - R);
        const Y = (v) => T + (1 - Number(v) / yMax) * (H - T - B);
        const meanX = rows.reduce((a, p) => a + Number(p.povertyPct), 0) / rows.length;
        const meanY = rows.reduce((a, p) => a + Number(p.allocationPerBarangayPesos), 0) / rows.length;
        const slope = rows.reduce((a, p) => a + (Number(p.povertyPct) - meanX) * (Number(p.allocationPerBarangayPesos) - meanY), 0) / Math.max(1, rows.reduce((a, p) => a + (Number(p.povertyPct) - meanX) ** 2, 0));
        const line = (x) => meanY + slope * (x - meanX);
        let content = '';
        for (let i = 0; i <= 4; i++) {
            const val = yMax * i / 4, y = Y(val);
            content += `<line x1="${L}" y1="${y}" x2="${W - R}" y2="${y}" stroke="#e0e6df"/><text x="${L - 8}" y="${y + 4}" text-anchor="end" fill="#647268" font-size="11">₱${(val / 1000000).toFixed(0)}m</text>`;
        }
        content += `<line x1="${L}" y1="${T}" x2="${L}" y2="${H - B}" stroke="#89968d"/><line x1="${L}" y1="${H - B}" x2="${W - R}" y2="${H - B}" stroke="#89968d"/>`;
        content += `<line x1="${X(0)}" y1="${Y(line(0))}" x2="${X(xMax)}" y2="${Y(line(xMax))}" stroke="#B58600" stroke-width="2" stroke-dasharray="6 5"/>`;
        for (let i = 0; i <= 4; i++) { const x = xMax * i / 4; content += `<text x="${X(x)}" y="${H - B + 20}" text-anchor="middle" fill="#647268" font-size="11">${x}%</text>`; }
        content += rows.map((p) => {
            const highlighted = /zamboanga del norte|ilocos norte/i.test(p.region);
            return `<circle cx="${X(p.povertyPct)}" cy="${Y(p.allocationPerBarangayPesos)}" r="${highlighted ? 5 : 3.5}" fill="${highlighted ? '#0038A8' : '#6B8FCC'}" fill-opacity="${highlighted ? '.95' : '.72'}"><title>${esc(p.region)} · ${Number(p.povertyPct).toFixed(1)}% poverty · ${peso(p.allocationPerBarangayPesos)} per barangay</title></circle>`;
        }).join('');
        content += `<text x="${(L + W - R) / 2}" y="${H - 10}" text-anchor="middle" fill="#46564c" font-size="12">2023 poverty incidence among families</text><text transform="translate(17 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle" fill="#46564c" font-size="12">Allocation per official barangay</text>`;
        return svgWrap(content, 'Scatterplot of province poverty incidence and MPB allocation per official barangay', `0 0 ${W} ${H}`) + '<div class="chart-legend"><span><i class="legend-dot"></i>Province · hover over a point for details</span><span><i class="legend-dot gold"></i>Descriptive linear fit</span></div>';
    }

    function provinceRankings(points) {
        const rows = points.filter((p) => p.povertyPct != null && Number.isFinite(Number(p.povertyPct)))
            .sort((a, b) => Number(b.povertyPct) - Number(a.povertyPct));
        if (rows.length < 15) return '<p>Province ranking data is unavailable.</p>';
        const middleStart = Math.floor((rows.length - 5) / 2);
        const maxPoverty = Math.max(...rows.map((p) => Number(p.povertyPct)), 1);
        const densityRows = rows.filter((p) => p.allocationPerBarangayPesos != null && Number.isFinite(Number(p.allocationPerBarangayPesos)));
        const maxDensity = Math.max(...densityRows.map((p) => Number(p.allocationPerBarangayPesos)), 1);
        const densityLabel = (value) => value >= 1000000 ? `₱${(value / 1000000).toFixed(1)}M` : `₱${(value / 1000).toFixed(0)}k`;
        const groups = [
            { title: 'Top 5', detail: 'Ranks 1–5 · highest poverty incidence', rows: rows.slice(0, 5) },
            { title: 'Middle 5', detail: `Ranks ${middleStart + 1}–${middleStart + 5} · centered on the median`, rows: rows.slice(middleStart, middleStart + 5) },
            { title: 'Bottom 5', detail: `Ranks ${rows.length - 4}–${rows.length} · lowest poverty incidence`, rows: rows.slice(-5) }
        ];
        const groupMarkup = groups.map((group) => {
            const firstRank = rows.indexOf(group.rows[0]) + 1;
            return `<section class="province-group"><div class="province-group-heading"><h5>${esc(group.title)}</h5><span>${esc(group.detail)}</span></div><div class="province-pair-head"><span>Province</span><span>Poverty incidence · 0–${maxPoverty.toFixed(1)}%</span><span>Allocation per barangay · 0–${densityLabel(maxDensity)}</span></div>${group.rows.map((p, i) => {
                const poverty = Number(p.povertyPct);
                const allocation = p.allocationPesos == null ? null : Number(p.allocationPesos);
                const compact = allocation == null ? 'Allocation unavailable' : allocation >= 1e9 ? `₱${(allocation / 1e9).toFixed(2)}B` : `₱${(allocation / 1e6).toFixed(0)}M`;
                const projectRows = p.projectRows == null ? 'Rows unavailable' : `${fmt(p.projectRows)} project rows`;
                const density = p.allocationPerBarangayPesos == null ? null : Number(p.allocationPerBarangayPesos);
                const focusProvince = /zamboanga del norte|ilocos norte/i.test(p.region);
                return `<div class="province-rank-row${focusProvince ? ' focus-province' : ''}"><div class="province-place"><strong>${firstRank + i}. ${esc(p.region)}</strong><small>${projectRows} · ${compact} total mapped allocation</small></div><div class="province-measure" role="img" aria-label="${esc(p.region)}: ${poverty.toFixed(1)} percent poverty incidence among families"><strong>${poverty.toFixed(1)}%</strong><span class="bar-track"><i class="bar-fill" style="width:${100 * poverty / maxPoverty}%"></i></span></div><div class="province-measure" role="img" aria-label="${esc(p.region)}: ${density == null ? 'allocation density unavailable' : `${peso(density)} per official barangay`}"><strong>${density == null ? '—' : densityLabel(density)}</strong><span class="bar-track"><i class="bar-fill gold" style="width:${density == null ? 0 : 100 * density / maxDensity}%"></i></span></div></div>`;
            }).join('')}</section>`;
        }).join('');
        const focus = ['Zamboanga Del Norte', 'Ilocos Norte'].map((name) => rows.find((p) => p.region.toLowerCase() === name.toLowerCase())).filter(Boolean);
        const focusMarkup = focus.length === 2 ? `<div class="province-focus"><strong>Provinces in the infographic · 2023 poverty incidence among families</strong><div>${focus.map((p) => `<span><b>${esc(p.region)} · ${Number(p.povertyPct).toFixed(1)}%</b><small>${p.projectRows == null ? 'Rows unavailable' : `${fmt(p.projectRows)} rows`} · ${p.allocationPesos == null ? 'Allocation unavailable' : peso(p.allocationPesos)}</small></span>`).join('')}</div></div>` : '';
        return `<div class="province-groups">${groupMarkup}</div>${focusMarkup}<p class="chart-note">Both bar columns use one shared scale across all 79 provinces within that measure: poverty incidence among families, and mapped MPB allocation per official barangay. Provinces are ranked by poverty incidence; allocation density is a separate comparison. Allocation spans GAA FY2015–FY2026 and proposed FY2027 House Bill, not verified spending.</p>`;
    }

    function ratioChart(a, b, labelA, labelB, type) {
        const ratio = Number(a) / Number(b);
        const max = Math.max(Number(a), Number(b));
        return `<div class="callout-stat"><strong>${ratio.toFixed(2)}×</strong><span>${esc(labelA.toLowerCase())} per ${esc(labelB.toLowerCase().replace(/records?/, 'record').replace(/beds/, 'bed'))}</span></div><div class="chart-bars"><div class="bar-row"><span class="bar-label">${esc(labelA)}</span><span class="bar-track"><i class="bar-fill" style="width:${100 * Number(a) / max}%"></i></span><span class="bar-value">${fmt(a)}</span></div><div class="bar-row"><span class="bar-label">${esc(labelB)}</span><span class="bar-track"><i class="bar-fill gold" style="width:${100 * Number(b) / max}%"></i></span><span class="bar-value">${fmt(b)}</span></div></div><div class="chart-legend"><span>${type === 'school' ? '47,372 of 48,129 public-school records were joined.' : '60,744 beds across 781 joined government hospitals/infirmaries.'}</span></div>`;
    }

    function detailCard(plan, index) {
        return `<article class="story-card"><div class="story-head"><span class="story-number">${String(index + 1).padStart(2, '0')}</span><h3 class="story-title">MPB infographic</h3></div><div class="visual-pair"><section class="visual-cell"><p class="cell-label">The simple picture</p><div class="source-infographic" data-infographic="${index}"></div></section><section class="visual-cell"><p class="cell-label">Explore the detail</p><h4 class="detail-title">${esc(plan.title)}</h4><div class="detail-chart">${plan.chart(window.mpbHomeData)}</div><p class="chart-note">${esc(plan.note)}</p><a class="detail-link" href="${plan.href}">${esc(plan.link)} →</a></section></div></article>`;
    }

    function mountInfographics(sourceHtml) {
        const source = new DOMParser().parseFromString(sourceHtml, 'text/html');
        const panels = Array.from(source.querySelectorAll('section.simple-panel'));
        const styles = Array.from(source.querySelectorAll('head style')).slice(0, 4).map((node) => node.textContent).join('\n');
        const sprite = Array.from(source.querySelectorAll('svg')).find((node) => node.querySelector('defs'));
        if (panels.length < chartPlans.length) throw new Error('The MPB simple page did not contain all eight infographic panels.');
        panels.slice(0, chartPlans.length).forEach((panel, index) => {
            const host = list.querySelector(`[data-infographic="${index}"]`);
            const shadow = host.attachShadow({ mode: 'open' });
            const panelCopy = panel.cloneNode(true);
            const sourceHeading = panelCopy.querySelector('h2');
            if (sourceHeading) sourceHeading.remove();
            panelCopy.querySelectorAll('a[href]').forEach((a) => {
                const href = a.getAttribute('href') || '';
                if (!href || href.startsWith('#') || href.startsWith('/') || /^[a-z]+:/i.test(href)) return;
                a.setAttribute('href', `/static/nep-preview/${href}`);
            });
            shadow.innerHTML = `<style>${styles}:host{display:block;color:#17233b;font-family:Inter,system-ui,sans-serif}section.simple-panel{margin:0!important;box-shadow:none!important;border-radius:10px!important;padding:18px!important}section.simple-panel h2{font-size:clamp(20px,2vw,27px)!important}section.simple-panel .simple-period{font-size:11px!important}</style>${sprite ? sprite.outerHTML : ''}${panelCopy.outerHTML}`;
            const h2 = panel.querySelector('h2');
            const heading = list.querySelectorAll('.story-title')[index];
            if (h2 && heading) heading.textContent = h2.textContent.trim();
        });
    }

    async function init() {
        list.innerHTML = '<p class="load-error" role="status">Loading the MPB infographics and detailed charts…</p>';
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 12000);
        try {
            const [sourceResponse, dataResponse, educationResponse, historyResponse] = await Promise.all([
                fetch(`${researchBase}mpb-simple.html`, { signal: controller.signal, headers: { Accept: 'text/html' } }),
                fetch(`${researchBase}mpb-simple-data.json`, { signal: controller.signal, headers: { Accept: 'application/json' } }),
                fetch(`${researchBase}education-health-data.json`, { signal: controller.signal, headers: { Accept: 'application/json' } }),
                fetch('/static/data/mpb-historical-multiplicity.json', { signal: controller.signal, headers: { Accept: 'application/json' } })
            ]);
            if (!sourceResponse.ok) throw new Error(`The MPB infographic page returned ${sourceResponse.status}.`);
            if (!dataResponse.ok) throw new Error(`The MPB chart data returned ${dataResponse.status}.`);
            if (!educationResponse.ok) throw new Error(`The regional facility data returned ${educationResponse.status}.`);
            if (!historyResponse.ok) throw new Error(`The exact historical counts returned ${historyResponse.status}.`);
            const [sourceHtml, data, education, historicalMultiplicity] = await Promise.all([sourceResponse.text(), dataResponse.json(), educationResponse.json(), historyResponse.json()]);
            if (!sourceHtml || !data) throw new Error('The MPB research source is incomplete.');
            window.mpbHomeData = data;
            data.educationRows = education.geographyRows;
            data.historicalMultiplicity = historicalMultiplicity;
            if (!Array.isArray(data.provincePovertyPoints)) throw new Error('The MPB chart data is incomplete.');
            list.innerHTML = chartPlans.map(detailCard).join('');
            mountInfographics(sourceHtml);
        } catch (error) {
            const message = error.name === 'AbortError' ? 'The MPB research files did not load within 12 seconds.' : error.message;
            list.innerHTML = `<div class="load-error" role="alert"><strong>MPB charts could not load.</strong> ${esc(message)} <a href="https://research.bettergov.ph/static/nep-preview/mpb-simple.html">Open the MPB infographic page</a>.</div>`;
        } finally {
            clearTimeout(timer);
            list.setAttribute('aria-busy', 'false');
        }
    }

    init();
})();

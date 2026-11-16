(() => {
    const list = document.getElementById('mpb-story-list');
    if (!list) return;
    const researchBase = 'https://research.bettergov.ph/static/nep-preview/';

    const chartPlans = [
        { title: 'Among returning recipients, which FY2027 titles repeat?', note: 'Focuses on the 3,225 FY2027 recipient barangays (75.1%) with earlier MPB records. Each bar counts a distinct FY2027 title/barangay match: an earlier title match or a new title in a returning barangay.', href: `${researchBase}mpb.html#fy2027-mpb-history`, link: 'Review FY2027 recipient history', chart: (d) => returningTitleHistory(d.returningRecipientTitleHistory2027) },
        { title: 'How many FY2027 rows have 5 of 5 document types matched?', note: 'Distribution by matched document types. Five of five means a file match for all named types, including POW; it does not verify that the POW contains bill rows.', href: `${researchBase}mpb.html#fy2027-mpb-documents`, link: 'Review document coverage', chart: (d) => documentDistribution(d.documents2027) },
        { title: 'Three views of MPB records across barangays', note: 'Combines the unified page’s top upgrade, Tech Tree score, and total allocation rankings. The chart shows the top 10 barangays in each ranking; open the full tables for filters and project rows.', href: 'https://research.bettergov.ph/static/nep-preview/mpb-barangay.html', link: 'Open the unified barangay tables', chart: (d) => unifiedBarangayChart(d.unifiedBarangayRankings) },
        { title: 'Historical records across all official barangays', note: 'Each bar counts barangays with exactly that many distinct MPB title matches from FY2015–FY2026. No mapped match does not establish that a barangay has no building or received no funding.', href: `${researchBase}mpb-regional-province.html`, link: 'Explore historical distribution', chart: (d) => historicalMultiplicityChart(d.historicalMultiplicity) },
        { title: 'Poverty and allocation per barangay', note: 'Each dot is a province. The line is a descriptive linear fit; it does not show that poverty determines allocations.', href: `${researchBase}mpb-regional-province.html`, link: 'Review the poverty comparison and methods', chart: (d) => scatter(d.provincePovertyPoints) },
        { title: 'Top, middle and bottom provinces by poverty incidence', note: 'This combines the top five, middle five, and bottom five provinces by 2023 poverty incidence into one chart. Poverty and allocation per official barangay use separate vertical scales. Zamboanga del Norte and Ilocos Norte are highlighted; allocations are not spending.', href: `${researchBase}mpb-regional-province.html`, link: 'Explore all province rankings and methods', chart: (d) => provinceRankings(d.provincePovertyPoints) },
        { title: 'MPB records and public schools by region', note: 'Each tile shows public-school records per MPB project row in that region. These are regional totals, not matched projects and schools.', href: `${researchBase}education-health.html#data-coverage`, link: 'Review school coverage and counts', chart: (d) => regionalTiles(d.educationRows,'depedPublicSchoolCount','public schools per MPB row') },
        { title: 'MPB project rows outnumber joined government hospital beds', note: 'Each square shows reported beds and joined hospital records per MPB project row. Values below 1 mean fewer beds or hospital records than MPB rows in that region. These are regional totals, not matched records.', href: `${researchBase}education-health.html#data-coverage`, link: 'Review hospital and bed coverage', chart: (d) => hospitalRegionalTiles(d.educationRows) }
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
    function returningTitleHistory(data) {
        if (!data) return '<p>Returning recipient title history is unavailable.</p>';
        const total=Number(data.totalTitleMatches)||1, repeat=Number(data.repeatTitleMatches)||0, fresh=Number(data.newTitleMatches)||0;
        const repeatSquares=Math.round(40*repeat/total), squares=Array.from({length:40},(_,i)=>`<rect x="${(i%10)*30}" y="${Math.floor(i/10)*30}" width="23" height="23" rx="4" fill="${i<repeatSquares?'#0038A8':'#FCD116'}"/>`).join('');
        return `<div class="chart-legend"><span>${fmt(data.returningBarangays)} returning FY2027 recipient barangays · ${fmt(data.totalTitleMatches)} distinct title/barangay matches</span></div><div class="callout-stat"><strong>${(100*repeat/total).toFixed(1)}%</strong><span>repeat an earlier title</span></div>${svgWrap(squares,'40 squares: 9 blue squares for repeat title matches and 31 yellow squares for new titles in returning barangays','0 0 300 120')}<div class="chart-legend"><span><i class="legend-dot" style="background:#FCD116"></i>New title in a returning barangay · ${fmt(fresh)} (${(100*fresh/total).toFixed(1)}%)</span><span><i class="legend-dot" style="background:#0038A8"></i>Repeat an earlier title · ${fmt(repeat)} (${(100*repeat/total).toFixed(1)}%)</span><span>Total: ${fmt(data.totalTitleMatches)}</span></div><p class="chart-note">A repeated title match identifies the same normalized title in the same barangay across years; it does not establish duplicate scope, construction, or spending.</p>`;
    }
    function documentDistribution(d) {
        const rows=d.countsByMatchedTypeCount||[], max=Math.max(...rows.map(x=>Number(x.projectRows||x.rows||x.count||0)),1), vals=rows.map(x=>Number(x.projectRows||x.rows||x.count||0));
        const colors={0:'#dc3545',1:'#f59e0b',2:'#facc15',3:'#7c3aed',4:'#2563eb',5:'#16a34a'};
        const fiveOfFive=Number(rows.find(x=>Number(x.matchedTypeCount??x.count)===5)?.projectRows||0),total=Number(d.denominatorProjectRows)||0,fiveOfFivePct=total?100*fiveOfFive/total:0;
        const tokenPow=Number(d.tokenPowNoBillRowsWithinFiveOfFive)||0,greenRows=Math.max(0,fiveOfFive-tokenPow);
        const W=500,H=210,L=38,B=38,T=12, step=(W-L-12)/Math.max(rows.length,1), bars=rows.map((x,i)=>{const n=vals[i],h=(H-T-B)*n/max,label=Number(x.matchedTypeCount??x.count??i),xPos=L+i*step+8,width=step-16,y=H-B-h;if(label===5&&tokenPow>0&&n>0){const flaggedH=h*tokenPow/n;return `<rect x="${xPos}" y="${y}" width="${width}" height="${h-flaggedH}" rx="4" fill="${colors[5]}"><title>5 of 5 document types matched: ${fmt(greenRows)} rows not flagged by the Token POW review</title></rect><rect x="${xPos}" y="${H-B-flaggedH}" width="${width}" height="${flaggedH}" rx="4" fill="#dc3545"><title>${fmt(tokenPow)} five-of-five rows flagged: no bill rows recovered in accepted-title parsed POW files</title></rect><text x="${xPos+width/2}" y="${H-B+17}" text-anchor="middle" fill="#46564c" font-size="12">5</text>`}return `<rect x="${xPos}" y="${y}" width="${width}" height="${h}" rx="4" fill="${colors[label]||'#94a3b8'}"><title>${label} of 5 document types matched: ${fmt(n)} rows</title></rect><text x="${xPos+width/2}" y="${H-B+17}" text-anchor="middle" fill="#46564c" font-size="12">${label}</text>`}).join('');
        return `<div class="chart-legend"><span>Rows by number of the 5 document types matched</span></div>${svgWrap(`<line x1="${L}" y1="${H-B}" x2="${W}" y2="${H-B}" stroke="#89968d"/>${bars}`,'Distribution of FY2027 rows by number of matched document types; the five-type bar is split to show Token POW review flags',`0 0 ${W} ${H}`)}<div class="chart-legend"><span>${fmt(fiveOfFive)} rows have 5 of 5 file types matched · ${fiveOfFivePct.toFixed(1)}%</span><span>${fmt(total)} rows assessed</span></div><div class="chart-legend"><span><i class="legend-dot" style="background:${colors[0]}"></i>0</span><span><i class="legend-dot" style="background:${colors[1]}"></i>1</span><span><i class="legend-dot" style="background:${colors[2]}"></i>2</span><span><i class="legend-dot" style="background:${colors[3]}"></i>3</span><span><i class="legend-dot" style="background:${colors[4]}"></i>4</span><span><i class="legend-dot" style="background:${colors[5]}"></i>5 of 5</span></div><div class="chart-legend"><span><i class="legend-dot" style="background:#dc3545"></i>${fmt(tokenPow)} Token POW review flags within the 5-of-5 bar</span></div><p class="chart-pow-note">A matched POW file can still lack bill rows. <a href="${researchBase}pow.html#token-pow-content-review">Review the token-POW content check ↗</a>. The red segment flags rows where every accepted-title parsed POW had zero recovered bill rows; this is a parser-based review flag, not source-PDF confirmation.</p>`;
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
        const data=(rows||[]).filter(x=>x.level==='region'&&Number(x.mpbRows)>0).map(x=>({...x,rate:Number(x[key]||0)/Number(x.mpbRows)})).sort((a,b)=>b.rate-a.rate), max=Math.max(...data.map(x=>x.rate),0.01);
        return `<div class="tile-grid">${data.map(x=>`<div class="region-tile" style="--tile:${(0.15+.85*x.rate/max).toFixed(2)}" title="${esc(x.name)}: ${x.rate.toFixed(2)} public schools per MPB row"><b>${esc(x.region.replace(/ Region|Administrative Region| Region \(.*\)/g,''))}</b><strong>${x.rate.toFixed(2)}</strong></div>`).join('')}</div><div class="chart-legend"><span>${caption}</span><span>Color intensity scales to the highest regional ratio</span></div>`;
    }
    function hospitalRegionalTiles(rows) {
        const data=(rows||[]).filter(x=>x.level==='region'&&Number(x.mpbRows)>0).map(x=>{
            const beds=Number(x.philhealthGovernmentHospitalBeds)||0;
            const hospitals=Number(x.philhealthHealthCounts?.hospitals)||0;
            return {...x,beds,hospitals,bedsPerMPB:beds?beds/Number(x.mpbRows):null,hospitalsPerMPB:hospitals?hospitals/Number(x.mpbRows):null};
        });
        const maxBed=Math.max(0.01,...data.map(x=>x.bedsPerMPB||0)),maxHospital=Math.max(0.01,...data.map(x=>x.hospitalsPerMPB||0));
        const shortName=name=>name.replace(/^Bangsamoro Autonomous Region In Muslim Mindanao \(BARMM\)$/,'BARMM').replace(/^Cordillera Administrative Region$/,'CAR').replace(/^National Capital Region$/,'NCR').replace(/^Negros Island Region$/,'NIR').replace(/ Region.*$/,'').replace(/ Region$/,'');
        const scale=(value,max)=>Math.max(3,100*value/max);
        return `<div class="tile-grid hospital-tile-grid">${data.map(x=>`<div class="hospital-region-tile" title="${esc(x.name)} · ${fmt(x.mpbRows)} MPB rows · ${fmt(x.beds)} reported beds · ${fmt(x.hospitals)} joined hospital records"><b>${esc(shortName(x.region))}</b><div class="hospital-tile-measure" aria-label="Reported beds per MPB row: ${x.bedsPerMPB===null?'no bed data':x.bedsPerMPB.toFixed(3)}"><strong class="bed-ratio-value">${x.bedsPerMPB===null?'—':x.bedsPerMPB.toFixed(3)}</strong><i><em class="bed-ratio" style="width:${x.bedsPerMPB===null?0:scale(x.bedsPerMPB,maxBed)}%"></em></i></div><div class="hospital-tile-measure" aria-label="Joined hospital records per MPB row: ${x.hospitalsPerMPB===null?'no hospital data':x.hospitalsPerMPB.toFixed(3)}"><strong class="hospital-ratio-value">${x.hospitalsPerMPB===null?'—':x.hospitalsPerMPB.toFixed(3)}</strong><i><em class="hospital-ratio" style="width:${x.hospitalsPerMPB===null?0:scale(x.hospitalsPerMPB,maxHospital)}%"></em></i></div></div>`).join('')}</div><div class="chart-legend"><span><i class="legend-dot gold"></i>Reported government beds per MPB row · scale max ${maxBed.toFixed(3)}</span><span><i class="legend-dot" style="background:#087A61"></i>Joined hospital records per MPB row · scale max ${maxHospital.toFixed(3)}</span></div>`;
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
        const rows = points.filter((p) => p.povertyPct != null && p.allocationPerBarangayPesos != null && Number.isFinite(Number(p.povertyPct)) && Number.isFinite(Number(p.allocationPerBarangayPesos)))
            .sort((a,b) => Number(b.povertyPct)-Number(a.povertyPct));
        if (rows.length < 15) return '<p>Province ranking data is unavailable.</p>';
        const middleStart=Math.floor((rows.length-5)/2), selected=[...rows.slice(0,5),...rows.slice(middleStart,middleStart+5),...rows.slice(-5)].sort((a,b)=>Number(b.povertyPct)-Number(a.povertyPct));
        const maxPoverty=Math.max(...selected.map(p=>Number(p.povertyPct)),1),povertyScale=Math.ceil(maxPoverty/10)*10;
        const maxDensity=Math.max(...selected.map(p=>Number(p.allocationPerBarangayPesos)),1),densityScale=Math.ceil(maxDensity/5000000)*5000000;
        const densityLabel=value=>Number(value)===0?'₱0':value>=1000000?`₱${(value/1000000).toFixed(value>=10000000?0:1)}M`:`₱${(value/1000).toFixed(0)}k`;
        const W=1000,H=480,L=82,R=116,T=54,B=164,plotW=W-L-R,plotH=H-T-B,base=T+plotH,step=plotW/selected.length,barW=14,gap=5;
        let content='';
        for(let i=0;i<=4;i++){
            const f=i/4,y=base-f*plotH;
            if(i>0)content+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="#E0E6DF"/>`;
            content+=`<text x="${L-8}" y="${y+4}" text-anchor="end" fill="#B58600" font-size="10" font-weight="700">${(povertyScale*f).toFixed(0)}%</text><text x="${W-R+8}" y="${y+4}" fill="#0038A8" font-size="10" font-weight="700">${esc(densityLabel(densityScale*f))}</text>`;
        }
        content+=`<line x1="${L}" y1="${T}" x2="${L}" y2="${base}" stroke="#B58600" stroke-width="1.5"/><line x1="${W-R}" y1="${T}" x2="${W-R}" y2="${base}" stroke="#0038A8" stroke-width="1.5"/><line x1="${L}" y1="${base}" x2="${W-R}" y2="${base}" stroke="#89968D"/>`;
        [5,10].forEach((cut,index)=>{const x=L+step*cut;content+=`<line x1="${x}" y1="${T}" x2="${x}" y2="${base}" stroke="#94A3B8" stroke-dasharray="3 4"/><text x="${L+step*(index*5+2.5)}" y="39" text-anchor="middle" fill="#647268" font-size="9" font-weight="700">${['Top 5','Middle 5'][index]}</text>`;});
        content+=`<text x="${L+step*12.5}" y="39" text-anchor="middle" fill="#647268" font-size="9" font-weight="700">Bottom 5</text>`;
        selected.forEach((p,i)=>{
            const center=L+i*step+step/2,poverty=Number(p.povertyPct),density=Number(p.allocationPerBarangayPesos),focus=/zamboanga del norte|ilocos norte/i.test(p.region),stroke=focus?'#C2410C':'none',strokeWidth=focus?2:0;
            const ph=plotH*poverty/povertyScale,dh=plotH*density/densityScale,px=center-gap/2-barW,dx=center+gap/2;
            const rowEvidence=`${p.projectRows==null?'':` · ${fmt(p.projectRows)} MPB rows`}${p.allocationPesos==null?'':` · ${peso(p.allocationPesos)} total listed allocation`}`,tooltip=`${p.region} · poverty incidence ${poverty.toFixed(1)}% · allocation ${peso(density)} per official barangay${rowEvidence} · poverty rank ${rows.indexOf(p)+1}`;
            content+=`<rect x="${px}" y="${base-ph}" width="${barW}" height="${ph}" rx="2" fill="#B58600" stroke="${stroke}" stroke-width="${strokeWidth}"><title>${esc(tooltip)}</title></rect><rect x="${dx}" y="${base-dh}" width="${barW}" height="${dh}" rx="2" fill="#0038A8" stroke="${stroke}" stroke-width="${strokeWidth}"><title>${esc(tooltip)}</title></rect>`;
            const label=p.region.length>22?`${p.region.slice(0,21)}…`:p.region;
            content+=`<text transform="translate(${center-2} ${base+8}) rotate(90)" text-anchor="start" fill="${focus?'#9A3412':'#46564C'}" font-size="9" font-weight="${focus?800:500}"><title>${esc(p.region)}</title>${esc(label)}</text>`;
        });
        content+=`<text x="${L}" y="18" fill="#B58600" font-size="10" font-weight="750">2023 poverty incidence · left axis</text><text x="${W-R}" y="18" text-anchor="end" fill="#0038A8" font-size="10" font-weight="750">Listed allocation per official barangay · right axis</text>`;
        const chart=svgWrap(content,'One grouped vertical bar chart comparing poverty incidence and MPB allocation per official barangay across top, middle, and bottom provinces by poverty incidence.',`0 0 ${W} ${H}`);
        const legend=`<div class="chart-legend"><span><i class="legend-dot gold"></i>Poverty incidence · 0–${povertyScale}%</span><span><i class="legend-dot" style="background:#0038A8"></i>Allocation per official barangay · ₱0–${esc(densityLabel(densityScale))}</span><span><i style="display:inline-block;width:10px;height:10px;border:2px solid #C2410C;border-radius:2px"></i>Zamboanga del Norte and Ilocos Norte</span><span>Top 5 · middle 5 · bottom 5 provinces combined, ranked by poverty</span></div>`;
        return chart+legend;
    }

    function ratioChart(a, b, labelA, labelB, type) {
        const ratio = Number(a) / Number(b);
        const max = Math.max(Number(a), Number(b));
        return `<div class="callout-stat"><strong>${ratio.toFixed(2)}×</strong><span>${esc(labelA.toLowerCase())} per ${esc(labelB.toLowerCase().replace(/records?/, 'record').replace(/beds/, 'bed'))}</span></div><div class="chart-bars"><div class="bar-row"><span class="bar-label">${esc(labelA)}</span><span class="bar-track"><i class="bar-fill" style="width:${100 * Number(a) / max}%"></i></span><span class="bar-value">${fmt(a)}</span></div><div class="bar-row"><span class="bar-label">${esc(labelB)}</span><span class="bar-track"><i class="bar-fill gold" style="width:${100 * Number(b) / max}%"></i></span><span class="bar-value">${fmt(b)}</span></div></div><div class="chart-legend"><span>${type === 'school' ? '47,372 of 48,129 public-school records were joined.' : '60,744 beds across 781 joined government hospitals/infirmaries.'}</span></div>`;
    }

    function unifiedBarangayChart(data) {
        if (!data?.tables) return '<p class="prompt">Unified barangay rankings are unavailable.</p>';
        const compactPeso = (value) => value >= 1e9 ? `₱${(value/1e9).toFixed(1)}B` : value >= 1e6 ? `₱${(value/1e6).toFixed(1)}M` : value >= 1e3 ? `₱${(value/1e3).toFixed(0)}k` : peso(value);
        const specs = [
            { key:'upgrades', metric:'highestLevel', label:'Highest level', subtitle:'Repeat-title level: how many times a matching MPB title appears across years', color:'#0038A8', format:v=>`Level ${fmt(v)}`, axis:v=>fmt(v) },
            { key:'techTree', metric:'namedMPBs', label:'MPBs in barangay', subtitle:'Count of distinct named MPB title matches', color:'#087A61', format:v=>fmt(v), axis:v=>fmt(v) },
            { key:'economy', metric:'allocationPesos', label:'Listed allocation', subtitle:'Total listed allocation across available years', color:'#B58600', format:v=>compactPeso(v), axis:v=>compactPeso(v) }
        ];
        const ranked = new Map();
        specs.forEach(spec => (data.tables[spec.key]?.rows || []).forEach((row, index) => {
            const id = `${row.province}|${row.municipality}|${row.barangay}`.toLocaleLowerCase();
            if (!ranked.has(id)) ranked.set(id, { row, values:{} });
            ranked.get(id).values[spec.key] = { value:Number(row[spec.metric] || 0), rank:index + 1 };
        }));
        const places = [...ranked.values()].sort((a,b) => {
            const rankOf = x => Math.min(...specs.map(s => x.values[s.key]?.rank ?? Infinity));
            return rankOf(a)-rankOf(b) || a.row.barangay.localeCompare(b.row.barangay);
        });
        const maxima = Object.fromEntries(specs.map(s => [s.key,Math.max(1,...places.map(p=>p.values[s.key]?.value||0))]));
        const W=1000,H=430,L=160,R=15,T=50,B=150,plotW=W-L-R,plotH=H-T-B,base=T+plotH,step=plotW/places.length,barW=Math.min(8,step*.23),gap=1.5;
        const axes=specs.map((s,i)=>({ ...s, x:L-103+i*48, max:maxima[s.key] }));
        let content='';
        [0,.5,1].forEach(f=>{
            const y=base-f*plotH;
            if(f>0)content+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="#E0E6DF"/>`;
            axes.forEach(a=>content+=`<text x="${a.x-4}" y="${y+3}" text-anchor="end" fill="${a.color}" font-size="8" font-weight="700">${a.axis(a.max*f)}</text>`);
        });
        axes.forEach(a=>content+=`<line x1="${a.x}" y1="${T}" x2="${a.x}" y2="${base}" stroke="${a.color}" stroke-width="1.5"/><line x1="${a.x-3}" y1="${T}" x2="${a.x+3}" y2="${T}" stroke="${a.color}"/><line x1="${a.x-3}" y1="${base}" x2="${a.x+3}" y2="${base}" stroke="${a.color}"/>`);
        content+=`<line x1="${L}" y1="${base}" x2="${W-R}" y2="${base}" stroke="#89968D"/>`;
        places.forEach((place,i)=>{
            const center=L+i*step+step/2;
            specs.forEach((s,j)=>{
                const entry=place.values[s.key];
                if(!entry)return;
                const height=Math.max(1,plotH*entry.value/maxima[s.key]),x=center+(j-1)*(barW+gap)-barW/2,y=base-height;
                const title=`${place.row.barangay} · ${place.row.municipality}, ${place.row.province} · ${s.label}: ${s.format(entry.value)} · rank ${entry.rank} of 10`;
                content+=`<rect x="${x}" y="${y}" width="${barW}" height="${height}" rx="1.5" fill="${s.color}"><title>${esc(title)}</title></rect>`;
            });
            const label=place.row.barangay.length>20?`${place.row.barangay.slice(0,19)}…`:place.row.barangay;
            content+=`<text transform="translate(${center-2} ${base+8}) rotate(90)" text-anchor="start" fill="#46564c" font-size="8"><title>${esc(`${place.row.barangay} · ${place.row.municipality}, ${place.row.province}`)}</title>${esc(label)}</text>`;
        });
        content+=`<text x="${L}" y="18" fill="#46564c" font-size="10" font-weight="700">Barangay</text><text x="${L}" y="34" fill="#647268" font-size="9">Each colored axis has its own scale · through FY${fmt(data.throughFiscalYear)}</text>`;
        const legend=`<div class="chart-legend unified-chart-legend">${axes.map(a=>`<span class="unified-legend-item"><i style="background:${a.color}"></i><span><b>${esc(a.label)} · 0–${esc(a.axis(a.max))}</b><small>${esc(a.subtitle)}</small></span></span>`).join('')}<span>Each barangay appears only in rankings where it is in that measure’s top 10.</span></div>`;
        return `<div class="unified-multi-axis-chart">${svgWrap(content,'Top barangays compared in one grouped vertical bar chart. Each measure has an independent vertical axis and scale.',`0 0 ${W} ${H}`)}</div>${legend}<p class="chart-note">Grouped columns share one barangay axis. The colored y-axes scale repeat-title level, distinct named MPB matches, and listed allocation independently; hover a bar for its exact value and rank. Repeat-title matches are a screening signal, not proof of the same physical building.</p>`;
    }

    function detailCard(plan, index) {
        const wideDetail = [2, 5].includes(index) ? ' story-card-wide-detail' : '';
        return `<article class="story-card${wideDetail}"><div class="story-head"><span class="story-number">${String(index + 1).padStart(2, '0')}</span><h3 class="story-title">MPB infographic</h3></div><div class="visual-pair"><section class="visual-cell"><p class="cell-label">The simple picture</p><div class="source-infographic" data-infographic="${index}"></div></section><section class="visual-cell"><p class="cell-label">Explore the detail</p><h4 class="detail-title">${esc(plan.title)}</h4><div class="detail-chart">${plan.chart(window.mpbHomeData)}</div><p class="chart-note">${esc(plan.note)}</p><a class="detail-link" href="${plan.href}" target="_blank" rel="noopener noreferrer">${esc(plan.link)} →</a></section></div></article>`;
    }

    function mountInfographics(sourceHtml) {
        const source = new DOMParser().parseFromString(sourceHtml, 'text/html');
        const panels = Array.from(source.querySelectorAll('section.simple-panel'));
        const styles = Array.from(source.querySelectorAll('head style')).slice(0, 4).map((node) => node.textContent).join('\n');
        const sprite = Array.from(source.querySelectorAll('svg')).find((node) => node.querySelector('defs'));
        if (panels.length < chartPlans.length) throw new Error('The MPB simple page did not contain all eight infographic panels.');
        panels.slice(0, chartPlans.length).forEach((panel, index) => {
            const host = list.querySelector(`[data-infographic="${index}"]`);
            host.classList.add('loaded');
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
            const [sourceResponse, dataResponse, educationResponse, historyResponse, rankingsResponse] = await Promise.all([
                fetch(`${researchBase}mpb-simple.html?v=mpb-token-pow-20261116`, { signal: controller.signal, headers: { Accept: 'text/html' } }),
                fetch(`${researchBase}mpb-simple-data.json?v=mpb-token-pow-20261116`, { signal: controller.signal, headers: { Accept: 'application/json' } }),
                fetch(`${researchBase}education-health-data.json`, { signal: controller.signal, headers: { Accept: 'application/json' } }),
                fetch('/static/data/mpb-historical-multiplicity.json', { signal: controller.signal, headers: { Accept: 'application/json' } }),
                fetch('/static/data/mpb-unified-top-chart.json', { signal: controller.signal, headers: { Accept: 'application/json' } })
            ]);
            if (!sourceResponse.ok) throw new Error(`The MPB infographic page returned ${sourceResponse.status}.`);
            if (!dataResponse.ok) throw new Error(`The MPB chart data returned ${dataResponse.status}.`);
            if (!educationResponse.ok) throw new Error(`The regional facility data returned ${educationResponse.status}.`);
            if (!historyResponse.ok) throw new Error(`The exact historical counts returned ${historyResponse.status}.`);
            if (!rankingsResponse.ok) throw new Error(`The unified barangay rankings returned ${rankingsResponse.status}.`);
            const [sourceHtml, data, education, historicalMultiplicity, unifiedBarangayRankings] = await Promise.all([sourceResponse.text(), dataResponse.json(), educationResponse.json(), historyResponse.json(), rankingsResponse.json()]);
            if (!sourceHtml || !data) throw new Error('The MPB research source is incomplete.');
            window.mpbHomeData = data;
            data.educationRows = education.geographyRows;
            data.historicalMultiplicity = historicalMultiplicity;
            data.unifiedBarangayRankings = unifiedBarangayRankings;
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

(()=>{
  const root=document.getElementById('connectivity-places-inventory');if(!root)return;
  const $=id=>document.getElementById(id),fmt=x=>Number(x||0).toLocaleString('en-PH'),
    esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const load=async name=>{const r=await fetch(name);if(!r.ok)throw Error(`${name}: HTTP ${r.status}`);return r.json()};
  if($('fmr-venue-summary'))load('connectivity-remote-fmr-venues.json').then(data=>{
    const rows=data.rows||[],query=$('fmr-venue-query'),year=$('fmr-venue-year'),size=$('fmr-venue-size'),body=$('fmr-venue-rows'),pageLabel=$('fmr-venue-page');
    $('fmr-venue-summary').textContent=`${fmt(data.uniqueRoadRecords)} coordinate-backed FMR routes · ${fmt(data.matchedRoadVenuePairs)} route–venue pairs within ${fmt(data.bufferMeters)} m. Venue pairs by source: ${Object.entries(data.venuePairsBySource||{}).map(([k,v])=>`${fmt(v)} ${k}`).join(' · ')}`;
    [...new Set(rows.map(r=>String(r.year)))].sort((a,b)=>Number(b)-Number(a)).forEach(y=>year.add(new Option(`FY${y}`,y)));
    let page=0;function draw(){const term=query.value.trim().toLowerCase(),matches=rows.filter(r=>(!year.value||String(r.year)===year.value)&&(!term||[r.roadTitle,r.venueName,r.venueType,r.municipality,r.province,r.region].join(' ').toLowerCase().includes(term))),per=Number(size.value),pages=Math.max(1,Math.ceil(matches.length/per));page=Math.max(0,Math.min(page,pages-1));body.innerHTML=matches.slice(page*per,(page+1)*per).map(r=>`<tr><td>FY${esc(r.year)}<small style="display:block">${esc(r.stage)} · ${esc(r.roadStatus)}</small></td><td>${esc(r.roadTitle)}${r.allocationPesos==null?'':`<small style="display:block">₱${fmt(r.allocationPesos)}</small>`}</td><td>${esc(r.venueName)}<small style="display:block">${esc(r.venueType)}</small></td><td>${esc([r.municipality,r.province].filter(Boolean).join(' · ')||'Place unresolved')}<small style="display:block">${esc(r.region)}</small></td><td class="num">${fmt(r.distanceMeters)} m</td><td><button type="button" class="connectivity-map-open" data-connectivity-map="${esc(r.roadId)}" aria-label="Map FMR route and venue ${esc(r.venueName)}">Map</button></td><td><a href="${esc(r.roadSourceUrl)}" target="_blank" rel="noopener noreferrer">Road source ↗</a> · <a href="${esc(r.venueSourceUrl)}" target="_blank" rel="noopener noreferrer">Venue ↗</a></td></tr>`).join('')||'<tr><td colspan="7">No coordinate-backed remote FMR routes match a municipal visitor venue within 100 m.</td></tr>';pageLabel.textContent=`${matches.length?page*per+1:0}–${Math.min((page+1)*per,matches.length)} of ${fmt(matches.length)} · Page ${page+1} of ${pages}`;$('fmr-venue-prev').disabled=page===0;$('fmr-venue-next').disabled=page>=pages-1}
    [year,size].forEach(el=>el.addEventListener('change',()=>{page=0;draw()}));query.addEventListener('input',()=>{page=0;draw()});$('fmr-venue-prev').onclick=()=>{page--;draw()};$('fmr-venue-next').onclick=()=>{page++;draw()};draw();
  }).catch(e=>{$('fmr-venue-summary').textContent='FMR–venue matches could not be loaded: '+e.message});
  Promise.allSettled([load('connectivity-venues-data.json'),load('connectivity-property-indicators-data.json')]).then(results=>{
    const datasets=results.filter(r=>r.status==='fulfilled').map(r=>r.value),rows=datasets.flatMap(d=>d.rows||[]),failed=results.filter(r=>r.status==='rejected');
    if(!datasets.length)throw Error('Place inventories could not be loaded.');
    const venues=results[0].status==='fulfilled'?results[0].value:null,properties=results[1].status==='fulfilled'?results[1].value:null;
    $('place-source-summary').textContent=`${fmt(venues?.count)} mapped visitor venues · ${fmt(properties?.count)} subdivision / estate / residential-property candidates. ${venues?Object.entries(venues.typeCounts||{}).map(([k,v])=>`${fmt(v)} ${k.toLowerCase()}`).join(' · '):''}${failed.length?' One source inventory did not load.':''}`;
    const dates=[...new Set(datasets.flatMap(d=>(d.inputs||[]).map(x=>x.snapshotUtc?.slice(0,10))).filter(Boolean))];
    $('place-source-date').textContent=`OSM snapshots: ${dates.join(', ')}. Government/public-use indicators screened; business operation, property ownership and valuation remain unverified. Municipality location is a proxy, not a remote-road finding.`;
    const type=$('place-type'),q=$('place-query'),admin=$('place-admin'),size=$('place-size');
    [...new Set(rows.map(r=>r.type))].sort().forEach(k=>type.add(new Option(k,k)));
    let page=0;
    function draw(){
      const term=q.value.trim().toLowerCase(),matches=rows.filter(r=>(!type.value||r.type===type.value)&&(!admin.value||r.adminType===admin.value||admin.value==='unresolved'&&!r.adminType)&&(!term||[r.name,r.type,r.province,r.municipality,r.region,r.id].join(' ').toLowerCase().includes(term))),per=Number(size.value),pages=Math.max(1,Math.ceil(matches.length/per));
      page=Math.max(0,Math.min(page,pages-1));
      $('place-rows').innerHTML=matches.slice(page*per,(page+1)*per).map(r=>`<tr><td>${esc(r.name)}<small style="display:block">${esc(r.type)}</small></td><td>${esc([r.municipality,r.province].filter(Boolean).join(' · ')||'Place unresolved')}<small style="display:block">${esc(r.adminType||'Unresolved')} · ${esc(r.region)}</small></td><td>${esc(r.evidence||[r.buildingTag&&'building='+r.buildingTag,r.landuseTag&&'landuse='+r.landuseTag].filter(Boolean).join('; '))}<small style="display:block">${esc(r.coordinateBasis||(r.geometry?.type==='Polygon'?'Mapped polygon':'Mapped point / source bounds'))}</small></td><td>${r.areaSquareMeters==null?'—':fmt(r.areaSquareMeters)+' m²'}<small style="display:block">${r.recordKind==='Private-property cue'?'Value / ownership unverified':'Mapped business use'}</small></td><td><a href="${esc(r.sourceUrl)}" target="_blank" rel="noopener noreferrer">OSM source ↗</a></td></tr>`).join('')||'<tr><td colspan="5">No source places match these filters.</td></tr>';
      $('place-page').textContent=`${matches.length?page*per+1:0}–${Math.min((page+1)*per,matches.length)} of ${fmt(matches.length)} · Page ${page+1} of ${pages}`;
      $('place-prev').disabled=page===0;$('place-next').disabled=page>=pages-1;
    }
    [type,admin,size].forEach(el=>el.addEventListener('change',()=>{page=0;draw()}));q.addEventListener('input',()=>{page=0;draw()});
    $('place-prev').onclick=()=>{page--;draw()};$('place-next').onclick=()=>{page++;draw()};draw();
  }).catch(e=>{$('place-source-summary').textContent='Place inventory unavailable: '+e.message;});
})();

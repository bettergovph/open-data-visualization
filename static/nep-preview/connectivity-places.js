(()=>{
  const root=document.getElementById('connectivity-places-inventory');if(!root)return;
  const $=id=>document.getElementById(id),fmt=x=>Number(x||0).toLocaleString('en-PH'),
    esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const load=async name=>{const r=await fetch(name);if(!r.ok)throw Error(`${name}: HTTP ${r.status}`);return r.json()};
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

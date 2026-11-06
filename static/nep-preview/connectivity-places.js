(()=>{
  const root=document.getElementById('connectivity-places-inventory');if(!root)return;
  const revealNames=document.documentElement.dataset.connectivityReveal==='true';
  const $=id=>document.getElementById(id),fmt=x=>Number(x||0).toLocaleString('en-PH'),
    esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const venueHash=async value=>{
    const normalized=String(value??'').normalize('NFKC').trim().replace(/\s+/g,' ').toLocaleLowerCase('en-PH');
    if(!globalThis.crypto?.subtle)throw Error('SHA-256 requires a secure browser context (HTTPS or localhost).');
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(normalized));
    return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
  };
  const hashLabel=(hash,name)=>revealNames?'<span>'+esc(name||'Name unavailable')+'</span>':'<code>SHA-256 '+esc(hash)+'</code>';
  const googleMapsLink=(lat,lon,label='Google Maps satellite ↗')=>{const a=Number(lat),b=Number(lon);if(!Number.isFinite(a)||!Number.isFinite(b))return '';const url='https://www.google.com/maps/@?api=1&map_action=map&center='+encodeURIComponent(a+','+b)+'&zoom=18&basemap=satellite';return `<a href="${url}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`};
  const routeCoordinateGap=r=>{const raw=[r.startLatitude,r.startLongitude,r.endLatitude,r.endLongitude];if(raw.some(x=>x==null||x===''))return null;const c=raw.map(Number);if(!c.every(Number.isFinite))return null;const rad=x=>x*Math.PI/180,dl=rad(c[2]-c[0]),dn=rad(c[3]-c[1]),a=Math.sin(dl/2)**2+Math.cos(rad(c[0]))*Math.cos(rad(c[2]))*Math.sin(dn/2)**2;return {coordinates:c,distance:6371008.8*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a))}};
  const googleRouteLink=r=>{const check=routeCoordinateGap(r);if(!check)return '';if(check.distance>10000)return `<strong style="display:inline-block;padding:4px 7px;color:#8f1515;background:#fee2e2;border:1px solid #dc2626;border-radius:4px" title="Source endpoint coordinates are implausibly far apart for this FMR record; verify them before routing">⚠ RED FLAG: source coordinates about ${fmt(check.distance/1000)} km apart; route suppressed</strong>`;const c=check.coordinates,url='https://www.google.com/maps/dir/?api=1&origin='+encodeURIComponent(c[0]+','+c[1])+'&destination='+encodeURIComponent(c[2]+','+c[3])+'&travelmode=driving';return `<a href="${url}" target="_blank" rel="noopener noreferrer" title="Google Maps suggested driving route and distance between endpoints; not the project alignment or straight-line measurement">Route + distance ↗</a>`};
  const DATA_VERSION='20261106-venues18-properties9-routecheck4';
  const load=async name=>{const url=new URL(name,location.href);url.searchParams.set('v',DATA_VERSION);const r=await fetch(url);if(!r.ok)throw Error(`${name}: HTTP ${r.status}`);return r.json()};
  async function routePlaces(file,prefix,property=false){
    if(!$(prefix+'-summary'))return;
    try{
      const data=await load(file),rows=await Promise.all((data.rows||[]).map(async r=>({...r,venueNameHash:await venueHash(r.venueName)})));
      const query=$(prefix+'-query'),year=$(prefix+'-year'),size=$(prefix+'-size'),body=$(prefix+'-rows'),label=$(prefix+'-page');
      $(prefix+'-summary').textContent=`${fmt(data.uniqueRoadRecords)} coordinate-backed FMR routes · ${fmt(data.matchedRoadPlacePairs??data.matchedRoadVenuePairs)} route–${property?'property':'venue'} pairs within ${fmt(data.bufferMeters)} m.`;
      [...new Set(rows.map(r=>String(r.year)))].sort((a,b)=>Number(b)-Number(a)).forEach(y=>year.add(new Option(`FY${y}`,y)));
      let page=0;
      function draw(){
        const term=query.value.trim().toLowerCase(),matches=rows.filter(r=>(!year.value||String(r.year)===year.value)&&(!term||[r.roadTitle,r.venueName,r.venueType,r.municipality,r.province,r.region,r.placeId].join(' ').toLowerCase().includes(term))),per=Number(size.value),pages=Math.max(1,Math.ceil(matches.length/per));
        page=Math.max(0,Math.min(page,pages-1));
        body.innerHTML=matches.slice(page*per,(page+1)*per).map(r=>{const gap=routeCoordinateGap(r),bad=gap&&gap.distance>100000;return `<tr${bad?' style="background:#fff0f0;box-shadow:inset 4px 0 #b91c1c"':''}><td>FY${esc(r.year)}<small style="display:block">${esc(r.stage)} · ${esc(r.roadStatus)}</small></td><td>${esc(r.roadTitle)}${r.allocationPesos==null?'':`<small style="display:block">₱${fmt(r.allocationPesos)}</small>`}</td><td>${hashLabel(r.venueNameHash,r.venueName)}<small style="display:block">${esc(r.venueType)}</small>${r.areaSquareMeters==null?'':`<small style="display:block">${fmt(r.areaSquareMeters)} m² mapped footprint</small>`}</td><td>${esc([r.municipality,r.province].filter(Boolean).join(' · ')||'Place unresolved')}<small style="display:block">${esc(r.region)}</small></td><td class="num">${fmt(r.distanceMeters)} m<small style="display:block;white-space:normal">${esc(r.distanceBasis||'Straight source-endpoint segment to mapped venue point')}</small></td><td><button type="button" class="connectivity-map-open" data-connectivity-map="${esc(r.roadId)}" aria-label="Open FMR route and nearby DPWH road map">FMR + road map</button><small>${googleMapsLink(property?r.latitude:r.venueLatitude,property?r.longitude:r.venueLongitude,'Place satellite view ↗')}</small><small>${googleRouteLink(r)}</small></td><td><span>Offline DPWH shapefiles</span> · <a href="${esc(r.venueSourceUrl)}" target="_blank" rel="noopener noreferrer">${property?'Property':'Venue'} source ↗</a></td></tr>`}).join('')||`<tr><td colspan="7">No coordinate-backed municipal FMR routes match the selected ${property?'property':'venue'} records within 100 m.</td></tr>`;
        label.textContent=`${matches.length?page*per+1:0}–${Math.min((page+1)*per,matches.length)} of ${fmt(matches.length)} · Page ${page+1} of ${pages}`;$(prefix+'-prev').disabled=page===0;$(prefix+'-next').disabled=page>=pages-1;
      }
      [year,size].forEach(el=>el.addEventListener('change',()=>{page=0;draw()}));query.addEventListener('input',()=>{page=0;draw()});$(prefix+'-prev').onclick=()=>{page--;draw()};$(prefix+'-next').onclick=()=>{page++;draw()};draw();
    }catch(e){$(prefix+'-summary').textContent='Route/place matches could not be loaded: '+e.message;}
  }
  routePlaces('connectivity-remote-fmr-venues.json','fmr-venue');
  routePlaces('connectivity-remote-fmr-properties.json','fmr-property',true);
  Promise.allSettled([load('connectivity-venues-data.json'),load('connectivity-property-indicators-data.json'),load('connectivity-official-venues-data.json')]).then(async results=>{
    const datasets=results.filter(r=>r.status==='fulfilled').map(r=>r.value),rows=await Promise.all(datasets.flatMap(d=>(d.rows||[]).filter(r=>r.recordKind!=='Official venue listing'||!r.matchedOsmIds?.length)).map(async r=>({...r,nameHash:await venueHash(r.name)}))),failed=results.filter(r=>r.status==='rejected');
    if(!datasets.length)throw Error('Place inventories could not be loaded.');
    const venues=results[0].status==='fulfilled'?results[0].value:null,properties=results[1].status==='fulfilled'?results[1].value:null,official=results[2].status==='fulfilled'?results[2].value:null;
    $('place-source-summary').textContent=`${fmt(venues?.count)} mapped visitor venues · ${fmt(properties?.count)} subdivision / estate / residential-property candidates · ${fmt(official?.count)} official tourism listings (${fmt(official?.matchedMapRecords)} matched to map records). ${venues?Object.entries(venues.typeCounts||{}).map(([k,v])=>`${fmt(v)} ${k.toLowerCase()}`).join(' · '):''}${failed.length?' One source inventory did not load.':''}`;
    const dates=[...new Set(datasets.flatMap(d=>(d.inputs||[]).map(x=>x.snapshotUtc?.slice(0,10))).filter(Boolean))];
    $('place-source-date').textContent=`OSM snapshots: ${dates.join(', ')}. Official municipal tourism directory retrieved ${official?.rows?.[0]?.retrievedAtUtc?.slice(0,10)||'not available'}. Government/public-use indicators screened; business operation, property ownership and valuation remain unverified. Municipality location is a proxy, not a remote-road finding.`;
    const type=$('place-type'),q=$('place-query'),admin=$('place-admin'),size=$('place-size');
    [...new Set(rows.map(r=>r.type))].sort().forEach(k=>type.add(new Option(k,k)));
    let page=0;
    function draw(){
      const term=q.value.trim().toLowerCase(),matches=rows.filter(r=>(!type.value||r.type===type.value)&&(!admin.value||r.adminType===admin.value||admin.value==='unresolved'&&!r.adminType)&&(!term||[r.name,r.type,r.province,r.municipality,r.region,r.id].join(' ').toLowerCase().includes(term))),per=Number(size.value),pages=Math.max(1,Math.ceil(matches.length/per));
      page=Math.max(0,Math.min(page,pages-1));
      $('place-rows').innerHTML=matches.slice(page*per,(page+1)*per).map(r=>`<tr><td>${hashLabel(r.nameHash,r.name)}<small style="display:block">${esc(r.type)}</small></td><td>${esc([r.municipality,r.province].filter(Boolean).join(' · ')||'Place unresolved')}<small style="display:block">${esc(r.adminType||'Unresolved')} · ${esc(r.region)}</small><small style="display:block">${googleMapsLink(r.latitude,r.longitude,'Google Maps ↗')}</small></td><td>${esc(r.evidence||[r.buildingTag&&'building='+r.buildingTag,r.landuseTag&&'landuse='+r.landuseTag,r.accessTag&&'access='+r.accessTag,r.leisureTag&&'leisure='+r.leisureTag].filter(Boolean).join('; '))}<small style="display:block">${esc(r.coordinateBasis||(r.geometry?.type==='Polygon'?'Mapped polygon':'Mapped point / source bounds'))}</small>${(r.directoryEvidence||[]).map(e=>`<small style="display:block"><a href="${esc(e.sourceUrl)}" target="_blank" rel="noopener noreferrer">Municipal tourism listing ↗</a> · ${esc(e.municipality)}, ${esc(e.province)} · ${esc(e.locationStatus)}</small>`).join('')}</td><td>${r.areaSquareMeters==null?'—':fmt(r.areaSquareMeters)+' m²'}<small style="display:block">${r.recordKind==='Private-property cue'?'Value / ownership unverified':'Mapped business use'}</small></td><td><a href="${esc(r.sourceUrl)}" target="_blank" rel="noopener noreferrer">${esc(r.source||'Source')} ↗</a></td></tr>`).join('')||'<tr><td colspan="5">No source places match these filters.</td></tr>';
      $('place-page').textContent=`${matches.length?page*per+1:0}–${Math.min((page+1)*per,matches.length)} of ${fmt(matches.length)} · Page ${page+1} of ${pages}`;
      $('place-prev').disabled=page===0;$('place-next').disabled=page>=pages-1;
    }
    [type,admin,size].forEach(el=>el.addEventListener('change',()=>{page=0;draw()}));q.addEventListener('input',()=>{page=0;draw()});
    $('place-prev').onclick=()=>{page--;draw()};$('place-next').onclick=()=>{page++;draw()};draw();
  }).catch(e=>{$('place-source-summary').textContent='Place inventory unavailable: '+e.message;});
})();

(()=>{
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=x=>Number(x||0).toLocaleString('en-PH');
  let payloadPromise,boundaryPromise,dialog;
  const fetchJson=async name=>{const r=await fetch(name);if(!r.ok)throw Error(`${name}: HTTP ${r.status}`);return r.json()};
  const payload=()=>payloadPromise||(payloadPromise=fetchJson('connectivity-map-data.json'));
  const boundaries=()=>boundaryPromise||(boundaryPromise=fetchJson('out-of-place-boundaries.json'));

  function utm51(lon,lat){
    const a=6378137,e=.00669437999014,k=.9996,latR=lat*Math.PI/180,lonR=lon*Math.PI/180,lon0=123*Math.PI/180;
    const ep=e/(1-e),n=a/Math.sqrt(1-e*Math.sin(latR)**2),t=Math.tan(latR)**2,c=ep*Math.cos(latR)**2,aa=Math.cos(latR)*(lonR-lon0);
    const m=a*((1-e/4-3*e**2/64-5*e**3/256)*latR-(3*e/8+3*e**2/32+45*e**3/1024)*Math.sin(2*latR)+(15*e**2/256+45*e**3/1024)*Math.sin(4*latR)-(35*e**3/3072)*Math.sin(6*latR));
    return [k*n*(aa+(1-t+c)*aa**3/6+(5-18*t+t*t+72*c-58*ep)*aa**5/120)+500000,k*(m+n*Math.tan(latR)*(aa**2/2+(5-t+9*c+4*c*c)*aa**4/24+(61-58*t+t*t+600*c-330*ep)*aa**6/720))];
  }
  function inRings(lon,lat,rings){let inside=false;for(const ring of rings||[]){let hit=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];if((yi>lat)!==(yj>lat)&&lon<(xj-xi)*(lat-yi)/(yj-yi)+xi)hit=!hit;}if(hit)inside=!inside;}return inside;}
  function boundsOf(features){const b={minX:Infinity,minY:Infinity,maxX:-Infinity,maxY:-Infinity};for(const f of features)for(const ring of f.rings||[])for(const p of ring){const [x,y]=utm51(p[0],p[1]);b.minX=Math.min(b.minX,x);b.maxX=Math.max(b.maxX,x);b.minY=Math.min(b.minY,y);b.maxY=Math.max(b.maxY,y);}return b;}
  function nearMunicipalities(features,points){
    const hits=features.filter(f=>points.some(p=>inRings(p[0],p[1],f.rings)));
    if(!hits.length)return [];
    const base=hits[0],pool=features.filter(f=>f.province===base.province),baseBox=boundsOf([base]);
    const neighbors=pool.filter(f=>!hits.includes(f)).map(f=>{const b=boundsOf([f]);const dx=Math.max(0,baseBox.minX-b.maxX,b.minX-baseBox.maxX),dy=Math.max(0,baseBox.minY-b.maxY,b.minY-baseBox.maxY);return {f,d:Math.hypot(dx,dy)};}).filter(x=>x.d<12000).sort((a,b)=>a.d-b.d).slice(0,5).map(x=>x.f);
    return [...new Set([...hits,...neighbors])];
  }
  function style(){if(document.getElementById('connectivity-map-style'))return;const s=document.createElement('style');s.id='connectivity-map-style';s.textContent=`
    .connectivity-map-dialog{width:min(1180px,96vw);max-width:none;max-height:94vh;padding:0;border:0;border-radius:16px;color:#18313d;box-shadow:0 24px 80px #001a2b55}
    .connectivity-map-dialog::backdrop{background:#071b2dcc}.connectivity-map-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:18px 22px;background:#00246A;color:white;border-bottom:4px solid #FCD116}.connectivity-map-head h2{font-size:1.2rem;line-height:1.35;margin:0}.connectivity-map-head p{margin:5px 0 0;color:#e4edf7;font-size:.92rem}.connectivity-map-close{flex:none;border:1px solid #ffffff88;background:transparent;color:white;border-radius:8px;padding:7px 12px;font:inherit;cursor:pointer}.connectivity-map-body{padding:14px 18px 18px}.connectivity-map-svg{display:block;width:100%;height:auto;max-height:68vh;background:#f7fafb;border:1px solid #d5e0e5;border-radius:12px}.connectivity-map-legend{display:flex;flex-wrap:wrap;gap:8px 18px;margin:10px 0;color:#263f4b;font-size:.9rem}.connectivity-map-legend span{display:inline-flex;align-items:center;gap:7px}.connectivity-map-dot{width:12px;height:12px;border-radius:50%;display:inline-block}.connectivity-map-caveat{margin:8px 0 0;color:#52636d;font-size:.88rem}.connectivity-map-error{padding:28px;color:#9a2c31}.connectivity-map-layer-label{display:inline-flex;align-items:center;gap:8px;margin:2px 0 6px;font-weight:700}.connectivity-map-layer-label select{max-width:min(82vw,380px);padding:7px;border:1px solid #9aaeb8;border-radius:7px;font:inherit}.connectivity-map-source-status,.connectivity-map-source{display:block;margin:3px 0;color:#52636d;font-size:.86rem}.connectivity-map-source a{color:#174f7a}
    @media(max-width:650px){.connectivity-map-head{padding:14px}.connectivity-map-body{padding:10px}.connectivity-map-svg{max-height:60vh}}
  `;document.head.append(s);}
  function ensureDialog(){
    if(dialog)return dialog;style();dialog=document.createElement('dialog');dialog.className='connectivity-map-dialog';dialog.setAttribute('aria-labelledby','connectivity-map-title');
    dialog.innerHTML='<div class="connectivity-map-head"><div><h2 id="connectivity-map-title">Connectivity map</h2><p id="connectivity-map-subtitle"></p></div><button class="connectivity-map-close" type="button" aria-label="Close map">Close</button></div><div class="connectivity-map-body"><div id="connectivity-map-content" aria-live="polite">Loading map layers…</div><div class="connectivity-map-legend"><span><i class="connectivity-map-dot" style="background:#e35d3f"></i>Budgeted FMR route (straight between source endpoints)</span><span><i class="connectivity-map-dot" style="background:#e6ad26"></i>Source start/end</span><span><i class="connectivity-map-dot" style="background:#714ac7"></i>Mapped visitor venue</span><span><i style="display:inline-block;width:22px;border-top:4px solid #2878ad"></i>Nearest classified road section</span></div><p class="connectivity-map-caveat">DA LUS overlays show mapped crop areas, not parcel-level farm locations or verified access. FMR geometry is a straight segment between source endpoints. Venue points are OSM mapping leads; proximity does not prove access or current operation. Municipality outlines use the DPWH City-Municipal Boundaries layer.</p></div>';
    dialog.querySelector('.connectivity-map-close').addEventListener('click',()=>dialog.close());dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});document.body.append(dialog);return dialog;
  }
  const escAttr=s=>esc(s).replace(/`/g,'&#96;');
  function svgMap(project,allBoundaries,road){
    const width=1100,height=620,local={x:12,y:12,w:730,h:596},inset={x:754,y:12,w:334,h:596};
    const start=utm51(project.start[0],project.start[1]),end=utm51(project.end[0],project.end[1]),venues=(project.venues||[]).map(v=>({...v,xy:utm51(Number(v.longitude),Number(v.latitude))}));
    const locals=nearMunicipalities(allBoundaries.provinceFeatures||[],[project.start,project.end,...venues.map(v=>[v.longitude,v.latitude])]);
    let minX=Math.min(start[0],end[0],...venues.map(v=>v.xy[0])),maxX=Math.max(start[0],end[0],...venues.map(v=>v.xy[0])),minY=Math.min(start[1],end[1],...venues.map(v=>v.xy[1])),maxY=Math.max(start[1],end[1],...venues.map(v=>v.xy[1]));
    const span=Math.max(maxX-minX,maxY-minY,900),pad=Math.max(1200,span*.45);minX-=pad;maxX+=pad;minY-=pad;maxY+=pad;
    const localBounds={minX,minY,maxX,maxY};
    const projectPoint=(p,b,r)=>({x:r.x+((p[0]-b.minX)/(b.maxX-b.minX))*r.w,y:r.y+r.h-((p[1]-b.minY)/(b.maxY-b.minY))*r.h});
    const escPath=pts=>pts.map(p=>`${p[0]},${p[1]}`).join(' ');
    const polygons=locals.map(f=>`<path d="${(f.rings||[]).map(ring=>{const pts=ring.map(ll=>{const q=projectPoint(utm51(ll[0],ll[1]),localBounds,local);return `${q.x.toFixed(1)},${q.y.toFixed(1)}`;});return `M${pts.join(' L')}Z`;}).join(' ')}" fill="#dce9dc" fill-opacity=".22" stroke="#748d80" stroke-width="1.3" fill-rule="evenodd"><title>${esc(f.city||f.municipality||'Mapped locality')}, ${esc(f.province||'')}</title></path>`).join('');
    const roadPaths=road?.pathsUtm51||[];
    const localRoadSvg=roadPaths.map(path=>{const pts=path.map(p=>projectPoint(p,localBounds,local)),list=escPath(pts),title=`${esc(road.name||project.roadName||'Nearest classified road')} · ${esc(road.class||project.roadClass||'class unavailable')}`;return `<polyline points="${list}" fill="none" stroke="#fff" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/><polyline points="${list}" fill="none" stroke="#075f9b" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"><title>${title}</title></polyline>`;}).join('');
    let nearest={distance:Infinity,point:null,endpoint:null};
    for(const endpoint of [start,end])for(const path of roadPaths)for(let i=1;i<path.length;i++){
      const a=path[i-1],b=path[i],dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy,t=den?Math.max(0,Math.min(1,((endpoint[0]-a[0])*dx+(endpoint[1]-a[1])*dy)/den)):0,q=[a[0]+t*dx,a[1]+t*dy],distance=Math.hypot(endpoint[0]-q[0],endpoint[1]-q[1]);
      if(distance<nearest.distance)nearest={distance,point:q,endpoint};
    }
    const nearestSvg=nearest.point?(()=>{const a=projectPoint(nearest.endpoint,localBounds,local),b=projectPoint(nearest.point,localBounds,local);return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#163d58" stroke-width="2.5" stroke-dasharray="7 5"/><circle cx="${b.x}" cy="${b.y}" r="8" fill="#075f9b" stroke="white" stroke-width="3"><title>Nearest point on ${esc(road?.name||project.roadName||'DPWH classified road')}: ${number(nearest.distance)} m from FMR endpoint</title></circle>`;})():'';
    const a=projectPoint(start,localBounds,local),b=projectPoint(end,localBounds,local);
    const route=`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#e35d3f" stroke-width="6" stroke-linecap="round"/><circle cx="${a.x}" cy="${a.y}" r="8" fill="#e6ad26" stroke="white" stroke-width="2"><title>FMR source start</title></circle><circle cx="${b.x}" cy="${b.y}" r="8" fill="#e6ad26" stroke="white" stroke-width="2"><title>FMR source end</title></circle><text x="${a.x+10}" y="${a.y-8}" class="map-label">Start</text><text x="${b.x+10}" y="${b.y-8}" class="map-label">End</text>`;
    const venueSvg=venues.map(v=>{const q=projectPoint(v.xy,localBounds,local);return `<circle cx="${q.x}" cy="${q.y}" r="7" fill="#714ac7" stroke="white" stroke-width="2"><title>${esc(v.name)} · ${esc(v.type)} · ${number(v.distanceMeters)} m</title></circle>`;}).join('');
    const nearestName=project.roadName||road?.name||'DPWH classified road';
    let roadSvg=`<rect x="${inset.x}" y="${inset.y}" width="${inset.w}" height="${inset.h}" rx="10" fill="#f8fafb" stroke="#cad6dc"/><text x="${inset.x+14}" y="${inset.y+26}" class="map-title">Nearest DPWH road</text><text x="${inset.x+14}" y="${inset.y+47}" class="map-subtitle">${esc(nearestName)} · ${esc(project.roadClass||road?.class||'class not recorded')}</text>`;
    const paths=road?.pathsUtm51||[];let rb={minX:Infinity,minY:Infinity,maxX:-Infinity,maxY:-Infinity};for(const path of paths)for(const p of path){rb.minX=Math.min(rb.minX,p[0]);rb.maxX=Math.max(rb.maxX,p[0]);rb.minY=Math.min(rb.minY,p[1]);rb.maxY=Math.max(rb.maxY,p[1]);}
    if(paths.length&&Number.isFinite(rb.minX)){
      const padR=Math.max(250,(Math.max(rb.maxX-rb.minX,rb.maxY-rb.minY)||500)*.08);rb.minX-=padR;rb.maxX+=padR;rb.minY-=padR;rb.maxY+=padR;
      roadSvg+=`<g clip-path="url(#road-clip)">`+paths.map(path=>{const pts=path.map(p=>projectPoint(p,rb,{x:inset.x+16,y:inset.y+72,w:inset.w-32,h:inset.h-100}));return `<polyline points="${escPath(pts)}" fill="none" stroke="#2878ad" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;}).join('')+'</g>';
      roadSvg+=`<text x="${inset.x+14}" y="${inset.y+inset.h-16}" class="map-subtitle">${number(project.nearestDistanceMeters)} m from closest FMR endpoint · section ${esc(project.roadSection||'')}</text>`;
    }else roadSvg+=`<text x="${inset.x+18}" y="${inset.y+100}" class="map-subtitle">No matched road geometry for this source row.</text>`;
    const localTitle=locals.length?`${locals[0].city||locals[0].municipality||'Mapped locality'}, ${locals[0].province||''}`:'Municipality not resolved from boundaries';
    const noVenueLabel=project.venueMatchCount?'A venue match is listed, but its coordinates are unavailable for plotting.':'No matched visitor venue within 100 m in the current inventory.';
    return `<svg class="connectivity-map-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Map of FMR endpoints, nearest DPWH road, municipality boundary and visitor venues"><style>.map-title{font:700 16px system-ui;fill:#173746}.map-subtitle{font:12px system-ui;fill:#536976}.map-label{font:700 13px system-ui;fill:#523100;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}</style><defs><clipPath id="local-clip"><rect x="${local.x+1}" y="${local.y+38}" width="${local.w-2}" height="${local.h-39}"/></clipPath><clipPath id="road-clip"><rect x="${inset.x+12}" y="${inset.y+64}" width="${inset.w-24}" height="${inset.h-92}"/></clipPath></defs><rect width="${width}" height="${height}" fill="#f4f8f9"/><rect x="${local.x}" y="${local.y}" width="${local.w}" height="${local.h}" rx="10" fill="#fff" stroke="#cad6dc"/><text x="${local.x+14}" y="${local.y+26}" class="map-title">FMR route · ${esc(localTitle)}</text><g clip-path="url(#local-clip)">${polygons}${localRoadSvg}${nearestSvg}${route}${venueSvg}${venues.length?venues.map((v,i)=>{const q=projectPoint(v.xy,localBounds,local);return `<text x="${q.x+9}" y="${q.y+4+i%2*14}" class="map-label">${esc(v.name)}</text>`;}).join(''):`<text x="24" y="72" class="map-subtitle">${esc(noVenueLabel)}</text>`}</g>${roadSvg}</svg>`;
  }
  async function open(id){
    const dlg=ensureDialog(),content=dlg.querySelector('#connectivity-map-content');dlg.querySelector('#connectivity-map-title').textContent='FMR and road connection details';content.textContent='Loading route, road and municipality geometry…';dlg.showModal();
    try{
      const [data,bounds]=await Promise.all([payload(),boundaries()]),project=data.projects?.find?.(row=>String(row.id)===String(id))||data.projects?.[id];
      if(!project)throw Error('Map geometry is not available for this project record.');
      const road=project.roadSection?data.roads?.[project.roadSection]:null;
      dlg.querySelector('#connectivity-map-title').textContent=project.title||'Connectivity map';
      dlg.querySelector('#connectivity-map-subtitle').textContent=[project.region,project.roadName,project.roadClass,project.nearestDistanceMeters==null?'':`${number(project.nearestDistanceMeters)} m to nearest road`].filter(Boolean).join(' · ');
      content.innerHTML=`<p class="connectivity-map-source-status" role="status">DA crop overlays are temporarily unavailable: the map service returned HTTP 404 for its WMS/WFS endpoint. Municipality outlines, FMR points, road sections and venue points remain visible.</p><p class="connectivity-map-source">The DA catalog identifies rainfed rice/corn, irrigated rice and coconut land-use layers. <a href="https://geomapping.da.gov.ph/prdp/map_generator" target="_blank" rel="noopener noreferrer">Open the DA PRDP Enhanced Geomapping System ↗</a>. These crop-area layers are proxies, not individual farm parcels.</p><div id="connectivity-map-drawing">${svgMap(project,bounds,road)}</div>`;
    }catch(error){content.innerHTML=`<p class="connectivity-map-error">Map layers could not be loaded: ${esc(error.message||error)}</p>`;}
  }
  document.addEventListener('click',event=>{const button=event.target.closest('[data-connectivity-map]');if(!button)return;event.preventDefault();open(button.dataset.connectivityMap);});
})();

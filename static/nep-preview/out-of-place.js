(() => {
  const data = window.OUT_OF_PLACE_DATA;
  const allProjects = data.projects || [];
  let projects = [];
  const mapNode = document.getElementById('map');
  const card = document.getElementById('project-card');
  const listNode = document.getElementById('project-list');
  const countNode = document.getElementById('count');
  const status = document.getElementById('status');
  const search = document.getElementById('search');
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const norm = value => String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  function pointInRings(lon,lat,rings){let inside=false;for(const ring of rings||[]){let hit=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];if((yi>lat)!==(yj>lat)&&lon<(xj-xi)*(lat-yi)/(yj-yi)+xi)hit=!hit;}if(hit)inside=!inside;}return inside;}
  const money = value => '₱' + Number(value || 0).toLocaleString('en-PH');
  const params = new URLSearchParams(location.search);
  let selected = 0;
  let boundaries = {national:[],provinceFeatures:[]};
  document.getElementById('method').textContent = data.method;
  function shareUrl(project) { return project.sharePage || new URL('?project=' + encodeURIComponent(project.id), location.href).href; }
  let focused = true;
  function mapPoint(lon, lat, bounds, rect={x:0,y:0,w:1200,h:900}) {
    const pad=42,centerLat=(bounds.minLat+bounds.maxLat)/2,cos=Math.max(.2,Math.cos(centerLat*Math.PI/180));
    const rx=Math.max(.002,(bounds.maxLon-bounds.minLon)*cos),ry=Math.max(.002,bounds.maxLat-bounds.minLat),scale=Math.min((rect.w-2*pad)/rx,(rect.h-2*pad)/ry);
    const usedW=rx*scale,usedH=ry*scale,left=rect.x+(rect.w-usedW)/2,bottom=rect.y+(rect.h-usedH)/2;
    return {x:left+((lon-bounds.minLon)*cos)*scale,y:rect.y+rect.h-bottom-(lat-bounds.minLat)*scale};
  }
  let boundaryBoxCache = new WeakMap();
  function featureBounds(feature) {
    if (boundaryBoxCache.has(feature)) return boundaryBoxCache.get(feature);
    const box={minLon:Infinity,maxLon:-Infinity,minLat:Infinity,maxLat:-Infinity};
    for(const ring of feature.rings||[]) for(const [lon,lat] of ring){box.minLon=Math.min(box.minLon,lon);box.maxLon=Math.max(box.maxLon,lon);box.minLat=Math.min(box.minLat,lat);box.maxLat=Math.max(box.maxLat,lat);}
    boundaryBoxCache.set(feature,box);return box;
  }
  function featureGap(a,b) { return {x:Math.max(0,a.minLon-b.maxLon,b.minLon-a.maxLon),y:Math.max(0,a.minLat-b.maxLat,b.minLat-a.maxLat)}; }
  function neighborsOf(anchor, pool) {
    if(!anchor)return [];
    const anchorBounds=featureBounds(anchor),limit=.035;
    let neighbors=pool.filter(f=>f!==anchor).filter(f=>{const gap=featureGap(anchorBounds,featureBounds(f));return gap.x<=limit&&gap.y<=limit;});
    if(!neighbors.length) neighbors=pool.filter(f=>f!==anchor).map(f=>({f,g:featureGap(anchorBounds,featureBounds(f))})).sort((a,b)=>Math.hypot(a.g.x,a.g.y)-Math.hypot(b.g.x,b.g.y)).slice(0,1).map(x=>x.f);
    return neighbors;
  }
  function localityFeatures(project) {
    const all=boundaries.provinceFeatures||[];
    const containing=all.find(f=>pointInRings(project.longitude,project.latitude,f.rings));
    const candidates=containing?all.filter(f=>norm(f.province)===norm(containing.province)):all.filter(f=>norm(f.province)===norm(project.province)||(f.nearbyProjectIds||[]).includes(project.id));
    const pool=candidates.length?candidates:all;
    const anchor=containing||pool.slice().sort((a,b)=>{
      const pointBox={minLon:project.longitude,maxLon:project.longitude,minLat:project.latitude,maxLat:project.latitude};
      const ga=featureGap(pointBox,featureBounds(a)),gb=featureGap(pointBox,featureBounds(b));
      return Math.hypot(ga.x*Math.cos(project.latitude*Math.PI/180),ga.y)-Math.hypot(gb.x*Math.cos(project.latitude*Math.PI/180),gb.y);
    })[0];
    return {features:anchor?[anchor,...neighborsOf(anchor,pool)]:[],containing,anchor};
  }
  function intendedLocalityFeatures(project) {
    const all=boundaries.provinceFeatures||[];
    const named=all.filter(f=>isNamedIntendedLocality(project,f)).sort((a,b)=>(Number(norm(b.province)===norm(project.province))-Number(norm(a.province)===norm(project.province)))||((b.city||b.municipality||'').length-(a.city||a.municipality||'').length));
    if(named.length){
      const anchor=named[0],pool=all.filter(f=>norm(f.province)===norm(anchor.province));
      return {features:[anchor,...neighborsOf(anchor,pool)],anchor,target:anchor,resolved:true};
    }
    const province=all.filter(f=>norm(f.province)===norm(project.province));
    return {features:province,anchor:null,target:null,resolved:false};
  }
  function isNamedIntendedLocality(project, feature) {
    const place=feature.city||feature.municipality;
    if(!place)return false;
    const base=norm(String(place).replace(/\s*\(capital\)\s*$/i,''));
    const aliases=new Set([base]);
    if(base.startsWith('city of ')){const name=base.slice(8);aliases.add(name);aliases.add(`${name} city`);}
    if(base.endsWith(' city')){const name=base.slice(0,-5);aliases.add(name);aliases.add(`city of ${name}`);}
    const title=` ${norm(project.projectName)} `;
    return [...aliases].filter(Boolean).some(name=>title.includes(` ${name} `));
  }
  function isOutsideResolvedIntendedLocality(project) {
    const intended=intendedLocalityFeatures(project).target;
    return Boolean(intended && !pointInRings(project.longitude,project.latitude,intended.rings));
  }
  function hasInsertionFlag(project) { return (project.analysisFlags||[]).some(flag=>/potential nep insertion/i.test(flag.label||'')); }
  function nearestBoundary(project, features) {
    const radius=6371008.8, lat0=project.latitude*Math.PI/180, cosLat=Math.cos(lat0);
    let best=null;
    for(const feature of features||[]) {
      let distance=Infinity;
      for(const ring of feature.rings||[]) for(let i=0;i<ring.length;i++) {
        const a=ring[i],b=ring[(i+1)%ring.length];
        const ax=(a[0]-project.longitude)*Math.PI/180*radius*cosLat, ay=(a[1]-project.latitude)*Math.PI/180*radius;
        const bx=(b[0]-project.longitude)*Math.PI/180*radius*cosLat, by=(b[1]-project.latitude)*Math.PI/180*radius;
        const dx=bx-ax,dy=by-ay,den=dx*dx+dy*dy;
        const t=den?Math.max(0,Math.min(1,-(ax*dx+ay*dy)/den)):0;
        distance=Math.min(distance,Math.hypot(ax+t*dx,ay+t*dy));
      }
      if(Number.isFinite(distance)&&(!best||distance<best.meters)) best={feature,meters:distance,inside:pointInRings(project.longitude,project.latitude,feature.rings)};
    }
    return best;
  }
  function formatBoundaryDistance(project, local) {
    const candidates=local?.containing?[local.containing]:(local?.features||[]);
    const nearest=nearestBoundary(project,candidates);
    if(!nearest)return 'Not available from mapped boundaries';
    const place=nearest.feature.city||nearest.feature.municipality||'mapped locality';
    const distance=nearest.meters<1000?`${Math.max(10,Math.round(nearest.meters/10)*10).toLocaleString('en-PH')} m`:`${(nearest.meters/1000).toFixed(2)} km`;
    return `About ${distance} from the mapped boundary of ${place}`;
  }
  function locationReviewFlags(project, local) {
    const flags=[];
    const landed=local?.containing;
    if(!landed) flags.push('Coordinate is outside the currently mapped municipality/city boundaries');
    else {
      const intended=(local.features||[]).find(feature=>isNamedIntendedLocality(project,feature));
      const landedPlace=landed.city||landed.municipality||'mapped locality';
      if(intended&&intended.key!==landed.key) flags.push(`Coordinate falls in ${landedPlace}, outside the project-named locality ${intended.city||intended.municipality}`);
      if(project.province&&norm(landed.province)!==norm(project.province)) flags.push(`Coordinate falls in ${landed.province}, outside the province named in the project`);
    }
    return flags;
  }
  function renderMap() {
    const project=projects[selected];
    if(!focused||!project){
      drawComparisonMap([{title:'Philippines overview',kind:'overview',features:boundaries.national||[]}],null);
      document.getElementById('map-view-label').textContent=project?'Philippines overview · select a project point to focus the map':'No projects outside a resolved intended locality';
      return;
    }
    const intended=intendedLocalityFeatures(project),landing=localityFeatures(project);
    const intendedTarget=intended.target;
    const landingTarget=landing.containing||null;
    const intendedName=intendedTarget?(intendedTarget.city||intendedTarget.municipality):null;
    const landingName=landing.containing?(landing.containing.city||landing.containing.municipality):null;
    document.getElementById('map-view-label').textContent=`Project ${selected+1} of ${projects.length} · intended, landing and adjacent areas`;
    const combinedFeatures=[...new Map([...(intended.features||[]),...(landing.features||[])].map(feature=>[feature.key,feature])).values()];
    const intendedTitle=intendedName?`intended · ${intendedName}, ${intendedTarget.province}`:`intended area · ${project.province||'province not resolved'}`;
    const landingTitle=landingName?`landing · ${landingName}, ${landingTarget.province}`:'landing · outside mapped municipalities/cities';
    drawComparisonMap([{title:`${intendedTitle} · ${landingTitle} · adjacent localities`,kind:'combined',features:combinedFeatures,target:intendedTarget,landingKey:landingTarget?.key,project}],project);
  }
  function drawComparisonMap(views,selectedProject) {
    const width=1200,height=900,gap=0,outer=12;
    views=views.slice(0,1); // Always render one map canvas with all intended, landing and adjacent areas.
    const viewWidth=width-outer*2;
    let contents='';
    for(let index=0;index<views.length;index++){
      const view=views[index],rect={x:outer+index*(viewWidth+gap),y:outer,w:viewWidth,h:height-outer*2};
      contents+=`<rect x="${rect.x}" y="${rect.y}" width="${rect.w}" height="${rect.h}" rx="12" fill="#fff" stroke="#E0E0E0"/>`;
      contents+=`<text x="${rect.x+16}" y="${rect.y+25}" class="map-window-title">${esc(view.title)}</text>`;
      const mapRect={x:rect.x+8,y:rect.y+38,w:rect.w-16,h:rect.h-46},features=view.features||[];
      const bounds={minLon:Infinity,maxLon:-Infinity,minLat:Infinity,maxLat:-Infinity};
      for(const f of features)for(const ring of f.rings||[])for(const [lon,lat] of ring){bounds.minLon=Math.min(bounds.minLon,lon);bounds.maxLon=Math.max(bounds.maxLon,lon);bounds.minLat=Math.min(bounds.minLat,lat);bounds.maxLat=Math.max(bounds.maxLat,lat);}
      const plottedProject=view.project||null;
      if(plottedProject){bounds.minLon=Math.min(bounds.minLon,plottedProject.longitude);bounds.maxLon=Math.max(bounds.maxLon,plottedProject.longitude);bounds.minLat=Math.min(bounds.minLat,plottedProject.latitude);bounds.maxLat=Math.max(bounds.maxLat,plottedProject.latitude);}
      if(!Number.isFinite(bounds.minLon)){bounds.minLon=116;bounds.maxLon=127.5;bounds.minLat=4;bounds.maxLat=21.5;}
      if(view.kind==='overview'){bounds.minLon=116;bounds.maxLon=127.5;bounds.minLat=4;bounds.maxLat=21.5;}
      if(plottedProject&&features.length){const padx=Math.max(.02,(bounds.maxLon-bounds.minLon)*.12),pady=Math.max(.02,(bounds.maxLat-bounds.minLat)*.12);bounds.minLon-=padx;bounds.maxLon+=padx;bounds.minLat-=pady;bounds.maxLat+=pady;}
      contents+=features.map(feature=>{
        const path=(feature.rings||[]).map(ring=>'M'+ring.map(([lon,lat],i)=>{const q=mapPoint(lon,lat,bounds,mapRect);return (i?'L':'')+q.x.toFixed(1)+','+q.y.toFixed(1);}).join(' ')+'Z').join(' ');
        const intended=(view.kind==='intended'||view.kind==='combined')&&view.target&&feature.key===view.target.key;
        const landing=view.landingKey&&feature.key===view.landingKey;
        const adjacent=(view.kind==='landing'||view.kind==='combined')&&feature.key!==view.landingKey&&feature.key!==view.target?.key;
        const cls=['map-feature',intended?'intended-area':'',landing?'coordinate-area':'',adjacent?'nearby-feature':''].filter(Boolean).join(' ');
        return `<path class="${cls}" fill-rule="evenodd" d="${path}"/>`;
      }).join('');
      if(plottedProject){const q=mapPoint(plottedProject.longitude,plottedProject.latitude,bounds,mapRect);contents+=`<g class="point selected" role="img" aria-label="Printed project coordinate"><title>Printed project coordinate</title><circle cx="${q.x.toFixed(1)}" cy="${q.y.toFixed(1)}" r="12"/><text x="${q.x.toFixed(1)}" y="${q.y.toFixed(1)}">●</text></g>`;}
      if(view.kind==='overview'){
        contents+=projects.map((item,projectIndex)=>{const q=mapPoint(item.longitude,item.latitude,bounds,mapRect);return `<g class="point" data-index="${projectIndex}" role="button" tabindex="0" aria-label="Project ${projectIndex+1}: ${esc(item.projectName)}"><title>${projectIndex+1}. ${esc(item.projectName)}</title><circle cx="${q.x.toFixed(1)}" cy="${q.y.toFixed(1)}" r="8"/><text x="${q.x.toFixed(1)}" y="${q.y.toFixed(1)}">${projectIndex+1}</text></g>`;}).join('');
      }
    }
    mapNode.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Map showing the intended project area, printed coordinate landing area and adjacent localities"><rect width="${width}" height="${height}" fill="#FAFAFA"/>${contents}</svg>`;
    mapNode.querySelectorAll('[data-index]').forEach(el=>{el.addEventListener('click',()=>select(Number(el.dataset.index)));el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(Number(el.dataset.index));}});});
  }
  function renderCard() {
    const p=projects[selected]; if(!p){card.innerHTML='<p>No project has a coordinate outside a resolved project-named municipality or city.</p>';return;}
    const url=shareUrl(p); const fb='https://www.facebook.com/sharer/sharer.php?u='+encodeURIComponent(url);
    const local=localityFeatures(p); const reviewFlags=[...(p.analysisFlags||[]),...locationReviewFlags(p,local).map(label=>({label}))];
    const flagsHtml=reviewFlags.length?`<section class="review-flags" aria-label="Project review flags">${reviewFlags.map(flag=>`<div class="review-flag"><strong>${esc(flag.label||flag)}</strong>${flag.detail?`<small>${esc(flag.detail)}</small>`:''}</div>`).join('')}</section>`:'<div class="review-flags"><div class="review-flag clear"><strong>No review flags identified by these screens</strong><small>This is not a certification that the project has no issues.</small></div></div>';
    const reps=p.representativeCards||[];
    const facecards=reps.filter(r=>r.photoUrl).map(r=>`<article class="representative-facecard"><a class="face-photo" href="${esc(r.profileUrl||'#')}" target="_blank" rel="noopener"><img src="${esc(r.cachedPhotoUrl || r.photoUrl)}" alt="Official photo of ${esc(r.name||r.officialName||'representative')}" loading="lazy" referrerpolicy="no-referrer"></a><div><strong>${esc(r.name||r.officialName||'Representative')}</strong><span>${esc(r.district||'Geographic district')}</span><a class="face-profile" href="${esc(r.profileUrl||'#')}" target="_blank" rel="noopener">Official House profile ↗</a></div></article>`).join('');
    const facecardHtml=`<section class="representative-section"><h3>Geographic representative</h3>${facecards||'<p>No geographic representative was resolved for this project coordinate.</p>'}<p class="representative-caveat">This is a geographic district association based on the cited location evidence, not evidence of sponsorship.</p></section>`;
    card.innerHTML=`<div class="card-kicker">Project ${selected+1} of ${projects.length} · ${esc(p.coordinateStatus)}</div><button class="map-focus" type="button" id="zoom-to-locality">Focus map ↗</button><h2>${esc(p.projectName)}</h2><div class="office">Listed office: ${esc(p.office || 'Not stated')}</div>${flagsHtml}<dl class="facts"><div><dt>Allocation in HGAB 3rd</dt><dd>${money(p.amountPesos)}</dd></div><div><dt>Named province</dt><dd>${esc(p.province || 'Not resolved from project/office text')}</dd></div><div><dt>Distance to nearest mapped border</dt><dd>${esc(formatBoundaryDistance(p,localityFeatures(p)))}</dd></div><div><dt>Source</dt><dd>${esc(p.sourceVolume || 'HGAB 3rd DPWH schedule')}, PDF page ${esc(p.sourcePage)}</dd></div><div><dt>Project ID</dt><dd>${esc(p.id)}</dd></div></dl>${facecardHtml}<p>The map distinguishes the project-named intended area, the coordinate landing area, and neighboring or nearest localities. Border distance is approximate and follows the mapped city/municipality geometry; a plotted point is a review lead, not a finding.</p><div class="share"><button class="primary" type="button" id="native-share">Share project</button><a href="${fb}" target="_blank" rel="noopener" aria-label="Share this project on Facebook"><strong>f</strong> Share on Facebook</a><a class="copy" href="${url}" id="copy-link">Copy project link</a></div>`;
    document.getElementById('zoom-to-locality').addEventListener('click',()=>{focused=true;renderMap();});
    const nativeShare=document.getElementById('native-share');
    if (!navigator.share) nativeShare.hidden=true;
    nativeShare.addEventListener('click', async () => { try { await navigator.share({title:`Out of place? · ${p.projectName}`,text:`${p.office || 'DPWH project'} · HGAB 3rd project coordinate review. A location signal is a review lead, not a finding.`,url}); } catch (error) { if (error?.name !== 'AbortError') status.textContent='Sharing could not be opened. Use Facebook or copy the project link.'; } });
    document.getElementById('copy-link').addEventListener('click', async e => { e.preventDefault(); try { if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(url); else { const input=document.createElement('textarea'); input.value=url; input.style.position='fixed'; input.style.opacity='0'; document.body.append(input); input.select(); const copied=document.execCommand('copy'); input.remove(); if (!copied) throw new Error('Clipboard unavailable'); } status.textContent='Project link copied.'; } catch { status.textContent='Could not copy the link. Open the project share page to copy its address.'; window.open(url,'_blank','noopener'); } });
  }
  card.addEventListener('click', event => {
    if (event.target.closest('a,button,input,select')) return;
    focused=true;
    renderMap();
  });
  function renderList() {
    const term=search.value.trim().toLowerCase();
    const filtered=projects.map((p,i)=>({p,i})).filter(({p})=>!term||`${p.projectName} ${p.office} ${p.id}`.toLowerCase().includes(term));
    countNode.textContent=`${filtered.length} of ${projects.length} projects`;
    listNode.innerHTML=filtered.map(({p,i})=>`<button type="button" data-index="${i}" aria-current="${i===selected}"><strong>${i+1}. ${esc(p.projectName)}</strong><small>${esc(p.office)} · ${esc(p.coordinateRaw)}</small></button>`).join('');
    listNode.querySelectorAll('[data-index]').forEach(node=>node.addEventListener('click',()=>select(Number(node.dataset.index))));
  }
  function select(index) { if(!projects.length)return; selected=(index+projects.length)%projects.length; focused=true; history.replaceState(null,'','?project='+encodeURIComponent(projects[selected].id)); renderMap(); renderCard(); renderList(); }
  document.getElementById('previous').addEventListener('click',()=>select(selected-1));
  document.getElementById('next').addEventListener('click',()=>select(selected+1));
  document.getElementById('reset-map').addEventListener('click',()=>{focused=false;renderMap();});
  search.addEventListener('input',renderList);
  countNode.textContent='Checking project coordinates against mapped intended localities…';
  fetch('out-of-place-boundaries.json').then(r=>r.ok?r.json():Promise.reject()).then(x=>{boundaries=x;projects=allProjects.filter(isOutsideResolvedIntendedLocality);projects.sort((a,b)=>{const insertionOrder=Number(hasInsertionFlag(b))-Number(hasInsertionFlag(a));if(insertionOrder)return insertionOrder;if(hasInsertionFlag(a))return Number(b.amountPesos||0)-Number(a.amountPesos||0);return Number(a.sourcePage||0)-Number(b.sourcePage||0);});document.getElementById('method').textContent='Shows only projects whose coordinate falls outside a project-named municipality or city. Projects without a resolvable intended locality are omitted because their location cannot be classified as outside.';selected=Math.max(0,projects.findIndex(p=>p.id===params.get('project')));if(!projects.length)status.textContent='No projects fall outside a resolved project-named municipality or city.';renderCard();renderList();renderMap();}).catch(()=>{status.textContent='Mapped boundaries could not load, so outside projects cannot be verified and are not shown.';boundaries={national:[],provinceFeatures:[]};projects=[];selected=0;renderCard();renderList();renderMap();});
})();
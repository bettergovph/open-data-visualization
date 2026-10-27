(() => {
  const data = window.OUT_OF_PLACE_DATA;
  const projects = data.projects || [];
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
  let selected = Math.max(0, projects.findIndex(p => p.id === params.get('project')));
  let boundaries = {national:[],provinceFeatures:[]};
  document.getElementById('method').textContent = data.method;
  function shareUrl(project) { return project.sharePage || new URL('?project=' + encodeURIComponent(project.id), location.href).href; }
  let focused = Boolean(params.get('project'));
  function mapPoint(lon, lat, bounds) {
    const w=1000,h=800,pad=35,centerLat=(bounds.minLat+bounds.maxLat)/2,cos=Math.max(.2,Math.cos(centerLat*Math.PI/180));
    const rx=Math.max(.002,(bounds.maxLon-bounds.minLon)*cos),ry=Math.max(.002,bounds.maxLat-bounds.minLat),scale=Math.min((w-2*pad)/rx,(h-2*pad)/ry);
    const usedW=rx*scale,usedH=ry*scale,left=(w-usedW)/2,bottom=(h-usedH)/2;
    return {x:left+((lon-bounds.minLon)*cos)*scale,y:h-bottom-(lat-bounds.minLat)*scale};
  }
  function renderMap() {
    const selectedProject=projects[selected];
    const province=selectedProject?.province;
    const activeFeatures=focused&&province ? boundaries.provinceFeatures.filter(f=>norm(f.province)===norm(province)||(f.nearbyProjectIds||[]).includes(selectedProject.id)) : boundaries.national;
    const bounds={minLon:Infinity,maxLon:-Infinity,minLat:Infinity,maxLat:-Infinity};
    for(const f of activeFeatures) for(const ring of f.rings||[]) for(const [lon,lat] of ring){bounds.minLon=Math.min(bounds.minLon,lon);bounds.maxLon=Math.max(bounds.maxLon,lon);bounds.minLat=Math.min(bounds.minLat,lat);bounds.maxLat=Math.max(bounds.maxLat,lat);}
    if(focused&&selectedProject){const lon=selectedProject.longitude,lat=selectedProject.latitude;bounds.minLon=Math.min(bounds.minLon,lon);bounds.maxLon=Math.max(bounds.maxLon,lon);bounds.minLat=Math.min(bounds.minLat,lat);bounds.maxLat=Math.max(bounds.maxLat,lat);}
    if(!Number.isFinite(bounds.minLon)){bounds.minLon=116;bounds.maxLon=127.5;bounds.minLat=4;bounds.maxLat=21.5;}
    if(!focused){bounds.minLon=116;bounds.maxLon=127.5;bounds.minLat=4;bounds.maxLat=21.5;}
    if(focused&&province){const padx=Math.max(.06,(bounds.maxLon-bounds.minLon)*.08),pady=Math.max(.06,(bounds.maxLat-bounds.minLat)*.08);bounds.minLon-=padx;bounds.maxLon+=padx;bounds.minLat-=pady;bounds.maxLat+=pady;}
    const coordinateFeature=focused&&selectedProject?activeFeatures.find(f=>pointInRings(selectedProject.longitude,selectedProject.latitude,f.rings)):null;
    const featureSvg=activeFeatures.map(f => {const d=(f.rings||[]).map(ring=>'M'+ring.map(([lon,lat],i)=>{const p=mapPoint(lon,lat,bounds);return (i?'L':'')+p.x.toFixed(1)+','+p.y.toFixed(1);}).join(' ')+'Z').join(' ');const cls=f.key===coordinateFeature?.key?'map-feature coordinate-area':focused&&f.nearbyProjectIds?.includes(selectedProject?.id)&&norm(f.province)!==norm(province)?'map-feature nearby-feature':'map-feature';return `<path class="${cls}" fill-rule="evenodd" d="${d}"/>`;}).join('');
    const points = projects.map((p,i) => { const q=mapPoint(p.longitude,p.latitude,bounds); const visible=!focused||!province||norm(p.province)===norm(province)||i===selected; return visible?`<g class="point ${i===selected?'selected':''}" data-index="${i}" role="button" tabindex="0" aria-label="Project ${i+1}: ${esc(p.projectName)}"><title>${i+1}. ${esc(p.projectName)} · ${esc(p.office)}</title><circle cx="${q.x.toFixed(1)}" cy="${q.y.toFixed(1)}" r="${i===selected?12:8}"/><text x="${q.x.toFixed(1)}" y="${q.y.toFixed(1)}">${i+1}</text></g>`:''; }).join('');
    const foundPlace=coordinateFeature?(coordinateFeature.city||coordinateFeature.municipality):null;
    document.getElementById('map-view-label').textContent=focused&&province?`${province} · ${foundPlace?`coordinate in ${foundPlace}, ${coordinateFeature.province}`:'municipality/city boundaries'}`:'Philippines · all coordinate-bearing projects';
    mapNode.innerHTML = `<svg viewBox="0 0 1000 800" role="img" aria-label="${focused&&province?esc(province)+' municipality and city boundaries':'Philippines map with project coordinates'}"><rect width="1000" height="800" fill="#f8fbfa"/>${featureSvg}${points}</svg>`;
    mapNode.querySelectorAll('[data-index]').forEach(node => { node.addEventListener('click', () => select(Number(node.dataset.index))); node.addEventListener('keydown', e => { if(e.key==='Enter'||e.key===' '){e.preventDefault();select(Number(node.dataset.index));} }); });
  }
  function renderCard() {
    const p=projects[selected]; if(!p){card.innerHTML='<p>No matching project.</p>';return;}
    const url=shareUrl(p); const fb='https://www.facebook.com/sharer/sharer.php?u='+encodeURIComponent(url);
    const reps=p.representativeCards||[];
    const facecards=reps.filter(r=>r.photoUrl).map(r=>`<article class="representative-facecard"><a class="face-photo" href="${esc(r.profileUrl||'#')}" target="_blank" rel="noopener"><img src="${esc(r.photoUrl)}" alt="Official photo of ${esc(r.name||r.officialName||'representative')}" loading="lazy" referrerpolicy="no-referrer"></a><div><strong>${esc(r.name||r.officialName||'Representative')}</strong><span>${esc(r.district||'Geographic district')}</span><a class="face-profile" href="${esc(r.profileUrl||'#')}" target="_blank" rel="noopener">Official House profile ↗</a></div></article>`).join('');
    const facecardHtml=`<section class="representative-section"><h3>Geographic representative</h3>${facecards||'<p>No geographic representative was resolved for this project coordinate.</p>'}<p class="representative-caveat">This is a geographic district association based on the cited location evidence, not evidence of sponsorship.</p></section>`;
    card.innerHTML=`<div class="card-kicker">Project ${selected+1} of ${projects.length} · ${esc(p.coordinateStatus)}</div><h2>${esc(p.projectName)}</h2><div class="office">Listed office: ${esc(p.office || 'Not stated')}</div><dl class="facts"><div><dt>Allocation in HGAB 3rd</dt><dd>${money(p.amountPesos)}</dd></div><div><dt>Named province</dt><dd>${esc(p.province || 'Not resolved from project/office text')}</dd></div><div><dt>Printed coordinate pair</dt><dd>${esc(p.coordinateRaw)} · ${Number(p.latitude).toFixed(6)}, ${Number(p.longitude).toFixed(6)}</dd></div><div><dt>Coordinate order</dt><dd>${esc(p.coordinateOrientation)}</dd></div><div><dt>Source</dt><dd>${esc(p.sourceVolume || 'HGAB 3rd DPWH schedule')}, PDF page ${esc(p.sourcePage)}</dd></div><div><dt>Project ID</dt><dd>${esc(p.id)}</dd></div></dl>${facecardHtml}<p>The province view uses municipality/city shapes from the cached DPWH boundary layer. The title’s place and DEO/LEG text are shown for comparison; the map is a review lead, not a finding.</p><div class="share"><button class="primary" type="button" id="native-share">Share project</button><a href="${fb}" target="_blank" rel="noopener" aria-label="Share this project on Facebook"><strong>f</strong> Share on Facebook</a><a class="copy" href="${url}" id="copy-link">Copy project link</a></div>`;
    const nativeShare=document.getElementById('native-share');
    if (!navigator.share) nativeShare.hidden=true;
    nativeShare.addEventListener('click', async () => { try { await navigator.share({title:`Out of place? · ${p.projectName}`,text:`${p.office || 'DPWH project'} · HGAB 3rd project coordinate review. A location signal is a review lead, not a finding.`,url}); } catch (error) { if (error?.name !== 'AbortError') status.textContent='Sharing could not be opened. Use Facebook or copy the project link.'; } });
    document.getElementById('copy-link').addEventListener('click', async e => { e.preventDefault(); try { if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(url); else { const input=document.createElement('textarea'); input.value=url; input.style.position='fixed'; input.style.opacity='0'; document.body.append(input); input.select(); const copied=document.execCommand('copy'); input.remove(); if (!copied) throw new Error('Clipboard unavailable'); } status.textContent='Project link copied.'; } catch { status.textContent='Could not copy the link. Open the project share page to copy its address.'; window.open(url,'_blank','noopener'); } });
  }
  function renderList() {
    const term=search.value.trim().toLowerCase();
    const filtered=projects.map((p,i)=>({p,i})).filter(({p})=>!term||`${p.projectName} ${p.office} ${p.id}`.toLowerCase().includes(term));
    countNode.textContent=`${filtered.length} of ${projects.length} projects`;
    listNode.innerHTML=filtered.map(({p,i})=>`<button type="button" data-index="${i}" aria-current="${i===selected}"><strong>${i+1}. ${esc(p.projectName)}</strong><small>${esc(p.office)} · ${esc(p.coordinateRaw)}</small></button>`).join('');
    listNode.querySelectorAll('[data-index]').forEach(node=>node.addEventListener('click',()=>select(Number(node.dataset.index))));
  }
  function select(index) { selected=(index+projects.length)%projects.length; focused=true; history.replaceState(null,'','?project='+encodeURIComponent(projects[selected].id)); renderMap(); renderCard(); renderList(); }
  document.getElementById('previous').addEventListener('click',()=>select(selected-1));
  document.getElementById('next').addEventListener('click',()=>select(selected+1));
  document.getElementById('reset-map').addEventListener('click',()=>{focused=false;renderMap();});
  search.addEventListener('input',renderList);
  renderCard(); renderList();
  fetch('out-of-place-boundaries.json').then(r=>r.ok?r.json():Promise.reject()).then(x=>{boundaries=x;renderMap();}).catch(()=>{status.textContent='Cached municipality/city boundaries could not load; project points and cards remain available.';boundaries={national:[],provinceFeatures:[]};renderMap();});
})();

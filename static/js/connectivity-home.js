(() => {
  const map = document.getElementById('ph-map');
  const layer = document.getElementById('municipality-layer');
  const details = document.getElementById('detail-content');
  const status = document.getElementById('map-status');
  const search = document.getElementById('place-search');
  const results = document.getElementById('search-results');
  const fmt = n => Number(n || 0).toLocaleString('en-PH');
  const money = n => '₱' + Number(n || 0).toLocaleString('en-PH', {maximumFractionDigits:0});
  const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const colors = ['#E7EEF5','#C1D0EC','#8FA9DA','#5177C4','#0038A8'];
  let features = [], selectedLayer = 'road', selected = null, baseView = [0,0,760,1120];
  const projectLabel = {road:'DPWH roads',bridge:'DPWH bridges',fmr:'FY2027 FMR proposals'};
  const xy = ([lon,lat]) => [((lon-116.3)*67).toFixed(1),((21.3-lat)*65).toFixed(1)];
  const pathFor = f => (f.rings||[]).map(r=>r.map((p,i)=>{const [x,y]=xy(p);return `${i?'L':'M'}${x},${y}`}).join(' ')+' Z').join(' ');
  function count(f){return Number(f.counts?.[selectedLayer]||0)}
  function fillFor(f){const n=count(f);if(!n)return colors[0];const max=Math.max(...features.map(count),1),score=n/max;return colors[Math.min(4,Math.max(1,Math.ceil(score*4)))];}
  function renderMap(){
    layer.innerHTML=features.map(f=>`<path class="map-land${selected===f?' selected':''}" d="${pathFor(f)}" fill="${fillFor(f)}" fill-rule="evenodd" tabindex="0" role="button" aria-label="${esc(f.name)}, ${esc(f.province)} · ${fmt(count(f))} ${projectLabel[selectedLayer].toLowerCase()}" data-key="${esc(f.key)}"><title>${esc(f.name)}, ${esc(f.province)} · ${fmt(count(f))} ${projectLabel[selectedLayer].toLowerCase()}</title></path>`).join('');
    layer.querySelectorAll('.map-land').forEach(el=>{const f=features.find(x=>x.key===el.dataset.key);el.addEventListener('click',()=>select(f));el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(f)}})});
    const label=projectLabel[selectedLayer];document.getElementById('legend-title').textContent=`${label} · lighter to darker`;
  }
  function select(f){if(selected)layer.querySelector(`[data-key="${CSS.escape(selected.key)}"]`)?.classList.remove('selected');selected=f;layer.querySelector(`[data-key="${CSS.escape(f.key)}"]`)?.classList.add('selected');showDetails(f);}
  function showDetails(f){
    const items=f.items?.[selectedLayer]||[], sorted=[...items].sort((a,b)=>Number(b.amount||0)-Number(a.amount||0));
    const counts=f.counts||{}, totals=f.totals||{};
    const titleRows=sorted.slice(0,60).map(x=>`<article class="project"><h4>${esc(x.title||'Untitled project')}</h4><p>${money(x.amount)}${x.sourcePage?` · Source p. ${esc(x.sourcePage)}`:''}${x.source?` · ${esc(x.source)}`:''}</p></article>`).join('');
    details.innerHTML=`<p class="kicker">${esc(f.province)}${f.city?' · city':' · municipality'}</p><h3>${esc(f.name)}</h3><div class="stat-grid"><div class="stat road"><strong>${fmt(counts.road)}</strong><span>Named DPWH road rows</span></div><div class="stat bridge"><strong>${fmt(counts.bridge)}</strong><span>Named DPWH bridge rows</span></div><div class="stat fmr"><strong>${fmt(counts.fmr)}</strong><span>FMR endpoint matches</span></div></div><div class="amount-line">Road allocations <b>${money(totals.road)}</b></div><div class="amount-line">Bridge allocations <b>${money(totals.bridge)}</b></div><div class="amount-line">FMR proposals <b>${money(totals.fmr)}</b></div><h4 style="margin:18px 0 4px;font-size:14px">${projectLabel[selectedLayer]} · ${fmt(items.length)} records</h4><div class="project-list">${titleRows||'<p class="prompt">No records are matched to this municipality in the selected layer.</p>'}${items.length>60?`<p class="prompt">Showing 60 of ${fmt(items.length)} matched project records, ordered by amount.</p>`:''}</div>`;
  }
  function renderSearch(){
    const q=search.value.trim().toLocaleLowerCase('en');
    if(q.length<2){results.innerHTML='';return;}
    const matches=features.filter(f=>`${f.name} ${f.province}`.toLocaleLowerCase('en').includes(q)).slice(0,12);
    results.innerHTML=matches.length?`<div class="project-list" style="max-height:230px">${matches.map(f=>`<button type="button" data-key="${esc(f.key)}" style="display:block;width:100%;padding:9px 3px;border:0;border-bottom:1px solid #E0E0E0;background:#fff;text-align:left;cursor:pointer"><strong>${esc(f.name)}</strong><small style="display:block;color:#616161">${esc(f.province)} · ${fmt(f.counts?.[selectedLayer])} ${projectLabel[selectedLayer].toLowerCase()}</small></button>`).join('')}</div>`:'<p class="prompt">No municipality found.</p>';
    results.querySelectorAll('button[data-key]').forEach(b=>b.addEventListener('click',()=>{const f=features.find(x=>x.key===b.dataset.key);if(f){select(f);focus(f)}}));
  }
  function focus(f){const [x0,y0,x1,y1]=f.bbox, cx=(x0+x1)/2,cy=(y0+y1)/2,w=Math.max(.12,x1-x0)*85,h=Math.max(.12,y1-y0)*85, aspect=760/1120;let vw=Math.max(w,h*aspect)*1.8,vh=vw/aspect;const vx=(cx-116.3)*67-vw/2,vy=(21.3-cy)*65-vh/2;map.setAttribute('viewBox',`${vx} ${vy} ${vw} ${vh}`)}
  async function init(){
    try{
      const r=await fetch('/static/data/connectivity-landing.json');if(!r.ok)throw Error(`Map data returned ${r.status}`);const data=await r.json();features=data.features||[];if(!features.length)throw Error('No municipality boundaries were found.');
      renderMap();const covered=features.filter(f=>f.counts?.road||f.counts?.bridge||f.counts?.fmr).length;
      status.textContent=`${fmt(features.length)} municipality and city boundaries · ${fmt(covered)} with at least one mapped project · select an area to inspect records`;
      document.getElementById('attribution').innerHTML=`Boundary source: ${esc(data.boundarySource)} <a href="https://github.com/faeldon/philippines-json-maps" target="_blank" rel="noopener noreferrer">dataset details ↗</a>; underlying boundaries from <a href="https://data.humdata.org/dataset/cod-ab-phl" target="_blank" rel="noopener noreferrer">NAMRIA and PSA via OCHA COD-AB (CC BY-IGO) ↗</a>. ${esc(data.roadBridgeSource)}. ${esc(data.fmrSource)}.`;
      const top=[...features].sort((a,b)=>b.counts.road-a.counts.road).slice(0,5);
      details.innerHTML=`<p class="kicker">National view · FY2027 proposals</p><h3>Explore by municipality</h3><p class="prompt">Select a shaded municipality to see its project rows. Darker shading means more records in the selected layer; it does not indicate project quality or completion.</p><h4 style="font-size:14px">Most named road rows</h4>${top.map((f,i)=>`<button type="button" data-key="${esc(f.key)}" style="display:flex;width:100%;justify-content:space-between;padding:10px 2px;border:0;border-bottom:1px solid #E0E0E0;background:#fff;text-align:left;cursor:pointer"><span>${i+1}. ${esc(f.name)}, ${esc(f.province)}</span><b>${fmt(f.counts.road)}</b></button>`).join('')}`;
      details.querySelectorAll('button[data-key]').forEach(b=>b.addEventListener('click',()=>{const f=features.find(x=>x.key===b.dataset.key);select(f);focus(f)}));
    }catch(e){status.textContent='The municipality map could not be loaded.';layer.innerHTML='';details.innerHTML=`<p class="load-error">${esc(e.message||e)}</p>`;}
  }
  document.querySelectorAll('[data-layer]').forEach(button=>button.addEventListener('click',()=>{selectedLayer=button.dataset.layer;document.querySelectorAll('[data-layer]').forEach(x=>x.setAttribute('aria-pressed',String(x===button)));renderMap();if(selected)showDetails(selected);renderSearch()}));
  search.addEventListener('input',renderSearch);
  document.getElementById('zoom-in').addEventListener('click',()=>{const [x,y,w,h]=map.getAttribute('viewBox').split(' ').map(Number),nw=w*.72,nh=h*.72;map.setAttribute('viewBox',`${x+(w-nw)/2} ${y+(h-nh)/2} ${nw} ${nh}`)});
  document.getElementById('zoom-out').addEventListener('click',()=>{const [x,y,w,h]=map.getAttribute('viewBox').split(' ').map(Number),nw=Math.min(760,w/0.72),nh=Math.min(1120,h/0.72);map.setAttribute('viewBox',`${x-(nw-w)/2} ${y-(nh-h)/2} ${nw} ${nh}`)});
  document.getElementById('zoom-reset').addEventListener('click',()=>map.setAttribute('viewBox',baseView.join(' ')));
  init();
})();

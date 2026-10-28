(()=>{
  const root=document.getElementById('deo-change-explorer');
  if(!root)return;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const peso=value=>'₱'+Number(value||0).toLocaleString('en-PH');
  const signedPeso=value=>(value>0?'+':value<0?'−':'')+'₱'+Math.abs(Number(value||0)).toLocaleString('en-PH');
  const mapPair=document.getElementById('deo-change-map-pair');
  const card=document.getElementById('deo-change-card');
  const list=document.getElementById('deo-change-list');
  const search=document.getElementById('deo-change-search');
  const status=document.getElementById('deo-change-count');
  const previous=document.getElementById('deo-change-previous');
  const next=document.getElementById('deo-change-next');
  let offices={},all=[],visible=[],selected=0;

  function renderOffice(office,side){
    const title=esc(office?.name||'Office boundary unavailable');
    if(office?.kind==='central')return `<div class="deo-change-mapbox deo-change-central"><img src="dpwh-logo.svg" alt="Department of Public Works and Highways seal"><strong>DPWH</strong><span>Central Office</span></div>`;
    if(!['deo','aggregate'].includes(office?.kind)||!office.rings?.length)return `<div class="deo-change-mapbox deo-change-unresolved"><strong>${title}</strong><span>No single matching DEO boundary in the source snapshot</span></div>`;
    const points=office.rings.flat();
    const midLat=points.reduce((sum,p)=>sum+p[1],0)/points.length,cos=Math.max(.25,Math.cos(midLat*Math.PI/180));
    const xy=points.map(p=>[p[0]*cos,-p[1]]),xs=xy.map(p=>p[0]),ys=xy.map(p=>p[1]);
    const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    const width=340,height=220,pad=17,scale=Math.min((width-pad*2)/Math.max(maxX-minX,1e-8),(height-pad*2)/Math.max(maxY-minY,1e-8));
    const dx=(width-(maxX-minX)*scale)/2,dy=(height-(maxY-minY)*scale)/2;
    const paths=office.rings.map(ring=>ring.map((p,i)=>{const x=dx+(p[0]*cos-minX)*scale,y=dy+(-p[1]-minY)*scale;return `${i?'L':'M'}${x.toFixed(1)},${y.toFixed(1)}`}).join(' ')+' Z').join(' ');
    return `<div class="deo-change-mapbox"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Mapped engineering district area for ${title}"><rect width="${width}" height="${height}" rx="10" fill="#FAFAFA"/><path class="deo-boundary ${side}" d="${paths}" fill-rule="evenodd"/></svg><strong>${title}</strong><span>${esc([office.province,office.region].filter(Boolean).join(' · '))}${office.kind==='aggregate'?' · aggregate, not one DEO':''}</span></div>`;
  }

  function draw(){
    visible=all.filter(row=>`${row.title} ${row.nepOffice} ${row.hgabOffice}`.toLowerCase().includes(search.value.trim().toLowerCase()));
    if(!visible.length){status.textContent='No office-change records match this search.';mapPair.innerHTML='';card.innerHTML='';list.innerHTML='';previous.disabled=next.disabled=true;return;}
    selected=Math.min(selected,visible.length-1);
    const row=visible[selected],from=offices[row.nepOffice],to=offices[row.hgabOffice],delta=Number(row.hgabAmountPesos||0)-Number(row.nepAmountPesos||0);
    status.textContent=`${selected+1} of ${visible.length} office changes`;
    previous.disabled=selected===0;next.disabled=selected>=visible.length-1;
    mapPair.innerHTML=`${renderOffice(from,'from')}<div class="deo-change-arrow" aria-hidden="true">→</div>${renderOffice(to,'to')}`;
    card.innerHTML=`<div class="deo-change-kicker">Office change ${selected+1} of ${visible.length} · HGAB 3rd PDF p. ${esc(row.hgabPage)}</div><h3>${esc(row.title)}</h3><div class="deo-change-offices"><div><small>NEP office</small><strong>${esc(row.nepOffice)}</strong></div><div><small>HGAB 3rd office</small><strong>${esc(row.hgabOffice)}</strong></div></div><div class="deo-change-cost"><div><small>NEP allocation</small><strong>${peso(row.nepAmountPesos)}</strong></div><div><small>HGAB 3rd allocation</small><strong>${peso(row.hgabAmountPesos)}</strong></div><div class="deo-change-delta"><small>Allocation change</small><strong>${signedPeso(delta)}</strong><small>${delta>0?'increase':delta<0?'decrease':'no change'}${row.nepAmountPesos?` · ${delta>0?'+':''}${(delta/Number(row.nepAmountPesos)*100).toFixed(1)}%`:''}</small></div></div><p class="deo-change-source">NEP PDF p. ${esc(row.nepPage)} → HGAB 3rd PDF p. ${esc(row.hgabPage)}. The map shows the DPWH engineering-district areas associated with the listed offices.</p>`;
    list.innerHTML=visible.map((item,i)=>`<button type="button" data-index="${i}" aria-current="${i===selected}"><strong>${esc(item.title)}</strong><small>${esc(item.nepOffice)} → ${esc(item.hgabOffice)}</small><small>${signedPeso(Number(item.hgabAmountPesos||0)-Number(item.nepAmountPesos||0))} allocation change</small></button>`).join('');
    list.querySelectorAll('[data-index]').forEach(button=>button.addEventListener('click',()=>{selected=Number(button.dataset.index);draw()}));
  }
  search.addEventListener('input',()=>{selected=0;draw()});
  previous.addEventListener('click',()=>{selected=Math.max(0,selected-1);draw()});
  next.addEventListener('click',()=>{selected=Math.min(visible.length-1,selected+1);draw()});
  fetch(root.dataset.source).then(response=>{if(!response.ok)throw Error('Office boundary data could not be loaded.');return response.json()}).then(data=>{offices=data.offices||{};all=data.projects||[];draw()}).catch(error=>{status.textContent=error.message;mapPair.innerHTML='';card.innerHTML='<p>Office-change maps could not be loaded.</p>';});
})();

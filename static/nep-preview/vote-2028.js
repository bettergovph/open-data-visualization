(()=>{
  'use strict';
  const $=id=>document.getElementById(id),yearFilter=$('vote-year'),officeFilter=$('vote-office'),search=$('vote-search'),body=$('vote-body'),status=$('vote-status'),prev=$('vote-prev'),next=$('vote-next'),pageLabel=$('vote-page'),dialog=$('vote-dialog');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=n=>Number(n||0).toLocaleString('en-PH');
  const fmtYear=y=>y==null||y===''?'—':String(Number.isFinite(Number(y))?Number(y):y);
  const key=v=>String(v||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toUpperCase().replace(/[^A-Z0-9]/g,'');
  const place=r=>[r.municipality,r.province].filter(Boolean).join(', ')||r.district||r.region||'Place not recorded';
  const term=o=>`${fmtYear(o.officeStartYear??o.electionYear)}–${fmtYear(o.termThroughYear)}`;
  let people=[],families={},familyEvidence={},page=0,pageSize=50,view=[],sourceNames=new Map();
  function sourceLink(url,label){return /^https?:\/\//i.test(url||'')?`<a href="${esc(url)}" target="_blank" rel="noreferrer">${esc(label||sourceNames.get(url)||'Source')}</a>`:''}
  const urls=o=>[...new Set([o.roleSourceUrl,...(o.roleSourceUrls||[]),...(o.sourceUrls||[])].filter(Boolean))];
  function officeSources(o){return urls(o).map((url,i)=>sourceLink(url,`Source${urls(o).length>1?' '+(i+1):''}`)).join(' · ')}
  function pastText(p){return (p.pastPositions||[]).map(o=>`${o.position} · ${place(o)} · ${o.terms.map(term).join(', ')}`).join('; ')}
  function familyMembers(p){
    const members=new Map();
    for(const fk of p.familyKeys||[])for(const m of families[fk]||[]){
      if((p.personKeys||[]).includes(m.personKey)||key(m.name)===key(p.name))continue;
      const k=key(m.name),entry=members.get(k)||{...m,offices:[]};
      for(const office of m.offices||[])if(!entry.offices.some(x=>JSON.stringify(x)===JSON.stringify(office)))entry.offices.push(office);
      members.set(k,entry);
    }
    return [...members.values()].sort((a,b)=>a.name.localeCompare(b.name));
  }
  function overlaps(p){
    const members=new Map(),qualifying=new Set(p.noVoteYears||[]);
    for(const office of p.offices||[])for(const other of office.concurrentFamilyOfficeholders||[]){
      if(key(other.name)===key(p.name)||(p.personKeys||[]).includes(other.personKey))continue;
      const years=(other.overlapYears||[]).filter(y=>qualifying.has(y));if(!years.length)continue;
      const k=key(other.name),entry=members.get(k)||{name:other.name,aliases:other.aliases||[],offices:[],overlapYears:new Set()};
      years.forEach(y=>entry.overlapYears.add(y));
      const detail={...other,overlapYears:years};
      if(!entry.offices.some(o=>o.position===detail.position&&o.electionYear===detail.electionYear&&place(o)===place(detail)))entry.offices.push(detail);
      members.set(k,entry);
    }
    return [...members.values()].sort((a,b)=>a.name.localeCompare(b.name));
  }
  function evidenceFor(p){const entries=[];for(const fk of p.familyKeys||[])for(const item of familyEvidence[fk]||[])if(!entries.some(x=>x.relationship===item.relationship&&x.sourceUrl===item.sourceUrl))entries.push(item);return entries}
  function filtered(){
    const yr=yearFilter.value,office=officeFilter.value,q=search.value.trim().toLowerCase();
    return people.filter(p=>(p.offices||[]).some(o=>(!yr||String(o.electionYear)===yr)&&(!office||o.officeGroup===office))&&(!q||[p.name,...(p.aliases||[]),...(p.offices||[]).flatMap(o=>[o.position,o.officeGroup,o.province,o.municipality,o.district,o.party]),...familyMembers(p).map(m=>m.name)].join(' ').toLowerCase().includes(q)))
      .sort((a,b)=>a.powerRank-b.powerRank||a.name.localeCompare(b.name));
  }
  function render(){
    view=filtered();const pages=Math.max(1,Math.ceil(view.length/pageSize));page=Math.min(page,pages-1);
    body.innerHTML=view.slice(page*pageSize,(page+1)*pageSize).map((p,i)=>{
      const rowId=page*pageSize+i,o=p.latestOffice,connections=overlaps(p),history=familyMembers(p);
      const alias=(p.aliases||[]).length?`<small>Also recorded as: ${esc(p.aliases.join(', '))}</small>`:'';
      const initials=p.name.split(/\s+/).filter(Boolean).slice(0,2).map(x=>x[0]).join('').toUpperCase();const portrait=p.portrait?`<a class="vote-portrait-link" href="${esc(p.portrait.sourceUrl||'#')}" target="_blank" rel="noreferrer" aria-label="Open portrait source for ${esc(p.name)}"><img class="vote-portrait" src="${esc(p.portrait.localUrl)}" alt="Portrait of ${esc(p.name)}" loading="lazy"></a>`:`<span class="vote-portrait-missing" title="No verified portrait matched in the current database" aria-label="No verified portrait matched">${esc(initials)}</span>`;const portraitSource=p.portrait?.sourceUrl?`<small class="vote-photo-source"><a href="${esc(p.portrait.sourceUrl)}" target="_blank" rel="noreferrer">Photo source${p.portrait.photoCongress?` · ${esc(p.portrait.photoCongress)}th Congress`:''}</a></small>`:'';
      const past=(p.pastPositions||[]).map(position=>`<div class="vote-past-position"><strong>${esc(position.position)}</strong><small>${esc(place(position))} · ${esc(position.terms.map(term).join(', '))}</small>${officeSources(position)?`<small>${officeSources(position)}</small>`:''}</div>`).join('')||'<span class="vote-clear">No earlier position recorded</span>';
      return `<tr><td><span class="vote-mark" role="img" aria-label="Qualifying family overlap in at least one modeled year"></span></td><td><div class="vote-person-block">${portrait}<div class="vote-person-info"><span class="vote-person">${esc(p.name)}</span>${alias}${p.personKeys.length>1?'<small>Multiple source identities retained; check places and evidence.</small>':''}${portraitSource}</div></div></td><td>${esc(o.position)}<small>${esc(o.officeGroup)} · ${term(o)}</small>${officeSources(o)?`<small>${officeSources(o)}</small>`:''}</td><td>${past}</td><td>${esc(place(o))}</td><td>${esc(o.party||'—')}</td><td>${esc(p.electionYears.join(', '))}<small>Criterion years: ${esc(p.noVoteYears.join(', '))}</small></td><td>${connections.length?`<button type="button" class="vote-detail-btn" data-row="${rowId}">${fmt(connections.length)} people · overlap details</button>`:'—'}</td><td>${history.length?`<button type="button" class="vote-detail-btn" data-history-row="${rowId}">${fmt(history.length)} people · history</button>`:'No linked family history'}</td></tr>`;
    }).join('')||`<tr><td colspan="9">${search.value.trim()?`VOTE for ${esc(search.value.trim())}`:'No names match these filters.'}</td></tr>`;
    const first=view.length?page*pageSize+1:0,last=Math.min((page+1)*pageSize,view.length);
    status.textContent=`${fmt(first)}–${fmt(last)} of ${fmt(view.length)} unique names · sorted by highest recorded office, then name. Year and office filters match the same recorded term.`;
    pageLabel.textContent=`Page ${fmt(page+1)} of ${fmt(pages)}`;prev.disabled=page===0;next.disabled=page>=pages-1;
  }
  function setup(data){
    people=data.people||[];families=data.families||{};familyEvidence=data.familyLinkEvidence||{};
    const photoCoverage=$('vote-photo-coverage');if(photoCoverage){const count=people.filter(p=>p.portrait).length;photoCoverage.textContent=`Verified portrait matches: ${fmt(count)} of ${fmt(people.length)} unique names. Initials mark records without a verified portrait match; similar names are left unpictured.`}
    sourceNames=new Map((data.reviewedOnlineSources||[]).map(s=>[s.url,s.title]));
    $('vote-total').textContent=fmt(data.summary?.officialRows||0);
    $('vote-no-total').textContent=fmt(people.length);
    $('vote-house-total').textContent=fmt(data.summary?.currentHouseRosterRows||0);
    $('vote-house-linked').textContent=fmt(data.summary?.currentHouseFamilyLinkedRows||0);
    $('vote-house-family-groups').textContent=fmt(data.summary?.currentHouseHistoricalFamilyPageGroupMatches||0);
    $('vote-house-dynasty').textContent=fmt(data.summary?.currentHouseHistoricalDynastyScreenFlags||0);
    $('vote-year-range').textContent=(data.years||[]).length?`${data.years[0]}–${data.years[data.years.length-1]}`:'—';
    drawYearChart(data.summary?.uniqueNamesByYear||{});
    for(const y of [...new Set(people.flatMap(p=>p.electionYears))].sort((a,b)=>b-a)){const o=document.createElement('option');o.value=String(y);o.textContent=String(y);yearFilter.append(o)}
    for(const name of [...new Set(people.flatMap(p=>p.officeGroups))].sort((a,b)=>a.localeCompare(b))){const o=document.createElement('option');o.value=name;o.textContent=name;officeFilter.append(o)}
    const catalog=$('vote-online-source-list');if(catalog)catalog.innerHTML=(data.reviewedOnlineSources||[]).map(s=>`<li>${sourceLink(s.url,s.title)} <small>Reviewed ${esc(s.reviewedAt)}</small></li>`).join('');
    const note=$('vote-enrichment-note');if(note)note.textContent=`Latest source review: ${data.onlineEnrichment?.reviewedAt||'not stated'} · ${fmt(data.onlineEnrichment?.reviewedPeople)} named officials and ${fmt(data.onlineEnrichment?.reviewedOfficeTerms)} office terms checked against ${fmt((data.reviewedOnlineSources||[]).length)} cited online sources. These records supplement the archive and include corrections to historical office labels.`;
    [yearFilter,officeFilter,search].forEach(el=>el.addEventListener(el===search?'input':'change',()=>{page=0;render()}));
    prev.onclick=()=>{if(page>0){page--;render()}};next.onclick=()=>{page++;render()};
    body.addEventListener('click',e=>{
      const button=e.target.closest('[data-row],[data-history-row]');if(!button)return;
      const p=view[Number(button.dataset.row??button.dataset.historyRow)];if(!p)return;
      $('vote-dialog-title').textContent=p.name;
      const history=button.hasAttribute('data-history-row');
      $('vote-dialog-note').textContent=history?'Linked family members and their recorded elected offices. Source identities, office terms and citations are retained.':'Distinct linked family members with modeled overlap in the criterion years: '+p.noVoteYears.join(', ')+'.';
      let entries;
      if(history){entries=familyMembers(p).map(m=>`<li><strong>${esc(m.name)}</strong>${m.offices.map(o=>`<br>${esc(o.position)} · ${esc(place(o))} · ${term(o)}${officeSources(o)?`<br>${officeSources(o)}`:''}`).join('')}</li>`)}
      else{entries=overlaps(p).map(m=>`<li><strong>${esc(m.name)}</strong><small>Overlap years: ${esc([...m.overlapYears].sort((a,b)=>a-b).join(', '))}</small>${m.offices.map(o=>`<br>${esc(o.position)} · ${esc(place(o))} · election ${fmt(o.electionYear)}`).join('')}</li>`)}
      const evidence=evidenceFor(p).map(item=>`<li><strong>Family relationship evidence:</strong> ${esc(item.relationship)} · ${sourceLink(item.sourceUrl)}</li>`);
      $('vote-dialog-list').innerHTML=[...entries,...evidence].join('')||'<li>No linked details are recorded.</li>';dialog.showModal();
    });
    $('vote-dialog-close').onclick=()=>dialog.close();dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
    $('vote-export').onclick=()=>{
      const columns=['Name','Recorded aliases','Latest recorded office','Highest recorded office rank','Latest place','Latest party','Recorded election years','Past positions','All recorded office terms','Role evidence URLs','Family relationship evidence URLs','Concurrent family members','Criterion overlap years','Historical family members'];
      const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';
      const csv=[columns,...view.map(p=>[p.name,(p.aliases||[]).join('; '),p.latestOffice.position,p.powerRank+1,place(p.latestOffice),p.latestOffice.party,p.electionYears.join('; '),pastText(p),p.offices.map(o=>`${o.position} · ${place(o)} · ${term(o)}`).join('; '),[...new Set(p.offices.flatMap(urls))].join('; '),[...new Set(evidenceFor(p).map(e=>e.sourceUrl))].join('; '),overlaps(p).map(m=>m.name).join('; '),p.noVoteYears.join('; '),familyMembers(p).map(m=>m.name).join('; ')])].map(row=>row.map(quote).join(',')).join('\r\n');
      const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='vote-2028-unique-names.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
    render();
  }
  function drawYearChart(byYear){
    const svg=$('vote-year-chart'),years=Object.keys(byYear).sort((a,b)=>Number(a)-Number(b));
    if(!years.length){svg.innerHTML='<text x="24" y="40">No screened names by year are available.</text>';return}
    const values=years.map(y=>Number(byYear[y]||0)),max=Math.max(1,...values),left=52,right=18,top=26,bottom=48,w=800,h=280,pw=w-left-right,ph=h-top-bottom,step=pw/years.length,bw=Math.min(58,step*.56);
    const ticks=[0,Math.ceil(max/2),max].filter((v,i,a)=>a.indexOf(v)===i);let parts=[`<title>Unique screened names by recorded election year</title><desc>${years.map((y,i)=>`${y}: ${values[i]}`).join('; ')}</desc>`];
    for(const tick of ticks){const y=top+ph-tick/max*ph;parts.push(`<line x1="${left}" y1="${y}" x2="${w-right}" y2="${y}" stroke="#dfe6ec"/><text x="${left-9}" y="${y+4}" text-anchor="end">${fmt(tick)}</text>`)}
    years.forEach((year,i)=>{const x=left+i*step+(step-bw)/2,bh=values[i]/max*ph,y=top+ph-bh;parts.push(`<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="5" fill="#b42318"><title>${year}: ${fmt(values[i])} unique names</title></rect><text class="chart-value" x="${x+bw/2}" y="${Math.max(top-4,y-7)}" text-anchor="middle">${fmt(values[i])}</text><text x="${x+bw/2}" y="${h-17}" text-anchor="middle">${year}</text>`)});
    parts.push(`<line x1="${left}" y1="${top+ph}" x2="${w-right}" y2="${top+ph}" stroke="#8d9ba5"/>`);svg.innerHTML=parts.join('');
  }
  fetch('vote-2028-data.json?v=dea3eb1becb9').then(r=>{if(!r.ok)throw Error('Vote 2028 data is unavailable');return r.json()}).then(setup).catch(e=>{status.textContent=`Could not load the historical records: ${e.message}`;body.innerHTML='<tr><td colspan="9">The dataset could not be loaded.</td></tr>'});
})();

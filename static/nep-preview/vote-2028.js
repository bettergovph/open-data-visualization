(()=>{
  const $=id=>document.getElementById(id),yearFilter=$('vote-year'),officeFilter=$('vote-office'),search=$('vote-search'),body=$('vote-body'),status=$('vote-status'),prev=$('vote-prev'),next=$('vote-next'),pageLabel=$('vote-page'),dialog=$('vote-dialog');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=n=>Number(n||0).toLocaleString('en-PH');
  const place=r=>[r.municipality,r.province].filter(Boolean).join(', ')||r.district||r.region||'Place not recorded';
  let records=[],families={},page=0,pageSize=50,view=[];
  function filtered(){
    const yr=yearFilter.value,office=officeFilter.value,q=search.value.trim().toLowerCase();
    return records.filter(r=>(!yr||String(r.electionYear)===yr)&&(!office||r.officeGroup===office)&&(!q||`${r.name} ${r.position} ${r.officeGroup} ${r.province} ${r.municipality} ${r.district} ${r.party} ${(r.concurrentFamilyOfficeholders||[]).map(x=>x.name+' '+x.position).join(' ')}`.toLowerCase().includes(q)))
      .sort((a,b)=>Number(b.doNotVote)-Number(a.doNotVote)||b.electionYear-a.electionYear||a.name.localeCompare(b.name));
  }
  function render(){
    view=filtered();const pages=Math.max(1,Math.ceil(view.length/pageSize));page=Math.min(page,pages-1);const visible=view.slice(page*pageSize,(page+1)*pageSize);
    body.innerHTML=visible.map((r,i)=>{
      const rowId=page*pageSize+i;const connectionCount=(r.concurrentFamilyOfficeholders||[]).length;
      const family=(families[r.familyKey]||[]).filter(member=>member.personKey!==r.personKey);
      return `<tr><td>${r.doNotVote?'<span class="vote-no" aria-label="NO · do not vote under this page rule">NO</span>':'<span class="vote-clear">—</span>'}</td><td><span class="vote-person">${esc(r.name)}</span><small>${esc(r.familyBasis||'No linked family group in source')}</small></td><td>${esc(r.position)}<small>${esc(r.officeGroup)}</small>${r.roleNote?`<small>${esc(r.roleNote)}</small>`:''}${r.roleSourceUrl?`<small><a href="${esc(r.roleSourceUrl)}" target="_blank" rel="noreferrer">Role source</a></small>`:''}</td><td>${esc(place(r))}</td><td>${esc(r.party||'—')}</td><td>${fmt(r.electionYear)}<small>Modeled in office ${fmt(r.officeStartYear??r.electionYear)}–${fmt(r.termThroughYear)}</small></td><td>${connectionCount?`<button type="button" class="vote-detail-btn" data-row="${rowId}">${fmt(connectionCount)} overlap · details</button>`:'—'}</td><td>${family.length?`<button type="button" class="vote-detail-btn" data-history-row="${rowId}">${fmt(family.length)} historical · details</button>`:'No linked family history'}</td></tr>`;
    }).join('')||'<tr><td colspan="8">No NO records match these filters.</td></tr>';
    const first=view.length?page*pageSize+1:0,last=Math.min((page+1)*pageSize,view.length);
    status.textContent=`${fmt(first)}–${fmt(last)} of ${fmt(view.length)} matching officeholder records · NO marks qualifying same-year family officeholding under the stated exception.`;
    pageLabel.textContent=`Page ${fmt(page+1)} of ${fmt(pages)}`;prev.disabled=page===0;next.disabled=page>=pages-1;
  }
  function setup(data){
    records=(data.records||[]).filter(r=>r.doNotVote);
    families=data.families||{};
    $('vote-total').textContent=fmt(data.summary?.officialRows||records.length);
    $('vote-no-total').textContent=fmt(data.summary?.noVoteRows||0);
    $('vote-year-range').textContent=(data.years||[]).length?`${data.years[0]}–${data.years[data.years.length-1]}`:'—';
    const noByYear=data.summary?.byYear||{};drawYearChart(noByYear);
    for(const y of [...new Set(records.map(r=>r.electionYear))].sort((a,b)=>b-a)){const o=document.createElement('option');o.value=String(y);o.textContent=String(y);yearFilter.append(o)}
    for(const name of [...new Set(records.map(r=>r.officeGroup))].sort((a,b)=>a.localeCompare(b))){const o=document.createElement('option');o.value=name;o.textContent=name;officeFilter.append(o)}
    [yearFilter,officeFilter,search].forEach(el=>el.addEventListener(el===search?'input':'change',()=>{page=0;render()}));
    prev.onclick=()=>{if(page>0){page--;render()}};next.onclick=()=>{page++;render()};
    body.addEventListener('click',e=>{const button=e.target.closest('[data-row],[data-history-row]');if(!button)return;const index=Number(button.dataset.row??button.dataset.historyRow);const row=view[index];if(!row)return;$('vote-dialog-title').textContent=row.name;
      if(button.hasAttribute('data-history-row')){
        const history=(families[row.familyKey]||[]).filter(member=>member.personKey!==row.personKey);
        $('vote-dialog-note').textContent=`Historical office records for ODV-linked family members of ${row.name}. These records can inform your own decision; history alone does not automatically mark a person NO.`;
        $('vote-dialog-list').innerHTML=history.map(member=>`<li><strong>${esc(member.name)}</strong>${member.offices.map(office=>`<br><span>${esc(office.position)} · ${esc(place(office))} · ${fmt(office.officeStartYear??office.electionYear)}–${fmt(office.termThroughYear)}${office.party?` · ${esc(office.party)}`:''}${office.roleNote?`<br>${esc(office.roleNote)}`:''}${office.roleSourceUrl?`<br><a href="${esc(office.roleSourceUrl)}" target="_blank" rel="noreferrer">Role source</a>`:''}</span>`).join('')}</li>`).join('')||'<li>No other linked family members are recorded in this source.</li>';
      }else{
        $('vote-dialog-note').textContent=`${row.position} · ${place(row)} · election record ${row.electionYear}; modeled in office ${row.officeStartYear??row.electionYear}–${row.termThroughYear}. ${row.roleNote||''} NO requires qualifying same-year family officeholding; one local plus one national is excluded. ${row.roleSourceUrl?'The table links the role source.':''}`;
        $('vote-dialog-list').innerHTML=(row.concurrentFamilyOfficeholders||[]).map(other=>`<li><strong>${esc(other.name)}</strong> · ${esc(other.position)} · ${esc(place(other))}<br><small>Term overlap: ${esc((other.overlapYears||[]).join(', '))} · ODV election record: ${fmt(other.electionYear)}</small></li>`).join('')||'<li>No concurrent family officeholder detail in the source.</li>';
      }dialog.showModal()});
    $('vote-dialog-close').onclick=()=>dialog.close();dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
    $('vote-export').onclick=()=>{const cols=['Rule','Name','Position','Office group','Province','Municipality / city','District','Party','Election year','Modeled term through','Family basis','Role evidence URL','Role note','Concurrent family officeholders','NO years','Historical family members'];const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';const csv=[cols.map(quote).join(','),...view.map(r=>[r.doNotVote?'NO · Do not vote':'',r.name,r.position,r.officeGroup,r.province,r.municipality,r.district,r.party,r.electionYear,r.termThroughYear,r.familyBasis,r.roleSourceUrl,r.roleNote,(r.concurrentFamilyOfficeholders||[]).map(x=>`${x.name} (${x.position})`).join('; '),(r.noVoteYears||[]).join('; '),(families[r.familyKey]||[]).filter(member=>member.personKey!==r.personKey).map(member=>`${member.name}: ${member.offices.map(o=>`${o.position} ${o.electionYear}`).join(', ')}`).join('; ')].map(quote).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='vote-2028-officeholder-screen.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
    render();
  }
  function drawYearChart(byYear){
    const svg=$('vote-year-chart');const years=Object.keys(byYear).sort((a,b)=>Number(a)-Number(b));
    if(!years.length){svg.innerHTML='<text x="24" y="40">No NO records by year are available.</text>';return}
    const values=years.map(y=>Number(byYear[y]?.noVoteRows||0)),max=Math.max(1,...values),left=52,right=18,top=26,bottom=48,w=800,h=280,pw=w-left-right,ph=h-top-bottom,step=pw/years.length,bw=Math.min(58,step*.56);
    const ticks=[0,Math.ceil(max/2),max].filter((v,i,a)=>a.indexOf(v)===i);let parts=[`<title>NO officeholder records by election year</title><desc>${years.map((y,i)=>`${y}: ${values[i]}`).join('; ')}</desc>`];
    for(const tick of ticks){const y=top+ph-(tick/max)*ph;parts.push(`<line x1="${left}" y1="${y}" x2="${w-right}" y2="${y}" stroke="#dfe6ec"/><text x="${left-9}" y="${y+4}" text-anchor="end">${fmt(tick)}</text>`)}
    years.forEach((year,i)=>{const x=left+i*step+(step-bw)/2,bh=(values[i]/max)*ph,y=top+ph-bh;parts.push(`<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="5" fill="#b42318"><title>${year}: ${fmt(values[i])} NO records</title></rect><text class="chart-value" x="${x+bw/2}" y="${Math.max(top-4,y-7)}" text-anchor="middle">${fmt(values[i])}</text><text x="${x+bw/2}" y="${h-17}" text-anchor="middle">${year}</text>`)});
    parts.push(`<line x1="${left}" y1="${top+ph}" x2="${w-right}" y2="${top+ph}" stroke="#8d9ba5"/>`);svg.innerHTML=parts.join('');
  }
  fetch('vote-2028-data.json').then(r=>{if(!r.ok)throw Error('Vote 2028 source JSON is unavailable');return r.json()}).then(setup).catch(e=>{status.textContent=`Could not load the ODV records: ${e.message}`;body.innerHTML='<tr><td colspan="8">The dataset could not be loaded.</td></tr>'});
})();

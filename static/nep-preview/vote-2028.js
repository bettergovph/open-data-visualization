(()=>{
  const $=id=>document.getElementById(id),yearFilter=$('vote-year'),officeFilter=$('vote-office'),search=$('vote-search'),noVoteOnly=$('vote-no-only'),body=$('vote-body'),status=$('vote-status'),prev=$('vote-prev'),next=$('vote-next'),pageLabel=$('vote-page'),dialog=$('vote-dialog');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=n=>Number(n||0).toLocaleString('en-PH');
  const place=r=>[r.municipality,r.province].filter(Boolean).join(', ')||r.district||r.region||'Place not recorded';
  let records=[],families={},page=0,pageSize=50,view=[];
  function filtered(){
    const yr=yearFilter.value,office=officeFilter.value,q=search.value.trim().toLowerCase();
    return records.filter(r=>(!yr||String(r.electionYear)===yr)&&(!office||r.officeGroup===office)&&(!noVoteOnly.checked||r.doNotVote)&&(!q||`${r.name} ${r.position} ${r.officeGroup} ${r.province} ${r.municipality} ${r.district} ${r.party} ${(r.concurrentFamilyOfficeholders||[]).map(x=>x.name+' '+x.position).join(' ')}`.toLowerCase().includes(q)))
      .sort((a,b)=>Number(b.doNotVote)-Number(a.doNotVote)||b.electionYear-a.electionYear||a.name.localeCompare(b.name));
  }
  function render(){
    view=filtered();const pages=Math.max(1,Math.ceil(view.length/pageSize));page=Math.min(page,pages-1);const visible=view.slice(page*pageSize,(page+1)*pageSize);
    body.innerHTML=visible.map((r,i)=>{
      const rowId=page*pageSize+i;const connectionCount=(r.concurrentFamilyOfficeholders||[]).length;
      const family=(families[r.familyKey]||[]).filter(member=>member.personKey!==r.personKey);
      return `<tr><td>${r.doNotVote?'<span class="vote-no" aria-label="NO · do not vote under this page rule">NO</span>':'<span class="vote-clear">—</span>'}</td><td><span class="vote-person">${esc(r.name)}</span><small>${esc(r.familyBasis||'No linked family group in source')}</small></td><td>${esc(r.position)}<small>${esc(r.officeGroup)}</small></td><td>${esc(place(r))}</td><td>${esc(r.party||'—')}</td><td>${fmt(r.electionYear)}<small>Term modeled through ${fmt(r.termThroughYear)}</small></td><td>${connectionCount?`<button type="button" class="vote-detail-btn" data-row="${rowId}">${fmt(connectionCount)} overlap · details</button>`:'—'}</td><td>${family.length?`<button type="button" class="vote-detail-btn" data-history-row="${rowId}">${fmt(family.length)} historical · details</button>`:'No linked family history'}</td></tr>`;
    }).join('')||'<tr><td colspan="8">No records match these filters.</td></tr>';
    const first=view.length?page*pageSize+1:0,last=Math.min((page+1)*pageSize,view.length);
    status.textContent=`${fmt(first)}–${fmt(last)} of ${fmt(view.length)} matching officeholder records · NO marks qualifying same-year family officeholding under the stated exception.`;
    pageLabel.textContent=`Page ${fmt(page+1)} of ${fmt(pages)}`;prev.disabled=page===0;next.disabled=page>=pages-1;
  }
  function setup(data){
    records=data.records||[];
    families=data.families||{};
    $('vote-total').textContent=fmt(data.summary?.officialRows||records.length);
    $('vote-no-total').textContent=fmt(data.summary?.noVoteRows||0);
    $('vote-year-range').textContent=(data.years||[]).length?`${data.years[0]}–${data.years[data.years.length-1]}`:'—';
    for(const y of [...(data.years||[])].sort((a,b)=>b-a)){const o=document.createElement('option');o.value=String(y);o.textContent=String(y);yearFilter.append(o)}
    for(const name of [...new Set(records.map(r=>r.officeGroup))].sort((a,b)=>a.localeCompare(b))){const o=document.createElement('option');o.value=name;o.textContent=name;officeFilter.append(o)}
    [yearFilter,officeFilter,search,noVoteOnly].forEach(el=>el.addEventListener(el===search?'input':'change',()=>{page=0;render()}));
    prev.onclick=()=>{if(page>0){page--;render()}};next.onclick=()=>{page++;render()};
    body.addEventListener('click',e=>{const button=e.target.closest('[data-row],[data-history-row]');if(!button)return;const index=Number(button.dataset.row??button.dataset.historyRow);const row=view[index];if(!row)return;$('vote-dialog-title').textContent=row.name;
      if(button.hasAttribute('data-history-row')){
        const history=(families[row.familyKey]||[]).filter(member=>member.personKey!==row.personKey);
        $('vote-dialog-note').textContent=`Historical office records for ODV-linked family members of ${row.name}. These records can inform your own decision; history alone does not automatically mark a person X.`;
        $('vote-dialog-list').innerHTML=history.map(member=>`<li><strong>${esc(member.name)}</strong>${member.offices.map(office=>`<br><span>${esc(office.position)} · ${esc(place(office))} · ${fmt(office.electionYear)}${office.termThroughYear!==office.electionYear?`–${fmt(office.termThroughYear)}`:''}${office.party?` · ${esc(office.party)}`:''}</span>`).join('')}</li>`).join('')||'<li>No other linked family members are recorded in this source.</li>';
      }else{
        $('vote-dialog-note').textContent=`${row.position} · ${place(row)} · election record ${row.electionYear}. NO requires qualifying same-year family officeholding; one local plus one national is excluded.`;
        $('vote-dialog-list').innerHTML=(row.concurrentFamilyOfficeholders||[]).map(other=>`<li><strong>${esc(other.name)}</strong> · ${esc(other.position)} · ${esc(place(other))}<br><small>Term overlap: ${esc((other.overlapYears||[]).join(', '))} · ODV election record: ${fmt(other.electionYear)}</small></li>`).join('')||'<li>No concurrent family officeholder detail in the source.</li>';
      }dialog.showModal()});
    $('vote-dialog-close').onclick=()=>dialog.close();dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
    $('vote-export').onclick=()=>{const cols=['Rule','Name','Position','Office group','Province','Municipality / city','District','Party','Election year','Modeled term through','Family basis','Concurrent family officeholders','NO years','Historical family members'];const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';const csv=[cols.map(quote).join(','),...view.map(r=>[r.doNotVote?'NO · Do not vote':'',r.name,r.position,r.officeGroup,r.province,r.municipality,r.district,r.party,r.electionYear,r.termThroughYear,r.familyBasis,(r.concurrentFamilyOfficeholders||[]).map(x=>`${x.name} (${x.position})`).join('; '),(r.noVoteYears||[]).join('; '),(families[r.familyKey]||[]).filter(member=>member.personKey!==r.personKey).map(member=>`${member.name}: ${member.offices.map(o=>`${o.position} ${o.electionYear}`).join(', ')}`).join('; ')].map(quote).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='vote-2028-officeholder-screen.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
    render();
  }
  fetch('vote-2028-data.json').then(r=>{if(!r.ok)throw Error('Vote 2028 source JSON is unavailable');return r.json()}).then(setup).catch(e=>{status.textContent=`Could not load the ODV records: ${e.message}`;body.innerHTML='<tr><td colspan="8">The dataset could not be loaded.</td></tr>'});
})();

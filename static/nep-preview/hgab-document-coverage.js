(()=>{
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=v=>Number(v||0).toLocaleString('en-PH');
  const peso=v=>'₱'+fmt(v);
  const body=document.getElementById('all-hgab-coverage-rows');
  if(!body)return;
  const search=document.getElementById('all-hgab-coverage-search');
  const count=document.getElementById('all-hgab-coverage-count');
  const pageLabel=document.getElementById('all-hgab-coverage-page');
  const prev=document.getElementById('all-hgab-coverage-prev');
  const next=document.getElementById('all-hgab-coverage-next');
  const size=document.getElementById('all-hgab-coverage-page-size');
  let rows=[],page=0;
  function render(){
    const q=search.value.trim().toLocaleLowerCase();
    const filtered=rows.filter(r=>[r.hgabId,r.title,r.office,r.region,r.documentMatchStatus,...(r.signatories||[]).flatMap(s=>[s.name,s.role,...(s.sources||[])])].join(' ').toLocaleLowerCase().includes(q));
    const perPage=Number(size.value)||50,pages=Math.max(1,Math.ceil(filtered.length/perPage));
    page=Math.max(0,Math.min(page,pages-1));
    const start=page*perPage,shown=filtered.slice(start,start+perPage);
    body.innerHTML=shown.map(r=>{
      const match=r.documentMatchStatus||((r.proposalDocumentsMatched&&r.senateHgabDocumentsMatched)?'Both sources':r.proposalDocumentsMatched?'Proposal only':r.senateHgabDocumentsMatched?'Senate HGAB only':'No current match');
      const proposal=r.proposalDocumentsMatched?'<strong>Matched'+(r.proposalMatchedFileRecords?' · '+fmt(r.proposalMatchedFileRecords)+' linked records':'')+'</strong><small>'+esc((r.proposalDocumentSources||[]).join(' · '))+(r.proposalDocumentTypes?.length?' · '+esc(r.proposalDocumentTypes.join(', ')):'')+'</small>':'No matched Proposal document';
      const senate=r.senateHgabDocumentsMatched?'<strong>Matched</strong><small>'+esc((r.senateDocumentTypes||[]).join(', ')||'Supporting file')+' · '+fmt(r.senateMatchedFileRecords)+' file records</small>':'No matched Senate HGAB file';
      const signatories=(r.signatories||[]).map(s=>'<div><strong>'+esc(s.name)+'</strong>'+(s.role?' · '+esc(s.role):'')+(s.sources?.length?'<small>'+esc(s.sources.join('; '))+'</small>':'')+'</div>').join('');
      const signatoryCell='<strong>'+fmt(r.signatoryCandidateCount??(r.signatories||[]).length)+' candidates</strong>'+(signatories||'<small>No extracted signatory candidate</small>');
      return '<tr><td>'+esc(r.hgabId)+'</td><td>'+esc(r.title)+'</td><td>'+esc(r.office)+(r.region?'<small>'+esc(r.region)+'</small>':'')+'</td><td class="num">'+peso(r.amountPesos)+'</td><td>'+proposal+'</td><td>'+senate+'</td><td>'+signatoryCell+'</td></tr>';
    }).join('')||'<tr><td colspan="7">No HGAB projects match this search.</td></tr>';
    count.textContent=fmt(filtered.length)+' of '+fmt(rows.length)+' HGAB projects';
    pageLabel.textContent=filtered.length?'Page '+(page+1)+' of '+pages+' · '+(start+1)+'–'+Math.min(start+perPage,filtered.length):'No rows';
    prev.disabled=page===0;next.disabled=page+1>=pages;
  }
  search.addEventListener('input',()=>{page=0;render()});
  size.addEventListener('change',()=>{page=0;render()});
  prev.addEventListener('click',()=>{page--;render()});
  next.addEventListener('click',()=>{page++;render()});
  fetch('hgab-document-coverage.json?v=60b6a72fd92c').then(r=>{if(!r.ok)throw Error('Coverage export unavailable ('+r.status+')');return r.json()}).then(d=>{rows=Array.isArray(d.projects)?d.projects:[];render()}).catch(e=>{body.innerHTML='<tr><td colspan="7">Could not load the all-HGAB coverage export. '+esc(e.message)+'</td></tr>';count.textContent='Coverage unavailable';console.error(e)});
})();

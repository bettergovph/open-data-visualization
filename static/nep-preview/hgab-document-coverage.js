(()=>{
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=v=>Number(v||0).toLocaleString('en-PH');
  const peso=v=>'₱'+fmt(v);
  const body=document.getElementById('all-hgab-coverage-rows')||document.getElementById('coverage-rows');
  if(!body)return;
  const allHgab=body.id==='all-hgab-coverage-rows';
  const prefix=allHgab?'all-hgab-coverage':'coverage';
  const section=document.getElementById('all-hgab-document-coverage');
  const search=document.getElementById(prefix+'-search');
  const count=document.getElementById(prefix+'-count');
  const pageLabel=document.getElementById(prefix+'-page');
  const prev=document.getElementById(prefix+'-prev');
  const next=document.getElementById(prefix+'-next');
  const size=document.getElementById(prefix+'-page-size');
  let rows=[],page=0;
  function render(){
    const q=search.value.trim().toLocaleLowerCase();
    const filtered=rows.filter(r=>[r.hgabId,r.title,r.office,r.region,...(r.senateDocuments||[]).flatMap(d=>[d.documentId,d.documentName,d.documentType]),...(r.signatories||[]).flatMap(s=>[s.name,s.role,...(s.sources||[])])].join(' ').toLocaleLowerCase().includes(q));
    const perPage=Number(size.value)||50,pages=Math.max(1,Math.ceil(filtered.length/perPage));
    page=Math.max(0,Math.min(page,pages-1));
    const start=page*perPage,shown=filtered.slice(start,start+perPage);
    body.innerHTML=shown.map(r=>{
      const proposal=r.proposalDocumentsMatched
        ?'<strong>Matched'+(r.proposalMatchedFileRecords?' · '+fmt(r.proposalMatchedFileRecords)+' linked records':'')+'</strong><small>'+esc((r.proposalDocumentSources||[]).join(' · '))+(r.proposalDocumentTypes?.length?' · '+esc(r.proposalDocumentTypes.join(', ')):'')+'</small>'
        :'No matched Proposal document';
      const senate=r.senateHgabDocumentsMatched
        ?'<strong>Matched</strong><small>'+esc((r.senateDocumentTypes||[]).join(', ')||'Supporting file')+' · '+fmt(r.senateMatchedFileRecords)+' file records</small>'
        :'No matched Senate HGAB file';
      const documents=(r.senateDocuments||[]).map(d=>'<div><a href="'+esc(d.url)+'" target="_blank" rel="noopener noreferrer">'+esc(d.documentId||d.documentName)+'</a><small>'+esc(d.documentType||'Other')+(d.fileLinkId!=null?' · file-link ID '+esc(d.fileLinkId):'')+'</small></div>').join('')||'<small>No uniquely linked file names</small>';
      const documentCell=allHgab?'<td>'+documents+'</td>':'';
      const signatories=(r.signatories||[]).map(s=>'<div><strong>'+esc(s.name)+'</strong>'+(s.role?' · '+esc(s.role):'')+(s.sources?.length?'<small>'+esc(s.sources.join('; '))+'</small>':'')+'</div>').join('');
      const signatoryCell='<strong>'+fmt(r.signatoryCandidateCount??(r.signatories||[]).length)+' candidates</strong>'+(signatories||'<small>No extracted signatory candidate</small>');
      return '<tr><td>'+esc(r.hgabId)+'</td><td>'+esc(r.title)+'</td><td>'+esc(r.office)+(r.region?'<small>'+esc(r.region)+'</small>':'')+'</td><td class="num">'+peso(r.amountPesos)+'</td><td>'+proposal+'</td><td>'+senate+'</td>'+documentCell+'<td>'+signatoryCell+'</td></tr>';
    }).join('')||'<tr><td colspan="'+(allHgab?'8':'7')+'">No '+(allHgab?'HGAB':'HGAB-only')+' projects match this search.</td></tr>';
    count.textContent=fmt(filtered.length)+' of '+fmt(rows.length)+' '+(allHgab?'HGAB':'HGAB-only')+' projects';
    pageLabel.textContent=filtered.length?'Page '+(page+1)+' of '+pages+' · '+(start+1)+'–'+Math.min(start+perPage,filtered.length):'No rows';
    prev.disabled=page===0;next.disabled=page+1>=pages;
  }
  search.addEventListener('input',()=>{page=0;render()});
  size.addEventListener('change',()=>{page=0;render()});
  prev.addEventListener('click',()=>{page--;render()});
  next.addEventListener('click',()=>{page++;render()});
  const source=section?.dataset.hgabCoverageSource;
  if(!source){body.innerHTML='<tr><td colspan="'+(allHgab?'8':'7')+'">Coverage source is not configured.</td></tr>';count.textContent='Coverage unavailable';return;}
  const indexSource=source.replace(/\.json(?:\?.*)?$/,'-index.json');
  (window.loadReportShardedJson?window.loadReportShardedJson(indexSource):fetch(source).then(r=>{if(!r.ok)throw Error('Coverage export unavailable ('+r.status+')');return r.json()})).then(d=>{rows=Array.isArray(d.projects)?d.projects:[];render()}).catch(e=>{body.innerHTML='<tr><td colspan="'+(allHgab?'8':'7')+'">Could not load the document coverage export. '+esc(e.message)+'</td></tr>';count.textContent='Coverage unavailable';console.error(e)});
})();

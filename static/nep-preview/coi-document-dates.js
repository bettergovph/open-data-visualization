(()=>{
  const body=document.getElementById('coi-date-rows');
  if(!body)return;
  const input=document.getElementById('coi-date-search');
  const filter=document.getElementById('coi-date-filter');
  const count=document.getElementById('coi-date-count');
  const pageLabel=document.getElementById('coi-date-page');
  const previous=document.getElementById('coi-date-prev');
  const next=document.getElementById('coi-date-next');
  const fmt=value=>Number(value||0).toLocaleString('en-PH');
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let documents=[],page=0;const pageSize=25;
  const draw=()=>{
    const query=input.value.trim().toLocaleLowerCase(),mode=filter.value;
    const filtered=documents.filter(doc=>{
      const hasDates=(doc.dates||[]).length>0;
      const dates=(doc.dates||[]).map(date=>`${date.printedDate} ${date.isoDate}`).join(' ');
      return (mode==='dated'?hasDates:mode==='missing'?!hasDates:true)&&(!query||`${doc.file} ${doc.projectCode} ${doc.matchStatus} ${dates}`.toLocaleLowerCase().includes(query));
    });
    const pages=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.max(0,Math.min(page,pages-1));
    body.innerHTML=filtered.slice(page*pageSize,(page+1)*pageSize).map(doc=>{
      const dates=(doc.dates||[]).length?doc.dates.map(date=>`<div><strong>${esc(date.printedDate)}</strong>${date.sourcePages?.length?`<small>Source page(s): ${date.sourcePages.map(fmt).join(', ')}</small>`:''}</div>`).join(''):'<span class="muted">No printed date extracted</span>';
      return `<tr><td><strong>${esc(doc.file.split('/').slice(0,-1).join('/'))}</strong><small>${esc(doc.file.split('/').pop())}</small></td><td>${esc(doc.projectCode||'—')}</td><td>${esc(String(doc.matchStatus||'unknown').replaceAll('_',' '))}</td><td class="coi-date-values">${dates}</td></tr>`;
    }).join('')||'<tr><td colspan="4">No COI PDFs match this filter.</td></tr>';
    count.textContent=`${fmt(filtered.length)} of ${fmt(documents.length)} COI PDFs`;
    pageLabel.textContent=filtered.length?`Page ${page+1} of ${pages}`:'No matching COI PDFs';
    previous.disabled=page===0;next.disabled=page+1>=pages;
  };
  fetch('coi-document-dates.json?v=printed-dates-34317-1').then(response=>{if(!response.ok)throw Error(`HTTP ${response.status}`);return response.json()}).then(data=>{
    documents=data.documents||[];draw();
  }).catch(error=>{body.innerHTML=`<tr><td colspan="4">COI printed-date records could not be loaded: ${esc(error.message)}</td></tr>`;count.textContent='COI date records unavailable';});
  input.addEventListener('input',()=>{page=0;draw()});filter.addEventListener('change',()=>{page=0;draw()});
  previous.addEventListener('click',()=>{page--;draw()});next.addEventListener('click',()=>{page++;draw()});
})();

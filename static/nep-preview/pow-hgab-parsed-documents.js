(()=>{
  const fmt=n=>Number(n||0).toLocaleString();
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const label=value=>String(value||'unknown').replaceAll('_',' ');
  const query=document.getElementById('hgab-pow-query');
  const match=document.getElementById('hgab-pow-match');
  const tbody=document.querySelector('#hgab-pow-table tbody');
  const pageSize=20;
  let rows=[],page=0;
  const render=()=>{
    const needle=query.value.trim().toLocaleLowerCase();
    const selected=rows.filter(row=>{
      const text=[row.code,row.hgabTitle,row.hgabId,row.proposalCode,(row.candidateHgabIds||[]).join(' ')].join(' ').toLocaleLowerCase();
      return (!needle||text.includes(needle))&&(!match.value||row.matchStatus===match.value);
    });
    const pages=Math.max(1,Math.ceil(selected.length/pageSize));
    page=Math.min(page,pages-1);
    document.getElementById('hgab-pow-count').textContent=`${fmt(selected.length)} of ${fmt(rows.length)} parsed Senate files`;
    document.getElementById('hgab-pow-page').textContent=selected.length?`Page ${page+1} of ${pages}`:'No files match this search';
    document.getElementById('hgab-pow-prev').disabled=page===0;
    document.getElementById('hgab-pow-next').disabled=page+1>=pages;
    tbody.innerHTML=selected.slice(page*pageSize,(page+1)*pageSize).map(row=>{
      const title=row.hgabTitle?`<strong>${esc(row.hgabTitle)}</strong><small>${esc(row.hgabId||'')}</small>`:
        row.candidateHgabIds?.length?`Unconfirmed candidate ${esc(row.candidateHgabIds.join(', '))}`:'No accepted title match';
      return `<tr><td>${esc(row.code||'—')}</td><td>${title}</td><td>${esc(label(row.matchStatus))}</td><td>${esc(label(row.status))}</td><td>${fmt(row.rowCount)}</td><td>${fmt(row.categorySummaryRowCount)}</td><td>${fmt(row.pageCount)}</td><td>${esc(row.proposalCode||'—')}</td></tr>`;
    }).join('')||'<tr><td colspan="8">No parsed Senate HGAB POW files match this filter.</td></tr>';
  };
  fetch('pow-hgab-parsed-documents.json').then(response=>{
    if(!response.ok)throw Error(`HTTP ${response.status}`);
    return response.json();
  }).then(data=>{
    rows=data.documents||[];
    const summary=data.summary||{};
    const counts=[
      [fmt(summary.parsedDocuments),'Senate HGAB POW files parsed'],
      [fmt(summary.documentsWithBillRows),'files with recovered bill rows'],
      [fmt(summary.billRows),'machine-extracted bill rows'],
      [fmt(summary.printedCategories),'category-summary rows'],
      [fmt(summary.filesWithAcceptedHgabTitleMatch),'files with an accepted HGAB title match'],
      [fmt(summary.uniqueMatchedHgabProjectRows),'unique HGAB project rows linked by title'],
    ];
    document.getElementById('hgab-pow-summary').innerHTML=counts.map(([value,caption])=>`<div class="metric"><strong>${value}</strong><span>${esc(caption)}</span></div>`).join('');
    const options=[...new Set(rows.map(row=>row.matchStatus||'unknown'))].sort();
    match.innerHTML='<option value="">All title-match statuses</option>'+options.map(value=>`<option value="${esc(value)}">${esc(label(value))}</option>`).join('');
    document.getElementById('hgab-pow-export').addEventListener('click',()=>{
      const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
      const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='senate-hgab-pow-parsed-records.json';link.click();
      setTimeout(()=>URL.revokeObjectURL(link.href),1000);
    });
    render();
  }).catch(error=>{
    document.getElementById('hgab-pow-summary').innerHTML=`<p class="caution">Could not load parsed Senate HGAB POW records: ${esc(error.message)}</p>`;
    tbody.innerHTML='<tr><td colspan="8">Parsed Senate HGAB POW records are unavailable.</td></tr>';
  });
  query.addEventListener('input',()=>{page=0;render()});
  match.addEventListener('change',()=>{page=0;render()});
  document.getElementById('hgab-pow-prev').addEventListener('click',()=>{page--;render()});
  document.getElementById('hgab-pow-next').addEventListener('click',()=>{page++;render()});
})();

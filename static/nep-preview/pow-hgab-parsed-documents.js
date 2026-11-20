(()=>{
  const fmt=n=>Number(n||0).toLocaleString();
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const label=value=>String(value||'unknown').replaceAll('_',' ');
  const fetchJson=async url=>{
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),15000);
    try{
      const response=await fetch(url,{signal:controller.signal});
      if(!response.ok)throw Error(`HTTP ${response.status}`);
      return await response.json();
    }catch(error){
      if(error.name==='AbortError')throw Error(`Request timed out while loading ${url}`);
      throw error;
    }finally{clearTimeout(timeout)}
  };
  const query=document.getElementById('hgab-pow-query');
  const match=document.getElementById('hgab-pow-match');
  const tbody=document.querySelector('#hgab-pow-table tbody');
  const pageSize=20;
  const tokenBody=document.querySelector('#token-pow-table tbody');
  const tokenQuery=document.getElementById('token-pow-query');
  const tokenSignal=document.getElementById('token-pow-signal');
  const tokenPageSize=20;
  let tokenProjects=[],tokenPage=0;
  const showTokenLoadError=error=>{
    const metrics=document.getElementById('token-pow-metrics');
    const note=document.getElementById('token-pow-note');
    if(metrics)metrics.innerHTML=`<p class="caution">Could not compare POW parser results with 5/5 project records: ${esc(error.message)}</p>`;
    if(note)note.textContent='The no-detail comparison could not be loaded.';
    if(tokenBody)tokenBody.innerHTML='<tr><td colspan="4">5/5 comparison data is unavailable.</td></tr>';
  };
  const renderTokenRows=()=>{
    if(!tokenBody)return;
    const needle=(tokenQuery?.value||'').trim().toLocaleLowerCase();
    const signal=tokenSignal?.value||'';
    const filtered=tokenProjects.filter(row=>{
      const docsText=row.tokenFiles.map(file=>file.code).join(' ');
      const text=[row.project.title,row.project.hgabId,row.project.office,docsText].join(' ').toLocaleLowerCase();
      return (!needle||text.includes(needle))&&(!signal||(signal==='summary'?row.summaryFiles.length>0:row.summaryFiles.length===0));
    });
    const pages=Math.max(1,Math.ceil(filtered.length/tokenPageSize));
    tokenPage=Math.min(tokenPage,pages-1);
    const shown=filtered.slice(tokenPage*tokenPageSize,(tokenPage+1)*tokenPageSize);
    document.getElementById('token-pow-count').textContent=`${fmt(filtered.length)} of ${fmt(tokenProjects.length)} 5/5 projects`;
    document.getElementById('token-pow-page').textContent=filtered.length?`Page ${tokenPage+1} of ${pages}`:'No projects match this search';
    document.getElementById('token-pow-prev').disabled=tokenPage===0;
    document.getElementById('token-pow-next').disabled=tokenPage+1>=pages;
    tokenBody.innerHTML=shown.map(row=>{
      const project=row.project;
      const files=row.tokenFiles.map(file=>{
        return `<div>${esc(file.code)}<small>${fmt(file.pageCount)} page(s) · ${fmt(file.categorySummaryRowCount)} category-summary row(s)</small></div>`;
      }).join('');
      const summary=`${fmt(row.summaryFiles.length)} file(s) with category-summary rows`;
      const empty=`${fmt(row.emptyFiles.length)} file(s) with no category-summary rows`;
      const signalText=row.summaryFiles.length?`${summary}; ${empty}`:'No category summary recovered; parser failure or sparse source needs review';
      return `<tr><td><strong>${esc(project.title)}</strong><small>${esc(project.hgabId)} · ${esc(project.office||'')} · ₱${fmt(project.amountPesos)}</small></td><td>${fmt(project.senateMatchedFileRecords)} matched file record(s)<small>${(project.senateDocumentTypes||[]).length}/5 named types</small></td><td>${files}</td><td>${esc(signalText)}</td></tr>`;
    }).join('')||'<tr><td colspan="4">No 5/5 projects match this filter.</td></tr>';
  };
  const renderTokenReview=(parsed,coverage)=>{
    const documents=parsed.documents||[];
    const noBill=documents.filter(file=>file.status==='no_bill_rows_recovered');
    const withSummary=noBill.filter(file=>Number(file.categorySummaryRowCount||0)>0);
    const byProject=new Map();
    documents.forEach(file=>{
      if(!file.hgabId)return;
      if(!byProject.has(file.hgabId))byProject.set(file.hgabId,[]);
      byProject.get(file.hgabId).push(file);
    });
    const required=['BP 202','Certificate of Implementability','Development Council','Geotagged photos','POW'];
    const complete=(coverage.projects||[]).filter(project=>required.every(type=>(project.senateDocumentTypes||[]).includes(type)));
    tokenProjects=complete.map(project=>{
      const parsedFiles=byProject.get(project.hgabId)||[];
      const tokenFiles=parsedFiles.filter(file=>file.status==='no_bill_rows_recovered');
      if(!parsedFiles.length||!tokenFiles.length||tokenFiles.length!==parsedFiles.length)return null;
      return {project,tokenFiles,summaryFiles:tokenFiles.filter(file=>Number(file.categorySummaryRowCount||0)>0),emptyFiles:tokenFiles.filter(file=>!Number(file.categorySummaryRowCount||0))};
    }).filter(Boolean).sort((a,b)=>(Number(b.project.amountPesos)||0)-(Number(a.project.amountPesos)||0)||String(a.project.hgabId).localeCompare(String(b.project.hgabId)));
    const adjusted=Math.max(0,complete.length-tokenProjects.length);
    const denominator=(coverage.projects||[]).length;
    const completePct=denominator?(100*complete.length/denominator).toFixed(2):'0.00';
    const adjustedPct=denominator?(100*adjusted/denominator).toFixed(2):'0.00';
    const metric=(value,caption)=>`<div class="metric"><strong>${esc(value)}</strong><span>${esc(caption)}</span></div>`;
    document.getElementById('token-pow-metrics').innerHTML=[
      metric(`${fmt(noBill.length)} / ${fmt(documents.length)}`,'parsed POW files with zero recovered bill rows'),
      metric(`${fmt(withSummary.length)} / ${fmt(noBill.length)}`,'no-bill files with category-summary rows; summary-only candidates'),
      metric(`${fmt(tokenProjects.length)} / ${fmt(complete.length)}`,`${fmt(tokenProjects.reduce((n,row)=>n+row.tokenFiles.length,0))} no-detail POW files across 5/5 projects`),
      metric(`${fmt(adjusted)} / ${fmt(denominator)}`,'5/5 rows remaining after the no-detail POW check'),
    ].join('');
    document.getElementById('token-pow-note').textContent=`The Undocumented HGAB page reports ${fmt(complete.length)} of ${fmt(denominator)} HGAB-only rows at 5/5 (${completePct}%). ${fmt(tokenProjects.length)} of those rows have no bill rows in any accepted-title parsed POW. Counting these as potential POW-content deficiencies leaves ${fmt(adjusted)} of ${fmt(denominator)} rows (${adjustedPct}%) at 5/5. Among their ${fmt(tokenProjects.reduce((n,row)=>n+row.tokenFiles.length,0))} files, ${fmt(tokenProjects.reduce((n,row)=>n+row.summaryFiles.length,0))} have category-summary rows and ${fmt(tokenProjects.reduce((n,row)=>n+row.emptyFiles.length,0))} have none. These are parser-based review flags, not source-PDF confirmation: category totals without item rows may be a token/summary-only POW or a parser failure. Search the listed file codes in the parsed POW inventory to review each record.`;
    tokenPage=0;
    renderTokenRows();
  };
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
  const parsedPromise=fetchJson('pow-hgab-parsed-documents.json').then(data=>{
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
    return data;
  });
  const coveragePromise=fetchJson('hgab-only-document-coverage.json');
  parsedPromise.catch(error=>{
    document.getElementById('hgab-pow-summary').innerHTML=`<p class="caution">Could not load parsed Senate HGAB POW records: ${esc(error.message)}</p>`;
    tbody.innerHTML='<tr><td colspan="8">Parsed Senate HGAB POW records are unavailable.</td></tr>';
    showTokenLoadError(error);
  });
  Promise.all([parsedPromise,coveragePromise])
    .then(([data,coverage])=>renderTokenReview(data,coverage))
    .catch(showTokenLoadError);
  query.addEventListener('input',()=>{page=0;render()});
  match.addEventListener('change',()=>{page=0;render()});
  document.getElementById('hgab-pow-prev').addEventListener('click',()=>{page--;render()});
  document.getElementById('hgab-pow-next').addEventListener('click',()=>{page++;render()});
  tokenQuery?.addEventListener('input',()=>{tokenPage=0;renderTokenRows()});
  tokenSignal?.addEventListener('change',()=>{tokenPage=0;renderTokenRows()});
  document.getElementById('token-pow-prev')?.addEventListener('click',()=>{tokenPage--;renderTokenRows()});
  document.getElementById('token-pow-next')?.addEventListener('click',()=>{tokenPage++;renderTokenRows()});
})();

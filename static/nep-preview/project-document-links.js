(()=>{
'use strict';
const normalize=v=>String(v||'').normalize('NFKC').replace(/\s+/g,' ').trim();
const route=location.pathname.includes('/static/nep-preview/')?'project-documents.html':'/static/nep-preview/project-documents.html';
const style=document.createElement('style');style.textContent='.transparency-record-status{font-size:12px;line-height:1.4;overflow-wrap:anywhere}.transparency-record-status[data-status="incomplete_documents"],.transparency-record-status[data-status="unmatched"]{color:#85490b}.transparency-record-status a{display:block;text-decoration:underline}.transparency-coverage-method{font-size:13px;padding:12px;border:1px solid #b5c8c5;border-radius:6px;background:#f5f8f7}';document.head.append(style);
fetch('/static/nep-preview/project-document-index.json').then(r=>{if(!r.ok)throw Error('Document index unavailable');return r.json()}).then(d=>{
 const coverage=d.coverage;if(!coverage)return;
 const index=new Map(Object.entries(coverage.titles)),codes=new Map(Object.values(coverage.titles).filter(r=>r.code&&r.status!=='candidate_match').map(r=>[r.code,r])),unmatched=new Set(['not_found','no_verified_match','candidate_match','ambiguous_match']);
 const note=document.createElement('aside');note.className='transparency-coverage-method';note.id='transparency-document-method';
 const heading=document.createElement('strong');heading.textContent='DPWH transparency document column';note.append(heading);
 const description=document.createElement('p');description.textContent='FY2027 NEP listing snapshot, retrieved '+coverage.snapshotRetrievedAtUtc+'. Unmatched takes precedence over document counts. It means no verified portal counterpart; it does not establish that a project is absent from the live portal. Otherwise the column shows listed documents against a minimum of '+coverage.expectedMinimumDocuments+'. Fewer than five is incomplete under this screening threshold. Five or more does not establish document types, readable PDFs or verified contents. A listed record with zero documents is separate from an unmatched project.';note.append(description);
 const methods=document.createElement('p');methods.textContent=coverage.methodology.join(' ')+' For a comparison row containing two FY2027 projects, any unmatched project takes precedence. If both match, the lowest document count is shown; individual counts and matching details are available in the cell tooltip. Historical GAA comparison projects are excluded.';note.append(methods);
 const source=document.createElement('a');source.href='https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS/tree/'+coverage.sourceCommit;source.textContent='Retained source and reconciliation snapshot ↗';source.target='_blank';source.rel='noopener';note.append(source);
 function entries(row,headers){
  const found=[];
  [...row.cells].forEach((cell,i)=>{
   const header=headers[i]||'';
   if(cell.classList.contains('transparency-record-status')||/GAA|prior|past|closest|202[0-6]/i.test(header)||!/project|line item|NEP|HGAB|extracted.*record/i.test(header))return;
   const raw=normalize(cell.textContent);
   if(/GAA source|GAA-202[0-6]|FY202[0-6]/i.test(raw))return;
   const title=raw.replace(/\s*·\s*(?:p\d+:r\d+|2027DPWH-Proposal-\d+|NEP source|HB10858|\d+- HB|GAA-20\d\d).*$/,'').trim(),code=raw.match(/\b2027DPWH-Proposal-\d{5}\b/)?.[0],entry=code?codes.get(code)||index.get(title):index.get(title);
   if(entry&&!found.some(r=>r.title===title))found.push({title,...entry});
  });return found;
 }
 function paint(cell,items){
  cell.className='transparency-record-status';
  if(!items.length){cell.textContent='—';return}
  const miss=items.some(r=>unmatched.has(r.status)),counts=items.filter(r=>r.documentCount!=null).map(r=>r.documentCount),outside=items.some(r=>r.status==='outside_snapshot_scope');
  if(miss){cell.dataset.status='unmatched';cell.textContent='Unmatched'}
  else if(outside){cell.dataset.status='outside_snapshot_scope';cell.textContent='Outside NEP listing scope'}
  else if(counts.length===items.length){const n=Math.min(...counts);cell.dataset.status=n<coverage.expectedMinimumDocuments?'incomplete_documents':'five_or_more_listed';cell.textContent=n+' documents'+(n<coverage.expectedMinimumDocuments?' · incomplete':'')+(items.length>1?' · lowest in row':'')}
  else{cell.dataset.status='documents_unknown';cell.textContent='Document count unavailable'}
  cell.title=items.map(r=>r.title+' — '+r.status+(r.documentCount!=null?' · '+r.documentCount+' listed documents':'')+' · '+r.matchBasis).join('\n')+'\nSnapshot: '+coverage.snapshotRetrievedAtUtc;
  items.filter(r=>r.code&&!unmatched.has(r.status)).forEach((entry,i)=>{
   const a=document.createElement('a');a.className='nep-document-link';a.href=route+'?project='+encodeURIComponent(entry.code);a.target='_blank';a.rel='noopener';a.textContent=items.length>1?'NEP record '+(i+1)+' →':'NEP record →';a.title=entry.title;
   a.addEventListener('click',event=>{if(event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;const popup=window.open(a.href,'nepProjectDocuments','popup,width=1180,height=900,scrollbars=yes,resizable=yes');if(popup){event.preventDefault();popup.opener=null;popup.focus()}});cell.append(a);
  });
 }
 let scheduled=false;
 function scan(){scheduled=false;observer.disconnect();let tagged=false;
 document.querySelectorAll('main table').forEach(table=>{
  const headerRow=table.tHead?.rows[table.tHead.rows.length-1];if(!headerRow)return;
  const headers=[...headerRow.cells].filter(h=>!h.classList.contains('transparency-status-heading')).map(h=>normalize(h.textContent));
  const pending=[...table.tBodies].flatMap(body=>[...body.rows]).filter(row=>!row.querySelector('.transparency-record-status')).map(row=>({row,items:entries(row,headers)}));
  if(!headerRow.querySelector('.transparency-status-heading')&&!pending.some(r=>r.items.length))return;
  if(!headerRow.querySelector('.transparency-status-heading')){const th=document.createElement('th');th.className='transparency-status-heading';th.scope='col';th.textContent='DPWH transparency';headerRow.append(th)}
  pending.forEach(({row,items})=>{
   if(row.cells.length===1&&row.cells[0].colSpan>1){row.cells[0].colSpan=headers.length+1;return}
   paint(row.insertCell(),items);tagged=true;
  });
 });
 if(tagged&&!note.isConnected)(document.querySelector('main')||document.body).append(note);
 observer.observe(document.querySelector('main')||document.body,{childList:true,subtree:true});}
 const observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;requestAnimationFrame(scan)}});scan();
}).catch(()=>{});
})();

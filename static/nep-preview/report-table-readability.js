(()=>{
'use strict';
if(window.ReportTableReadabilityLoaded)return;
window.ReportTableReadabilityLoaded=true;
const normalize=value=>String(value||'').replace(/\s+/g,' ').trim();
const empty=value=>/^(?:[—–\-\s]*|n\/?a|none|unknown|unresolved|not (?:available|resolved|identified|established))$/i.test(normalize(value));
function label(table){const section=table.closest('section,article');return normalize(section?.querySelector('h2,h3')?.textContent)||'Report table'}
const pagination=new WeakMap();
function tableRows(table){return [...table.tBodies].flatMap(body=>[...body.rows]).filter(row=>row.cells.length>0)}
function exportJSON(table){
 const headers=[...(table.tHead?.rows[table.tHead.rows.length-1]?.cells||[])].map(cell=>normalize(cell.textContent));
 const rows=tableRows(table).map(row=>Object.fromEntries(headers.map((header,index)=>[header,normalize(cellText(row.cells[index]||document.createElement('td')))])));
 const blob=new Blob([JSON.stringify({table:label(table),exportedAtUtc:new Date().toISOString(),rowCount:rows.length,rows},null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');
 link.href=url;link.download=(label(table).toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')||'report-table')+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function addJsonExport(host,table){
 if(!host||host.querySelector(':scope > .report-table-export-json'))return;
 const button=document.createElement('button');button.type='button';button.className='report-table-export-json';button.textContent='Export loaded rows JSON';button.title='Export all rows currently loaded in this table, including rows on other pages.';button.onclick=()=>exportJSON(table);host.append(button);
}
function mirrorPager(table,wrap,bottom){
 if(!bottom||bottom.dataset.reportPagerMirrored)return;
 const top=bottom.cloneNode(true);top.dataset.reportPagerMirror='true';top.classList.add('report-table-pagination-top');top.setAttribute('aria-label',label(table)+' pages · top controls');
 bottom.dataset.reportPagerMirrored='true';
 [...top.querySelectorAll('[id]')].forEach(el=>el.removeAttribute('id'));
 wrap.before(top);
 const originals=[...bottom.querySelectorAll('button,a,select,input')],clones=[...top.querySelectorAll('button,a,select,input')];
 const sync=()=>clones.forEach((clone,index)=>{const original=originals[index];if(!original)return;clone.disabled=Boolean(original.disabled);if('value'in clone)clone.value=original.value;if(clone.tagName==='BUTTON'||clone.tagName==='A')clone.textContent=original.textContent});
 clones.forEach((clone,index)=>{const original=originals[index];if(!original)return;if(clone.tagName==='SELECT'||clone.tagName==='INPUT')clone.addEventListener('change',()=>{original.value=clone.value;original.dispatchEvent(new Event('change',{bubbles:true}))});else clone.addEventListener('click',event=>{event.preventDefault();original.click()})});
 const observer=new MutationObserver(sync);observer.observe(bottom,{subtree:true,childList:true,attributes:true,characterData:true});bottom.addEventListener('click',()=>requestAnimationFrame(sync));sync();
 addJsonExport(top,table);
}
const sharedScript=document.currentScript?.src||new URL('report-table-readability.js',location.href).href;
let evidenceLoader;
function linkedEvidence(){
 if(window.ReportProjectEvidence)return Promise.resolve(window.ReportProjectEvidence);
 if(!evidenceLoader)evidenceLoader=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=new URL('project-evidence-details.js?v=e4bfcea3670e',sharedScript).href;script.onload=()=>window.ReportProjectEvidence?resolve(window.ReportProjectEvidence):reject(Error('Evidence reader did not initialize'));script.onerror=()=>reject(Error('Evidence reader could not be loaded'));document.head.append(script)}).catch(e=>{evidenceLoader=null;throw e});
 return evidenceLoader;
}
const titleHeader=text=>{
 const value=normalize(text).toLowerCase();
 if(value==='enacted gaa line item')return false;
 if(/\b(?:amount|allocation|cost|rate|price|count|entries|project id|project rows|project lines)\b/.test(value))return false;
 return /\bproject\b/.test(value)||(/\b(?:closest|prior|current|nep|hgab|gaa)\b.*\btitle\b/.test(value)&&!/\bsimilarity\b/.test(value))||/\b(?:nep|hgab|gaa)\b.*\bline(?: item)?\b/.test(value)||/^extracted hgab record$/.test(value)||/^(?:(?:2nd|3rd|first|second|third) reading line|title)$/.test(value)||/^(?:facility|school\s*\/\s*building|named project)$/.test(value);
};
window.ReportProjectDetails={enrichLinked:request=>linkedEvidence().then(reader=>reader.enrich(request))};
document.dispatchEvent(new Event('report-project-details-ready'));
const detailDialog=(()=>{
 const dialog=document.createElement('dialog');dialog.className='report-project-dialog';dialog.setAttribute('aria-labelledby','report-project-dialog-title');
 dialog.setAttribute('data-report-table-exempt','true');
 dialog.innerHTML='<div class="report-project-card"><header><div><span class="report-project-kicker">Additional linked records</span><h2 id="report-project-dialog-title"></h2></div><button type="button" class="report-project-close" aria-label="Close project details">×</button></header><section class="report-linked-project-evidence" aria-live="polite"></section></div>';
 document.body.append(dialog);
 dialog.querySelector('.report-project-close').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close()});
 return dialog;
})();
function cellText(cell){const copy=cell.cloneNode(true);copy.querySelectorAll('.report-project-details-trigger').forEach(node=>node.remove());return normalize(copy.textContent)}
function openProjectDetails(table,row,titleIndexes){
 const head=table.tHead?.rows[table.tHead.rows.length-1];if(!head||row.cells.length!==head.cells.length)return;
 const title=titleIndexes.map(index=>cellText(row.cells[index])).filter(Boolean).join(' · ');
 detailDialog.querySelector('#report-project-dialog-title').textContent=title||'Project details';
 if(!detailDialog.open)detailDialog.showModal();
 const host=detailDialog.querySelector('.report-linked-project-evidence'),request={};host._loadingRequest=request;
 const titles=titleIndexes.flatMap(index=>{const cell=row.cells[index],copy=cell.cloneNode(true);copy.querySelectorAll('button,small,.report-project-details-trigger').forEach(n=>n.remove());const text=normalize(copy.textContent);return [cell.dataset.projectTitle,text,text.split(' · ')[0],cellText(cell)].filter(Boolean)});
 host.innerHTML='<h3>Linked project evidence</h3><p role="status">Loading linked source records…</p>';
 const visible={headers:[...head.cells].map(cell=>normalize(cell.innerText||cell.textContent)),values:[...row.cells].map(cellText)};
 linkedEvidence().then(reader=>{if(host._loadingRequest===request)reader.enrich({host,table,row,titles,visible})}).catch(e=>{if(host._loadingRequest===request)host.textContent='Linked source records could not be loaded: '+e.message});
}
document.addEventListener('click',event=>{
 const trigger=event.target.closest('.report-project-details-trigger');
 const cell=trigger?.closest('td,th');
 if(!cell)return;
 const mapped=event.target.closest('[data-mpb-project-id]');
 if(mapped&&window.ReportMpbDetails?.hasRecord(mapped.dataset.mpbProjectId))return;
 const table=cell.closest('table'),head=table?.tHead?.rows[table.tHead.rows.length-1];
 if(!head)return;
 const indexes=[...head.cells].map((th,index)=>titleHeader(th.textContent)?index:-1).filter(index=>index>=0).slice(0,1);
 if(!indexes.length)return;
 event.preventDefault();event.stopPropagation();openProjectDetails(table,cell.parentElement,indexes);
},true);
function paginate(table,wrap){
 const rows=tableRows(table);
 let state=pagination.get(table);
 // Preserve native filtering, sorting and pagination controls.
 const next=wrap.nextElementSibling;
 const nativePager=next?.matches('.pager,.pagination,.report-table-pagination,[data-pagination]')&&next.querySelector('button');
 if(!state&&(table.dataset.nativePagination==='true'||nativePager)){mirrorPager(table,wrap,nativePager?next:null);return}
 if(!state&&rows.length<=10)return;
 if(!state){
  const makeNav=position=>{const nav=document.createElement('nav');nav.className='report-table-pagination report-table-pagination-'+position;nav.setAttribute('aria-label',label(table)+' pages · '+position+' controls');const previous=document.createElement('button'),following=document.createElement('button'),caption=document.createElement('span'),select=document.createElement('select'),sizeLabel=document.createElement('label');previous.type=following.type='button';previous.textContent='Previous';following.textContent='Next';caption.setAttribute('aria-live','polite');sizeLabel.append('Rows per page ');[10,25,50,100].forEach(n=>{const option=document.createElement('option');option.value=n;option.textContent=n;select.append(option)});select.value='10';sizeLabel.append(select);nav.append(previous,caption,following,sizeLabel);return{nav,previous,following,caption,select}};
  const top=makeNav('top'),bottom=makeNav('bottom');wrap.before(top.nav);wrap.after(bottom.nav);
  state={page:0,size:10,navs:[top,bottom]};pagination.set(table,state);
  for(const nav of state.navs){nav.previous.onclick=()=>{state.page--;scan()};nav.following.onclick=()=>{state.page++;scan()};nav.select.onchange=()=>{state.size=Number(nav.select.value);state.page=0;scan()}}
  addJsonExport(top.nav,table);
 }
 const pages=Math.max(1,Math.ceil(rows.length/state.size));state.page=Math.max(0,Math.min(state.page,pages-1));
 rows.forEach((row,i)=>row.classList.toggle('report-page-hidden',i<state.page*state.size||i>=(state.page+1)*state.size));
 const text=rows.length?`${state.page*state.size+1}–${Math.min(rows.length,(state.page+1)*state.size)} of ${rows.length} rows`:'No rows';
 state.navs.forEach(nav=>{if(nav.caption.textContent!==text)nav.caption.textContent=text;nav.previous.disabled=state.page===0;nav.following.disabled=state.page===pages-1;nav.select.value=String(state.size);nav.nav.hidden=rows.length<=state.size&&rows.length<=10});
}
function update(table){
 // The full HGAB coverage table owns its own search and pagination. Keep all
 // seven columns even if a page wrapper or cached markup drops the section flag.
 if(table.id==='all-hgab-document-coverage-table'||table.matches('[data-report-table-exempt]')||table.closest('[data-report-table-exempt]'))return;
 let wrap=table.parentElement;
 if(!wrap.classList.contains('report-table-scroll')){
  if(wrap.children.length===1&&/tablewrap|table-wrap|table-scroll|evidence-table|table-container/.test(wrap.className))wrap.classList.add('report-table-scroll');
  else{const holder=document.createElement('div');holder.className='report-table-scroll';table.before(holder);holder.append(table);wrap=holder}
  wrap.setAttribute('role','region');wrap.setAttribute('aria-label',label(table));
 }
 paginate(table,wrap);
 if(!wrap.previousElementSibling?.matches('.report-table-pagination')&&!wrap.nextElementSibling?.matches('.report-table-pagination'))addJsonExport(wrap,table);
 const header=table.tHead?.rows[table.tHead.rows.length-1];if(!header)return;
 const rows=[...table.tBodies].flatMap(body=>[...body.rows]);
 updateProjectTable(table,header,rows);
 [...header.cells].forEach((th,i)=>{
  if(!/^(?:straight.line meters|distance (?:meters|\(m\)))$/i.test(normalize(th.textContent)))return;
  th.classList.add('report-distance-column');
  rows.forEach(row=>{
   if(row.cells.length!==header.cells.length)return;
   const cell=row.cells[i],raw=normalize(cell.textContent);
   cell.classList.add('report-distance-value');
   if(!/^\d[\d,]*(?:\.\d+)?$/.test(raw))return;
   const value=Number(raw.replaceAll(',',''));if(!Number.isFinite(value))return;
   cell.dataset.distanceMeters=String(value);
   cell.textContent=value.toLocaleString('en-PH',{minimumFractionDigits:1,maximumFractionDigits:1})+' m';
   cell.title=value===0?'Same printed coordinates; this does not independently establish the same building.':'Approximate straight-line separation of the printed coordinate pair, in meters; not road distance.';
  });
 });
 [...header.cells].forEach((th,i)=>{
  if(!/^(?:congressman|congresswoman|congressional representative|representative)(?:\b|\()/i.test(normalize(th.textContent)))return;
  // Preserve physical column indexes for enrichment, sorting and CSV scripts.
  // Hide only simple columns whose currently rendered data cells are all empty.
  const cells=rows.filter(row=>row.cells.length===header.cells.length&&[...row.cells].every(cell=>cell.colSpan===1&&cell.rowSpan===1)).map(row=>row.cells[i]);
  const hide=cells.length>0&&cells.every(cell=>empty(cell.textContent));
  th.classList.toggle('report-empty-representative',hide);
  rows.forEach(row=>{if(row.cells.length===header.cells.length)row.cells[i].classList.toggle('report-empty-representative',hide)});
 });
}
function updateProjectTable(table,header,rows){
 const titleIndexes=[...header.cells].map((th,index)=>titleHeader(th.textContent)?index:-1).filter(index=>index>=0);
 const visible=new Set();if(titleIndexes.length)visible.add(titleIndexes[0]);
 if(titleIndexes.length){
  const candidates=[...header.cells].map((th,index)=>({index,label:normalize(th.textContent).toLowerCase(),width:Math.max(normalize(th.textContent).length,...rows.map(row=>row.cells.length===header.cells.length?Math.min(100,cellText(row.cells[index]).length):0))})).filter(item=>!titleIndexes.includes(item.index));
  const score=label=>{
   if(/\b(?:per meter|per km|per lane|density|unit rate|rate\s*\/|price per)\b/.test(label))return 14;
   if(/\b(?:allocation|amount|total cost|cost|peso|appropriation|budget)\b/.test(label))return 12;
   if(/\b(?:top pow|pow category|leading extracted pow|named schools|named buildings)\b/.test(label))return 11;
   if(/\b(?:quantity|qty|length|meters|metres|lanes|schools|buildings|doors|units)\b/.test(label))return 10;
   if(/\b(?:flag|review|status|difference|change|adjustment|scope|interpretation)\b/.test(label))return 7;
   if(/\b(?:program|office|district|region|year|source|page|evidence|basis)\b/.test(label))return 4;
   return 2;
  };
  candidates.sort((a,b)=>score(b.label)-score(a.label)||b.width-a.width||a.index-b.index);
  candidates.slice(0,Math.max(1,3-visible.size)).forEach(item=>visible.add(item.index));
 }
 [...header.cells].forEach((cell,index)=>{
  const isPrimaryTitle=index===titleIndexes[0],isVisible=visible.has(index);
  cell.classList.toggle('report-card-hidden-column',!isVisible&&titleIndexes.length>0);
  cell.classList.toggle('report-project-title-column',isPrimaryTitle);
 });
 rows.forEach(row=>{
  if(row.cells.length!==header.cells.length)return;
  [...row.cells].forEach((cell,index)=>{
   const isPrimaryTitle=index===titleIndexes[0],isVisible=visible.has(index);
   cell.classList.toggle('report-card-hidden-column',!isVisible&&titleIndexes.length>0);
   cell.classList.toggle('report-project-title-cell',isPrimaryTitle);
   if(!isPrimaryTitle){cell.removeAttribute('data-report-project-title');cell.querySelectorAll('.report-project-details-trigger').forEach(node=>node.remove());return}
   if(cell.querySelector('.report-project-details-trigger'))return;
   cell.dataset.reportProjectTitle='true';
   if(!cell.querySelector('[data-mpb-project-id]')){
    const button=document.createElement('button');button.type='button';button.className='report-project-details-trigger';button.textContent='Details';
    const title=cellText(cell);button.setAttribute('aria-label','Open project details for '+title.slice(0,180));cell.append(button);
   }
  });
 });
 if(!titleIndexes.length)return;
 let group=table.querySelector(':scope > colgroup.report-project-colgroup');
 if(!group){group=table.querySelector(':scope > colgroup');if(group)group.classList.add('report-project-colgroup');else{group=document.createElement('colgroup');group.className='report-project-colgroup';table.insertBefore(group,table.firstChild)}}
 if(group.children.length!==header.cells.length){group.replaceChildren(...[...header.cells].map(()=>document.createElement('col')))}
 const titleShare=Math.max(50,Math.min(85,Number(table.dataset.reportPrimaryTitleShare)||66));
 const metaIndexes=[...visible].filter(index=>index!==titleIndexes[0]);
 const metaWidths=metaIndexes.map(index=>Math.max(5,normalize(header.cells[index].textContent).length,...rows.map(row=>row.cells.length===header.cells.length?Math.min(40,cellText(row.cells[index]).length):0)));
 const metaTotal=metaWidths.reduce((a,b)=>a+b,0)||metaWidths.length;
 [...group.children].forEach((col,index)=>{
  let width='0%';
  const ti=index===titleIndexes[0]?0:-1,mi=metaIndexes.indexOf(index);
  if(ti>=0)width=`${titleShare.toFixed(2)}%`;
  else if(mi>=0)width=`${((100-titleShare)*metaWidths[mi]/metaTotal).toFixed(2)}%`;
  if(col.style.width!==width)col.style.width=width;
  col.classList.toggle('report-project-title-col',ti>=0);
  col.classList.toggle('report-card-hidden-column',!visible.has(index));
 });
}
// Resolve direct evidence fragments after asynchronous sections are created.
// This is anchor navigation, not a redirect or a bookmark compatibility layer.
let anchorPending=location.hash.slice(1),anchorResolved=false;
try{anchorPending=decodeURIComponent(anchorPending)}catch(e){anchorPending=''}
const cancelAnchor=()=>{anchorResolved=true};
window.addEventListener('wheel',cancelAnchor,{passive:true});window.addEventListener('touchstart',cancelAnchor,{passive:true});
window.addEventListener('hashchange',()=>{try{anchorPending=decodeURIComponent(location.hash.slice(1))}catch(e){anchorPending=''}anchorResolved=false;scan()});
function resolveAnchor(){if(!anchorPending||anchorResolved)return;const target=document.getElementById(anchorPending);if(target&&target.getClientRects().length){anchorResolved=true;requestAnimationFrame(()=>target.scrollIntoView({block:'start'}))}}
let pending=false;
const observer=new MutationObserver(()=>{if(!pending){pending=true;requestAnimationFrame(scan)}});
function scan(){pending=false;observer.disconnect();document.querySelectorAll('table').forEach(update);resolveAnchor();observer.observe(document.body,{childList:true,subtree:true,characterData:true})}
scan();
})();

(()=>{
'use strict';
const normalize=value=>String(value||'').replace(/\s+/g,' ').trim();
const empty=value=>/^(?:[—–\-\s]*|n\/?a|none|unknown|unresolved|not (?:available|resolved|identified|established))$/i.test(normalize(value));
function label(table){const section=table.closest('section,article');return normalize(section?.querySelector('h2,h3')?.textContent)||'Report table'}
const pagination=new WeakMap();
const titleHeader=text=>{
 const value=normalize(text).toLowerCase();
 if(/\b(?:amount|allocation|cost|rate|price|count|entries|project id)\b/.test(value))return false;
 return /\bproject\b/.test(value)||(/\b(?:closest|prior|current|nep|hgab|gaa)\b.*\btitle\b/.test(value)&&!/\bsimilarity\b/.test(value))||/\b(?:nep|hgab|gaa)\b.*\bline(?: item)?\b/.test(value)||/^extracted hgab record$/.test(value)||/^(?:(?:2nd|3rd|first|second|third) reading line|title)$/.test(value)||/^(?:facility|school\s*\/\s*building|named project)$/.test(value);
};
const detailDialog=(()=>{
 const dialog=document.createElement('dialog');dialog.className='report-project-dialog';dialog.setAttribute('aria-labelledby','report-project-dialog-title');
 dialog.innerHTML='<div class="report-project-card"><header><div><span class="report-project-kicker">Project row · source-table details</span><h2 id="report-project-dialog-title"></h2></div><button type="button" class="report-project-close" aria-label="Close project details">×</button></header><div class="report-project-fields"></div><nav class="report-project-links" aria-label="Project evidence links"></nav></div>';
 document.body.append(dialog);
 dialog.querySelector('.report-project-close').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close()});
 return dialog;
})();
function cellText(cell){const copy=cell.cloneNode(true);copy.querySelectorAll('.report-project-details-trigger').forEach(node=>node.remove());return normalize(copy.textContent)}
function safeLinks(row){
 const links=[];
 row.querySelectorAll('a[href]').forEach(anchor=>{
  try{const url=new URL(anchor.getAttribute('href'),location.href);if(!['http:','https:'].includes(url.protocol))return;links.push({label:normalize(anchor.innerText||anchor.textContent)||url.hostname,url:url.href})}catch{}
 });
 const seen=new Set();return links.filter(link=>!seen.has(link.url)&&seen.add(link.url));
}
function openProjectDetails(table,row,titleIndexes){
 const head=table.tHead?.rows[table.tHead.rows.length-1];if(!head||row.cells.length!==head.cells.length)return;
 const title=titleIndexes.map(index=>cellText(row.cells[index])).filter(Boolean).join(' · ');
 const fields=[];
 [...head.cells].forEach((th,index)=>{
  const label=normalize(th.innerText||th.textContent),value=cellText(row.cells[index]);
  if(!value||!label||titleIndexes.includes(index))return;
  fields.push(`<div class="report-project-field"><dt>${escapeHTML(label)}</dt><dd>${escapeHTML(value)}</dd></div>`);
 });
 const links=safeLinks(row);
 detailDialog.querySelector('#report-project-dialog-title').textContent=title||'Project details';
 detailDialog.querySelector('.report-project-fields').innerHTML=fields.length?fields.join(''):'<p>No additional row details are available.</p>';
 detailDialog.querySelector('.report-project-links').innerHTML=links.length?`<strong>Source links</strong>${links.map(link=>`<a href="${escapeHTML(link.url)}" target="_blank" rel="noopener">${escapeHTML(link.label)} ↗</a>`).join('')}`:'';
 if(!detailDialog.open)detailDialog.showModal();
}
function escapeHTML(value){return String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}
document.addEventListener('click',event=>{
 const trigger=event.target.closest('.report-project-details-trigger');
 const cell=trigger?.closest('td')||event.target.closest('td[data-report-project-title]');
 if(!cell||event.target.closest('[data-mpb-project-id]'))return;
 const table=cell.closest('table'),head=table?.tHead?.rows[table.tHead.rows.length-1];
 if(!head)return;
 const indexes=[...head.cells].map((th,index)=>titleHeader(th.textContent)?index:-1).filter(index=>index>=0).slice(0,2);
 if(!indexes.length)return;
 event.preventDefault();event.stopPropagation();openProjectDetails(table,cell.parentElement,indexes);
},true);
document.addEventListener('keydown',event=>{
 if(event.key!=='Enter'&&event.key!==' ')return;
 const cell=event.target.closest('td[data-report-project-title]');if(!cell)return;
 event.preventDefault();const table=cell.closest('table'),head=table?.tHead?.rows[table.tHead.rows.length-1];if(!head)return;
 const indexes=[...head.cells].map((th,index)=>titleHeader(th.textContent)?index:-1).filter(index=>index>=0).slice(0,2);openProjectDetails(table,cell.parentElement,indexes);
});
function paginate(table,wrap){
 const rows=[...table.tBodies].flatMap(body=>[...body.rows]);
 let state=pagination.get(table);
 // Preserve native filtering, sorting and pagination controls.
 const next=wrap.nextElementSibling;
 if(!state&&next?.matches('.pager,.pagination,[data-pagination]')&&next.querySelector('button'))return;
 if(!state&&rows.length<=10)return;
 if(!state){
  const nav=document.createElement('nav');nav.className='report-table-pagination';nav.setAttribute('aria-label',label(table)+' pages');
  const previous=document.createElement('button'),following=document.createElement('button'),caption=document.createElement('span'),select=document.createElement('select'),sizeLabel=document.createElement('label');
  previous.type=following.type='button';previous.textContent='Previous';following.textContent='Next';caption.setAttribute('aria-live','polite');sizeLabel.append('Rows per page ');
  [10,25,50,100].forEach(n=>{const option=document.createElement('option');option.value=n;option.textContent=n;select.append(option)});select.value='10';sizeLabel.append(select);nav.append(previous,caption,following,sizeLabel);wrap.after(nav);
  state={page:0,size:10,nav,previous,following,caption,select};pagination.set(table,state);
  previous.onclick=()=>{state.page--;scan()};following.onclick=()=>{state.page++;scan()};select.onchange=()=>{state.size=Number(select.value);state.page=0;scan()};
 }
 const pages=Math.max(1,Math.ceil(rows.length/state.size));state.page=Math.max(0,Math.min(state.page,pages-1));
 rows.forEach((row,i)=>row.classList.toggle('report-page-hidden',i<state.page*state.size||i>=(state.page+1)*state.size));
 const text=rows.length?`${state.page*state.size+1}–${Math.min(rows.length,(state.page+1)*state.size)} of ${rows.length} rows`:'No rows';
 if(state.caption.textContent!==text)state.caption.textContent=text;
 state.previous.disabled=state.page===0;state.following.disabled=state.page===pages-1;
 state.nav.hidden=rows.length<=state.size&&rows.length<=10;
}
function update(table){
 if(table.closest('[data-report-table-exempt]'))return;
 let wrap=table.parentElement;
 if(!wrap.classList.contains('report-table-scroll')){
  if(wrap.children.length===1&&/tablewrap|table-wrap|table-scroll|evidence-table|table-container/.test(wrap.className))wrap.classList.add('report-table-scroll');
  else{const holder=document.createElement('div');holder.className='report-table-scroll';table.before(holder);holder.append(table);wrap=holder}
  wrap.setAttribute('role','region');wrap.setAttribute('aria-label',label(table));
 }
 paginate(table,wrap);
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
 const visible=new Set();titleIndexes.slice(0,2).forEach(index=>visible.add(index));
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
  const isTitle=titleIndexes.includes(index),isVisible=visible.has(index);
  cell.classList.toggle('report-card-hidden-column',!isVisible&&titleIndexes.length>0);
  cell.classList.toggle('report-project-title-column',isTitle);
 });
 rows.forEach(row=>{
  if(row.cells.length!==header.cells.length)return;
  [...row.cells].forEach((cell,index)=>{
   const isTitle=titleIndexes.includes(index),isVisible=visible.has(index);
   cell.classList.toggle('report-card-hidden-column',!isVisible&&titleIndexes.length>0);
   cell.classList.toggle('report-project-title-cell',isTitle);
   if(!isTitle||cell.querySelector('.report-project-details-trigger'))return;
   cell.dataset.reportProjectTitle='true';
   if(!cell.querySelector('[data-mpb-project-id]')){
    const button=document.createElement('button');button.type='button';button.className='report-project-details-trigger';button.textContent='Details';
    const title=cellText(cell);button.setAttribute('aria-label','Open project details for '+title.slice(0,180));cell.append(button);
   }
  });
 });
 if(!titleIndexes.length)return;
 let group=table.querySelector(':scope > colgroup.report-project-colgroup');
 if(!group){group=document.createElement('colgroup');group.className='report-project-colgroup';table.insertBefore(group,table.firstChild)}
 if(group.children.length!==header.cells.length){group.replaceChildren(...[...header.cells].map(()=>document.createElement('col')))}
 const titleShare=titleIndexes.length>1?72:66;
 const metaIndexes=[...visible].filter(index=>!titleIndexes.includes(index));
 const metaWidths=metaIndexes.map(index=>Math.max(5,normalize(header.cells[index].textContent).length,...rows.map(row=>row.cells.length===header.cells.length?Math.min(40,cellText(row.cells[index]).length):0)));
 const metaTotal=metaWidths.reduce((a,b)=>a+b,0)||metaWidths.length;
 [...group.children].forEach((col,index)=>{
  let width='0%';
  const ti=titleIndexes.slice(0,2).indexOf(index),mi=metaIndexes.indexOf(index);
  if(ti>=0)width=`${(titleShare/Math.min(2,titleIndexes.length)).toFixed(2)}%`;
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

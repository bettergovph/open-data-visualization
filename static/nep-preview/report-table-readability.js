(()=>{
'use strict';
const normalize=value=>String(value||'').replace(/\s+/g,' ').trim();
const empty=value=>/^(?:[—–\-\s]*|n\/?a|none|unknown|unresolved|not (?:available|resolved|identified|established))$/i.test(normalize(value));
function label(table){const section=table.closest('section,article');return normalize(section?.querySelector('h2,h3')?.textContent)||'Report table'}
const pagination=new WeakMap();
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
let pending=false;
const observer=new MutationObserver(()=>{if(!pending){pending=true;requestAnimationFrame(scan)}});
function scan(){pending=false;observer.disconnect();document.querySelectorAll('table').forEach(update);observer.observe(document.body,{childList:true,subtree:true,characterData:true})}
scan();
})();

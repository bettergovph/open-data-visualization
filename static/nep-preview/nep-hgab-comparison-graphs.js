(()=>{
'use strict';
if(location.pathname.endsWith('/dpwh-hgab-comparison.html'))return;
const ns='http://www.w3.org/2000/svg',cache=new WeakMap();
const normalize=v=>String(v||'').replace(/\s+/g,' ').trim();
const peso=v=>'₱'+Number(v).toLocaleString('en-PH',{maximumFractionDigits:0});
function money(cell){
 const raw=normalize(cell?.textContent);if(!raw||/^(?:—|–|-|n\/a|unknown|not available)$/i.test(raw))return null;
 const match=raw.match(/^(?:₱|PHP\s*)?\s*([+−-]?\s*[\d,]+(?:\.\d+)?)\s*([BMK])?\s*$/i);
 if(!match)return null;const n=Number(match[1].replace(/[,\s]/g,'').replace('−','-'));
 return Number.isFinite(n)?n*({B:1e9,M:1e6,K:1e3}[match[2]?.toUpperCase()]||1):null;
}
function svgNode(tag,attrs={},text){const node=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([key,value])=>node.setAttribute(key,value));if(text!=null)node.textContent=text;return node}
function fullLabel(svg,row,i,y){
 const text=svgNode('text',{x:8,y:y+8,fill:'#24434b','font-size':16});
 const label=`${row.number}. ${row.label}`,parts=label.match(/.{1,36}(?:\s|$)|.{1,36}/g)||[label];
 parts.slice(0,2).forEach((s,j)=>text.append(svgNode('tspan',{x:8,dy:j?20:0},s.trim()+(j===1&&parts.length>2?'…':''))));
 text.append(svgNode('title',{},row.label));svg.append(text);
}
function graphic(rows,delta){
 const figure=document.createElement('figure'),caption=document.createElement('figcaption');caption.textContent=delta?'Allocation change · red = decrease, green = increase':'Stage amounts · blue = NEP, teal = HGAB 3rd reading';figure.append(caption);
 const height=75+rows.length*70,svg=svgNode('svg',{viewBox:`0 0 900 ${height}`,role:'img','aria-label':caption.textContent});
 const peak=Math.max(1,...rows.map(r=>delta?Math.abs(r.house-r.nep):Math.max(r.nep,r.house)));
 const left=335,width=540,zero=left+width/2;
 svg.append(svgNode('line',{x1:delta?zero:left,x2:delta?zero:left,y1:20,y2:height-40,stroke:'#99b4af'}));
 svg.append(svgNode('text',{x:delta?zero:left,y:height-15,'text-anchor':delta?'middle':'start','font-size':16,fill:'#24434b'},delta?'0 · HGAB minus NEP':'Allocation in pesos · common linear scale'));
 rows.forEach((r,i)=>{
  const y=40+i*70;fullLabel(svg,r,i,y);
  if(delta){
   const change=r.house-r.nep,w=Math.abs(change)/peak*(width/2-15),x=change<0?zero-w:zero;
   const bar=svgNode('rect',{x,y:y-4,width:Math.max(w,change===0?0:1),height:23,rx:3,fill:change<0?'#b33b35':'#187345'});
   bar.append(svgNode('title',{},`${r.label}: ${change<0?'decrease':'increase'} ${peso(Math.abs(change))}; NEP ${peso(r.nep)}, HGAB ${peso(r.house)}`));svg.append(bar);
   svg.append(svgNode('text',{x:zero,y:y+38,'text-anchor':'middle','font-size':16,fill:'#24434b'},(change>0?'+':change<0?'−':'')+peso(Math.abs(change))));
  }else{
   [[r.nep,'#426b9b',-6,'NEP'],[r.house,'#087e78',14,'HGAB']].forEach(([amount,color,offset,stage])=>{
    const bar=svgNode('rect',{x:left,y:y+offset,width:Math.max(0,amount/peak*(width-15)),height:16,rx:2,fill:color});bar.append(svgNode('title',{},`${r.label} · ${stage}: ${peso(amount)}`));svg.append(bar);
   });
   svg.append(svgNode('text',{x:left,y:y+48,'font-size':15,fill:'#24434b'},`${peso(r.nep)} → ${peso(r.house)}`));
  }
 });figure.append(svg);return figure;
}
function draw(table){
 if(table.closest('.archived-overview,#historical-nep-2nd,[id*="historical-nep-2nd"]')||!table.getClientRects().length)return;
 const headers=[...(table.tHead?.rows[table.tHead.rows.length-1]?.cells||[])].map(h=>normalize(h.textContent));
 const allocation=h=>/allocation|amount|budget|funding/i.test(h)&&!/adjustment|change|increase|decrease/i.test(h);
 const nep=headers.findIndex(h=>/\bNEP\b/i.test(h)&&allocation(h)),house=headers.findIndex(h=>/\bHGAB\b/i.test(h)&&allocation(h));
 if(nep<0||house<0)return;
 const label=headers.findIndex(h=>/project|category|sub.program|funding type|facility|programme|program/i.test(h)&&!allocation(h)&&!/^graph project$/i.test(h));
 const records=[...table.tBodies].flatMap(body=>[...body.rows]).filter(row=>!row.classList.contains('report-page-hidden')&&row.cells.length>=headers.length).map((row,i)=>({number:i+1,label:normalize(row.cells[label<0?0:label]?.textContent),nep:money(row.cells[nep]),house:money(row.cells[house])})).filter(r=>r.nep!=null&&r.house!=null&&r.nep>=0&&r.house>=0);
 if(!records.length){cache.get(table)?.node.remove();cache.delete(table);return}
 const signature=JSON.stringify(records),prior=cache.get(table);if(prior?.signature===signature)return;
 const rows=[...records].sort((a,b)=>Math.abs(b.house-b.nep)-Math.abs(a.house-a.nep)||b.house-a.house).slice(0,10);
 const panel=prior?.node||document.createElement('div');panel.className='nep-hgab-comparison-graphs';panel.replaceChildren();
 const note=document.createElement('p');note.className='comparison-chart-note';note.textContent=`NEP → HGAB 3rd reading · ${rows.length} of ${records.length} comparable records on this table page, ordered by largest absolute allocation change. Numbers identify the table rows. Values follow this table’s scope; blank or unresolved amounts are excluded, not treated as zero. Filters and pagination update these charts.`;panel.append(note);
 const grid=document.createElement('div');grid.className='comparison-chart-grid';grid.append(graphic(rows,false));
 if(rows.some(r=>r.house!==r.nep))grid.append(graphic(rows,true));
 else{const same=document.createElement('p');same.textContent='No allocation change among these comparable records.';grid.append(same)}panel.append(grid);
 const anchor=table.closest('.report-table-scroll')||table;if(!panel.isConnected)anchor.before(panel);
 cache.set(table,{node:panel,signature});
}
let scheduled=false;const observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;requestAnimationFrame(scan)}});
function scan(){scheduled=false;observer.disconnect();document.querySelectorAll('main table').forEach(draw);observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class','hidden']})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',scan,{once:true});else scan();
})();

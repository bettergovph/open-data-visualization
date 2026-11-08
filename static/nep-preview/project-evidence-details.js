/* Linked public evidence, fetched only when a Details dialog is opened. */
(()=>{'use strict';
 const script=document.currentScript,base=new URL('project-evidence/',script?.src||location.href);
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const norm=v=>String(v??'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
 const label=v=>String(v).replace(/([a-z0-9])([A-Z])/g,'$1 $2').replace(/_/g,' ').replace(/^./,c=>c.toUpperCase());
 const bucket=v=>{let hash=2166136261;for(const c of new TextEncoder().encode(v))hash=Math.imul(hash^c,16777619)>>>0;return(hash&255).toString(16).padStart(2,'0')};
 let manifestPromise;const shards=new Map();
 async function manifest(){if(!manifestPromise)manifestPromise=fetch(new URL('manifest.json',base),{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('Evidence index: HTTP '+r.status);return r.json()}).catch(e=>{manifestPromise=null;throw e});return manifestPromise}
 async function shard(code,m){if(!m.shards[code])return {titles:{}};if(!shards.has(code)){const p=fetch(new URL(m.shards[code].path+'?v='+m.shards[code].version,base)).then(r=>{if(!r.ok)throw Error('Linked evidence: HTTP '+r.status);return r.json()}).catch(e=>{shards.delete(code);throw e});shards.set(code,p)}return shards.get(code)}
 function url(value){try{const u=new URL(value,location.href);return ['http:','https:'].includes(u.protocol)?u.href:null}catch{return null}}
 function comparable(value){
  if(value===null||value===undefined)return '';
  if(typeof value==='number')return String(value);
  const raw=String(value).trim().replace(/[₱,$\s,]/g,'');
  if(raw&&Number.isFinite(Number(raw)))return String(Number(raw));
  return norm(value);
 }
 function alreadyVisible(key,value,visible){
  if(!visible||value===null||value===undefined||typeof value==='object')return false;
  const names={
   year:['year','fiscal year','fiscalyear'],fiscalyear:['year','fiscal year','fiscalyear'],
   stage:['stage','budget stage','version'],status:['status','document status','review status'],
   amountpesos:['amount','allocation','budget','hgab allocation','nep allocation','third total','third amount'],
   allocationpesos:['allocation','amount','budget','hgab allocation','nep allocation'],amountpesos:['amount','allocation','budget','hgab allocation','nep allocation'],
   amount_pesos:['amount','allocation','budget','hgab allocation','nep allocation'],
   office:['office','implementing office','district engineering office'],region:['region'],district:['district','legislative district'],
   code:['code','project code','hgab code','proposal code','occurrence id'],projectcode:['project code','code'],
   hgabid:['hgab code','hgab id','code'],id:['id','code','occurrence id'],
   sourcepage:['source page','page','source'],printedpage:['source page','page','source'],
   projectname:['project','project title','title','name'],title:['project','project title','title','name'],name:['project','project title','title','name']
  };
  const keyName=norm(key),matches=names[keyName.replaceAll(' ','')]||[keyName],wanted=comparable(value);
  if(!wanted)return false;
  const index=(visible.headers||[]).findIndex(header=>matches.some(name=>norm(name)===norm(header)));
  if(index>=0&&comparable(visible.values?.[index])===wanted)return true;
  return (visible.values||[]).some(current=>comparable(current)===wanted&&wanted.length>2);
 }
 function valueHTML(value,key,visible){
  if(value===null||value===undefined||value==='')return '<span class="muted">Not recorded</span>';
  if(typeof value==='boolean')return value?'Yes':'No';
  if(typeof value==='number')return /year/i.test(key||'')?String(value):(/pesos|unitcost|secondtotal|thirdtotal|secondamount|thirdamount/i.test(key||'')?'₱':'')+value.toLocaleString('en-PH',{maximumFractionDigits:4});
  if(typeof value==='string'){
   if(/^https?:\/\//i.test(value)){const u=url(value);return u?'<a href="'+esc(u)+'" target="_blank" rel="noopener">Open source ↗</a>':esc(value)}
   return esc(value);
  }
  if(Array.isArray(value))return '<ol class="evidence-items">'+value.map(v=>'<li>'+valueHTML(v,key,visible)+'</li>').join('')+'</ol>';
  const entries=Object.entries(value).filter(([k,v])=>!alreadyVisible(k,v,visible));
  return entries.length?'<dl class="evidence-facts">'+entries.map(([k,v])=>'<div><dt>'+esc(label(k))+'</dt><dd>'+valueHTML(v,k,visible)+'</dd></div>').join('')+'</dl>':'<span class="muted">No additional values beyond the table.</span>';
 }
 function sourcePanel(record,visible){
  const section=document.createElement('section');section.className='linked-source-record';
  const meta=[record.year&&'FY'+record.year,record.stage,...record.identifiers].filter(value=>value&&!((visible?.values||[]).some(current=>comparable(current)===comparable(value))));
  const fields=Object.entries(record.fields||{}).filter(([k,v])=>!alreadyVisible(k,v,visible));
  section.innerHTML='<h4>'+esc(record.dataset)+'</h4>'+ (meta.length?'<p class="muted">'+esc(meta.join(' · '))+'</p>':'') + (fields.length?'<h5>Additional fields</h5><dl class="evidence-facts">'+fields.map(([k,v])=>'<div><dt>'+esc(label(k))+'</dt><dd>'+valueHTML(v,k,visible)+'</dd></div>').join('')+'</dl>':'');
  for(const id of record.identifiers.filter(id=>/^2027DPWH-Proposal-/.test(id))){const a=document.createElement('a');a.href=new URL('../project-documents.html?project='+encodeURIComponent(id),base).href;a.target='_blank';a.rel='noopener';a.textContent='Full project document record ↗';section.append(a)}
  for(const [key,value] of Object.entries(record.evidence||{})){
   const panel=document.createElement('details');panel.className='linked-evidence-section';panel.open=['flags','evidenceCautions','lengthReview'].includes(key);
   panel.innerHTML='<summary>'+esc(label(key))+(Array.isArray(value)?' · '+value.length+' records':'')+'</summary>';
   if(key==='documents'&&Array.isArray(value)){
    for(const doc of value){const d=document.createElement('details');d.className='linked-evidence-document';d.open=true;d.innerHTML='<summary>'+esc(String(doc.kind||'Document').toUpperCase())+' · '+esc(doc.status||'status unavailable')+' · '+(doc.billRows?.length||0)+' recovered bill rows</summary>'+valueHTML(Object.fromEntries(Object.entries(doc).filter(([k])=>!['billRows','costCategories'].includes(k))),null,visible);
     if(doc.costCategories?.length){const div=document.createElement('div');div.innerHTML='<h5>Printed cost categories</h5>';paged(div,doc.costCategories,visible);d.append(div)}
     if(doc.billRows?.length){const div=document.createElement('div');div.innerHTML='<h5>Recovered POW bill quantities and prices</h5>';paged(div,doc.billRows,visible);d.append(div)}panel.append(d)}
   }else if(Array.isArray(value))paged(panel,value,visible);else {const div=document.createElement('div');div.innerHTML=valueHTML(value,key,visible);panel.append(div)}
   section.append(panel);
  }
  return section;
 }
 function paged(host,records,visible){
  const content=document.createElement('div'),nav=document.createElement('div');nav.className='evidence-pagination';let page=0;
  const prev=document.createElement('button'),next=document.createElement('button'),status=document.createElement('span');prev.type=next.type='button';prev.textContent='Previous';next.textContent='Next';nav.append(prev,status,next);host.append(content,nav);
  function draw(){content.innerHTML='<ol start="'+(page*10+1)+'" class="evidence-items">'+records.slice(page*10,page*10+10).map(v=>'<li>'+valueHTML(v,null,visible)+'</li>').join('')+'</ol>';status.textContent=(page*10+1)+'–'+Math.min(records.length,(page+1)*10)+' of '+records.length;prev.disabled=page===0;next.disabled=(page+1)*10>=records.length;nav.hidden=records.length<=10}
  prev.onclick=()=>{page--;draw()};next.onclick=()=>{page++;draw()};draw();
 }
 function context(table,row){
  const head=table.tHead?.rows[table.tHead.rows.length-1],text=row.textContent;
  const identifiers=new Set(text.match(/HB\d+-[23]-[\w-]+|2027DPWH-Proposal-\d+|nep[_:-][\w:-]+|ib:p\d+:r\d+/gi)||[]);
  for(const el of [row,...row.querySelectorAll('[data-project-code],[data-project-id],[data-mpb-project-id],a[href]')]){
   for(const v of [el.dataset?.projectCode,el.dataset?.projectId,el.dataset?.hgabId,el.dataset?.mpbProjectId])if(v)identifiers.add(v);
   if(el.matches('a[href]'))try{const u=new URL(el.href);for(const k of ['project','code','id'])if(u.searchParams.get(k))identifiers.add(u.searchParams.get(k))}catch{}
  }
  const primaryIndex=row.querySelector('.report-project-title-cell')?.cellIndex;
  const primaryStage=head?.cells[primaryIndex]?.textContent.match(/\b(NEP|HGAB|GAA)\b/i)?.[1]?.toUpperCase();
  let year=row.dataset.projectYear,stage=row.dataset.projectStage||primaryStage,amount=null,district=null;
  if(head)[...head.cells].forEach((th,i)=>{const key=norm(th.textContent),cell=row.cells[i];if(!cell)return;const text=cell.textContent;
   if(!year&&/year|fiscal|stage/.test(key)){const columnStage=(th.textContent+' '+text).match(/\b(HGAB|GAA|NEP)\b/i)?.[1]?.toUpperCase();if(!primaryStage||!columnStage||columnStage===primaryStage){year=text.match(/(?:FY\s*)?((?:19|20)\d{2})\b/)?.[1];if(columnStage)stage=columnStage}}
   if(/^(?:district|legislative district)$/.test(key))district=text;
   if(amount===null&&/^(?:allocation|amount|budget|total cost)(?: |$)/.test(key)){const n=text.replace(/[,₱\s]/g,'');if(/^\d+(?:\.\d+)?$/.test(n))amount=Number(n)}
  });
  return {identifiers:[...identifiers],year:year?Number(year):null,stage,amount,district};
 }
 function selectCandidates(records,ctx){
  let result=records;
  if(ctx.district){const same=result.filter(r=>norm(r.fields.district)===norm(ctx.district));if(same.length)result=same}
  if(ctx.year){const same=result.filter(r=>Number(r.year)===ctx.year);if(same.length)result=same;else return []}
  if(ctx.stage){const s=String(ctx.stage).match(/HGAB|GAA|NEP/)?.[0];if(s){const same=result.filter(r=>String(r.stage||'').includes(s));if(same.length)result=same}}
  if(ctx.amount!==null){const same=result.filter(r=>[r.fields.amountPesos,r.fields.allocationPesos,r.fields.amount_pesos,r.fields.thirdTotal,r.fields.thirdAmount].some(v=>v!==undefined&&Math.abs(Number(v)-ctx.amount)<.01));if(same.length)result=same;else return []}
  return result;
 }
 async function enrich({host,table,row,titles,visible={headers:[],values:[]}}){
  const token={};host._evidenceToken=token;host.innerHTML='<h3>Linked project evidence</h3><p role="status">Looking up source identifiers, budget records and linked documents…</p>';
  try{
   const m=await manifest(),ctx=context(table,row),keys=[...new Set(titles.map(norm).filter(Boolean))];
   for(const title of [...keys].filter(k=>/^(?:roads?|bridges?|flood control|mpb|multi purpose buildings?)$/.test(k))){if(ctx.year)keys.push(title+' year '+ctx.year);if(ctx.district)keys.push(title+' district '+norm(ctx.district))}
   const codes=new Set(keys.map(bucket));for(const id of ctx.identifiers)for(const b of m.idBuckets[id]||[])codes.add(b);
   const payloads=await Promise.all([...codes].map(b=>shard(b,m)));if(host._evidenceToken!==token)return;
   const available=payloads.flatMap(p=>Object.values(p.titles).flat()),unique=rows=>[...new Map(rows.map(r=>[r.recordId,r])).values()];
   const byId=unique(available.filter(r=>r.identifiers.some(id=>ctx.identifiers.includes(id))));
   let matches=byId.length?byId:selectCandidates(unique(available.filter(r=>keys.includes(norm(r.title)))),ctx);
   const direct=matches.length;
   const linkedIds=[...new Set(matches.flatMap(r=>r.linkedIds||[]))],linkedCodes=new Set(linkedIds.flatMap(id=>m.idBuckets[id]||[]));
   const linkedPayloads=await Promise.all([...linkedCodes].map(b=>shard(b,m)));
   const linked=unique(linkedPayloads.flatMap(p=>Object.values(p.titles).flat()).filter(r=>r.identifiers.some(id=>linkedIds.includes(id))));
   if(host._evidenceToken!==token)return;
   host.innerHTML='<h3>Linked data and source documents</h3><p class="evidence-match-status">'+(matches.length?esc(byId.length?'Matched by explicit source identifier':'Matched by complete normalized title'+(ctx.year?', budget year':'')+(ctx.amount!==null?' and allocation context':''))+' · '+direct+' source observations'+(linked.length?' · '+linked.length+' linked counterpart/document records':''):'No distinct linked record was found for this row.')+'</p>';
   if(!matches.length)return;
   const groups=new Map();for(const r of matches){const identity=r.identifiers.find(id=>/^HB/.test(id))||r.identifiers.find(id=>/^2027DPWH-Proposal-/.test(id))||[r.year||'undated',r.stage||'stage unspecified',r.fields.amountPesos??r.fields.allocationPesos??'',norm(r.title)].join('|');if(!groups.has(identity))groups.set(identity,[]);groups.get(identity).push(r)}
   const sourceHost=document.createElement('div');
   function renderSelection(records){sourceHost.replaceChildren();for(const r of records)sourceHost.append(sourcePanel(r,visible));const ids=new Set(records.flatMap(r=>r.linkedIds||[])),chosen=linked.filter(r=>r.identifiers.some(id=>ids.has(id)));if(chosen.length){const section=document.createElement('details');section.className='linked-evidence-section';section.open=true;section.innerHTML='<summary>Linked NEP / Transparency counterparts · '+chosen.length+' source records</summary><p>Explicitly linked records from other budget stages. Stage amounts and project-document evidence are shown only when they add information beyond the table row.</p>';for(const r of chosen)section.append(sourcePanel(r,visible));sourceHost.append(section)}}
   if(groups.size>1){const control=document.createElement('label');control.className='evidence-record-picker';control.textContent='Source occurrence / year ';const select=document.createElement('select');select.append(new Option('Choose an occurrence to inspect',''));for(const [key,items] of groups){const r=items[0];select.append(new Option([r.year&&'FY'+r.year,r.stage,r.fields.amountPesos!=null?'₱'+Number(r.fields.amountPesos).toLocaleString('en-PH'):'',r.dataset,...r.identifiers].filter(Boolean).join(' · '),key))}control.append(select);host.append(control);select.onchange=()=>renderSelection(groups.get(select.value)||[]);const msg=document.createElement('p');msg.textContent=groups.size+' distinct occurrences share this title. Choose the intended record; their allocations are separate.';sourceHost.append(msg)}else renderSelection(matches);
   host.append(sourceHost);
   const note=document.createElement('p');note.className='muted';note.textContent='Source snapshot: '+m.generatedAtUtc+'.';host.append(note);
  }catch(e){if(host._evidenceToken===token){host.innerHTML='<h3>Linked data and source documents</h3><p role="status">Could not load linked evidence: '+esc(e.message)+'.</p>';const retry=document.createElement('button');retry.type='button';retry.textContent='Retry linked data';retry.onclick=()=>enrich({host,table,row,titles,visible});host.append(retry)}}
 }
 window.ReportProjectEvidence={enrich,norm,bucket};
})();

/* District allocations: annual charts, cumulative totals, and source project records. */
(()=>{'use strict';
const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+fmt(v);
window.integratedDataPromise.then(async D=>{
 const dist=$('trend-district'),year=$('rank-year'),category=$('rank-category'),query=$('project-filter'),metric=$('rank-metric');
 let projectPage=0,rankPage=0,drawId=0,allProjects=null;
 const projectPromise=fetch('integrated-project-data.json?v='+encodeURIComponent(D.buildVersion||'current')).then(r=>{if(!r.ok)throw Error('Project data: HTTP '+r.status);return r.json()}).then(d=>allProjects=d.projects);
 projectPromise.catch(e=>{$('project-results-status').textContent=e.message});
 for(const d of D.districts){const o=new Option(d.district,d.districtId);dist.add(o)}
 year.add(new Option('Total · all available years','all'));
 for(const p of D.periods)year.add(new Option('FY'+p.year+' '+p.stage,p.year+'|'+p.stage));
 for(const p of D.yearAvailability||[]){const o=new Option('FY'+p.year+' · unavailable',p.year+'|unavailable');o.disabled=true;o.title=p.reason;year.add(o)}
 category.add(new Option('All four project categories','all'));for(const c of D.categories)category.add(new Option(c,c));
 year.value='all';
 const byId=new Map(D.districts.map(d=>[d.districtId,d]));
 const periodMatches=p=>year.value==='all'||p.year+'|'+p.stage===year.value;
 function sum(rows){return rows.reduce((r,p)=>({totalPesos:r.totalPesos+Number(p.totalPesos??p.amountPesos??0),lineItems:r.lineItems+Number(p.lineItems??1)}),{totalPesos:0,lineItems:0})}
 function aggregate(){
  const result=new Map(D.districts.map(d=>{const row={...d,totalPesos:0,lineItems:0};if(year.value!=='all'){const portrait=d.representativePhotoSourcesByPeriod?.[year.value];row.representative=d.representativesByPeriod?.[year.value]||'Historical member unresolved';row.representativePhotoUrl=portrait?.url||null;row.representativePhotoSourceUrl=portrait?.sourceUrl||null;row.representativeContextStatus=d.representativeStatusByPeriod?.[year.value]||''}return [d.districtId,row]}));
  const q=query.value.trim().toLowerCase(),cat=category.value;
  if(q){for(const p of allProjects||[]){if(!periodMatches(p)||(cat!=='all'&&p.category!==cat)||!String(p.name).toLowerCase().includes(q))continue;const d=result.get(p.districtId);if(d){d.lineItems++;d.totalPesos+=Number(p.amountPesos||0)}}}
  else for(const a of D.annual){if(!periodMatches(a))continue;const value=cat==='all'?a:a.categories?.[cat];const d=result.get(a.districtId);if(d&&value){d.totalPesos+=Number(value.totalPesos||0);d.lineItems+=Number(value.lineItems||0)}}
  return [...result.values()];
 }
 function face(d){return d.representativePhotoUrl?'<img src="'+esc(d.representativePhotoUrl)+'" alt="'+esc(d.representative)+'" loading="lazy" title="'+esc('Portrait source: '+(d.representativePhotoSourceUrl||'source unavailable'))+'">':'<span class="portrait-unavailable" title="Portrait unavailable">'+esc((d.representative||'').split(/\s+/).map(s=>s[0]).slice(0,2).join(''))+'</span>'}
 function tableRow(d,index,total,byLines=false){return '<tr><td>'+fmt(index)+'</td><td>'+esc(d.district)+'</td><td><span class="representative">'+face(d)+'<span>'+esc(d.representative||'—')+'</span></span></td><td>'+fmt(d.lineItems)+'</td><td class="amount">'+peso(d.totalPesos)+'</td><td class="amount">'+(total?100*(byLines?d.lineItems:d.totalPesos)/total:0).toFixed(2)+'%</td></tr>'}
 function imageFallbacks(host){host.querySelectorAll('img').forEach(img=>img.addEventListener('error',()=>{const badge=document.createElement('span');badge.className='portrait-unavailable';badge.textContent='Photo unavailable';img.replaceWith(badge)},{once:true}))}
 function chart(){
  const selected=dist.value,d=byId.get(selected),q=query.value.trim().toLowerCase(),cat=category.value;
  const series=D.periods.map(p=>{
   const rows=q?(allProjects||[]).filter(x=>x.districtId===selected&&x.year===p.year&&x.stage===p.stage&&(cat==='all'||x.category===cat)&&String(x.name).toLowerCase().includes(q)):D.annual.filter(x=>x.districtId===selected&&x.year===p.year&&x.stage===p.stage).map(x=>cat==='all'?x:(x.categories?.[cat]||{lineItems:0,totalPesos:0}));
   const period=p.year+'|'+p.stage;
   return {...p,...sum(rows),portrait:d?.representativePhotoSourcesByPeriod?.[period],member:d?.representativesByPeriod?.[period]||'Member unresolved',rosterCongress:d?.representativeCongressByPeriod?.[period],contextStatus:d?.representativeStatusByPeriod?.[period]||''};
  });
  const W=1100,H=430,L=85,T=25,B=285,plotH=B-T,band=(W-L-25)/series.length,max=Math.max(1,...series.map(x=>x.totalPesos));
  const grid=[0,.25,.5,.75,1].map(t=>`<line x1="${L}" y1="${B-plotH*t}" x2="1080" y2="${B-plotH*t}" stroke="#ddd"/><text x="${L-10}" y="${B-plotH*t+4}" text-anchor="end" font-size="11">₱${(max*t/1e9).toFixed(1)}B</text>`).join('');
  const bars=series.map((p,i)=>{
   const x=L+i*band+band*.2,w=band*.6,h=p.totalPesos/max*plotH,cx=x+w/2;
   const nameLines=[];for(const word of p.member.split(/\s+/)){const last=nameLines.length-1;if(last>=0&&(nameLines[last]+' '+word).length<=17)nameLines[last]+=' '+word;else nameLines.push(word)}
   const nameText=nameLines.slice(0,3).map((line,j)=>`<text x="${cx}" y="${381+j*10}" font-size="8" text-anchor="middle">${esc(line)}</text>`).join('');
   const portrait=p.portrait?.url?`<a href="${esc(p.portrait.sourceUrl||p.portrait.url)}" target="_blank" rel="noopener noreferrer" aria-label="Portrait source and credit for ${esc(p.member)}"><image href="${esc(p.portrait.url)}" x="${cx-14}" y="331" width="28" height="36" preserveAspectRatio="xMidYMid slice"/></a>`:`<text x="${cx}" y="350" text-anchor="middle" font-size="7" fill="#6b7280">No verified photo</text>`;
   const evidence=p.portrait?' · Photograph: '+(p.portrait.photoCongress?p.portrait.photoCongress+'th Congress':'source date recorded in portrait audit')+' · '+(p.portrait.creator||'')+' · '+(p.portrait.license||'')+' · '+(p.portrait.sourceUrl||''):'';
   return `<g><title>${esc('FY'+p.year+' '+p.stage+' · '+p.rosterCongress+'th Congress · '+p.member+' · '+peso(p.totalPesos)+' · '+p.contextStatus+evidence)}</title><rect x="${x}" y="${B-h}" width="${w}" height="${h}" rx="4" fill="#0038A8"/><text x="${cx}" y="${Math.max(T+10,B-h-8)}" text-anchor="middle" font-size="10">${p.totalPesos?'₱'+(p.totalPesos/1e9).toFixed(2)+'B':'—'}</text><text x="${cx}" y="310" font-size="11" text-anchor="middle">FY${p.year}</text><text x="${cx}" y="324" font-size="8" text-anchor="middle">${p.rosterCongress}th Congress</text>${portrait}${nameText}</g>`;
  }).join('');
  $('allocation-chart').innerHTML=`<p class="muted">Names and portraits follow the corresponding Congress roster. Hover over a year for the member; click a portrait for its source and credit. <a href="integrated-historical-photo-audit.csv">Download portrait audit ↗</a></p><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Annual allocations and historical Congress members for ${esc(d?.district)}">${grid}${bars}</svg>`;
  $('allocation-chart').querySelectorAll('image').forEach(img=>img.addEventListener('error',()=>{const text=document.createElementNS('http://www.w3.org/2000/svg','text');text.setAttribute('x',Number(img.getAttribute('x'))+14);text.setAttribute('y','350');text.setAttribute('text-anchor','middle');text.setAttribute('font-size','7');text.textContent='Photo unavailable';img.replaceWith(text)},{once:true}));
 }
 async function draw(){
  const id=++drawId;if(query.value.trim())await projectPromise;if(id!==drawId)return;
  chart();const rows=aggregate(),selected=rows.find(x=>x.districtId===dist.value),totals=sum(rows),byLines=metric.value==='lines';
  rows.sort((a,b)=>byLines?(b.lineItems-a.lineItems||b.totalPesos-a.totalPesos):(b.totalPesos-a.totalPesos||b.lineItems-a.lineItems));
  $('period-total').textContent=peso(selected?.totalPesos);$('period-lines').textContent=fmt(selected?.lineItems);
  const cov=D.coverage.filter(periodMatches),unresolved=cov.reduce((n,c)=>n+Number(c.unresolvedPesos||0),0),assigned=cov.reduce((n,c)=>n+Number(c.assignedPesos||0),0);
  $('unresolved-total').textContent=query.value.trim()?'—':peso(unresolved);$('unresolved-label').textContent=query.value.trim()?'Unassigned title-filter coverage unavailable':'Unassigned allocation · '+(year.value==='all'?'all available years':'selected year');
  $('period-coverage-label').textContent='All classified categories · district-assigned share';$('period-coverage').textContent=assigned+unresolved?(100*assigned/(assigned+unresolved)).toFixed(1)+'%':'—';
  $('all-years-total').textContent=peso(totals.totalPesos);$('all-years-caption').textContent=(year.value==='all'?'All '+D.periods.length+' available year/stage snapshots':'Selected year/stage')+' · '+fmt(totals.lineItems)+' assigned project lines across all districts';
  $('ranking-title').textContent='District ranking · '+(year.value==='all'?'all available years':'selected year');$('lowest-title').textContent='Lowest-allocation districts · '+(year.value==='all'?'all available years':'selected year');
  const pages=Math.max(1,Math.ceil(rows.length/50));rankPage=Math.min(rankPage,pages-1);
  $('district-ranking').innerHTML=rows.slice(rankPage*50,rankPage*50+50).map((d,i)=>tableRow(d,rankPage*50+i+1,byLines?totals.lineItems:totals.totalPesos,byLines)).join('');
  $('ranking-page').textContent='Page '+(rankPage+1)+' of '+pages+' · '+rows.length+' districts';$('ranking-prev').disabled=!rankPage;$('ranking-next').disabled=rankPage+1>=pages;
  const rosterLabel=year.value==='all'?'Current district representative · context only':(D.districts[0].representativeCongressByPeriod?.[year.value]||'Historical')+'th Congress roster · context';
  for(const id of ['district-ranking','lowest-ranking'])$(id).closest('table').querySelectorAll('thead th')[2].textContent=rosterLabel;
  $('ranking-status').textContent='Ranked by '+(byLines?'project lines':'allocation')+' · '+(year.value==='all'?D.periods.length+' included snapshots · current roster context':'selected snapshot · corresponding Congress roster context')+'.';
  const lowest=rows.slice().sort((a,b)=>a.totalPesos-b.totalPesos||a.district.localeCompare(b.district)).slice(0,10);
  $('lowest-ranking').innerHTML=lowest.map((d,i)=>tableRow(d,i+1,totals.totalPesos)).join('');$('lowest-status').textContent='10 lowest totals, including zero, among '+rows.length+' districts.';imageFallbacks($('district-ranking'));imageFallbacks($('lowest-ranking'));
  await projectPromise;if(id!==drawId)return;
  const q=query.value.trim().toLowerCase(),matches=allProjects.filter(p=>p.districtId===dist.value&&periodMatches(p)&&(category.value==='all'||p.category===category.value)&&(!q||String(p.name).toLowerCase().includes(q)));
  const pp=Math.max(1,Math.ceil(matches.length/50));projectPage=Math.min(projectPage,pp-1);
  $('matching-project-rows').innerHTML=matches.slice(projectPage*50,projectPage*50+50).map(p=>'<tr data-project-year="'+p.year+'" data-project-stage="'+esc(p.stage)+'"><td>'+esc(p.name)+'</td><td>'+esc(byId.get(p.districtId)?.district)+'</td><td>'+esc(p.category)+'</td><td>'+peso(p.amountPesos)+'</td><td>'+p.year+' '+esc(p.stage)+'</td><td>'+esc(p.source)+'</td></tr>').join('')||'<tr><td colspan="6">No matching project rows.</td></tr>';
  $('project-results-status').textContent=fmt(matches.length)+' matching project rows · '+(year.value==='all'?'all available years':'selected year');$('matching-project-page').textContent='Page '+(projectPage+1)+' of '+pp+' · '+fmt(matches.length)+' rows';$('matching-project-prev').disabled=!projectPage;$('matching-project-next').disabled=projectPage+1>=pp;
 }
 function safeDraw(){draw().catch(e=>{$('ranking-status').textContent='Could not update district records: '+e.message})}
 [dist,year,category,metric].forEach(x=>x.addEventListener('change',()=>{rankPage=0;projectPage=0;safeDraw()}));let timer;query.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{rankPage=0;projectPage=0;safeDraw()},200)});
 $('ranking-prev').onclick=()=>{rankPage--;safeDraw()};$('ranking-next').onclick=()=>{rankPage++;safeDraw()};$('matching-project-prev').onclick=()=>{projectPage--;safeDraw()};$('matching-project-next').onclick=()=>{projectPage++;safeDraw()};
 $('rank-export').onclick=()=>{const rows=aggregate().sort((a,b)=>metric.value==='lines'?b.lineItems-a.lineItems:b.totalPesos-a.totalPesos),csv=[['District','Representative Congress context','Project lines','Allocation pesos','Period'],...rows.map(r=>[r.district,r.representative,r.lineItems,r.totalPesos,year.value])].map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n');const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv'}));const a=document.createElement('a');a.href=url;a.download='district-ranking.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
 safeDraw();
}).catch(e=>{$('ranking-status').textContent=e.message});
})();

(()=>{
const config={"dpwh.html": {"titles": ["Projects by region", "Other priority programs by district", "District Engineering Office allocation ranking"]}, "dpwh-hgab.html": {"ids": ["hgab-headline-breakdowns"], "titles": ["Projects by region", "Other priority programs by district", "District Engineering Office allocation ranking"]}, "dpwh-hgab-comparison.html": {"titles": ["2nd vs 3rd allocations", "Line changes after filters"]}, "fmr.html": {"titles": ["Regional allocations · NEP versus HGAB"]}, "hfep.html": {"ids": ["hfep-nep-stage-comparison", "reviewed-hfep-annex"], "titles": ["Allocation counts by facility type", "HFEP component allocation mix"]}, "nia-irrigation.html": {"ids": ["reviewed-nia-controls"]}, "nia.html": {"ids": ["nia-detail-reviewed-nia-controls"]}, "summary.html": {"ids": ["summary-neutral"]}},name=document.currentScript?.dataset.reportPage||location.pathname.split('/').pop()||'index.html',rule=config[name==='index.html'?'summary.html':name];
if(!rule)return;
const retired=new WeakSet();let scheduled=false;
function retire(node){
 if(!node||retired.has(node)||node.id==='upstream-budget-analysis')return;
 retired.add(node);
 for(const canvas of node.querySelectorAll('canvas')){
  try{if(window.Chart?.getChart)window.Chart.getChart(canvas)?.destroy();else if(window.Chart?.instances)Object.values(window.Chart.instances).filter(c=>c.canvas===canvas).forEach(c=>c.destroy());}catch(e){console.warn('Archived chart cleanup',e);}
 }
 // Keep original methodology prose and data downloads available beside the
 // upstream link. Only the overview charts/tables and their controls retire.
 const downloads=[...node.querySelectorAll('a[download]')].map(a=>a.cloneNode(true));
 const methods=[...node.querySelectorAll('p')].filter(p=>/method|scope|uncertain|not (?:proof|evidence)|source|missing|limitation|discrepancy|not.*(?:certif|establish)/i.test(p.textContent)).map(p=>p.cloneNode(true));
 const panel=document.createElement('div');panel.className='archived-analysis-link';
 panel.innerHTML='<p><strong>Higher-level overview moved to the archive.</strong> <a href="https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/#compare">Use csiiiv for current budget-stage totals and comparisons ↗</a> · <a href="archive.html#superseded-overviews">Archived sections and source revision</a>.</p>';
 if(downloads.length){const p=document.createElement('p');downloads.forEach((a,i)=>{if(i)p.append(' · ');p.append(a)});panel.append(p)}
 if(methods.length){const notes=document.createElement('div');notes.className='archived-supporting-methodology';notes.innerHTML='<h3>Retained source and scope notes</h3>';methods.forEach(p=>notes.append(p));panel.append(notes)}
 node.replaceChildren(panel);
 node.classList.add('archived-overview');
}
function scan(){
 scheduled=false;observer.disconnect();
 (rule.ids||[]).forEach(id=>retire(document.getElementById(id)));
 const titles=new Set(rule.titles||[]);
 document.querySelectorAll('main h2').forEach(h=>{if(titles.has(h.textContent.trim()))retire(h.closest('article,section,.card'))});
 observer.observe(document.querySelector('main')||document.body,{childList:true,subtree:true});
}
const observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;requestAnimationFrame(scan)}});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',scan,{once:true});else scan();
})();
(()=>{
  const root=document.getElementById('amount-mismatch-hero');
  if(!root)return;
  const fmt=n=>'₱'+Number(n||0).toLocaleString('en-PH',{maximumFractionDigits:0});
  const count=n=>Number(n||0).toLocaleString('en-PH');
  const sources=[
    {key:'POW',label:'POW · I. TOTAL ESTIMATED COST',get:p=>p.status==='comparable_total_estimated_cost'&&p.powEstimatePesos!=null?[Number(p.powEstimatePesos)]:[]},
    {key:'BP 202',label:'BP 202',get:p=>amounts(p,'BP 202')},
    {key:'Certificate of Implementability',label:'COI',get:p=>amounts(p,'Certificate of Implementability')}
  ];
  function amounts(project,key){
    return [...new Set((project.supportingDocumentAmounts||[])
      .filter(x=>x.documentKind===key&&x.status==='value_extracted'&&Number.isFinite(Number(x.amountPesos)))
      .map(x=>Number(x.amountPesos)))];
  }
  function summarize(projects,source){
    let mismatches=0,review=0,hgab=0,reported=0,absoluteGap=0,above=0,below=0;
    for(const project of projects){
      if(project.allocationPesos==null)continue;
      const values=source(project);
      if(!values.length)continue;
      const allocation=Number(project.allocationPesos);
      if(values.some(value=>Math.abs(value-allocation)<1))continue;
      mismatches++;
      if(values.length!==1){review++;continue;}
      const value=values[0],delta=value-allocation;
      hgab+=allocation;reported+=value;absoluteGap+=Math.abs(delta);
      if(delta>0)above++;else below++;
    }
    return{mismatches,review,hgab,reported,absoluteGap,above,below};
  }
  const cards=document.getElementById('mismatch-hero-cards');
  fetch('expectation-vs-reality-data.json?v=coi-linked-rescan-20261118-2')
    .then(response=>{if(!response.ok)throw Error('Comparison data unavailable');return response.json();})
    .then(data=>{
      const projects=data.projects||[];
      cards.innerHTML=sources.map(source=>{
        const result=summarize(projects,source.get);
        return `<article class="mismatch-hero-card"><h3>${source.label}</h3><strong class="mismatch-hero-count">${count(result.mismatches)}<small>projects differ from HGAB</small></strong><dl><dt>HGAB allocation · clear mismatches</dt><dd>${fmt(result.hgab)}</dd><dt>${source.key==='POW'?'POW TEC':'Source amount'} · clear mismatches</dt><dd>${fmt(result.reported)}</dd><dt>Combined absolute gap</dt><dd>${fmt(result.absoluteGap)}</dd><dt>Above / below HGAB</dt><dd>${count(result.above)} / ${count(result.below)}</dd></dl>${result.review?`<p class="mismatch-hero-footnote">${count(result.review)} additional project${result.review===1?'':'s'} have conflicting distinct amounts and are excluded from the combined totals.</p>`:''}</article>`;
      }).join('');
    })
    .catch(()=>{cards.innerHTML='<p class="mismatch-hero-loading">Mismatch summary could not be loaded.</p>';});
})();

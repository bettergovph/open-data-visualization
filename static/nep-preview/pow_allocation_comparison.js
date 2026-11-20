(()=>{
  const cards=document.getElementById('allocation-vs-pow-tec-metrics');
  const note=document.getElementById('allocation-vs-pow-tec-note');
  if(!cards)return;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=value=>Number(value||0).toLocaleString('en-PH');
  const peso=value=>'₱'+fmt(Math.round(Number(value||0)));
  const metric=(value,label)=>`<div class="metric"><strong>${esc(value)}</strong><span>${esc(label)}</span></div>`;
  fetch('expectation-vs-reality-data.json').then(response=>{
    if(!response.ok)throw Error(`HTTP ${response.status}`);
    return response.json();
  }).then(data=>{
    const summary=data.summary||{};
    const count=Number(summary.projectsWithComparableEstimate||0);
    if(!count)throw Error('No comparable POW total estimates are available');
    cards.innerHTML=[
      metric(fmt(count),'projects with one recovered POW total estimated cost'),
      metric(peso(summary.allocationPesos),'HGAB allocation for these projects'),
      metric(peso(summary.powEstimatePesos),'summed POW total estimated cost'),
      metric(`${Number(summary.differencePct||0)>0?'+':''}${Number(summary.differencePct||0).toFixed(2)}%`,'POW total estimated cost above allocation'),
    ].join('');
    if(note)note.textContent='This aggregate is maintained by the expectation vs reality comparison. It uses I. TOTAL ESTIMATED COST · As Submitted and includes only projects with one exact-title-matched POW and a recovered, reconciled total.';
  }).catch(error=>{
    cards.innerHTML=`<p class="caution">The expectation vs reality aggregate could not be loaded: ${esc(error.message)}</p>`;
  });
})();

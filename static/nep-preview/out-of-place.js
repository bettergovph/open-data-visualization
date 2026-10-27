(() => {
  const data = window.OUT_OF_PLACE_DATA;
  const projects = data.projects || [];
  const mapNode = document.getElementById('map');
  const card = document.getElementById('project-card');
  const listNode = document.getElementById('project-list');
  const countNode = document.getElementById('count');
  const status = document.getElementById('status');
  const search = document.getElementById('search');
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => '₱' + Number(value || 0).toLocaleString('en-PH');
  const params = new URLSearchParams(location.search);
  let selected = Math.max(0, projects.findIndex(p => p.id === params.get('project')));
  let boundaries = [];
  document.getElementById('method').textContent = data.method;
  function shareUrl(project) { const u = new URL(location.href); u.search = '?project=' + encodeURIComponent(project.id); u.hash = ''; return u.href; }
  function mapPoint(project) { return {x: 210 + (project.longitude - 116) / 11.8 * 520, y: 24 + (21.35 - project.latitude) / 16.7 * 750}; }
  function renderMap() {
    const w = 1000, h = 800;
    const features = boundaries.map(f => (f.rings || []).map(ring => '<path class="map-feature" d="M' + ring.map(([lon,lat],i) => { const p=mapPoint({longitude:lon,latitude:lat}); return (i?'L':'')+p.x.toFixed(1)+','+p.y.toFixed(1); }).join(' ') + 'Z"/>').join('')).join('');
    const points = projects.map((p,i) => { const q=mapPoint(p); return `<g class="point ${i===selected?'selected':''}" data-index="${i}" role="button" tabindex="0" aria-label="Project ${i+1}: ${esc(p.projectName)}"><title>${i+1}. ${esc(p.projectName)} · ${esc(p.office)}</title><circle cx="${q.x.toFixed(1)}" cy="${q.y.toFixed(1)}" r="${i===selected?12:9}"/><text x="${q.x.toFixed(1)}" y="${q.y.toFixed(1)}">${i+1}</text></g>`; }).join('');
    mapNode.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Map of printed project coordinates in the Philippines"><rect width="1000" height="800" fill="#f8fbfa"/>${features}${points}</svg>`;
    mapNode.querySelectorAll('[data-index]').forEach(node => { node.addEventListener('click', () => select(Number(node.dataset.index))); node.addEventListener('keydown', e => { if(e.key==='Enter'||e.key===' '){e.preventDefault();select(Number(node.dataset.index));} }); });
  }
  function renderCard() {
    const p=projects[selected]; if(!p){card.innerHTML='<p>No matching project.</p>';return;}
    const url=shareUrl(p); const fb='https://www.facebook.com/sharer/sharer.php?u='+encodeURIComponent(url);
    card.innerHTML=`<div class="card-kicker">Project ${selected+1} of ${projects.length} · ${esc(p.coordinateStatus)}</div><h2>${esc(p.projectName)}</h2><div class="office">Listed office: ${esc(p.office || 'Not stated')}</div><dl class="facts"><div><dt>Allocation in HGAB 3rd</dt><dd>${money(p.amountPesos)}</dd></div><div><dt>Printed coordinate pair</dt><dd>${esc(p.coordinateRaw)} · ${Number(p.latitude).toFixed(6)}, ${Number(p.longitude).toFixed(6)}</dd></div><div><dt>Coordinate order</dt><dd>${esc(p.coordinateOrientation)}</dd></div><div><dt>Source</dt><dd>${esc(p.sourceVolume || 'HGAB 3rd DPWH schedule')}, PDF page ${esc(p.sourcePage)}</dd></div><div><dt>Project ID</dt><dd>${esc(p.id)}</dd></div></dl><p>The title’s named place and DEO/LEG text are shown for comparison. Verify intended service area and coordinate against the source document and boundary evidence.</p><div class="share"><a href="${fb}" target="_blank" rel="noopener" aria-label="Share this project on Facebook"><strong>f</strong> Share on Facebook</a><a class="copy" href="${url}" id="copy-link">Copy project link</a></div>`;
    document.getElementById('copy-link').addEventListener('click', async e => { e.preventDefault(); try { await navigator.clipboard.writeText(url); status.textContent='Project link copied.'; } catch { location.href=url; } });
    history.replaceState(null,'','?project='+encodeURIComponent(p.id));
  }
  function renderList() {
    const term=search.value.trim().toLowerCase();
    const filtered=projects.map((p,i)=>({p,i})).filter(({p})=>!term||`${p.projectName} ${p.office} ${p.id}`.toLowerCase().includes(term));
    countNode.textContent=`${filtered.length} of ${projects.length} projects`;
    listNode.innerHTML=filtered.map(({p,i})=>`<button type="button" data-index="${i}" aria-current="${i===selected}"><strong>${i+1}. ${esc(p.projectName)}</strong><small>${esc(p.office)} · ${esc(p.coordinateRaw)}</small></button>`).join('');
    listNode.querySelectorAll('[data-index]').forEach(node=>node.addEventListener('click',()=>select(Number(node.dataset.index))));
  }
  function select(index) { selected=(index+projects.length)%projects.length; renderMap(); renderCard(); renderList(); }
  document.getElementById('previous').addEventListener('click',()=>select(selected-1));
  document.getElementById('next').addEventListener('click',()=>select(selected+1));
  search.addEventListener('input',renderList);
  renderCard(); renderList();
  fetch('mpb-municipality-boundaries.json').then(r=>r.ok?r.json():Promise.reject()).then(x=>{boundaries=x.features||[];renderMap();}).catch(()=>{status.textContent='Boundary outlines could not load; project points and cards remain available.';renderMap();});
})();

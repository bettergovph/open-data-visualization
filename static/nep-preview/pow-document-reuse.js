(()=>{
  const $=id=>document.getElementById(id);
  const fmt=n=>Number(n||0).toLocaleString('en-PH');
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const bytes=n=>{
    const size=Number(n)||0;
    if(size<1024)return `${fmt(size)} B`;
    if(size<1048576)return `${(size/1024).toFixed(1)} KB`;
    return `${(size/1048576).toFixed(2)} MB`;
  };
  const projectsFor=group=>group.projects||[];
  const groupsNode=$('document-reuse-rows'),typeNode=$('document-reuse-type'),queryNode=$('document-reuse-query');
  const pageSize=25;let groups=[],page=0;
  const codesFor=group=>new Set(projectsFor(group).map(project=>project.projectCode).filter(Boolean));
  const projectText=project=>[
    project.projectCode,project.title,project.source,project.region,project.office,
    ...(project.linkedRows||[]).flatMap(row=>[row.hgabId,row.title,row.region,row.office]),
    ...(project.files||[]).map(file=>file.filename),
  ].filter(Boolean).join(' ');
  const render=()=>{
    const type=typeNode.value,query=queryNode.value.trim().toLocaleLowerCase();
    const filtered=groups.filter(group=>{
      const hasType=!type||(group.documentTypes||[]).includes(type);
      const text=[group.sha256,...(group.documentTypes||[]),...projectsFor(group).map(projectText)].join(' ').toLocaleLowerCase();
      return hasType&&(!query||text.includes(query));
    });
    const pages=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.min(page,pages-1);
    $('document-reuse-count').textContent=`${fmt(filtered.length)} of ${fmt(groups.length)} identical-content groups`;
    $('document-reuse-page').textContent=filtered.length?`Page ${page+1} of ${pages}`:'No matching content groups';
    $('document-reuse-prev').disabled=page===0;$('document-reuse-next').disabled=page+1>=pages;
    groupsNode.innerHTML=filtered.slice(page*pageSize,(page+1)*pageSize).map(group=>{
      const projects=projectsFor(group),codes=codesFor(group).size;
      const list=projects.map(project=>{
        const linked=(project.linkedRows||[]).map(row=>`<div class="reuse-linked-row"><strong>${esc(row.hgabId)}</strong> · ${esc(row.title)}${row.region?` <span class="muted">· ${esc(row.region)}</span>`:''}</div>`).join('');
        const title=project.title?`<div>${esc(project.title)}${project.region?` <span class="muted">· ${esc(project.region)}</span>`:''}</div>`:'';
        const files=(project.files||[]).map(file=>{
          const link=file.sourceUrl?`<a href="${esc(file.sourceUrl)}" target="_blank" rel="noopener noreferrer">${esc(file.linkLabel||'Open PDF')} ↗</a>`:'<span class="muted">No public file link found</span>';
          const alternates=(file.additionalSourceUrls||[]).map(url=>`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">another exact copy ↗</a>`).join(' · ');
          const shared=file.linkProjectCode?` <span class="muted">(identical file listed under ${esc(file.linkProjectCode)})</span>`:'';
          return `<div class="reuse-file">${esc(file.filename)} · ${link}${shared}${alternates?` · ${alternates}`:''}</div>`;
        }).join('');
        return `<li><strong>${esc(project.projectCode||'Project code unavailable')}</strong> <span class="pill">${esc(project.source||'')}</span>${title}${linked}${files?`<small class="reuse-filenames">${files}</small>`:''}</li>`;
      }).join('');
      return `<tr><td>${(group.documentTypes||[]).map(esc).join('<br>')}</td><td><details><summary>${fmt(codes)} source project folders · show assignments</summary><ul class="reuse-project-list">${list}</ul></details></td><td>${bytes(group.sizeBytes)}</td><td><code title="SHA-256 ${esc(group.sha256)}">${esc(group.sha256)}</code></td></tr>`;
    }).join('')||'<tr><td colspan="4">No exact-content matches for this filter.</td></tr>';
  };
  fetch('pow-document-reuse.json?v=exact-content-scan-20261117').then(response=>{
    if(!response.ok)throw Error(`HTTP ${response.status}`);return response.json();
  }).then(data=>{
    groups=data.groups||[];
    const photo=groups.filter(group=>(group.documentTypes||[]).includes('Photos'));
    const photoCodes=new Set(photo.flatMap(group=>[...codesFor(group)]));
    const other=groups.filter(group=>!(group.documentTypes||[]).includes('Photos'));
    const sources=data.bySourceStage||{};
    $('document-reuse-summary').innerHTML=[
      [`${fmt(photo.length)}`,`identical photo-PDF groups · ${fmt(photoCodes.size)} project folders`],
      [`${fmt(other.length)}`,`other exact-content groups`],
      [`${fmt(sources['Proposal-only groups'])} / ${fmt(sources['Senate-HGAB-only groups'])}`,`Proposal-only / Senate-HGAB-only groups · ${fmt(sources['Cross-stage groups'])} cross-stage`],
      [fmt(data.scannedPdfFiles),`local PDFs scanned · ${esc(data.generatedAtUtc||'')}`],
    ].map(([value,label])=>`<div class="metric"><strong>${value}</strong><span>${label}</span></div>`).join('');
    $('document-reuse-method').textContent=data.method||'Exact SHA-256 matches confirm identical cached PDF bytes; they do not establish that project scope or use is the same.';
    const types=[...new Set(groups.flatMap(group=>group.documentTypes||[]))].sort((a,b)=>a==='Photos'?-1:b==='Photos'?1:a.localeCompare(b));
    typeNode.innerHTML='<option value="">All document types</option>'+types.map(type=>`<option value="${esc(type)}">${esc(type)}</option>`).join('');
    render();
  }).catch(error=>{
    groupsNode.innerHTML=`<tr><td colspan="4">Exact-content reuse data could not be loaded: ${esc(error.message)}</td></tr>`;
    $('document-reuse-method').textContent='The cached PDF comparison data is unavailable.';
  });
  queryNode.addEventListener('input',()=>{page=0;render()});
  typeNode.addEventListener('change',()=>{page=0;render()});
  $('document-reuse-prev').addEventListener('click',()=>{page--;render()});
  $('document-reuse-next').addEventListener('click',()=>{page++;render()});
})();

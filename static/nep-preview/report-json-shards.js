(()=>{
  'use strict';
  const cache=new Map();
  window.loadReportShardedJson=window.loadReportShardedJson||function(indexUrl){
    if(!cache.has(indexUrl))cache.set(indexUrl,(async()=>{
      const response=await fetch(indexUrl,{cache:'no-cache'});
      if(!response.ok)throw Error(`Index ${indexUrl}: HTTP ${response.status}`);
      const index=await response.json(),meta=index._shardedJson;
      if(!meta)return index;
      const result={...index};delete result._shardedJson;
      const version=encodeURIComponent(meta.version||'current');
      await Promise.all(Object.entries(meta.collections||{}).map(async([key,collection])=>{
        const payloads=await Promise.all((collection.files||[]).map(async item=>{
          const url=new URL(item.file, new URL(indexUrl,document.baseURI));url.searchParams.set('v',version);
          const shardResponse=await fetch(url,{cache:'force-cache'});
          if(!shardResponse.ok)throw Error(`Shard ${item.file}: HTTP ${shardResponse.status}`);
          return shardResponse.json();
        }));
        result[key]=payloads.flatMap(payload=>payload.rows||[]);
        if(result[key].length!==Number(collection.rows))throw Error(`Shard row count mismatch for ${key}`);
      }));
      return result;
    })());
    return cache.get(indexUrl);
  };
  const shardedAssets=new Set([
    'integrated-project-data.json','barangay-historical-data.json','congress-district-review-data.json',
    'connectivity-venues-data.json','dpwh-data.json','dpwh-hgab-comparison.json',
    'mpb-municipality-boundaries.json','out-of-place-boundaries.json','hgab-document-coverage.json',
    'hgab-only-document-coverage.json'
  ]);
  if(!window.__reportShardFetchInstalled){
    window.__reportShardFetchInstalled=true;
    const originalFetch=window.fetch.bind(window);
    window.fetch=(input,init)=>{
      let url;try{url=new URL(typeof input==='string'?input:input.url,document.baseURI)}catch(_){return originalFetch(input,init)}
      const method=String(init?.method||(typeof input!=='string'&&input.method)||'GET').toUpperCase();
      if(method!=='GET')return originalFetch(input,init);
      const name=url.pathname.split('/').pop();
      if(!shardedAssets.has(name))return originalFetch(input,init);
      const indexUrl=new URL(name.replace(/\.json$/,'-index.json'),url);
      indexUrl.search=url.search;
      return window.loadReportShardedJson(indexUrl.href).then(payload=>new Response(JSON.stringify(payload),{status:200,headers:{'content-type':'application/json'}})).catch(()=>originalFetch(input,init));
    };
  }
})();

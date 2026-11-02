/* Loads the public DPWH index and assembles its JSON shards. */
(()=>{
  let pending;
  window.loadDpwhInDepthData=()=>{
    if(pending)return pending;
    pending=(async()=>{
      const response=await fetch('dpwh-in-depth-data.json',{cache:'no-cache'});
      if(!response.ok)throw Error('DPWH data index unavailable ('+response.status+')');
      const index=await response.json();
      const arrays=index.arrayShards||null;
      const legacy=Array.isArray(index.projectShards)?{projects:index.projectShards}:null;
      if(!arrays&&!legacy)return index;
      const sources=arrays||legacy;
      await Promise.all(Object.entries(sources).map(async([key,shards])=>{
        const parts=await Promise.all(shards.map(async shard=>{
          const file=shard.path+'?v='+encodeURIComponent(shard.sha256||'');
          const result=await fetch(file,{cache:'force-cache'});
          if(!result.ok)throw Error('DPWH '+key+' data shard unavailable ('+result.status+')');
          const rows=await result.json();
          if(!Array.isArray(rows))throw Error('Invalid DPWH '+key+' data shard');
          const expected=shard.itemCount??shard.projectCount;
          if(Number.isFinite(expected)&&rows.length!==expected)throw Error('Incomplete DPWH '+key+' data shard');
          return rows;
        }));
        index[key]=parts.flat();
        const countField={projects:'projectCount',powPeers:'powPeerCount',summaryPeerGroups:'summaryPeerGroupCount'}[key];
        if(countField&&Number.isFinite(index[countField])&&index[key].length!==index[countField])throw Error('DPWH '+key+' data is incomplete');
      }));
      return index;
    })();
    return pending;
  };
})();

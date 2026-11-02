/* Loads the public DPWH index and assembles its project JSON shards. */
(()=>{
  let pending;
  window.loadDpwhInDepthData=()=>{
    if(pending)return pending;
    pending=(async()=>{
      const response=await fetch('dpwh-in-depth-data.json',{cache:'no-cache'});
      if(!response.ok)throw Error('DPWH data index unavailable ('+response.status+')');
      const index=await response.json();
      if(!Array.isArray(index.projectShards))return index;
      const parts=await Promise.all(index.projectShards.map(async shard=>{
        const file=shard.path+'?v='+encodeURIComponent(shard.sha256||'');
        const result=await fetch(file,{cache:'force-cache'});
        if(!result.ok)throw Error('DPWH project data shard unavailable ('+result.status+')');
        const rows=await result.json();
        if(!Array.isArray(rows))throw Error('Invalid DPWH project data shard');
        if(Number.isFinite(shard.projectCount)&&rows.length!==shard.projectCount)throw Error('Incomplete DPWH project data shard');
        return rows;
      }));
      index.projects=parts.flat();
      if(Number.isFinite(index.projectCount)&&index.projects.length!==index.projectCount)throw Error('DPWH project data is incomplete');
      return index;
    })();
    return pending;
  };
})();

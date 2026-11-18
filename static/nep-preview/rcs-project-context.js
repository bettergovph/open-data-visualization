/* Attach each Proposal project code to its uniquely selected HGAB row so the
   shared Details popup can load project-context records for RCS tables. */
(()=>{'use strict';
 const codes=new Map();
 const apply=()=>{for(const row of document.querySelectorAll('tr')){if(row.dataset.hgabId)continue;const match=row.textContent.match(/2027DPWH-Proposal-\d+/i);if(!match)continue;const record=codes.get(match[0].toUpperCase());if(record){row.dataset.projectCode=match[0].toUpperCase();row.dataset.hgabId=record.hgabId}}};
 fetch('rcs-stage-trace.json?v=20261118-1').then(r=>{if(!r.ok)throw Error('RCS project mapping unavailable');return r.json()}).then(data=>{for(const row of data.rows||[])if(row.sourceCode&&row.hgabId)codes.set(row.sourceCode.toUpperCase(),row);apply();new MutationObserver(apply).observe(document.body,{subtree:true,childList:true});}).catch(error=>console.warn('RCS Details project mapping:',error));
})();

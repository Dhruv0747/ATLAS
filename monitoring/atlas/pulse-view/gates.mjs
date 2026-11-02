// Observation rendering only; never grants robot permissions.
const finite=x=>typeof x==='number' && Number.isFinite(x);
export function stateFor(edge,snapshot,elapsedMs){
 if(!edge.verified)return 'UNVERIFIED';
 const s=snapshot,t=s?.topics?.[edge.topic];
 if(!s || s.up!==1 || !t || t.available!==1 ||
    ![s.queryTime,s.observedTime,s.requestMs,elapsedMs,t.rate,t.age,edge.limit].every(finite) ||
    elapsedMs<0 || s.requestMs<0 || s.requestMs>2000 || t.rate<0 || t.age<0 || edge.limit<=0)return 'UNAVAILABLE';
 const collectionAge=s.queryTime-s.observedTime+(elapsedMs+s.requestMs)/1000;
 if(s.queryTime<s.observedTime || collectionAge<0 || collectionAge>=30)return 'UNAVAILABLE';
 if(t.age+collectionAge>edge.limit)return 'STALE';
 return t.rate>0?'FRESH':'IDLE';
}

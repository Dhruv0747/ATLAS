// Grafana 12.1 authenticated datasource proxy; never a direct Prometheus URL.
const selector='job="atlas-jetson",instance="192.168.1.16:9118"';
const names=['up','atlas_exporter_observed_timestamp_seconds','atlas_topic_available','atlas_topic_rate_hz','atlas_topic_age_seconds'];
const tag=(expr,name)=>`label_replace(${expr},"__name__","${name}","__name__",".*")`;
export function queryURL(){
 const query=names.map(n=>`${n}{${selector}}`).concat(tag('vector(time())','_atlas_query_time'),tag(`timestamp(up{${selector}})`,'_atlas_up_time')).join(' or on(__name__,job,instance,topic) ');
 return '/api/datasources/proxy/uid/atlas-prom/api/v1/query?'+new URLSearchParams({query});
}
function number(s){if(typeof s!=='string'||!s.trim()||!Number.isFinite(Number(s)))throw Error('Invalid metric');return Number(s);}
export function decode(body,requestMs){
 if(!Number.isFinite(requestMs)||requestMs<0||requestMs>2000||body?.status!=='success'||body.data?.resultType!=='vector'||!Array.isArray(body.data.result)||body.data.result.length>256)throw Error('Invalid response');
 const scalar={},topics={},seen=new Set();
 for(const item of body.data.result){
  const m=item.metric,name=m?.__name__,topic=m?.topic;
  if(![...names,'_atlas_query_time','_atlas_up_time'].includes(name))throw Error('Unexpected metric');
  if(name!=='_atlas_query_time'&&(m.job!=='atlas-jetson'||m.instance!=='192.168.1.16:9118'))throw Error('Wrong source');
  const key=name+':'+(topic||'');if(seen.has(key))throw Error('Duplicate metric');seen.add(key);
  if(!Array.isArray(item.value)||item.value.length!==2||!Number.isFinite(item.value[0]))throw Error('Invalid sample');
  const value=number(item.value[1]);
  if(name.startsWith('atlas_topic_')){
   if(typeof topic!=='string'||!topic||topic==='__proto__'||topic==='constructor')throw Error('Invalid topic');
   const field={atlas_topic_available:'available',atlas_topic_rate_hz:'rate',atlas_topic_age_seconds:'age'}[name];
   (topics[topic]??={})[field]=value;
  }else scalar[name]=value;
 }
 const queryTime=scalar._atlas_query_time,upTime=scalar._atlas_up_time;
 if(!Number.isFinite(queryTime)||!Number.isFinite(upTime)||upTime>queryTime||queryTime-upTime>=30||!Number.isFinite(scalar.up)||!Number.isFinite(scalar.atlas_exporter_observed_timestamp_seconds))throw Error('Missing/stale source evidence');
 return {queryTime,observedTime:scalar.atlas_exporter_observed_timestamp_seconds,up:scalar.up,requestMs,topics};
}
export async function pollOnce(fetcher=fetch){
 const start=performance.now(),controller=new AbortController(),timer=setTimeout(()=>controller.abort(),2000);
 try{
  const response=await fetcher(queryURL(),{credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
  if(!response.ok)throw Error(response.status===401||response.status===403?'Grafana login/permission required':'Datasource unavailable');
  if(!response.headers.get('content-type')?.includes('application/json'))throw Error('Unexpected response type');
  const snapshot=decode(await response.json(),performance.now()-start);
  // Use the authenticated server's Date, not the PC wall clock. Date has 1s precision.
  const serverDate=Date.parse(response.headers.get('date'))/1000;
  if(!Number.isFinite(serverDate)||snapshot.queryTime>serverDate+1||serverDate-snapshot.queryTime>2)throw Error('Cached/invalid response clock');
  snapshot.requestMs+=Math.max(0,serverDate+1-snapshot.queryTime)*1000;
  return snapshot;
 }finally{clearTimeout(timer)}
}

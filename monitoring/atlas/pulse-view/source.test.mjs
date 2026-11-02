import {test} from 'node:test';
import assert from 'node:assert/strict';
import {decode,queryURL,pollOnce} from './source.mjs';
const series=(name,value,topic)=>({metric:{__name__:name,job:'atlas-jetson',instance:'192.168.1.16:9118',...(topic?{topic}:{})},value:[100,String(value)]});
function response(){return {status:'success',data:{resultType:'vector',result:[series('_atlas_query_time',100),series('_atlas_up_time',100),series('up',1),series('atlas_exporter_observed_timestamp_seconds',100),series('atlas_topic_available',1,'odom'),series('atlas_topic_rate_hz',10,'odom'),series('atlas_topic_age_seconds',0,'odom')]}};}
test('decode exact source, no cross-host or duplicate evidence',()=>{
 assert.equal(decode(response(),10).topics.odom.rate,10);
 const r=response();r.data.result.push(series('up',1));assert.throws(()=>decode(r,10));
 const x=response();x.data.result[2].metric.instance='wrong';assert.throws(()=>decode(x,10));
});
test('missing malformed stale and future evidence rejected',()=>{
 for(const value of ['NaN','Infinity','',null]){const r=response();r.data.result[0].value[1]=value;assert.throws(()=>decode(r,10));}
 const r=response();r.data.result[1].value[1]='69';assert.throws(()=>decode(r,10));
 assert.throws(()=>decode(response(),2001));assert.throws(()=>decode({status:'error'},0));
 const s=response();s.data.result[1].value[1]='101';assert.throws(()=>decode(s,10));
});
test('same-origin bounded cookie request and denied auth',async()=>{
 assert(queryURL().startsWith('/api/datasources/proxy/uid/atlas-prom/api/v1/query?'));
 let options;await assert.rejects(pollOnce(async(url,o)=>{options=o;return {ok:false,status:401};}));
 assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');assert.equal(options.redirect,'error');assert(options.signal);assert(!options.headers?.Authorization);
 const s=await pollOnce(async()=>({ok:true,headers:new Headers({'Content-Type':'application/json','Date':'Thu, 01 Jan 1970 00:01:40 GMT'}),json:async()=>response()}));assert.equal(s.up,1);
 await assert.rejects(pollOnce(async()=>({ok:true,headers:new Headers({'Content-Type':'application/json','Date':'Thu, 01 Jan 1970 00:02:40 GMT'}),json:async()=>response()})));
});

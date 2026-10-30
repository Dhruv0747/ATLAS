const assert=require('node:assert/strict');
const {requireStopped,verifyStopped}=require('./verify_ui_stopped.cjs');
(async()=>{
 requireStopped({state:'OFF',driver_stopped:true});
 for(const value of [null,{}, {state:'ACTIVE',driver_stopped:true},{state:'OFF'},{state:'OFF',driver_stopped:false},{state:'OFF',driver_stopped:'true'}])assert.throws(()=>requireStopped(value));
 for(const title of ['Camera off','Stopped safely']){
  let calls=0;
  const page={request:{get:async()=>{calls++;return {ok:()=>true,headers:()=>({}),json:async()=>({state:'OFF',driver_stopped:true})}}},
   waitForFunction:async fn=>{global.document={querySelector:()=>({textContent:title})};assert.equal(fn(),true);delete global.document;}};
  await verifyStopped(page,'http://fixture');assert.equal(calls,2);
  page.request.get=async()=>({ok:()=>true,headers:()=>({}),json:async()=>({state:'ACTIVE',driver_stopped:false})});
  await assert.rejects(()=>verifyStopped(page,'http://fixture'));
 }
 for(const response of [{ok:()=>false},{ok:()=>true,headers:()=>({age:'10'})},{ok:()=>true,headers:()=>({}),json:async()=>{throw Error('malformed JSON')}}]){
  await assert.rejects(()=>verifyStopped({request:{get:async()=>response}},'http://fixture'));
 }
 console.log('PASS: both safe labels, authoritative pre/post checks, active/missing/malformed/cached/API failure rejection');
})().catch(e=>{console.error(e);process.exit(1)});

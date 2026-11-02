import {test} from 'node:test';
import assert from 'node:assert/strict';
import {stateFor} from './gates.mjs';
const edge={verified:true,topic:'odom',limit:1};
const sample=()=>({up:1,queryTime:100,observedTime:100,requestMs:0,topics:{odom:{available:1,rate:10,age:0}}});
test('only verified fresh positive traffic animates',()=>{
 assert.equal(stateFor(edge,sample(),0),'FRESH');
 assert.equal(stateFor({...edge,verified:false},sample(),0),'UNVERIFIED');
 const s=sample();s.topics.odom.rate=0;assert.equal(stateFor(edge,s,0),'IDLE');
});
test('elapsed time and transport age stop pulses',()=>{
 assert.equal(stateFor(edge,sample(),1000),'FRESH');
 assert.equal(stateFor(edge,sample(),1001),'STALE');
 const s=sample();s.requestMs=1100;assert.equal(stateFor(edge,s,0),'STALE');
 s.queryTime=131;assert.equal(stateFor(edge,s,0),'UNAVAILABLE');
});
test('outage missing malformed and future data fail closed',()=>{
 assert.equal(stateFor(edge,null,0),'UNAVAILABLE');
 for(const field of ['up','queryTime','observedTime','requestMs']){
  for(const value of [undefined,NaN,Infinity,'1',null]){
   const s=sample();s[field]=value;assert.equal(stateFor(edge,s,0),'UNAVAILABLE');
  }
 }
 for(const field of ['available','rate','age']){
  for(const value of [undefined,NaN,Infinity,'1',null,-1]){
   const s=sample();s.topics.odom[field]=value;assert.equal(stateFor(edge,s,0),'UNAVAILABLE');
  }
 }
 const s=sample();s.observedTime=101;assert.equal(stateFor(edge,s,0),'UNAVAILABLE');
 s.observedTime=100;s.up=0;assert.equal(stateFor(edge,s,0),'UNAVAILABLE');
 assert.equal(stateFor(edge,sample(),-1),'UNAVAILABLE');
});

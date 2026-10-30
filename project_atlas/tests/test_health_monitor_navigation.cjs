const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.resolve(__dirname, '../web/v2');
const script = fs.readFileSync(path.join(web,'health-monitor.js'),'utf8');
const html = fs.readFileSync(path.join(web,'index.html'),'utf8');
function setup(platform) {
  const nodes={}; const events={};
  for(const id of ['healthMonitorConfirm','healthMonitorLink','healthMonitorHelp']) nodes[id]={
    handlers:{},attrs:{},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this[k]},addEventListener(k,v){this.handlers[k]=v}
  };
  vm.runInNewContext(script,{navigator:{platform},document:{getElementById:id=>nodes[id]},window:{addEventListener:(k,v)=>events[k]=v}});
  return {confirm:nodes.healthMonitorConfirm,link:nodes.healthMonitorLink,events};
}
test('Windows requires explicit confirmation and revokes it',()=>{
 const {confirm,link,events}=setup('Win32');
 assert.equal(confirm.disabled,false);assert.equal(link.href,undefined);
 confirm.checked=true;confirm.handlers.change();
 assert.equal(link.href,'http://127.0.0.1:3000/d/atlas-health-monitor/atlas-health-monitor');
 assert.equal(link.attrs['aria-disabled'],'false');
 events.pageshow();assert.equal(link.href,undefined);assert.equal(confirm.checked,false);
});
test('phone, Linux, Mac and unknown clients never get localhost href',()=>{
 for(const platform of ['iPhone','Linux armv8l','MacIntel','']) {
  const {confirm,link}=setup(platform); assert.equal(confirm.disabled,true);
  confirm.checked=true;confirm.handlers.change();assert.equal(link.href,undefined);
  let blocked=false;link.handlers.click({preventDefault(){blocked=true}});assert.equal(blocked,true);
 }
});
test('no network access, fabricated status or control calls',()=>{
 assert.doesNotMatch(script,/fetch\(|XMLHttpRequest|setInterval|localStorage|\/api\//);
 assert.match(html,/Monitoring status: unverified/);
 assert.match(html,/Windows\/WSL monitoring server may be offline/);
 assert.match(html,/id="healthMonitorLink"[^>]+target="_blank" rel="noopener noreferrer"/);
 assert.doesNotMatch(html.match(/id="healthMonitorLink"[^>]+/)[0],/href=/);
});
test('existing navigation and safety controls remain',()=>{
 for(const marker of ['id="v2Estop"','id="shutdownButton"','/v2/flysky-testlab','/v2/vision3d','/v2/command.js','/v2/home-cards.js']) assert.ok(html.includes(marker),marker);
 assert.match(html,/class="hm-lab"[^>]*><svg class="icon" aria-hidden="true"/);
});

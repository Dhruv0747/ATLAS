// Offline browser test. Intercepts every request; never contacts Grafana or Jetson.
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:1000}});
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());
   if(u.origin!=='http://atlas-pulse.test')return route.abort();
   const file=path.resolve(__dirname,'..','.'+u.pathname);
   if(!file.startsWith(path.resolve(__dirname,'..')+path.sep))return route.abort();
   await route.fulfill({path:file,contentType:file.endsWith('.mjs')?'application/javascript':file.endsWith('.json')?'application/json':'text/html'});
  });
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://atlas-pulse.test/pulse-view/index.html?offline=1');await page.waitForFunction(()=>window.atlasPulseTest);
  const visible=()=>page.locator('.pulse[visibility="visible"]').count();
  assert.equal(await visible(),0);
  const sample=await page.evaluate(()=>({up:1,queryTime:100,observedTime:100,requestMs:0,topics:Object.fromEntries(atlasPulseTest.topology.edges.filter(e=>e.verified).map(e=>[e.topic,{available:1,rate:10,age:0}]))}));
  await page.evaluate(s=>atlasPulseTest.accept(s),sample);await page.waitForFunction(()=>document.querySelectorAll('.pulse[visibility="visible"]').length===8);
  const pulse=page.locator('[data-pulse="odometry"]');const x=await pulse.getAttribute('cx');await page.waitForTimeout(160);assert.notEqual(await pulse.getAttribute('cx'),x);
  await page.waitForTimeout(1000);assert.equal(await pulse.getAttribute('visibility'),'hidden');assert.equal(await page.locator('[data-edge="odometry"]').getAttribute('data-state'),'STALE');
  const idle=structuredClone(sample);idle.queryTime=101;idle.observedTime=101;for(const t of Object.values(idle.topics))t.rate=0;
  await page.evaluate(s=>atlasPulseTest.accept(s),idle);await page.waitForTimeout(80);assert.equal(await visible(),0);
  assert.equal(await page.locator('[data-edge="odometry"]').getAttribute('data-state'),'IDLE');
  await page.evaluate(()=>atlasPulseTest.disconnect());await page.waitForTimeout(80);assert.equal(await visible(),0);
  assert.equal(await page.locator('[data-edge="odometry"]').getAttribute('data-state'),'UNAVAILABLE');
  assert.equal(await page.locator('[data-edge="astra_map"]').getAttribute('data-state'),'UNVERIFIED');
  const cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');
  const metrics=async()=>Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(m=>[m.name,m.value]));
  const baseline=await metrics();await page.waitForTimeout(3000);const idleEnd=await metrics();
  await page.evaluate(s=>{window.fixtureTimer=setInterval(()=>{s.queryTime+=.2;s.observedTime=s.queryTime;atlasPulseTest.accept(s)},200)}, {...sample,queryTime:102,observedTime:102});
  await page.waitForTimeout(3000);const activeEnd=await metrics();assert.equal(await visible(),8);
  await page.getByRole('button',{name:'Pause visual motion'}).click();await page.waitForTimeout(80);assert.equal(await visible(),0);
  await page.evaluate(()=>{clearInterval(fixtureTimer);atlasPulseTest.disconnect()});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(process.env.TEMP,'atlas-pulse-offline.png')});
  assert.equal(errors.length,0);
  console.log(JSON.stringify({result:'PASS',verifiedPulses:8,unverifiedPulses:0,expiry:true,idle:true,disconnect:true,pause:true,errors,idle3sTaskSeconds:idleEnd.TaskDuration-baseline.TaskDuration,active3sTaskSeconds:activeEnd.TaskDuration-idleEnd.TaskDuration,heapMiB:activeEnd.JSHeapUsedSize/1048576}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});

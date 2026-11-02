// Local isolated Grafana acceptance only. Never point this at production.
// NODE_PATH must provide existing Playwright. Credentials/fixtures remain outside git.
const fs = require('fs');
const path = require('path');
const {chromium} = require('playwright');
const lab = process.env.ATLAS_BROWSER_LAB;
if (!lab) throw Error('ATLAS_BROWSER_LAB required');
const base = 'http://127.0.0.1:3301';
const password = fs.readFileSync(path.join(lab,'grafana.env'),'utf8').match(/^GF_SECURITY_ADMIN_PASSWORD=(.+)$/m)[1];
const assert = require('assert/strict');
const topology = JSON.parse(fs.readFileSync(path.join(__dirname,'neural_topology.json'),'utf8'));
const dashboard = JSON.parse(fs.readFileSync(path.join(__dirname,'dashboards/atlas-neural.json'),'utf8'));
const states=[['FRESH OBSERVED','#32c48d',10],['STALE','#ffb357',10],['IDLE','#5794f2',0],['UNAVAILABLE','#8e8e93',null]];
function tagged(expr, fields){for(const [key,value] of Object.entries(fields)) expr=`label_replace((${expr}),${JSON.stringify(key)},${JSON.stringify(value)},"__name__",".*")`;return expr;}
const expected=topology.edges.map((e,i)=>({...e,state:e.verified?states[i%4]:['UNVERIFIED','#8e8e93',null]}));
const fixtures={nodes:dashboard.panels.find(p=>p.type==='nodeGraph').targets[0].expr,edges:expected.map(e=>tagged(e.state[2]===null?'vector(0/0)':`vector(${e.state[2]})`,{id:e.id,source:e.source,target:e.target,detail__topic:e.topic||'unmeasured',detail__evidence:e.verified?'Audited receipt':'Unverified link',secondarystat:e.state[0],color:e.state[1]})).join(' or ')};
const root = __dirname;
async function api(route,body) {
  const r=await fetch(base+route,{method:body?'POST':'GET',headers:{Authorization:'Basic '+Buffer.from('atlas_test:'+password).toString('base64'),'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  if(!r.ok) throw Error(route+' '+r.status+' '+await r.text());
  return r.json();
}
(async()=>{
  if (!(await api('/api/datasources')).some(d=>d.uid==='atlas-prom')) await api('/api/datasources',{name:'Offline fixture queries',uid:'atlas-prom',type:'prometheus',access:'proxy',url:'http://127.0.0.1:9090',jsonData:{httpMethod:'POST'}});
  for(const name of ['atlas-health.json','atlas-neural.json']) {
    const dashboard=JSON.parse(fs.readFileSync(path.join(root,'dashboards',name),'utf8'));
    delete dashboard.id;
    await api('/api/dashboards/db',{dashboard,overwrite:true});
  }
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.setDefaultTimeout(10000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const responses=[];
  await page.context().route('**/api/ds/query*',async route=>{
    const body=route.request().postDataJSON();
    for(const q of body.queries) q.expr=fixtures[q.refId] || 'vector(1)';
    const response=await route.fetch({postData:JSON.stringify(body)});
    responses.push(await response.json());
    await route.fulfill({response});
  });
  await page.goto(base+'/login');
  await page.getByLabel('Email or username').fill('atlas_test');
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  await page.waitForURL(url=>!url.pathname.includes('login'));
  const cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');
  const metrics=async()=>Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(x=>[x.name,x.value]));
  const before=await metrics(); const start=Date.now();
  await page.goto(base+'/d/atlas-live-neural-data-flow/atlas-live-neural-data-flow');
  await page.locator('[data-node-id]').nth(18).waitFor();
  const renderMs=Date.now()-start;
  assert.equal(await page.locator('[data-node-id]').count(),19);
  assert.equal(await page.locator('g[aria-label^="Edge from:"]').count(),20);
  for(let i=0;i<2;i++) await page.getByTitle('Zoom out',{exact:true}).click();
  const afterRender=await metrics();
  await page.getByTestId('node-click-rect-mcu').click();
  assert.equal(await page.getByRole('link',{name:'Topic diagnostics and history',exact:true}).count(),1);
  const nodeHref=await page.getByRole('link',{name:'Topic diagnostics and history',exact:true}).getAttribute('href');
  assert(nodeHref.includes('var-topic=unmeasured'));
  const healthLink=page.getByRole('link',{name:'ATLAS Health Monitor',exact:true});
  const popupPromise=page.waitForEvent('popup');await healthLink.click();const popup=await popupPromise;
  await popup.waitForURL('**/d/atlas-health-monitor/**');await popup.close();await page.keyboard.press('Escape');
  const edgeResults=[];
  for(const e of expected){
    const edge=page.locator(`g[aria-label="Edge from: ${e.source} to: ${e.target}"]`).filter({has:page.locator(`line[stroke="${e.state[1]}"]`)}).first();
    assert.equal(await edge.locator('line').first().getAttribute('stroke'),e.state[1]);
    // Dispatch on exact edge because parallel MCU edges geometrically overlap.
    await edge.dispatchEvent('click');
    const body=await page.locator('body').innerText();assert(body.includes(e.state[0]),e.id+' state');
    const link=page.getByRole('link',{name:'Topic diagnostics and history',exact:true});
    assert.equal(await link.count(),1);
    const href=await link.getAttribute('href');assert(href.includes('var-topic='+(e.topic||'unmeasured')));
    edgeResults.push({id:e.id,state:e.state[0],color:e.state[1],href});
    if(e.id==='scan'){
      const next=page.waitForEvent('popup');await link.click();const history=await next;
      await history.waitForURL('**var-topic=lidar**');await history.getByText('Observed ROS topic traffic',{exact:true}).first().waitFor();await history.close();
    }
    await page.keyboard.press('Escape');
  }
  assert.equal(await page.locator('animate,animateMotion').count(),0);
  await page.screenshot({path:path.join(lab,'desktop.png')});
  const countBefore=responses.filter(r=>r.results?.nodes).length;
  const idleStart=await metrics();await page.waitForTimeout(31000);const idleEnd=await metrics();
  assert(responses.filter(r=>r.results?.nodes).length>countBefore,'30s graph refresh');
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(1000);
  assert.equal(await page.locator('[data-node-id]').count(),19);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile page overflow');
  await page.getByTestId('node-click-rect-mcu').click({timeout:5000});
  const mobileLink=page.getByRole('link',{name:'Topic diagnostics and history',exact:true});
  assert.equal(await mobileLink.count(),1);const box=await mobileLink.boundingBox();assert(box.x>=0 && box.x+box.width<=390,'mobile menu links fit');
  const mobilePopup=page.waitForEvent('popup');await mobileLink.click();const detail=await mobilePopup;await detail.waitForURL('**var-topic=unmeasured**');await detail.close();
  await page.screenshot({path:path.join(lab,'mobile.png')});await page.keyboard.press('Escape');
  const report={result:'PASS',grafana:'12.1.0',browser:'Edge Chromium headless',fixtureOnly:true,nodes:19,edges:20,verifiedObservationPaths:8,states:edgeResults,refreshSeconds:30,desktop:[1440,1000],mobile:[390,844],errors,renderMs,renderTaskSeconds:afterRender.TaskDuration-before.TaskDuration,heapMiB:afterRender.JSHeapUsedSize/1048576,refreshWindowSeconds:31,refreshWindowTaskSeconds:idleEnd.TaskDuration-idleStart.TaskDuration};
  assert.equal(errors.length,0);fs.writeFileSync(path.join(lab,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,states:report.states.map(e=>({id:e.id,state:e.state}))}));
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

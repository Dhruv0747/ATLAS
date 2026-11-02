const {chromium}=require('playwright');
const path=require('path'),assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1280,height:900}});
  const page=await context.newPage();let mode='fresh',requests=0;
  const topics=['lidar','encoder_health','board_imu_heading','odom','us_validity','joy','control_policy','camera_info'];
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());if(url.origin!=='http://atlas-pulse.test')return route.abort();
   if(url.pathname.startsWith('/api/')){
    requests++;assert(url.pathname==='/api/datasources/proxy/uid/atlas-prom/api/v1/query');assert.equal(route.request().method(),'GET');assert(!route.request().headers().authorization);
    if(mode==='denied')return route.fulfill({status:401,contentType:'application/json',body:'{}'});
    if(mode==='timeout'){await new Promise(r=>setTimeout(r,2300));return route.abort().catch(()=>{});}
    const clock=100.999;
    const row=(name,value,topic)=>({metric:{__name__:name,...(name==='_atlas_query_time'?{}:{job:'atlas-jetson',instance:'192.168.1.16:9118'}),...(topic?{topic}:{})},value:[clock,String(value)]});
    const result=[row('_atlas_query_time',clock),row('_atlas_up_time',clock),row('up',mode==='down'?0:1),row('atlas_exporter_observed_timestamp_seconds',clock)];
    for(const t of topics)result.push(row('atlas_topic_available',1,t),row('atlas_topic_rate_hz',mode==='idle'?0:10,t),row('atlas_topic_age_seconds',mode==='stale'?10:0,t));
    return route.fulfill({headers:{'Content-Type':'application/json','Date':'Thu, 01 Jan 1970 00:01:40 GMT'},body:JSON.stringify({status:'success',data:{resultType:'vector',result}})});
   }
   const file=path.resolve(__dirname,'..','.'+url.pathname);if(!file.startsWith(path.resolve(__dirname,'..')+path.sep))return route.abort();
   return route.fulfill({path:file,contentType:file.endsWith('.mjs')?'application/javascript':file.endsWith('.json')?'application/json':'text/html'});
  });
  const states={fresh:'FRESH',idle:'IDLE',stale:'STALE',down:'UNAVAILABLE',denied:'UNAVAILABLE',timeout:'UNAVAILABLE'};
  for(const [scenario,expected]of Object.entries(states)){
   mode=scenario;await page.goto('http://atlas-pulse.test/pulse-view/index.html');
   await page.waitForFunction(()=>document.querySelector('#connection')?.textContent!=='Checking authenticated Grafana data…');
   await page.waitForTimeout(80);console.log(scenario,await page.locator('#connection').innerText());assert.equal(await page.locator('[data-edge="odometry"]').getAttribute('data-state'),expected);
   assert.equal(await page.locator('.pulse[visibility="visible"]').count(),mode==='fresh'?8:0);
   assert.equal(await page.evaluate(()=>typeof window.atlasPulseTest),'undefined');
  }
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.equal(await page.locator('.node').count(),19);
  console.log(JSON.stringify({result:'PASS',scenarios:Object.keys(states),authenticatedSourceAdapter:true,requests,desktop:[1280,900],mobile:[390,844],productionTestInjection:false}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});

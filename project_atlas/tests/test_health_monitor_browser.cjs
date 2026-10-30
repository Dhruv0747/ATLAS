// Isolated HTML fixtures; all rover-origin requests intercepted. No control calls.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const [beforeFile,afterFile,assets,edge]=process.argv.slice(2);
 const browser=await chromium.launch({executablePath:edge,headless:true});
 try {
  for(const [platform,width,height] of [['Win32',1440,1000],['iPhone',390,844]]) {
   const context=await browser.newContext({viewport:{width,height}});
   await context.addInitScript(p=>{
    Object.defineProperty(navigator,'platform',{get:()=>p});
    Object.defineProperty(navigator,'userAgentData',{get:()=>undefined});
   },platform);
   let html=fs.readFileSync(beforeFile);let unexpected=0;
   await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.origin==='http://127.0.0.1:3000')return route.continue();
    if(route.request().method()!=='GET'){unexpected++;return route.abort();}
    if(url.pathname==='/v2/')return route.fulfill({body:html,contentType:'text/html'});
    if(url.pathname==='/v2/health-monitor.js')return route.fulfill({body:fs.readFileSync(path.join(__dirname,'../web/v2/health-monitor.js')),contentType:'text/javascript'});
    const file=path.join(assets,path.basename(url.pathname));
    if(fs.existsSync(file))return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.css')?'text/css':'image/svg+xml'});
    return route.fulfill({status:404,body:''});
   });
   const page=await context.newPage();await page.goto('http://atlas.test/v2/');
   const oldLinks=await page.locator('.hm-labs a').evaluateAll(es=>es.map(e=>e.outerHTML));
   const oldOverflow=await page.evaluate(()=>document.documentElement.scrollWidth);
   html=fs.readFileSync(afterFile);await page.reload();
   assert.deepEqual(await page.locator('.hm-labs > a').evaluateAll(es=>es.map(e=>e.outerHTML)),oldLinks);
   assert.ok(await page.locator('link[href="/v2/material.css"]').count());
   await page.locator('#healthMonitorCard summary').click();
   assert.equal(await page.locator('#healthMonitorLink').getAttribute('href'),null);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth)<=Math.max(oldOverflow,width));
   if(platform==='Win32') {
    await page.locator('#healthMonitorConfirm').check();
    const popupPromise=page.waitForEvent('popup');await page.locator('#healthMonitorLink').click();
    const popup=await popupPromise;await popup.waitForLoadState('domcontentloaded');
    assert.ok(popup.url().startsWith('http://127.0.0.1:3000/'));
    assert.ok(popup.url().includes('login')||popup.url().includes('/d/atlas-health-monitor/'));
    await popup.close();
   } else assert.equal(await page.locator('#healthMonitorConfirm').isDisabled(),true);
   assert.equal(unexpected,0);
   await page.screenshot({path:afterFile+'.'+platform+'.png',fullPage:true});
   console.log(platform+': PASS (cards preserved, glass CSS retained, no added overflow, client gate/new-tab checked)');
   await context.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});

/* Offline intercepted requests only. Never connects to Jetson or runs a camera. */
const {chromium}=require('playwright');const fs=require('fs');const path=require('path');
(async()=>{
 const baseline=path.resolve(process.argv[2]),pkg=path.resolve(process.argv[3]);
 const repo=path.resolve(__dirname,'../../web/v2');
 const browser=await chromium.launch({headless:true,executablePath:process.env.VISION_BROWSER});
 const results=[];
 try{
  for(const width of [1440,768,390,320]){
   const values=[];
   for(const candidate of [false,true]){
    const page=await browser.newPage({viewport:{width,height:900}});const errors=[],writes=[],unknown=[];
    page.on('pageerror',e=>errors.push(String(e)));
    await page.route('**/*',async route=>{
     const req=route.request(),url=new URL(req.url());if(req.method()!=='GET')writes.push(req.method()+' '+url.pathname);
     if(url.pathname==='/api/vision3d/status')return route.fulfill({contentType:'application/json',body:fs.readFileSync(path.join(pkg,'offline-status.json'),'utf8')});
     let name=url.pathname==='/v2/vision3d'?'vision3d.html':url.pathname.replace(/^\/v2\//,'');
     if(name.includes('..'))return route.abort();
     let file=name==='vision3d.html'?path.join(pkg,candidate?'candidate.html':'original.html'):path.join(baseline,name);
     if(!fs.existsSync(file))file=path.join(repo,name);
     if(fs.existsSync(file)&&fs.statSync(file).isFile()){
      const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'}[path.extname(file)]||'application/octet-stream';
      return route.fulfill({contentType:mime,body:fs.readFileSync(file)});
     }
     unknown.push(url.pathname);return route.fulfill({status:404,body:''});
    });
    await page.goto('http://offline.invalid/v2/vision3d');
    await page.waitForFunction(()=>document.querySelector('#vlTitle').textContent==='Camera off');
    const observation=await page.evaluate(()=>({
     width:document.documentElement.scrollWidth,
     links:[...document.querySelectorAll('a')].map(n=>n.getAttribute('href')),
     originalIds:[...document.querySelectorAll('[id]')].filter(n=>!n.closest('#astraFeatureUi')).map(n=>n.id),
     material:!!document.querySelector('link[href="/v2/material.css"]'),
     cards:document.querySelectorAll('#astraFeatureUi article').length,
     disabled:document.querySelectorAll('#astraFeatureUi button:disabled').length
    }));
    if(errors.length||writes.length)throw Error(JSON.stringify({errors,writes}));
    if(candidate){
     if(observation.cards!==6||observation.disabled!==24||!observation.material)throw Error('missing panel/disabled control/material style');
     if(observation.width>width+1)throw Error('horizontal overflow '+width);
     if(JSON.stringify(observation.links)!==JSON.stringify(values[0].links)||JSON.stringify(observation.originalIds)!==JSON.stringify(values[0].originalIds))throw Error('existing navigation/control changed');
     await page.locator('#astraFeatureUi').scrollIntoViewIfNeeded();
     await page.screenshot({path:path.join(pkg,'ui-'+width+'.png'),fullPage:true});
    }
    values.push(observation);await page.close();
   }
   results.push({width,result:'PASS',baseline:values[0],candidate:values[1]});
  }
  fs.writeFileSync(path.join(pkg,'browser-results.json'),JSON.stringify(results,null,2));
  console.log(JSON.stringify(results.map(r=>({width:r.width,result:r.result}))))
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});

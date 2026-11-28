/* Synthetic UI regression only. Start sim_server.py first. NODE_PATH may point to bundled Playwright. */
const {chromium}=require('playwright');
const fs=require('fs');const path=require('path');
(async()=>{
 const base=process.env.VISION_SIM_URL||'http://127.0.0.1:8096',out=process.argv[2]||'artifacts/vision3d_ui';fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,...(process.env.VISION_BROWSER?{executablePath:process.env.VISION_BROWSER}:{})});const results=[];
 try{
  for(const [label,width,height]of [['desktop',1440,1000],['mobile',390,844]]){
   const page=await browser.newPage({viewport:{width,height},isMobile:label==='mobile',hasTouch:label==='mobile'});const errors=[],writes=[];
   page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>{if(r.method()!=='GET')writes.push(r.url());});
   await page.request.get(base+'/sim?scenario=live');await page.goto(base+'/v2/vision3d');await page.waitForFunction(()=>document.querySelector('#depthState').textContent==='DEPTH ACTIVE');
   await page.waitForFunction(()=>document.querySelector('#depthImage').naturalWidth>0);await page.locator('#depthImage').click({position:{x:30,y:30}});
   await page.waitForFunction(()=>document.querySelector('#measurement').textContent.includes('axial depth'));
   const box=await page.locator('#cloudCanvas').boundingBox();await page.mouse.move(box.x+80,box.y+80);await page.mouse.down();await page.mouse.move(box.x+140,box.y+100);await page.mouse.up();
   await page.locator('#zoomIn').click();await page.locator('#panMode').click();await page.locator('#resetView').click();
   const overflow=await page.evaluate(w=>document.documentElement.scrollWidth>w+1,width);if(overflow)throw Error(label+' horizontal overflow');
   await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,label+'.png'),fullPage:true});
   await page.request.get(base+'/sim?scenario=stale');await page.waitForTimeout(3000);await page.waitForFunction(()=>document.querySelector('#depthState').textContent==='STREAM STALE');
   if(await page.locator('#depthImage').getAttribute('src'))throw Error('stale image retained');
   await page.request.get(base+'/sim?scenario=unavailable');await page.waitForFunction(()=>document.querySelector('#depthState').textContent==='DEPTH UNAVAILABLE');
   await page.request.get(base+'/sim?scenario=live');await page.waitForFunction(()=>document.querySelector('#depthState').textContent==='DEPTH ACTIVE');
   await page.locator('#pause').click();await page.waitForTimeout(700);let count=0;page.on('request',()=>count++);await page.waitForTimeout(1000);if(count)throw Error('requests continue paused');
   if(errors.length||writes.length)throw Error(JSON.stringify({errors,writes}));results.push({label,passed:true,horizontal_overflow:overflow,errors,writes});await page.close();
  }
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({simulated:true,results},null,2));console.log(JSON.stringify(results));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

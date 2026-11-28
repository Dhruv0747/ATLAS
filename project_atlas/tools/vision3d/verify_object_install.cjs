/* Run only within a separately approved deployment validation. Read-only GETs. */
const {chromium}=require('playwright'),fs=require('fs'),crypto=require('crypto');
async function verifyStopped(page,base){
 const response=await page.request.get(base+'/api/vision3d/summary',{timeout:2000});
 if(!response.ok())throw Error('camera status unavailable');
 const status=await response.json();if(status.state!=='OFF')throw Error('camera not OFF');
 return {state:status.state,reported_driver_stopped:status.driver_stopped,process_authority:'separate installer kernel inventories required'};
}
const expected='2b34f948d6216720460d0856c8ec22b6143876c2e6b85b6ec365ada60eaf7242';
(async()=>{
 const base=process.argv[2],output=process.argv[3];if(!base||!output)throw Error('base URL and output path required');
 const browser=await chromium.launch({headless:true,executablePath:process.env.VISION_BROWSER});
 let result={result:'FAIL',candidate_sha256:expected};
 try{
  const rows=[];
  for(const width of [1440,390]){
   const page=await browser.newPage({viewport:{width,height:900}});const errors=[],writes=[];
   page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>{if(r.method()!=='GET')writes.push(r.method()+' '+r.url());});
   const response=await page.goto(base+'/v2/vision3d',{timeout:10000});
   if(!response.ok())throw Error('Lab page unavailable');
   const body=(await response.body()).toString().replace('<script src="/v2/home-nav.js"></script>','');
   if(crypto.createHash('sha256').update(body).digest('hex')!==expected)throw Error('served candidate hash mismatch');
   const authority=await verifyStopped(page,base);
   const ui=await page.evaluate(()=>({title:document.querySelector('#vlTitle').textContent,
    cards:document.querySelectorAll('#featureCards article').length,disabled:document.querySelectorAll('#featureCards button:disabled').length,
    overflow:document.documentElement.scrollWidth>innerWidth+1,material:!!document.querySelector('link[href="/v2/material.css"]'),
    preview:!!document.querySelector('#depthImage')&&!!document.querySelector('#rgbImage')&&!!document.querySelector('#measurement'),
    home:[...document.querySelectorAll('a')].some(a=>a.getAttribute('href')==='/v2/')}));
   if(ui.cards!==6||ui.disabled!==24||ui.overflow||!ui.material||!ui.preview||!ui.home||errors.length||writes.length)throw Error(JSON.stringify({ui,errors,writes}));
   rows.push({width,authority,ui});await page.close();
  }
  result={...result,result:'PASS',viewports:rows};
 }catch(e){result.error=String(e);process.exitCode=1;}
 finally{await browser.close();fs.writeFileSync(output,JSON.stringify(result,null,2));console.log(JSON.stringify(result));}
})().catch(e=>{console.error(e);process.exit(1)});

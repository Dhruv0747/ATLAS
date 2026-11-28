/* Run only within a separately approved deployment validation. Read-only GETs. */
const {chromium}=require('playwright'),fs=require('fs'),crypto=require('crypto');
const {verifyStopped}=require('./verify_ui_stopped.cjs');
const expected='6d12362130e53fc6bb545ddba51100bf20a957e2f1ea7284a88ea9743c17ea57';
(async()=>{
 const base=process.argv[2],output=process.argv[3];if(!base||!output)throw Error('base URL and output path required');
 const browser=await chromium.launch({headless:true,executablePath:process.env.VISION_BROWSER});
 let result={result:'FAIL',candidate_sha256:expected};
 try{
  const rows=[];
  for(const width of [1440,768,390,320]){
   const page=await browser.newPage({viewport:{width,height:900}});const errors=[],writes=[];
   page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>{if(r.method()!=='GET')writes.push(r.method()+' '+r.url());});
   const response=await page.goto(base+'/v2/vision3d',{timeout:10000});
   if(!response.ok())throw Error('Lab page unavailable');
   const body=(await response.body()).toString().replace('<script src="/v2/home-nav.js"></script>','');
   if(crypto.createHash('sha256').update(body).digest('hex')!==expected)throw Error('served candidate hash mismatch');
   const authority=await verifyStopped(page,base);
   const ui=await page.evaluate(()=>({title:document.querySelector('#vlTitle').textContent,
    cards:document.querySelectorAll('#astraFeatureUi article').length,disabled:document.querySelectorAll('#astraFeatureUi button:disabled').length,
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

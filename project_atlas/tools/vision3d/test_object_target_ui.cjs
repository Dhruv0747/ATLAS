/* Entirely intercepted synthetic UI wiring test, no rover/camera/inference. */
const {chromium}=require('playwright'),fs=require('fs'),path=require('path');
(async()=>{const pkg=path.resolve(process.argv[2]),base=path.resolve(process.argv[3]),repo=path.resolve(__dirname,'../../web/v2');
 const browser=await chromium.launch({headless:true,executablePath:process.env.VISION_BROWSER});
 try{for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:900}});let active=null,reports={},calls=[],errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  function state(){return {active,latest:null,features:['face','gesture','body','target','object','mapping'].map(id=>({id,state:reports[id]?.state||'UNAVAILABLE',reason:'SYNTHETIC UI TEST',report:reports[id]||null,start_available:!active&&['object','target'].includes(id)}))};}
  await page.route('**/*',async route=>{const request=route.request(),p=new URL(request.url()).pathname;
   if(p==='/api/vision3d/features'){
    if(request.method()==='POST'){const data=request.postDataJSON();calls.push(data);if(data.action==='start'){active=data.feature;reports[active]={state:'RUNNING',frames:0,reason:'synthetic'};}else if(data.action==='stop'){reports[active].state='FAILED';active=null;}else throw Error('unexpected operation');}
    return route.fulfill({contentType:'application/json',body:JSON.stringify(state())});
   }
   if(request.method()!=='GET')throw Error('unexpected write '+p);
   if(p==='/api/vision3d/status')return route.fulfill({contentType:'application/json',body:fs.readFileSync(path.join(base,'offline-status.json'),'utf8')});
   const name=p==='/v2/vision3d'?'vision3d.html':p.replace(/^\/v2\//,'');if(name.includes('..'))return route.abort();
   let f=path.join(pkg,'candidate',name);if(!fs.existsSync(f))f=path.join(pkg,'web/v2',name);if(!fs.existsSync(f))f=path.join(repo,name);
   if(!fs.existsSync(f))return route.fulfill({status:404,body:''});
   const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png','.svg':'image/svg+xml','.webp':'image/webp'}[path.extname(f)]||'application/octet-stream';
   return route.fulfill({contentType:mime,body:fs.readFileSync(f)});
  });
  await page.goto('http://fixture.invalid/v2/vision3d');await page.waitForSelector('.feature-card');
  const cards=page.locator('.feature-card');if(await cards.count()!==6)throw Error('six panels missing');
  for(const index of [0,1,2,5])if(await cards.nth(index).locator('button:disabled').count()!==4)throw Error('unapproved control enabled');
  for(const index of [4,3]){
   const card=cards.nth(index);await card.getByRole('button',{name:'Start Test',exact:true}).click();
   await card.getByRole('button',{name:'Stop Test',exact:true}).click();
  }
  if(calls.map(x=>x.action).join(',')!=='start,stop,start,stop')throw Error('Start/Stop wiring');
  if(calls[0].feature!=='object'||calls[2].feature!=='target')throw Error('feature mapping');
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('overflow');
  if(errors.length)throw Error(errors.join('\n'));
  console.log(JSON.stringify({width,result:'PASS',calls}));await page.close();
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});

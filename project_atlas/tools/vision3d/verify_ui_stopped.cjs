/* Test helper only: no application/runtime changes or camera actions. */
function requireStopped(status){
 if(!status||status.state!=='OFF'||status.driver_stopped!==true)
  throw Error('Authoritative camera status is not confirmed OFF/stopped');
}
async function verifyStopped(page,base){
 async function check(){
  const response=await page.request.get(base+'/api/vision3d/summary',{timeout:2000,headers:{'Cache-Control':'no-cache'}});
  if(!response.ok())throw Error('Camera status API unavailable');
  const age=response.headers()['age'];
  if(age!==undefined&&(!Number.isFinite(Number(age))||Number(age)>1))throw Error('Cached camera status rejected');
  const status=await response.json();requireStopped(status);return {state:status.state,driver_stopped:status.driver_stopped};
 }
 await check();
 await page.waitForFunction(()=>['Camera off','Stopped safely'].includes(document.querySelector('#vlTitle')?.textContent.trim()),null,{timeout:5000});
 return await check();
}
module.exports={requireStopped,verifyStopped};

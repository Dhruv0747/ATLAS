/* Read-only navigation; no requests to actuators or reset endpoints. */
(() => {
  const nav=document.createElement('nav');nav.setAttribute('aria-label','Command center navigation');
  nav.style.cssText='display:flex;gap:8px;flex-wrap:wrap;padding:10px;background:#071522;border-bottom:1px solid #305570;position:relative;z-index:4';
  for(const [label,url] of [['Home / Command Center','/v2/'],['Full-quality camera','/v2/camera'],['LiDAR 360°','/v2/lidar']]){
    const a=document.createElement('a');a.textContent=label;a.href=url;a.style.cssText='display:inline-block;padding:12px;color:#e7faff;background:#143248;border:1px solid #508da9;border-radius:8px;text-decoration:none';nav.append(a);
  }
  document.body.prepend(nav);
  if(['/v2/lidar','/v2/lidar.html','/v2/camera','/v2/camera.html'].includes(location.pathname)){
    const stop=document.getElementById('v2Estop');
    if(stop)stop.style.cssText+=';position:fixed;right:16px;bottom:16px;z-index:30;min-height:48px;min-width:110px';
    document.body.style.paddingBottom='80px';
  }
})();

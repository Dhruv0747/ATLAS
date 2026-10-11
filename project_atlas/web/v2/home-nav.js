/* Read-only navigation; no requests to actuators or reset endpoints. */
(() => {
  const nav=document.createElement('nav');nav.setAttribute('aria-label','Command center navigation');
  nav.style.cssText='display:flex;gap:8px;flex-wrap:wrap;padding:10px;background:#071522;border-bottom:1px solid #305570;position:relative;z-index:4';
  for(const [label,url] of [['Home / Command Center','/v2/'],['Full-quality camera','/v2/camera'],['LiDAR 360°','/v2/lidar']]){
    const a=document.createElement('a');a.textContent=label;a.href=url;a.style.cssText='display:inline-block;padding:12px;color:#e7faff;background:#143248;border:1px solid #508da9;border-radius:8px;text-decoration:none';nav.append(a);
  }
  document.body.prepend(nav);
})();

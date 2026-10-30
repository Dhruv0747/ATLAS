"""Single-use installation of reviewed 52d6b15; never starts camera/inference."""
import hashlib,json,math,os,shutil,signal,subprocess,sys,threading,time,urllib.request
from pathlib import Path
STAGE=Path(__file__).resolve().parent
PKG=STAGE/'package';LIVE=Path('/home/jetson/project_atlas')
sys.path.insert(0,str(LIVE/'tools/vision3d'))
import stationary_gate as G
from install_verification import wait_http_ready, verify_camera_off, camera_processes, require_no_guard_failures, failure_record
MANIFEST='a75bbd94a2f6218be9170507ac1a1c6267cadcca03e401477a2bfb0373a086e1'
REPLACE={'scripts/atlas_vision3d_web.py':'atlas_vision3d_web.py','web/v2/vision3d.html':'vision3d.html','web/v2/vision3d.js':'vision3d.js'}
NEW=['scripts/atlas_vision_feature_guard.py','scripts/atlas_vision_feature_lab.py','scripts/atlas_vision_feature_worker.py','scripts/atlas_vision_features.py','config/vision_feature_lab.json','web/v2/vision_features.js','web/v2/vision_features.css']
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name,value):
 p=STAGE/name;t=p.with_suffix('.tmp')
 with t.open('w') as f:json.dump(value,f,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def get(route):
 with urllib.request.urlopen('http://127.0.0.1:8088'+route,timeout=2) as r:return json.load(r)
def units():
 names=[s.split()[0] for s in subprocess.check_output(['systemctl','--user','list-units','--type=service','--all','--plain','--no-legend'],text=True,timeout=5).splitlines() if s.split() and s.split()[0].startswith(('atlas-','rover-'))]
 raw=subprocess.check_output(['systemctl','--user','show',*sorted(names),'-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState'],text=True,timeout=5)
 return {d['Id']:d for block in raw.strip().split('\n\n') if (d:=dict(x.split('=',1) for x in block.splitlines() if '=' in x))}
def protected(u):return {k:v for k,v in u.items() if k!='rover-status-web.service'}
def check():
 a=G.ticks();start=time.monotonic();time.sleep(1);b=G.ticks()
 if not .9<=time.monotonic()-start<=1.1:raise ValueError('sample timing')
 j=get('/api/status');r=G.check(G.cpu_delta(a,b),j)
 if max(r['thermal_c'].values())>=70:raise ValueError('temperature >=70')
 e=j['ros']['encoder_health'];v=e['value'];v=json.loads(v) if isinstance(v,str) else v
 if not (0<=e['age']<=1 and v['packet_fresh'] is True and v['link_state']=='LIVE' and 0<=v['packet_age_s']<=1 and v['encoder_interval_delta_m']==[0,0,0,0]):raise ValueError('encoder safety/freshness')
 a=verify_camera_off(lambda:get('/api/vision3d/summary'))
 return dict(at=time.time(),cpu=r['cpu_percent'],ram=r['ram_percent'],temp=max(r['thermal_c'].values()),policy=r['policy'],encoders=v,camera=a)
def put(src,dst):
 t=dst.with_name('.'+dst.name+'.52d6b15.tmp')
 if t.exists():raise ValueError('staging file exists')
 shutil.copy2(src,t);os.chmod(t,0o644)
 with t.open('rb') as f:os.fsync(f.fileno())
 os.replace(t,dst)
 fd=os.open(dst.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def restart():
 subprocess.run(['systemctl','--user','restart','rover-status-web'],check=True,timeout=15)
def ready(errors, events, enforce=True):
 def independent():
  if enforce:require_no_guard_failures(errors)
  if camera_processes():raise ValueError('camera/inference process present during readiness')
 return wait_http_ready(lambda:get('/api/status'),independent,events=events)
def resource_monitor(stop,errors,rows):
 try:
  a=G.ticks();previous=time.monotonic()
  while not stop.wait(1):
   now=time.monotonic();b=G.ticks();cpu=G.cpu_delta(a,b);a=b;window=now-previous;previous=now
   mem={x.split(':')[0]:int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines()}
   ram=100*(1-mem['MemAvailable']/mem['MemTotal']);required={'cpu-thermal','gpu-thermal','soc0-thermal','soc1-thermal','soc2-thermal','tj-thermal'};temps={}
   for z in Path('/sys/class/thermal').glob('thermal_zone*'):
    kind=(z/'type').read_text().strip()
    if kind in required:temps[kind]=float((z/'temp').read_text())/1000
   rows.append(dict(at=time.time(),mono=now,window=window,cpu=cpu,ram=ram,thermal=temps));save('resource-trace.json',rows)
   if not .9<=window<=1.1 or not math.isfinite(cpu) or cpu>75 or ram>80 or set(temps)!=required or any(not math.isfinite(t) or not 0<t<70 for t in temps.values()):errors.append('continuous resource guard failed: '+str(rows[-1]))
 except BaseException as exc:errors.append(str(exc))
def main():
 (STAGE/'ATTEMPT_USED').open('x').close();changed=[];restarted=False;result={'result':'FAIL','rollback':'not required'};stop=threading.Event();errors=[];trace=[];samples=[]
 monitor=None;readiness=[];rollback_readiness=[]
 try:
  if digest(PKG/'SHA256SUMS')!=MANIFEST:raise ValueError('manifest mismatch')
  for line in (PKG/'SHA256SUMS').read_text().splitlines():
   h,n=line.split('  ',1)
   if '..' in Path(n).parts or Path(n).is_absolute() or digest(PKG/n)!=h:raise ValueError('package mismatch '+n)
  if json.loads((PKG/'config/vision_feature_lab.json').read_text())['enabled'] is not False:raise ValueError('inference enabled')
  plan={f:PKG/'candidate'/n for f,n in REPLACE.items()};plan.update({f:PKG/f for f in NEW})
  for f,n in REPLACE.items():
   if (LIVE/f).is_symlink() or digest(LIVE/f)!=digest(PKG/'rollback'/n):raise ValueError('live baseline mismatch '+f)
  for f in NEW:
   if (LIVE/f).exists() or (LIVE/f).is_symlink():raise ValueError('unexpected destination '+f)
  before=units();save('services-before.json',before)
  G.preflight()
  for _ in range(3):samples.append(check())
  save('safety-samples.json',samples)
  protected_paths=['scripts/atlas_status_web.py','scripts/trt_yolo_detector.py','tools/vision3d/stationary_gate.py','web/v2/material.css','web/v2/vision3d.css']
  hashes={f:digest(LIVE/f) for f in protected_paths};save('protected-hashes.json',hashes)
  backup=STAGE/'backup';backup.mkdir()
  for f,n in REPLACE.items():
   shutil.copy2(LIVE/f,backup/n)
   if digest(backup/n)!=digest(PKG/'rollback'/n):raise ValueError('backup integrity')
  save('installation-plan.json',{f:{'candidate':digest(p),'original':digest(LIVE/f) if f in REPLACE else None} for f,p in plan.items()})
  if units()!=before:raise ValueError('services changed before install')
  monitor=threading.Thread(target=resource_monitor,args=(stop,errors,trace),daemon=True);monitor.start()
  for f,p in plan.items():
   if errors:raise ValueError(errors[0])
   put(p,LIVE/f);changed.append(f)
   if digest(LIVE/f)!=digest(p):raise ValueError('installed hash mismatch')
  restarted=True;save('restart-start.json',{'at':time.time(),'mono':time.monotonic()});restart()
  save('restart-return.json',{'at':time.time(),'mono':time.monotonic()})
  # A restart temporarily removes this HTTP observer; do not label the gap safe.
  # Independent resource sampling remains active. No stale safety snapshot reused.
  require_no_guard_failures(errors)
  ready(errors,readiness)
  samples.append(check());save('safety-samples.json',samples)
  require_no_guard_failures(errors)
  status=get('/api/vision3d/features');save('api-status.json',status)
  if status['active'] is not None or len(status['features'])!=6 or any(x['start_available'] for x in status['features']):raise ValueError('feature execution not disabled')
  print('INSTALLED_PENDING_BROWSER_VALIDATION',flush=True)
  deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   samples.append(check());save('safety-samples.json',samples)
   if errors:raise ValueError(errors[0])
   p=STAGE/'browser-validation.json'
   if p.exists():
    browser=json.loads(p.read_text())
    if browser.get('result')!='PASS' or browser.get('candidate_sha256')!=digest(PKG/'candidate/vision3d.html'):raise ValueError('browser rejected')
    break
  else:raise ValueError('browser validation timeout')
  for _ in range(10):
   samples.append(check())
   if errors:raise ValueError(errors[0])
  after=units();save('services-after.json',after)
  if protected(before)!=protected(after):raise ValueError('protected service identities changed')
  if after['rover-status-web.service']['ActiveState']!='active':raise ValueError('web not active')
  if any(digest(LIVE/f)!=h for f,h in hashes.items()):raise ValueError('protected file changed')
  if any(s['policy']!=samples[0]['policy'] for s in samples):raise ValueError('control policy changed')
  stop.set();monitor.join(3)
  if monitor.is_alive():raise ValueError('resource monitor did not stop cleanly')
  require_no_guard_failures(errors)
  result.update(result='PASS',installed={f:digest(LIVE/f) for f in plan},rollback='verified backups retained',inference_enabled=False,camera='OFF',protected_services_unchanged=True)
 except BaseException as exc:
  result.update(failure_record(exc,errors))
  try:
   for f in reversed(changed):
    if digest(LIVE/f)!=digest(plan[f]):raise ValueError('concurrent modification '+f)
    if f in REPLACE:put(backup/REPLACE[f],LIVE/f)
    else:(LIVE/f).unlink()
   if restarted:
    restart()
    # Historical failure remains latched; observe recovery, never admit installation.
    ready(errors,rollback_readiness,enforce=False)
   if changed:
    result['rollback']='FILES VERIFIED'
    result['postrollback_safety']=check();result['rollback']='VERIFIED'
  except BaseException as rollback_error:result['rollback_error']=str(rollback_error)
 finally:
  stop.set()
  if monitor:monitor.join(3)
  result['resource_guard_failures']=list(errors)
  save('readiness.json',readiness);save('rollback-readiness.json',rollback_readiness)
  save('safety-samples.json',samples);save('result.json',result)
  print(json.dumps(result),flush=True)
 return result['result']!='PASS'
if __name__=='__main__':
 signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt('termination')))
 sys.exit(main())

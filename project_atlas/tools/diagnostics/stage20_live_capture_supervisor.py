import pathlib,sys,json,time,uuid,subprocess,hashlib,os,shutil,fcntl
R=pathlib.Path('/home/jetson/project_atlas');D=R/'tools/stage20_public/tools/diagnostics';sys.path.insert(0,str(D))
from stage20_activation_evidence import Journal,snapshot,revoke_owned
if '--owner-approved-one-capture' not in sys.argv:
 raise SystemExit('Separate deployment and one-capture approval required; no action taken')
from stage20_production_gate import PUBLIC_RUNTIME_FILES,IDENTITY_FILES,current_boot_id
from stage20_capture_integrity import inspect
U='atlas-stage20-public-capture.service';root=R/'data/diagnostics/stage20_public'
grant=pathlib.Path.home()/'.config/project_atlas/stage20_public_approval.json'
out=pathlib.Path('/tmp/atlas-stationary30-avHg8uSb/live-once-'+uuid.uuid4().hex);out.mkdir()
journal=Journal(out);started=False;created=False
cpu_evidence=[]
def check():
 samples=[]
 def observe():
  sample=snapshot(root,cpu_samples=cpu_evidence,authorization_valid=True);samples.append(sample);return sample
 journal.admission(observe)
 return samples[0]
def emit(**d):journal.write('supervisor',**d)
def run(a):
 try:
  p=subprocess.run(a,text=True,capture_output=True,timeout=20)
  journal.write('subprocess',stdout=p.stdout,stderr=p.stderr,returncode=p.returncode)
  p.check_returncode();return p.stdout
 except subprocess.TimeoutExpired as exc:
  journal.write('subprocess_timeout',stdout=exc.stdout,stderr=exc.stderr)
  raise
def state():return dict(l.split('=',1) for l in run(['systemctl','--user','show',U,'-p','ActiveState','-p','MainPID','-p','NRestarts','-p','UnitFileState','-p','Result']).splitlines() if '=' in l)
def services():
 names=[l.split()[0] for l in run(['systemctl','--user','list-units','--all','--type=service','--plain','--no-legend']).splitlines() if l.split() and l.split()[0].startswith(('atlas','rover')) and l.split()[0]!=U]
 return run(['systemctl','--user','show','-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState','--',*sorted(names)])
def cpu():
 v=list(map(int,pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:9]));return sum(v),v[3]+v[4]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
result={}
try:
 m=json.loads(pathlib.Path('/tmp/atlas-stationary30-avHg8uSb/upgrade30_candidate/manifest.json').read_text())
 assert all(sha(pathlib.Path('/home/jetson')/f['path'])==f['after'] for f in m['files'])
 assert all(sha(pathlib.Path('/home/jetson')/n)==h for n,h in m['unchanged_baseline'].items())
 assert not grant.exists();s=state();assert s['ActiveState']=='inactive' and s['MainPID']=='0' and s['UnitFileState']=='static'
 for unit in ('atlas-nav2.service','atlas-explore.service'):
  assert run(['systemctl','--user','show',unit,'--value','-p','ActiveState']).strip()=='inactive'
 lock=(root/'.stage20.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);lock.close()
 before=services();(out/'services_before.txt').write_text(before);bags=set(root.glob('capture_*'))
 run(['/usr/bin/python3','/tmp/atlas-stationary30-avHg8uSb/first_live_readonly_probe.py'])
 sensor=json.loads(pathlib.Path('/tmp/atlas-stationary30-avHg8uSb/first-live-topic-preflight.json').read_text())
 journal.write('sensor_preflight',sample=sensor)
 journal.admission(lambda:snapshot(root,missing_sensors=sensor['missing'],authorization_valid=True))
 assert all(age<=2 for t,age in sensor['ages'].items() if t not in ('/amcl_pose','/particle_cloud','/tf_static'))
 status=check();assert shutil.disk_usage(root).free>=2*1024**3
 # Explicit independent interval admission, immediately before the single activation.
 previous=cpu();admission=[]
 for _ in range(5):
  t=time.monotonic();time.sleep(1);current=cpu();value=100*(1-(current[1]-previous[1])/(current[0]-previous[0]));admission.append(value);cpu_evidence.append({'percent':value,'interval_s':time.monotonic()-t});previous=current
 emit(phase='preflight',cpu=admission,status=status,sensors=sensor)
 journal.admission(lambda:snapshot(root,cpu_samples=cpu_evidence,authorization_valid=True))
 status=check()
 import urllib.request
 live=json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=2));policy=live['ros']['control_policy']['value']
 if isinstance(policy,str):policy=json.loads(policy)
 assert policy.get('commission_armed') is False
 data={'enabled':True,'owner_approved':True,'deployment_ready':True,'mode':'read_only_partial_public','capture_profile':'stationary_30_v1','source_commit':'04f9ad09025651e954d4e9bab03314a6a3700252','expires_after_boot_session':current_boot_id(),'grant_id':str(uuid.uuid4()),'runtime_identity':{n:sha(R/n) for n in PUBLIC_RUNTIME_FILES},'identity':{n:sha(R/n) for n in IDENTITY_FILES}}
 with grant.open('x') as f:
  stat=os.fstat(f.fileno());grant_identity=(stat.st_dev,stat.st_ino)
  created=True;journal.flags.update(grant_created=True,cleanup_required=True);json.dump(data,f);f.flush();os.fsync(f.fileno())
 created=True;journal.flags.update(grant_created=True,cleanup_required=True);os.chmod(grant,0o600)
 started=True;journal.flags['collector_started']=True;run(['systemctl','--user','start',U]);begin=time.monotonic();previous=cpu()
 while time.monotonic()-begin<65:
  sample_begin=time.monotonic();time.sleep(1);current=cpu();percent=100*(1-(current[1]-previous[1])/(current[0]-previous[0]));previous=current
  cpu_evidence=[{'percent':percent,'interval_s':time.monotonic()-sample_begin}]
  st=state()
  try:
   health=check();assert percent<=75,'whole-system CPU exceeded75%'
  except Exception as ex:
   emit(phase='stop_guard',cpu=percent,error=str(ex));run(['systemctl','--user','stop',U]);break
  emit(phase='recording',cpu=percent,health=health,unit=st)
  if st['ActiveState'] not in ('active','activating','deactivating'):break
 else:run(['systemctl','--user','stop',U])
 result={'started':True,'unit':state(),'captures':[str(p) for p in set(root.glob('capture_*'))-bags]}
 result['integrity']={p:inspect(p) for p in result['captures']}
except Exception as ex:
 result={'started':started,'error':str(ex),'exception_type':type(ex).__name__}
 try:journal.write('supervisor_exception',result=result,traceback=__import__('traceback').format_exc())
 except Exception:pass
 if started:run(['systemctl','--user','stop',U])
finally:
 cleanup_error=None
 if created:
  try:
   # Only revoke the exact grant owned by this attempt, even if archival fails.
   revoke_owned(grant,grant_identity,lambda p:shutil.copy2(p,out/'revoked_grant.json'))
   journal.flags['cleanup_required']=False
  except Exception as exc:cleanup_error=str(exc)
 result['cleanup_error']=cleanup_error
 result['status']='RECORDING ATTEMPTED' if started else 'PREFLIGHT BLOCKED'
 journal.finalize(result,{'final_unit':state,'grant_exists':grant.exists,
   'production_unchanged':lambda:services()==before if 'before' in globals() else None,
   'final_safety_observation':lambda:snapshot(root,authorization_valid=True)})

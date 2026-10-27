import os,sys,json,time,hashlib,subprocess,tarfile,shutil,signal,importlib.util,argparse,traceback,math,tempfile
from pathlib import Path
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from offboard_bridge_preflight import read_thermal
import safety_evidence
ROOT=Path('/UNCONFIGURED-B1-STAGING')
S=Path('/home/jetson/project_atlas/scripts'); U=Path.home()/'.config/systemd/user'
STATE=Path.home()/'.local/state/project_atlas/b1_interlock'
DROP=U/'rover-base-telemetry.service.d/98-b1-maintenance.conf'
BACK=ROOT/'rollback'; C=ROOT/'candidate'
UNITS=['rover-base-telemetry.service','atlas-sensor-recovery.service','atlas-cmd-vel-mux.service','atlas-safety-status.service','atlas-camera.service','atlas-ekf.service','atlas-localization.service','atlas-lidar.service','atlas-voice-companion.service','rover-status-web.service']
EXPECTED={str(S/'atlas_sensor_recovery.py'):'c6b5ac7979b6aff24c2f1a13a365d039b833da4c37997d3a8a07b21a928daaf5',str(U/'rover-base-telemetry.service'):'ff21ac6616d876182a4b0cdb7a42a2203c25d4dfd0b8d5e66fa77e4914c6cfae',str(U/'atlas-sensor-recovery.service'):'1b1010efa44deb44c5c706f212d0db16f762b904bc498b776b1a60185102e256',str(U/'rover-base-telemetry.service.d/priority.conf'):'91ba36a24dde057faa9a07831c688a71ab59239b8242d94d9057bdf61adc3bd8',str(U/'atlas-sensor-recovery.service.d/gnss-disabled.conf'):'ca513ea0abfa6c963a7f777ad635dfc298e9e9efb012fe5760cdfb210ccd1590'}
result={'status':'PREFLIGHT','source_commit':'8736c73cd8ee53d5b082b4fbb9066421143fc4f2','backup':str(BACK),'camera_started':False,'hardware_accessed':False}
modified=False
trace=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cmd(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=15)
def emit(): (ROOT/'result.json').write_text(json.dumps(result,indent=2))
def stats():
 text=cmd('systemctl','--user','show',*UNITS,'-p','Id','-p','ActiveState','-p','MainPID','-p','NRestarts')
 return {v['Id']:v for block in text.strip().split('\n\n') if (v:=dict(line.split('=',1) for line in block.splitlines()))}
def cpu():
 v=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]));return sum(v),v[3]+v[4]
def validate_resources(load, ram, thermal):
 for label,value in [('cpu',load),('ram',ram)]:
  if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100:
   raise ValueError('invalid '+label+' measurement')
 if thermal.get('platform_model_error') or thermal.get('thermal_read_errors'):
  raise ValueError('temperature measurement incomplete; admission blocked')
 values=list(thermal.get('thermal_zones_c',{}).values())
 if not values or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):
  raise ValueError('no trustworthy complete temperature measurement')
 peak=max(values)
 if load>75 or ram>80 or peak>70:
  raise ValueError('resource limits exceeded: CPU75/RAM80/TEMP70 unchanged')
 return peak

def resource():
 a=cpu();time.sleep(1);b=cpu()
 total,idle=b[0]-a[0],b[1]-a[1]
 if total<=0 or not 0<=idle<=total:raise ValueError('invalid CPU delta')
 load=100*(total-idle)/total
 mem={x.split(':')[0]:int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines()}
 if mem['MemTotal']<=0 or not 0<=mem['MemAvailable']<=mem['MemTotal']:raise ValueError('invalid RAM reading')
 ram=100*(1-mem['MemAvailable']/mem['MemTotal'])
 thermal=read_thermal()  # Existing bounded Nano-aware implementation, unchanged.
 row={'monotonic':time.monotonic(),'cpu_pct':load,'ram_pct':ram,'thermal':thermal}
 trace.append(row);(ROOT/'resources.json').write_text(json.dumps(trace,indent=2))
 row['temp_c']=validate_resources(load,ram,thermal)
 return row
def safety():
 d=None;api_error=None
 started=time.monotonic()
 try:
  with urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=3) as r:d=json.load(r)
 except Exception as exc:
  api_error=type(exc).__name__  # exception text/body can contain credentials
 evidence=safety_evidence.evaluate(d,api_error)
 evidence['fetch_started_monotonic']=started
 evidence['fetch_finished_monotonic']=time.monotonic()
 evidence['stage']='post-install' if modified else 'pre-install'
 accepted=api_error is None and gate.safe(d)
 evidence['original_gate_pass']=accepted
 if not accepted and not evidence['failed_predicates']:
  evidence['failed_predicates'].append('original_gate_disagreement')
 sequence=len(result.setdefault('safety_evidence',[]))+1
 path=ROOT/('safety-%03d.json'%sequence)
 entry={'path':str(path),'failed_predicates':evidence['failed_predicates']}
 result['safety_evidence'].append(entry)
 try:
  entry['sha256']=safety_evidence.save(path,evidence)
 except Exception as exc:
  entry['write_error_type']=type(exc).__name__
  entry['fallback_evidence']=evidence
  print(json.dumps({'safety_evidence_write_failure':entry},allow_nan=False),file=sys.stderr,flush=True)
  raise RuntimeError('safety evidence persistence failed; admission denied') from None
 if not accepted or evidence['failed_predicates']:
  raise RuntimeError('safety rejected: '+', '.join(evidence['failed_predicates']))
 count=gate_module.packet_counter(d)
 return {'packet_count':count,'policy':d['ros']['control_policy'],'cmd':d['ros']['cmd_vel'],'encoder':d['ros']['encoder_health']}
def atomic(src,dst):
 dst=Path(dst)
 fd,name=tempfile.mkstemp(prefix=dst.name+'.b1-',dir=dst.parent);os.close(fd)
 tmp=Path(name)
 try:
  shutil.copy2(src,tmp)
  if dst.exists():os.chmod(tmp,dst.stat().st_mode&0o777)
  with tmp.open('rb') as f:os.fsync(f.fileno())
  os.replace(tmp,dst)
  directory=os.open(dst.parent,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(directory)
  finally:os.close(directory)
 finally:
  tmp.unlink(missing_ok=True)
def stop_signal(*_):raise RuntimeError('deployment interrupted')

def deploy():
 global gate,gate_module,result,modified,recovery_restart_attempted,records
 if sys.flags.optimize:
  raise RuntimeError('optimized Python would remove assertions; refused')
 recovery_restart_attempted=False
 try:
  assert sha(ROOT/'baseline-backup.tar')=='6f583eb097236eb675986d472b7ece3c74722a051f1867a58e0b98fed2bda87a','independent baseline archive mismatch'
  assert sha(ROOT/'candidate.tar')=='a28c5ea60de2b9276a2a275d1c2bb0bd303d959a61821b7f0217dc05a428a756'
  C.mkdir();
  with tarfile.open(ROOT/'candidate.tar') as t:
   assert all('/' not in m.name and m.isfile() for m in t.getmembers());t.extractall(C)
  hashes=json.loads((C/'SHA256.json').read_text())
  for name,digest in hashes.items():assert sha(C/name)==digest,(name,'candidate mismatch')
  spec=importlib.util.spec_from_file_location('gate_candidate',C/'atlas_b1_interlock.py');gate_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate_module);gate=gate_module.Interlock()
  assert not STATE.exists() and not (S/'atlas_b1_interlock.py').exists() and not DROP.exists(),'unexpected existing installation'
  for name,digest in EXPECTED.items():assert sha(name)==digest,(name,'live baseline mismatch')
  assert sorted(str(p) for p in (U/'rover-base-telemetry.service.d').glob('*.conf'))==[str(U/'rover-base-telemetry.service.d/priority.conf')]
  before=stats();assert all(v['ActiveState']=='active' and int(v['MainPID'])>0 for v in before.values())
  result['services_before']=before;result['safety_before']=safety();result['resource_before']=resource();assert not gate_module.no_base_jobs() is False
  assert shutil.disk_usage(ROOT).free>100*1024*1024
  BACK.mkdir();records={}
  files=set(Path(n) for n in EXPECTED)
  for unit in UNITS[:2]:files.update((U/(unit+'.d')).glob('*'))
  for i,path in enumerate(sorted(files)):
   if not path.is_file():continue
   dest=BACK/str(i);shutil.copy2(path,dest);assert sha(dest)==sha(path)
   records[str(path)]={'backup':str(dest),'sha256':sha(dest),'mode':oct(path.stat().st_mode&0o777)}
  (BACK/'inventory.json').write_text(json.dumps(records,indent=2))
  (BACK/'units-before.txt').write_text(cmd('systemctl','--user','cat',*UNITS[:2]))
  result['backup_verified']=True;emit()
  # Repeat immediately before the first production write.
  safety();resource()
  for name,digest in EXPECTED.items():assert sha(name)==digest
  modified=True
  atomic(C/'atlas_b1_interlock.py',S/'atlas_b1_interlock.py')
  gate.initialize();assert gate.start_gate() and gate.load()['phase']=='IDLE'
  atomic(C/'atlas_sensor_recovery.py',S/'atlas_sensor_recovery.py')
  atomic(C/'b1-maintenance.conf',DROP)
  result['installed_hashes']={str(p):sha(p) for p in [S/'atlas_b1_interlock.py',S/'atlas_sensor_recovery.py',DROP]}
  cmd('systemctl','--user','daemon-reload')
  condition=cmd('systemctl','--user','show','rover-base-telemetry.service','-p','ExecCondition')
  assert str(S/'atlas_b1_interlock.py') in condition
  result['effective_condition']=condition
  recovery_restart_attempted=True
  cmd('systemctl','--user','restart','atlas-sensor-recovery.service')
  result['restarted_only']='atlas-sensor-recovery.service';emit()
  time.sleep(3)
  samples=[]
  for _ in range(6):
   samples.append(safety());resource()
  after=stats()
  for name,old in before.items():
   assert after[name]['ActiveState']=='active',name
   if name!='atlas-sensor-recovery.service':assert after[name]==old,('protected service changed',name)
  assert after['atlas-sensor-recovery.service']['MainPID']!=before['atlas-sensor-recovery.service']['MainPID']
  assert after['atlas-sensor-recovery.service']['NRestarts']=='0'
  assert samples[-1]['packet_count']>samples[0]['packet_count']
  assert gate.load()=={'version':1,'phase':'IDLE'} and gate.start_gate()
  for name,digest in result['installed_hashes'].items():assert sha(name)==digest
  result.update(status='DEPLOYED_AND_VERIFIED',services_after=after,safety_after=samples[-1],interlock=gate.load(),resource_after=trace[-1],packet_progression=[samples[0]['packet_count'],samples[-1]['packet_count']])
  result['recovery_journal']=cmd('journalctl','--user','-u','atlas-sensor-recovery.service','_PID='+after['atlas-sensor-recovery.service']['MainPID'],'-n','12','--no-pager')
  assert 'READY: full bounded fault recovery armed' in result['recovery_journal'],'missing recovery READY'
 except BaseException as exc:
  result['traceback']=traceback.format_exc()
  result['error']=repr(exc);result['status']='ABORTED_BEFORE_INSTALL' if not modified else 'VALIDATION_FAILED'
  if modified:
   try:
    if STATE.exists() and (STATE/'state.json').exists():
     assert gate.load()['phase']=='IDLE','uncertain latch: automatic rollback forbidden'
    rec=records[str(S/'atlas_sensor_recovery.py')]
    assert sha(rec['backup'])==rec['sha256'];atomic(rec['backup'],S/'atlas_sensor_recovery.py')
    if DROP.exists():
     DROP.unlink();cmd('systemctl','--user','daemon-reload')
    if recovery_restart_attempted:cmd('systemctl','--user','restart','atlas-sensor-recovery.service')
    (S/'atlas_b1_interlock.py').unlink(missing_ok=True)
    if STATE.exists():STATE.rename(BACK/'unused-idle-state')
    result['status']='ROLLED_BACK';result['services_after']=stats()
   except BaseException as rollback_error:result['rollback_error']=repr(rollback_error)
 finally:
  emit();print(json.dumps(result,indent=2),flush=True)

 return result

def main():
 global ROOT,BACK,C,result,modified,trace
 p=argparse.ArgumentParser(description='Approval-gated maintenance deployment; never runs B1')
 p.add_argument('--approve-maintenance-install',action='store_true')
 p.add_argument('--staging',type=Path,required=True)
 a=p.parse_args()
 if not a.approve_maintenance_install:
  p.error('separate owner approval required; no changes made')
 ROOT=a.staging.resolve();BACK=ROOT/'rollback';C=ROOT/'candidate'
 if not ROOT.is_dir() or C.exists() or BACK.exists() or (ROOT/'result.json').exists():
  p.error('use a new staged package directory; preserve previous attempt')
 result={'status':'PREFLIGHT','source_commit':'8736c73cd8ee53d5b082b4fbb9066421143fc4f2',
         'backup':str(BACK),'camera_started':False,'hardware_accessed':False}
 modified=False;trace=[]
 for sig in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT):signal.signal(sig,stop_signal)
 return 0 if deploy()['status']=='DEPLOYED_AND_VERIFIED' else 2

if __name__=='__main__':raise SystemExit(main())

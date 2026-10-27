import os,sys,json,time,hashlib,subprocess,tarfile,shutil,signal,importlib.util,argparse,traceback,math,tempfile,re
from pathlib import Path
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from offboard_bridge_preflight import read_thermal
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
STATUS_URL='http://127.0.0.1:8088/api/status'
STATUS_LIMIT=256*1024          # bytes of /api/status kept as evidence
SAFETY_SAMPLES=[]              # every evaluated safety snapshot, PASS or REJECT
EVIDENCE=[]                    # [{'path','sha256','bytes'}] of verified evidence files
SENSITIVE_KEY=re.compile(r'(pass(word|wd|phrase)?|secret|token|auth|cookie|session|credential|api[_-]?key|private|challenge|psk|ssid|bearer)',re.I)
SENSITIVE_VALUE=[(re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),'[REDACTED-IPV4]'),
                 (re.compile(r'\b(?:[0-9a-f]{1,4}:){4,7}[0-9a-f]{1,4}\b|(?<![0-9a-f:])[0-9a-f:]*::[0-9a-f:]*[0-9a-f](?![0-9a-f:])',re.I),'[REDACTED-IPV6]'),   # not hh:mm:ss
                 (re.compile(r'\b(?:tskey|ghp|gho|github_pat|sk|xox[abp])[-_][A-Za-z0-9_\-]{8,}'),'[REDACTED-TOKEN]'),
                 (re.compile(r'(?i)bearer\s+[A-Za-z0-9._\-]+'),'Bearer [REDACTED]')]


class SafetyRejected(AssertionError):
    """The safety gate rejected a snapshot. Subclass of AssertionError so callers keep fail-closed handling."""
    def __init__(self,message,record):
        super().__init__(message);self.record=record


class EvidenceError(RuntimeError):
    pass


def redact(value,key=''):
    """Copy of a JSON value with credentials/addresses removed. Safety fields are never renamed or dropped."""
    if key and SENSITIVE_KEY.search(key):
        return '[REDACTED]'
    if isinstance(value,dict):
        return {k:redact(v,str(k)) for k,v in value.items()}
    if isinstance(value,list):
        return [redact(v) for v in value]
    if isinstance(value,str):
        for pattern,replacement in SENSITIVE_VALUE:value=pattern.sub(replacement,value)
    return value


def write_evidence(name,obj):
    """Atomic JSON write (temp + fsync + rename + dir fsync), then re-read and hash-verify."""
    folder=ROOT/'evidence';folder.mkdir(exist_ok=True)
    data=(json.dumps(obj,indent=2,sort_keys=True,default=repr)+'\n').encode()
    digest=hashlib.sha256(data).hexdigest()
    fd,tmp=tempfile.mkstemp(prefix=name+'.',suffix='.tmp',dir=folder)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,folder/name)
        dfd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    finally:
        Path(tmp).unlink(missing_ok=True)
    if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:
        raise EvidenceError('evidence verification failed: '+name)
    entry={'path':str(folder/name),'sha256':digest,'bytes':len(data)}
    EVIDENCE[:]=[e for e in EVIDENCE if e['path']!=entry['path']]+[entry]
    return entry


def _number(v):
    return type(v) in (int,float) and math.isfinite(v)


def evaluate_safety(status):
    """Diagnostic, predicate-by-predicate view of Interlock.safe(status) (elapsed=0, as the wrapper calls it).
    Every missing, stale, malformed or wrong value is a failed predicate; nothing defaults to PASS."""
    preds=[]
    def add(name,ok,observed,reason=''):
        preds.append({'predicate':name,'pass':bool(ok),'observed':redact(observed),'reason':'' if ok else reason})
    if not isinstance(status,dict) or not isinstance(status.get('ros'),dict):
        add('api_shape',False,type(status).__name__ if not isinstance(status,dict) else sorted(status)[:40],'response has no ros object')
        return preds
    ros=status['ros']
    items={}
    for field in ('control_policy','cmd_vel'):
        item=ros.get(field)
        if not isinstance(item,dict) or 'value' not in item or 'age' not in item:
            add(field+'_present',False,item,field+' missing or lacks value/age')
            continue
        items[field]=item
        age=item['age']
        if not _number(age) or age<0:
            add(field+'_fresh',False,{'age':age,'sample_time':item.get('sample_time')},'age missing, non-numeric, non-finite or negative')
        else:
            add(field+'_fresh',age<=1,{'age':age,'sample_time':item.get('sample_time'),'observed_hz':item.get('observed_hz'),'limit_s':1},
                'telemetry older than 1 s')
    policy=None
    if 'control_policy' in items:
        raw=items['control_policy']['value']
        try:
            policy=json.loads(raw) if isinstance(raw,str) else raw
            if not isinstance(policy,dict):raise ValueError('policy is not an object')
        except Exception as exc:
            add('control_policy_parse',False,raw if isinstance(raw,str) else repr(raw),'control policy unparsable: '+repr(exc));policy=None
    if policy is not None:
        for name,key,want in (('estop_latched','stop_latched',True),('manual_only','manual_only',True),
                              ('commissioning_disarmed','commission_armed',False),('control_source_stopped','source','STOPPED')):
            if key not in policy:
                add(name,False,None,key+' missing')
            else:
                v=policy[key]
                ok=(v is want) if isinstance(want,bool) else (v==want)
                add(name,ok,{key:v,'stop_reason':policy.get('stop_reason')} if name=='estop_latched' else {key:v},
                    '%s is %r, required %r'%(key,v,want))
    if 'cmd_vel' in items:
        cmd=items['cmd_vel']['value']
        if not isinstance(cmd,dict):
            add('zero_command',False,cmd,'cmd_vel value is not an object')
        else:
            bad={k:cmd.get(k,'<missing>') for k in ('lin','ang') if not (_number(cmd.get(k)) and cmd.get(k)==0)}
            add('zero_command',not bad,{k:cmd.get(k,'<missing>') for k in ('lin','ang')},'non-zero, missing or non-numeric command: %r'%bad)
    return preds


def safety(phase='check'):
    """Fetch /api/status, keep the full redacted snapshot and per-predicate verdicts, then fail closed."""
    rec={'seq':len(SAFETY_SAMPLES)+1,'phase':phase,'url':STATUS_URL,'request_wall':time.time(),'request_monotonic':time.monotonic()}
    status=None
    try:
        with urllib.request.urlopen(STATUS_URL,timeout=3) as r:
            raw=r.read(STATUS_LIMIT+1);rec['http_status']=getattr(r,'status',None)
        rec['response_monotonic']=time.monotonic();rec['response_bytes']=len(raw)
        if len(raw)>STATUS_LIMIT:raise ValueError('status response exceeds %d bytes'%STATUS_LIMIT)
        status=json.loads(raw)
        rec['status_redacted']=redact(status)
    except Exception as exc:
        rec['api_error']=repr(exc);rec.setdefault('response_monotonic',time.monotonic())
    preds=evaluate_safety(status) if status is not None else [{'predicate':'api_available','pass':False,'observed':rec.get('api_error'),'reason':'status API error/timeout/malformed JSON'}]
    gate_ok=False
    if status is not None:
        try:gate_ok=gate.safe(status) is True
        except Exception as exc:rec['gate_error']=repr(exc)
    failed=[p['predicate'] for p in preds if not p['pass']]
    if not gate_ok and not failed:
        preds.append({'predicate':'gate_consistency','pass':False,'observed':rec.get('gate_error'),
                      'reason':'Interlock.safe rejected the snapshot although every diagnostic predicate passed'})
        failed=['gate_consistency']
    count=None
    if gate_ok and not failed:
        # packet_counter is the existing encoder-progress gate; its rejection is evidence too.
        try:count=gate_module.packet_counter(status)
        except Exception as exc:
            enc=status['ros'].get('encoder_health') if isinstance(status.get('ros'),dict) else None
            preds.append({'predicate':'encoder_packets','pass':False,'observed':redact(enc),'reason':repr(exc)})
            failed=['encoder_packets']
    rec['evaluated_monotonic']=time.monotonic()
    rec['evaluation_delay_s']=rec['evaluated_monotonic']-rec['response_monotonic']
    rec['predicates']=preds;rec['gate_verdict']=gate_ok;rec['packet_count']=count
    rec['verdict']='PASS' if gate_ok and not failed else 'REJECT'
    rec['failed_predicates']=failed
    SAFETY_SAMPLES.append(rec)
    try:
        write_evidence('safety-samples.json',SAFETY_SAMPLES)
        if rec['verdict']=='REJECT':
            rec['evidence']=write_evidence('safety-rejection-%03d.json'%rec['seq'],rec)
    except Exception as exc:
        rec['evidence_error']=repr(exc)
        if rec['verdict']=='PASS':
            raise EvidenceError('safety evidence could not be preserved: '+repr(exc)) from exc
    if rec['verdict']!='PASS':
        reasons='; '.join('%s (%s)'%(p['predicate'],p['reason']) for p in preds if not p['pass'])
        prefix='encoder packet evidence rejected' if failed==['encoder_packets'] else 'E-STOP/zero/manual-only policy failure'
        if rec.get('evidence_error'):reasons+='; EVIDENCE NOT SAVED: '+rec['evidence_error']
        raise SafetyRejected(prefix+': '+reasons,rec)
    return {'packet_count':count,'policy':status['ros']['control_policy'],'cmd':status['ros']['cmd_vel'],'encoder':status['ros']['encoder_health']}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cmd(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=15)
def emit():
 # Atomic + verified like all evidence (result.json stays at ROOT for compatibility).
 data=json.dumps(result,indent=2,default=repr)
 fd,tmp=tempfile.mkstemp(prefix='result.',suffix='.tmp',dir=ROOT)
 try:
  with os.fdopen(fd,'w') as f:f.write(data);f.flush();os.fsync(f.fileno())
  os.replace(tmp,ROOT/'result.json')
 finally:Path(tmp).unlink(missing_ok=True)
 if (ROOT/'result.json').read_text()!=data:raise EvidenceError('result.json verification failed')
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
  result['services_before']=before;result['safety_before']=safety('preflight');result['resource_before']=resource();assert not gate_module.no_base_jobs() is False
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
  safety('pre-write');resource()
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
  for i in range(6):
   samples.append(safety('postflight-%d'%(i+1)));resource()
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
  if isinstance(exc,SafetyRejected):
   result['safety_rejection']={'phase':exc.record.get('phase'),'seq':exc.record.get('seq'),'failed_predicates':exc.record.get('failed_predicates'),
                               'predicates':[p for p in exc.record.get('predicates',[]) if not p['pass']],'evaluation_delay_s':exc.record.get('evaluation_delay_s'),
                               'request_wall':exc.record.get('request_wall'),'api_error':exc.record.get('api_error'),
                               'evidence':exc.record.get('evidence'),'evidence_error':exc.record.get('evidence_error')}
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
  result['safety_samples']=[{k:r.get(k) for k in ('seq','phase','verdict','failed_predicates','evaluation_delay_s')} for r in SAFETY_SAMPLES]
  result['evidence']=list(EVIDENCE)
  try:emit()
  except Exception as emit_error:
   result['result_write_error']=repr(emit_error)   # main() then exits non-zero
  print(json.dumps(result,indent=2,default=repr),flush=True)

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
 if not ROOT.is_dir() or C.exists() or BACK.exists() or (ROOT/'result.json').exists() or (ROOT/'evidence').exists():
  p.error('use a new staged package directory; preserve previous attempt')
 result={'status':'PREFLIGHT','source_commit':'8736c73cd8ee53d5b082b4fbb9066421143fc4f2',
         'backup':str(BACK),'camera_started':False,'hardware_accessed':False}
 modified=False;trace=[];SAFETY_SAMPLES.clear();EVIDENCE.clear()
 for sig in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT):signal.signal(sig,stop_signal)
 r=deploy()
 return 0 if r['status']=='DEPLOYED_AND_VERIFIED' and 'result_write_error' not in r else 2

if __name__=='__main__':raise SystemExit(main())

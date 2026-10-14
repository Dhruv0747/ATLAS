"""Supervisor-only admission evidence. No grants, services or hardware operations."""
import datetime,json,math,os,sys,time,traceback,uuid,urllib.request,shutil
from pathlib import Path
from stage20_install_evidence import sanitize

class Refused(ValueError):
    def __init__(self,field,value,limit):
        self.field,self.value,self.limit=field,value,limit
        super().__init__('%s=%r violates %s'%(field,value,limit))

def revoke_owned(path,identity,archive):
    """Revoke only our exclusively created inode, even after partial JSON write."""
    path=Path(path)
    st=path.lstat()
    if path.is_symlink() or (st.st_dev,st.st_ino)!=identity:
        raise ValueError('grant ownership changed; refusing deletion')
    try:archive(path)
    finally:path.unlink()

def evaluate(s):
    def require(ok,k,v,limit):
        if not ok:raise Refused(k,v,limit)
    def maximum(k,v,limit):
        try:n=float(v)
        except (TypeError,ValueError):raise Refused(k,v,'finite number <=%s'%limit)
        require(math.isfinite(n) and 0<=n<=limit,k,v,'0..%s'%limit)
    for i,x in enumerate(s['cpu_samples']):maximum('cpu_samples[%d]'%i,x['percent'],75)
    maximum('dashboard_cpu',s['dashboard_cpu'],75)
    maximum('ram_percent',s['ram_percent'],80)
    maximum('temperature_c',s['temperature_c'],70)
    require(s['free_bytes']>=2*1024**3,'free_bytes',s['free_bytes'],'>=2147483648')
    for k in ('policy_age','command_age'):maximum(k,s[k],2)
    require(s['policy'].get('stop_latched') is True,'stop_latched',s['policy'].get('stop_latched'),'true')
    require(s['policy'].get('source')=='STOPPED','source',s['policy'].get('source'),'STOPPED')
    require(s['policy'].get('commission_armed') is False,'commission_armed',s['policy'].get('commission_armed'),'false')
    for k in ('lin','ang'):
        v=s['command'].get(k)
        try:ok=math.isfinite(float(v)) and abs(float(v))<=1e-9
        except (ValueError,TypeError):ok=False
        require(ok,'command.'+k,v,'zero')
    require(not s.get('missing_sensors',[]),'missing_sensors',s.get('missing_sensors'),'none')
    require(s.get('authorization_valid') is True,'authorization_valid',s.get('authorization_valid'),'true; separately approved scope')
    return {'admitted':True}

def snapshot(root,cpu_samples=(),missing_sensors=(),authorization_valid=False):
    # Only whitelisted telemetry; never persist the complete dashboard response.
    start=time.monotonic()
    with urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=2) as r:
        raw=r.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('oversized dashboard response')
    d=json.loads(raw);ros=d['ros'];system=d['system'];p=ros['control_policy']['value']
    if isinstance(p,str):p=json.loads(p)
    return {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'cpu_method':'/proc/stat aggregate first8 fields; idle+iowait idle; supplied actual intervals',
      'cpu_samples':list(cpu_samples),'dashboard_cpu':system.get('cpu_percent'),
      'dashboard_resource_age_s':system.get('resource_age_s'),
      'dashboard_resource_freshness':'UNKNOWN if resource_age_s absent; HTTP receipt is not measurement age',
      'http_elapsed_s':time.monotonic()-start,'ram_percent':system.get('ram_percent'),
      'temperature_c':str(system.get('temp')).split()[0],'free_bytes':shutil.disk_usage(root).free,
      'policy':{k:p.get(k) for k in ('stop_latched','source','commission_armed')},
      'policy_age':ros['control_policy'].get('age'),'command_age':ros['cmd_vel'].get('age'),
      'command':{k:ros['cmd_vel']['value'].get(k) for k in ('lin','ang')},
      'missing_sensors':list(missing_sensors),'authorization_valid':authorization_valid}

class Journal:
    def __init__(self,directory,terminal=None):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/('activation-'+uuid.uuid4().hex+'.jsonl')
        self.stream=os.fdopen(os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w')
        self.terminal=terminal or sys.stderr
        self.flags={'grant_created':False,'collector_started':False,'cleanup_required':False}
    def write(self,event,**data):
        record=sanitize({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'event':event,**self.flags,**data})
        line=json.dumps(record,allow_nan=True)
        # Sanitized terminal fallback exists even if file write/fsync fails.
        print(line,file=self.terminal,flush=True)
        self.stream.write(line+'\n');self.stream.flush();os.fsync(self.stream.fileno())
    def admission(self,provider,phase='preflight'):
        sample=None
        try:
            sample=provider()
            self.write('measurement',phase=phase,sample=sample) # BEFORE validation
            answer=evaluate(sample)
            self.write('admitted',phase=phase)
            return answer
        except Exception as e:
            info={'phase':phase,'sample':sample,'exception_type':type(e).__name__,
              'traceback':traceback.format_exc(),'error':str(e),
              'failed_field':getattr(e,'field',None),'rejecting_value':getattr(e,'value',None),
              'threshold':getattr(e,'limit',None),'status':'PREFLIGHT BLOCKED'}
            try:self.write('rejected',**info)
            except Exception as secondary:
                print(json.dumps(sanitize({'event':'evidence_write_failed',**info,'secondary':str(secondary)})),file=self.terminal,flush=True)
            raise
    def finalize(self,result,observers=None):
        # No mandatory validator in finally. Secondary errors never replace primary.
        result=dict(result);result.update(self.flags)
        for name,read in (observers or {}).items():
            try:result[name]=read()
            except Exception as e:result[name]={'unavailable':True,'error':str(e),'type':type(e).__name__}
        try:
            self.write('final',result=result)
            path=self.directory/('result-'+uuid.uuid4().hex+'.json')
            with path.open('x') as f:
                json.dump(sanitize(result),f,indent=2);f.flush();os.fsync(f.fileno())
        except Exception as e:
            print(json.dumps(sanitize({'event':'final_report_failed','result':result,'error':str(e)})),file=self.terminal,flush=True)
        finally:
            try:self.stream.close()
            except Exception:pass
        return result

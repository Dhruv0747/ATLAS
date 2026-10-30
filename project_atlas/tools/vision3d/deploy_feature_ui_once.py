"""Owner-approved single HTML transaction; no service/camera/control operations."""
import hashlib,json,os,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
LIVE=Path('/home/jetson/project_atlas/web/v2/vision3d.html')
OLD='1511d33f060c450a3afc0c120711f1da18587f5f37f9e0796fad7d577bcddb48'
NEW='6d12362130e53fc6bb545ddba51100bf20a957e2f1ea7284a88ea9743c17ea57'
sys.path.insert(0,'/home/jetson/project_atlas/tools/vision3d')
import stationary_gate as G

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name,data):
    p=ROOT/name;t=p.with_suffix('.tmp')
    with open(t,'w') as f:json.dump(data,f,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(t,p)
def get(route):
    with urllib.request.urlopen('http://127.0.0.1:8088'+route,timeout=2) as r:return json.load(r)
def units():
    names=[line.split()[0] for line in subprocess.check_output(['systemctl','--user','list-units','--type=service','--all','--plain','--no-legend'],text=True).splitlines() if line.split() and line.split()[0].startswith(('atlas-','rover-'))]
    return subprocess.check_output(['systemctl','--user','show',*sorted(names),'-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState'],text=True)
def snapshot():
    a=G.ticks();start=time.monotonic();time.sleep(1);b=G.ticks()
    if not .9<=time.monotonic()-start<=1.1:raise ValueError('CPU sample interval invalid')
    j=get('/api/status');v=G.check(G.cpu_delta(a,b),j)
    if max(v['thermal_c'].values())>=70:raise ValueError('temperature >=70')
    row=j['ros']['encoder_health'];e=row['value'];e=json.loads(e) if isinstance(e,str) else e
    if not 0<=row['age']<=1 or e['link_state']!='LIVE' or e['packet_fresh'] is not True or not 0<=e['packet_age_s']<=1 or e['encoder_interval_delta_m']!=[0,0,0,0]:raise ValueError('encoder freshness/stationarity failed')
    camera=get('/api/vision3d/summary')
    if camera['state']!='OFF' or camera['driver_stopped'] is not True:raise ValueError('Astra not OFF')
    v['encoders']=e;v['camera']=camera;v['at']=time.time();return v
def replace(source):
    tmp=LIVE.with_name('.vision3d-approved-ui.tmp')
    if tmp.exists():raise ValueError('unexpected existing staging file')
    try:
        shutil.copy2(source,tmp)
        os.chmod(tmp,LIVE.stat().st_mode & 0o777)
        with open(tmp,'rb') as f:os.fsync(f.fileno())
        os.replace(tmp,LIVE)
        fd=os.open(LIVE.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    finally:
        if tmp.exists():tmp.unlink()
def main():
    with open(ROOT/'ATTEMPT_USED','x') as f:f.write(str(time.time()))
    changed=False;samples=[];result={'result':'FAIL','changed_file':str(LIVE),'rollback':'not needed'}
    try:
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            h,name=line.split('  ',1)
            if Path(name).name!=name or digest(ROOT/name)!=h:raise ValueError('package checksum mismatch')
        if LIVE.is_symlink() or digest(LIVE)!=OLD or digest(ROOT/'candidate.html')!=NEW:raise ValueError('live/candidate hash mismatch')
        original=LIVE.read_bytes();candidate=(ROOT/'candidate.html').read_bytes()
        if candidate.count(b'class="btn" disabled')<24 or candidate.count(b'ATLAS-SIX-FEATURE-UI-BEGIN')!=1:raise ValueError('candidate structure')
        before=units();save('services-before.json',before)
        paths=[LIVE.parent/n for n in ['vision3d.js','vision3d.css','material.css','glass.css','base.css']]
        paths+=[Path('/home/jetson/project_atlas/scripts')/n for n in ['atlas_vision3d_web.py','atlas_status_web.py']]
        protected={str(p):digest(p) for p in paths};save('protected-hashes.json',protected)
        samples.append(snapshot());save('samples.json',samples)
        if units()!=before:raise ValueError('service identity changed during admission')
        shutil.copy2(LIVE,ROOT/'rollback.html')
        if digest(ROOT/'rollback.html')!=OLD:raise ValueError('backup mismatch')
        replace(ROOT/'candidate.html');changed=True
        if digest(LIVE)!=NEW:raise ValueError('installed hash mismatch')
        with urllib.request.urlopen('http://127.0.0.1:8088/v2/vision3d',timeout=2) as r:served=r.read(200000)
        if served.replace(b'<script src="/v2/home-nav.js"></script>',b'')!=candidate:raise ValueError('served page differs')
        print('INSTALLED_PENDING_BROWSER_VALIDATION',flush=True)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            samples.append(snapshot());save('samples.json',samples)
            if (ROOT/'browser-validation.json').exists():
                validation=json.loads((ROOT/'browser-validation.json').read_text())
                if validation.get('result')!='PASS' or validation.get('candidate_sha256')!=NEW:raise ValueError('browser validation failed')
                break
        else:raise ValueError('browser validation timed out')
        after=units();save('services-after.json',after)
        if after!=before:raise ValueError('protected service identity changed')
        if any(digest(p)!=h for p,h in protected.items()):raise ValueError('protected file changed')
        if any(s['policy']!=samples[0]['policy'] for s in samples):raise ValueError('controller policy changed')
        result.update(result='PASS',installed_sha256=digest(LIVE),rollback='verified exact-byte backup retained',protected_services_unchanged=True)
    except BaseException as e:
        result['error']=str(e)
        if changed:
            if digest(LIVE)==NEW and digest(ROOT/'rollback.html')==OLD:
                replace(ROOT/'rollback.html');result['rollback']='VERIFIED' if digest(LIVE)==OLD else 'FAILED'
            else:result['rollback']='BLOCKED: concurrent change; refusing overwrite'
    finally:
        save('result.json',result);print(json.dumps(result),flush=True)
    return 0 if result['result']=='PASS' else 1

if __name__=='__main__':sys.exit(main())

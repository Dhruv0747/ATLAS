"""Pinned installation-only file transaction. No service-control operations.
Uses existing ATLAS safety/camera checks and atomic-copy/rollback pattern.
CLI production root is fixed; tests call transact on isolated temporary trees.
"""
import argparse,base64,fcntl,hashlib,json,math,os,signal,stat,subprocess,sys,time
from pathlib import Path

LIVE=Path('/home/jetson/project_atlas')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(path,data):
    tmp=path.with_suffix('.tmp')
    with tmp.open('w') as f:json.dump(data,f,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    sync(path.parent)
def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
def target(root,name):
    p=root/name
    if Path(name).is_absolute() or '..' in Path(name).parts or p.resolve()!=p:
        raise ValueError('unsafe/symlink path '+name)
    return p

def metadata(p):
    s=p.stat()
    return dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid,mtime_ns=s.st_mtime_ns,
                xattrs={k:base64.b64encode(os.getxattr(p,k)).decode() for k in os.listxattr(p)})
def matches(p,digest,meta):
    if not p.exists():return digest is None
    if p.is_symlink() or not p.is_file() or digest is None:return False
    return sha(p)==digest and metadata(p)=={k:meta[k] for k in ('mode','uid','gid','mtime_ns','xattrs')}

def put(source,dest,meta):
    # Metadata is set BEFORE replacement. Failure leaves the old file intact.
    tmp=dest.with_name('.'+dest.name+'.mapping-install.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(source.read_bytes());f.flush()
            os.fchown(f.fileno(),meta['uid'],meta['gid']);os.fchmod(f.fileno(),meta['mode'])
            for k,v in meta['xattrs'].items():os.setxattr(f.fileno(),k,base64.b64decode(v))
            os.fsync(f.fileno())
        os.utime(tmp,ns=(meta['atime_ns'],meta['mtime_ns']))
        if not matches(tmp,sha(source),meta):raise ValueError('staged metadata/hash mismatch')
        os.utime(tmp,ns=(meta['atime_ns'],meta['mtime_ns']))
        os.replace(tmp,dest);sync(dest.parent)
    finally:
        if tmp.exists():tmp.unlink()

def validate_package(pkg,m):
    if m['activation_allowed'] is not False:raise ValueError('activation forbidden')
    for name,digest in m['support'].items():
        if sha(target(pkg/'support',name))!=digest:raise ValueError('support hash mismatch '+name)
    names=[f['path'] for f in m['files']]
    if len(names)!=len(set(names)):raise ValueError('duplicate target')
    for row in m['files']:
        name=row['path'];source=target(pkg/'payload',name)
        if sha(source)!=row['after']:raise ValueError('payload mismatch '+name)
        if name.endswith('.py'):compile(source.read_bytes(),name,'exec')
        if row['before'] is not None:
            if sha(target(pkg/'rollback',name))!=row['before']:raise ValueError('rollback mismatch '+name)
    if json.loads((pkg/'payload/config/onboard_mapping.json').read_text())['enabled'] is not False:
        raise ValueError('mapping not disabled')

def verify_baseline(root,m):
    for name,meta in m['existing_dirs'].items():
        p=target(root,name);a=p.stat()
        if not p.is_dir() or any(metadata(p)[k]!=meta[k] for k in ('mode','uid','gid')):raise ValueError('directory metadata drift '+name)
    for row in m['files']:
        if not matches(target(root,row['path']),row['before'],row['original']):raise ValueError('baseline drift '+row['path'])
    for name,digest in m['unchanged'].items():
        if sha(target(root,name))!=digest:raise ValueError('unchanged dependency drift '+name)
    for name in m['new_dirs']:
        if target(root,name).exists():raise ValueError('new directory already exists '+name)

def rollback(root,pkg,m):
    validate_package(pkg,m)
    # Validate ALL targets before touching any; never overwrite later edits.
    for row in m['files']:
        p=target(root,row['path'])
        if not (matches(p,row['before'],row['original']) or matches(p,row['after'],row['installed'])):
            raise ValueError('rollback refuses later drift '+row['path'])
    for row in reversed(m['files']):
        p=target(root,row['path'])
        if row['before'] is None:
            if p.exists():p.unlink();sync(p.parent)
        elif not matches(p,row['before'],row['original']):put(pkg/'rollback'/row['path'],p,row['original'])
    for name in reversed(m['new_dirs']):
        p=target(root,name)
        if p.exists():p.rmdir();sync(p.parent)  # only known, empty directory; never recursive
    for row in m['files']:
        p=target(root,row['path'])
        if not matches(p,row['before'],row['original']):raise ValueError('restoration mismatch')
        if row['before'] is not None:os.utime(p,ns=(row['original']['atime_ns'],row['original']['mtime_ns']))
    return 'EXACT_BYTES_AND_METADATA_VERIFIED'

def fresh(sample):
    stamp=sample['received_mono']
    if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=time.monotonic()-stamp<=1:
        raise ValueError('safety observation stale before file operation')

def transact(root,pkg,m,guard,identities,*,fail_after=None):
    validate_package(pkg,m);verify_baseline(root,m)
    before=identities();sample=guard();fresh(sample);changed=False
    try:
        for name in m['new_dirs']:
            fresh(sample)
            target(root,name).mkdir(mode=0o755);changed=True
        for i,row in enumerate(m['files'],1):
            if identities()!=before:raise ValueError('service identity changed')
            sample=guard()
            p=target(root,row['path'])
            if not matches(p,row['before'],row['original']):raise ValueError('concurrent file drift')
            fresh(sample)
            changed=True;put(pkg/'payload'/row['path'],p,row['installed'])
            if not matches(p,row['after'],row['installed']):raise ValueError('installed mismatch')
            if fail_after==i:raise RuntimeError('offline injected interruption')
        if identities()!=before:raise ValueError('service identity changed')
        sample=guard();fresh(sample)
        for row in m['files']:
            if not matches(target(root,row['path']),row['after'],row['installed']):raise ValueError('final installed drift '+row['path'])
        for name,digest in m['unchanged'].items():
            if sha(target(root,name))!=digest:raise ValueError('unrelated file changed')
        return dict(result='PASS',activation=False,services_unchanged=True,rollback='verified originals retained')
    except BaseException:
        signal.setitimer(signal.ITIMER_REAL,0)  # bounded install alarm must not interrupt restoration
        if changed:rollback(root,pkg,m)
        raise

def services():
    names=[l.split()[0] for l in subprocess.check_output(['systemctl','--user','list-units','--type=service','--all','--plain','--no-legend'],text=True,timeout=3).splitlines() if l.split() and l.split()[0].startswith(('atlas-','rover-'))]
    args=['-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState']
    return (subprocess.check_output(['systemctl','--user','show',*sorted(names),*args],timeout=3),
            subprocess.check_output(['systemctl','show','atlas-monitoring-firewall','atlas-monitoring-watchdog','atlas-monitoring-exporter',*args],timeout=3))

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['verify','install','rollback'])
    p.add_argument('--manifest-sha256',required=True);p.add_argument('--owner-approved-installation-only',action='store_true')
    a=p.parse_args();pkg=Path(__file__).resolve().parent
    if sha(pkg/'INSTALL.json')!=a.manifest_sha256:raise ValueError('manifest pin mismatch')
    m=json.loads((pkg/'INSTALL.json').read_text());validate_package(pkg,m)
    if a.action=='verify':verify_baseline(LIVE,m);print('READ_ONLY_BASELINE_PASS');return
    if not a.owner_approved_installation_only:raise ValueError('separate owner approval required')
    if os.geteuid()!=1000:raise ValueError('run as jetson, not root')
    lock=(pkg/'transaction.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if a.action=='rollback':print(rollback(LIVE,pkg,m));return
    (pkg/'ATTEMPT_USED').open('x').close()  # one attempt, never retry
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=m['boot_id']:raise ValueError('boot changed; re-review required')
    for path,digest in m['unit_files'].items():
        if sha(path)!=digest:raise ValueError('service configuration changed')
    pid=subprocess.check_output(['systemctl','--user','show','rover-status-web','-p','MainPID','--value'],text=True,timeout=2).strip()
    env=Path('/proc/'+pid+'/environ').read_bytes().split(b'\0')
    if any(x.startswith((b'ATLAS_RGBD_EVIDENCE_CACHE=',b'ATLAS_VISION3D_CAPTURE_DEADLINE=')) for x in env):raise ValueError('optional activation environment present')
    sys.path.insert(0,str(pkg/'payload/tools/vision3d'));sys.path.insert(0,str(pkg/'support'))
    from onboard_supervisor import observe,read_json
    from stationary_gate import ticks,cpu_delta
    from install_verification import verify_camera_off
    def guard():
        t=time.monotonic();first=ticks();time.sleep(1);last=ticks();elapsed=time.monotonic()-t
        sampled_at=time.monotonic()
        sample=observe(cpu_delta(first,last),elapsed)
        sample['received_mono']=sampled_at
        verify_camera_off(lambda:read_json('http://127.0.0.1:8088/api/vision3d/summary'))
        from calibration_capture import safety
        safety(sample,time.monotonic())
        return sample
    def interrupted(*_):raise RuntimeError('installation timeout/interruption')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGALRM,interrupted)
    signal.setitimer(signal.ITIMER_REAL,90)
    try:result=transact(LIVE,pkg,m,guard,services)
    except BaseException as e:
        result=dict(result='FAIL',reason=str(e),rollback='NOT_CLAIMED; verify exact baseline')
        try:verify_baseline(LIVE,m);result['rollback']='VERIFIED'
        except Exception as problem:result['rollback_error']=str(problem)
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    save(pkg/'result.json',result);print(json.dumps(result))
    if result['result']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()

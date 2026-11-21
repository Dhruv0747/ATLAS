"""Approval-gated passive attribution trial. Never starts/stops any service.
Independent of Recovery, requires existing Dashboard HTTP (not a web restart tool).
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import startup_cpu_attribution as collector
from snapshot_benchmark_once import fetch, resources, validate, terminate
from install_verification import verify_camera_off
from restart_policy import save

ROOT=Path(__file__).resolve().parent
SECONDS=12

def interrupted(*_):raise TimeoutError('interrupted/deadline')

def child_limits(expected_parent):
    # Set before exec; check against PID captured BEFORE fork (closes parent-death race).
    if ctypes.CDLL(None).prctl(1,signal.SIGKILL)!=0:os._exit(125)
    if os.getppid()!=expected_parent:os._exit(125)
    resource.setrlimit(resource.RLIMIT_CPU,(3,3))
    resource.setrlimit(resource.RLIMIT_AS,(128*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))

def units():
    raw=subprocess.check_output(['systemctl','--user','show','atlas-*.service','rover-*.service',
        '-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState','-p','ControlGroup'],text=True,timeout=2)
    rows={v['Id']:v for b in raw.strip().split('\n\n') if (v:=dict(x.split('=',1) for x in b.splitlines() if '=' in x))}
    recovery=rows['atlas-sensor-recovery.service']
    if recovery['MainPID']!='0' or recovery['ActiveState'] not in ('inactive','failed'):raise ValueError('Recovery not stopped')
    for name in ('rover-status-web.service','rover-base-telemetry.service','atlas-cmd-vel-mux.service'):
        if rows[name]['ActiveState']!='active' or rows[name]['MainPID']=='0':raise ValueError('protected service unavailable '+name)
    return rows

def discover_groups(service_rows,mountinfo=Path('/proc/self/mountinfo')):
    mounts=[]
    for line in mountinfo.read_text().splitlines():
        left,right=line.split(' - ',1);a,b=left.split(),right.split()
        if b[0]=='cgroup2' or (b[0]=='cgroup' and 'cpuacct' in b[2].split(',')):
            mounts.append((2 if b[0]=='cgroup2' else 1,Path(a[3]),Path(a[4])))
    groups=[];gaps=[]
    for name in ('atlas-sensor-recovery.service','atlas-localization.service','rover-status-web.service','atlas-cmd-vel-mux.service'):
        value=service_rows.get(name,{}).get('ControlGroup','')
        if not value:gaps.append({'unit':name,'reason':'no live cgroup'});continue
        found=False
        for version,root,mount in mounts:
            try:rel=Path(value).relative_to(root)
            except ValueError:continue
            base=mount.resolve();path=(base/rel).resolve()
            if not path.is_relative_to(base) or not base.is_relative_to('/sys/fs/cgroup'):raise ValueError('cgroup escape')
            groups.append((name,str(path),version));found=True;break
        if not found:raise ValueError('CPU cgroup mount unavailable '+name)
    if not groups:raise ValueError('no CPU cgroups resolved')
    return groups,gaps

def check(row,old):
    delta=collector.differences(old,row)
    if not .9<=delta['interval']<=1.1:raise ValueError('invalid sampling interval')
    # No API/thermal work after an already rejected CPU observation.
    if delta['cpu_pct']>75:raise ValueError('CPU guard '+str(delta['cpu_pct']))
    ram,temp=resources();started=time.monotonic();status=fetch('/api/status')
    return validate(status,delta['cpu_pct'],ram,temp,time.monotonic()-started)

def sample(directory,index,old,groups=(),collect=collector.snapshot,safety=check):
    current=collect(groups=groups)
    record={'snapshot':current,'previous_mono':old['mono'],'phase':'observe',
        'collector_cpu_s':time.process_time(),'collector_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    error=None
    try:
        record['delta']=collector.differences(old,current)
        record['safety']=safety(current,old)
        record['safe']=True
    except BaseException as exc:
        error=exc;record.update(safe=False,error=type(exc).__name__+': '+str(exc))
        delta=record.get('delta',{})
        record['failure_kind']='CPU_LIMIT' if delta.get('cpu_pct',0)>75 else ('SAMPLING_INTERVAL' if 'interval' in delta and not .9<=delta['interval']<=1.1 else 'SAFETY_OBSERVATION')
        # Fail state precedes durable full rejected endpoint, never a false PASS.
        save(directory/'health.json',{'safe':False,'mono':time.monotonic(),'error':record['error']})
    collector.persist(directory,index,record)
    if error:raise error
    save(directory/'health.json',{'safe':True,'mono':current['mono'],'index':index,'attribution_complete':current.get('complete',True)})
    return current

def observe(directory,groups):
    old=json.loads((directory/'baseline.json').read_text())
    try:
        for index in range(1,SECONDS+1):
            time.sleep(max(0,old['mono']+1-time.monotonic()))
            old=sample(directory,index,old,groups)
        save(directory/'observer-result.json',{'result':'PASS','samples':SECONDS})
    except BaseException as exc:
        save(directory/'health.json',{'safe':False,'mono':time.monotonic(),'error':str(exc)})
        save(directory/'observer-result.json',{'result':'FAIL','error':str(exc)})
        raise

def supervise(child,directory,baseline_mono,clock=time.monotonic,sleep=time.sleep):
    deadline=baseline_mono+15
    while child.poll() is None:
        now=clock()
        if now>deadline:raise TimeoutError('observer wall deadline')
        health=directory/'health.json'
        if health.exists():
            row=json.loads(health.read_text())
            if row.get('safe') is not True:
                # Already failed closed; bounded grace only for the rejected evidence write.
                try:child.wait(timeout=.3)
                except subprocess.TimeoutExpired:pass
                raise ValueError('observer failed')
            if not 0<=now-row['mono']<=1.8:raise ValueError('observer stale')
        elif now-baseline_mono>1.8:raise TimeoutError('observer startup missing')
        sleep(.02)
    if child.returncode!=0:raise ValueError('observer exited unsuccessfully')
    result=json.loads((directory/'observer-result.json').read_text())
    if result!={'result':'PASS','samples':SECONDS}:raise ValueError('observer completion missing')

def verify_package():
    lines=(ROOT/'SHA256SUMS').read_text().splitlines()
    required={'recovery_attribution_trial.py','startup_cpu_attribution.py','snapshot_benchmark_once.py','stationary_gate.py','install_verification.py','restart_policy.py'}
    if len(lines)!=len(required) or {line.split('  ',1)[1] for line in lines}!=required:raise ValueError('incomplete manifest')
    for line in lines:
        expected,name=line.split('  ',1)
        if Path(name).name!=name or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise ValueError('package mismatch '+name)

def run():
    verify_package()
    resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024*1024,)*2)
    (ROOT/'ATTEMPT_USED').open('x').close()
    directory=ROOT/'evidence';directory.mkdir(mode=0o700)
    child=None;result={'result':'FAIL','production_changed':False,'recovery_started':False}
    try:
        before=units();save(directory/'services-before.json',before)
        verify_camera_off(lambda:fetch('/api/vision3d/summary'))
        groups,gaps=discover_groups(before)
        save(directory/'groups.json',groups);save(directory/'group-gaps.json',gaps)
        old=collector.snapshot(groups=groups);collector.persist(directory,0,{'snapshot':old,'phase':'preflight'})
        for index in range(20,23):
            time.sleep(max(0,old['mono']+1-time.monotonic()));old=sample(directory,index,old,groups)
        if collector.differences(json.loads((directory/'021.json').read_text())['snapshot'],old)['cpu_pct']>=75:raise ValueError('admission CPU')
        if json.loads((directory/'022.json').read_text())['safety']['ram']>=80:raise ValueError('admission RAM')
        # Reuse last endpoint, do not discard gap/startup CPU. Child starts within first window.
        save(directory/'baseline.json',old);(directory/'health.json').unlink()
        parent=os.getpid()
        child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--observer'],
            preexec_fn=lambda:child_limits(parent),start_new_session=True)
        save(directory/'owned-child.json',{'pid':child.pid,'start_ticks':collector.stat(Path('/proc',str(child.pid),'stat').read_text())['start_ticks']})
        supervise(child,directory,old['mono'])
        old=json.loads((directory/'012.json').read_text())['snapshot']
        for index in range(30,33):
            time.sleep(max(0,old['mono']+1-time.monotonic()));old=sample(directory,index,old,groups)
        after=units();save(directory/'services-after.json',after)
        if before!=after:raise ValueError('service identity change')
        verify_camera_off(lambda:fetch('/api/vision3d/summary'))
        result['result']='PASS'
    except BaseException as exc:result['error']=type(exc).__name__+': '+str(exc)
    finally:
        terminate(child)
        result['cleanup']='owned child reaped; no production writes'
        save(directory/'result.json',result)
        files=sorted(directory.glob('*.json'))
        (directory/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))
    print(json.dumps(result));return int(result['result']!='PASS')

if __name__=='__main__':
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupted)
    parser=argparse.ArgumentParser();parser.add_argument('--approved-once',action='store_true');parser.add_argument('--observer',action='store_true');args=parser.parse_args()
    if args.observer:observe(ROOT/'evidence',json.loads((ROOT/'evidence'/'groups.json').read_text()))
    elif args.approved_once:sys.exit(run())
    else:parser.error('separate owner approval required')

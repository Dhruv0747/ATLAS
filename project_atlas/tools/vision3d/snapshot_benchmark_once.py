"""Single-use, owner-approval-gated isolated benchmark. No production writes.
HTTP must stay UP: this is not the web-restart safety supervisor.
"""
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from stationary_gate import ticks, cpu_delta, validate_policy, services
from install_verification import verify_camera_off

ROOT=Path(__file__).resolve().parent
PHASES=(('baseline',3),('benchmark',14),('after',3))
THERMAL={'cpu-thermal','gpu-thermal','soc0-thermal','soc1-thermal','soc2-thermal','tj-thermal'}


def fail_signal(*_):raise TimeoutError('deadline or interruption')


def fetch(route):
    # Total request budget, including slow/trickling bodies; main thread only.
    prior=signal.signal(signal.SIGALRM,fail_signal)
    signal.setitimer(signal.ITIMER_REAL,.5)
    try:
        with urllib.request.urlopen('http://127.0.0.1:8088'+route,timeout=.2) as response:
            raw=response.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('HTTP body quota')
        return json.loads(raw)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,prior)


def validate(status,cpu,ram,temps,request_elapsed=0):
    if not math.isfinite(cpu) or not 0<=cpu<=75:raise ValueError('CPU guard')
    if not math.isfinite(ram) or not 0<=ram<=80:raise ValueError('RAM guard')
    if set(temps)!=THERMAL or any(not math.isfinite(v) or not 0<v<70 for v in temps.values()):raise ValueError('temperature guard')
    ros=status['ros'];validate_policy(ros)
    for name in ('control_policy','cmd_vel','encoder_health'):
        age=ros[name]['age']
        if type(age) not in (int,float) or not 0<=age+request_elapsed<=1:raise ValueError('stale '+name)
    e=ros['encoder_health']['value'];e=json.loads(e) if isinstance(e,str) else e
    age=e['packet_age_s']
    if e['packet_fresh'] is not True or e['link_state']!='LIVE' or type(age) not in (int,float) or not 0<=age+ros['encoder_health']['age']+request_elapsed<=1:raise ValueError('telemetry missing/stale')
    delta=e['encoder_interval_delta_m']
    if len(delta)!=4 or any(type(x) not in (int,float) or not math.isfinite(x) or x!=0 for x in delta):raise ValueError('wheel motion')
    return {'cpu':cpu,'ram':ram,'temp':max(temps.values()),'telemetry_age':age,'estop':True,'stationary':True}


def resources():
    mem={s.split(':')[0]:int(s.split()[1]) for s in Path('/proc/meminfo').read_text().splitlines()}
    ram=100*(mem['MemTotal']-mem['MemAvailable'])/mem['MemTotal']
    temps={}
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        name=(zone/'type').read_text().strip()
        if name in THERMAL:temps[name]=float((zone/'temp').read_text())/1000
    return ram,temps


def child_limits():
    parent=os.getppid()
    if ctypes.CDLL(None).prctl(1,signal.SIGKILL)!=0:os._exit(125)
    if os.getppid()!=parent or parent==1:os._exit(125)
    resource.setrlimit(resource.RLIMIT_CPU,(3,3))
    resource.setrlimit(resource.RLIMIT_AS,(128*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))


def terminate(child):
    if child is None:return
    if child.poll() is None:
        child.terminate()
        try:child.wait(timeout=.5)
        except subprocess.TimeoutExpired:child.kill();child.wait(timeout=.5)
    if child.poll() is None:raise RuntimeError('benchmark still alive')


def run_window(sample,start_child,seconds,clock=time.monotonic,sleep=time.sleep):
    """Fixed cadence; reject delay rather than silently widening the CPU window."""
    child=None;rows=[];start=clock()
    try:
        child=start_child() if start_child else None
        for index in range(seconds):
            target=start+index+1;sleep(max(0,target-clock()))
            if clock()-target>.1:raise TimeoutError('sampling delayed')
            rows.append(sample())
            if child is not None and child.poll() is not None:
                if child.returncode!=0:raise RuntimeError('benchmark failed')
                break
        if child is not None and child.poll() is None:raise TimeoutError('benchmark wall deadline')
        return rows
    finally:terminate(child)


def main():
    if len(sys.argv)!=2 or sys.argv[1]!='--approved-once':raise ValueError('explicit approved invocation required')
    for line in (ROOT/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1)
        if Path(name).name!=name or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise ValueError('package hash mismatch')
    resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024*1024,)*2)
    (ROOT/'ATTEMPT_USED').open('x').close()
    evidence=ROOT/'evidence';evidence.mkdir(mode=0o700)
    scratch=Path(tempfile.mkdtemp(prefix='atlas-snapshot-benchmark-'))
    result={'result':'FAIL','production_changed':False,'scratch':str(scratch)};rows=[]
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,fail_signal)
    try:
        initial=services()
        if any(v['ActiveState']!='active' or v['MainPID']=='0' for v in initial.values()):raise ValueError('protected service unavailable')
        result['camera']=verify_camera_off(lambda:fetch('/api/vision3d/summary'))
        previous=[ticks(),time.monotonic()]
        def sample():
            now=time.monotonic();current=ticks();elapsed=now-previous[1]
            if not .9<=elapsed<=1.1:raise TimeoutError('CPU interval invalid')
            cpu=cpu_delta(previous[0],current);previous[:]=[current,now]
            if cpu>75:raise ValueError('CPU guard '+str(cpu))
            ram,temps=resources();began=time.monotonic();status=fetch('/api/status')
            row=validate(status,cpu,ram,temps,time.monotonic()-began)
            row.update(mono=now,interval=elapsed,wrapper_cpu=time.process_time(),wrapper_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            rows.append(row)
            return row
        run_window(sample,None,3)
        def launch():
            env={'PATH':'/usr/bin:/bin','TMPDIR':str(scratch),'PYTHONDONTWRITEBYTECODE':'1'}
            output=(evidence/'benchmark.json').open('wb')
            try:
                return subprocess.Popen([sys.executable,'-I','-B','-c',
                    'import sys,runpy;root=sys.argv[1];sys.path.insert(0,root);sys.argv=[root+"/benchmark_safety_snapshot.py"];runpy.run_path(sys.argv[0],run_name="__main__")',str(ROOT)],
                    env=env,stdout=output,stderr=subprocess.STDOUT,preexec_fn=child_limits)
            finally:output.close()
        # Reset endpoint only BETWEEN phases, with fresh pre-launch safety check
        # already complete. Preserve the previous CPU sample evidence.
        previous[:]=[ticks(),time.monotonic()]
        start=len(rows);run_window(sample,launch,14);end=len(rows)
        previous[:]=[ticks(),time.monotonic()];run_window(sample,None,3)
        final=services()
        if final!=initial:raise ValueError('protected service identity changed')
        result.update(result='PASS',baseline_indices=[0,start],active_indices=[start,end],after_indices=[end,len(rows)],services_before=initial,services_after=final)
    except BaseException as exc:result['error']=str(exc)
    finally:
        shutil.rmtree(scratch)
        result['cleanup']='VERIFIED' if not scratch.exists() else 'FAILED'
        result['samples']=rows
        (evidence/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False))
        files=sorted(p for p in evidence.iterdir() if p.is_file())
        (evidence/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))
    print(json.dumps({'result':result['result'],'cleanup':result['cleanup'],'evidence':str(evidence)}))
    return 0 if result['result']=='PASS' else 1

if __name__=='__main__':sys.exit(main())

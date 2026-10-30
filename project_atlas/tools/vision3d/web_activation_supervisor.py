"""Control layer only; unchanged reviewed backend package. Explicit approval required.

Run under a user transient unit with RuntimeMaxSec=180, Restart=no and ExecStopPost
invoking --recover. Recovery is idempotent and never starts a service by itself.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from restart_policy import Policy,save
from existing_safety_snapshot import Consumer

LIVE=Path('/home/jetson/project_atlas')
REVIEW=Path('/home/jetson/project-atlas-migration/object-target-staged-7dba9bd/review')
EXPECTED='a586c2d22276ef4f7385387a79cadd581b2c7a52567d89a8754ee051b9c99e68'

def sample_deadline(snapshot):
    stamp=snapshot['cpu_started']
    if type(stamp) not in (int,float) or not math.isfinite(stamp):raise ValueError('invalid aggregate sample timestamp')
    return stamp+1.0

def interval_valid(before,after):
    elapsed=after['cpu_started']-before['cpu_started']
    return math.isfinite(elapsed) and .9<=elapsed<=1.1

def persist_cpu_row(stage,row):
    output=stage/'process-cpu.jsonl';encoded=(json.dumps(row,allow_nan=False)+'\n').encode()
    if (output.stat().st_size if output.exists() else 0)+len(encoded)>16*1024*1024:raise ValueError('CPU evidence quota exceeded')
    with output.open('ab') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())

def measure_cpu_interval(cpu,before,after,hz,stage):
    delta=cpu.differences(before,after,hz)
    if not interval_valid(before,after):
        # Preserve the rejected raw endpoint and delta before fail-closed abort.
        # The previous endpoint is in the baseline or preceding JSONL row.
        persist_cpu_row(stage,{'kind':'rejected_timing','before_cpu_started':before['cpu_started'],
                              'before_cpu':before['cpu'],'snapshot':after,'delta':delta})
        raise ValueError('CPU sample interval failed: '+str(delta['aggregate_interval_s']))
    return delta

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def verify_package():
    if sha(REVIEW/'DEPLOYMENT_SHA256SUMS')!=EXPECTED:raise ValueError('review manifest changed')
    for line in (REVIEW/'DEPLOYMENT_SHA256SUMS').read_text().splitlines():
        h,n=line.split('  ',1)
        if Path(n).is_absolute() or '..' in Path(n).parts or sha(REVIEW/n)!=h:raise ValueError('review file mismatch')
def policy(stage):return Policy(stage,'rover-status-web.service',Path('/run/user')/str(os.getuid())/'systemd/user')
def restore_files(stage):
    path=stage/'installation-plan.json'
    if not path.exists():return
    for f,item in json.loads(path.read_text()).items():
        dest=LIVE/f
        if Path(f).is_absolute() or '..' in Path(f).parts:raise ValueError('rollback path escape')
        original=item['original'];candidate=item['candidate']
        if not dest.exists():
            if original is not None:raise ValueError('original missing '+f)
            continue
        current=sha(dest)
        if original is not None and current==original:continue
        if dest.is_symlink() or current!=candidate:raise ValueError('concurrent change '+f)
        if original is None:dest.unlink()
        else:
            source=stage/'backup'/dest.name
            if sha(source)!=original:raise ValueError('rollback backup mismatch')
            temp=dest.with_name('.'+dest.name+'.'+stage.name+'.recovery.tmp')
            intent=stage/'recovery-write-intent.json'
            expected={'destination':str(dest),'temporary':str(temp),'sha256':original}
            if temp.exists() or temp.is_symlink():
                if not intent.exists() or json.loads(intent.read_text())!=expected or temp.is_symlink() or temp.stat().st_nlink!=1:raise ValueError('unowned recovery temporary file')
                temp.unlink()  # resume an interrupted write owned by this transaction
            save(intent,expected)
            with temp.open('xb') as out:out.write(source.read_bytes());out.flush();os.fsync(out.fileno())
            os.chmod(temp,0o644);os.replace(temp,dest)
            fd=os.open(dest.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def recover(stage):
    # Always executed by systemd after main exit/kill, not dependent on HTTP/observer.
    if not (stage/'restart-policy.json').exists():return
    p=policy(stage);s=p.load()
    if s['restored']:
        result=stage/'controller-result.json'
        if result.exists() and json.loads(result.read_text()).get('result')=='PASS':return
        if (stage/'recovery.json').exists():
            restore_files(stage);p.restore();return
        # Crash/failure after policy restoration but before final acceptance:
        # explicit stop suppresses Restart=always; never start again here.
        p.stop_and_quiesce();restore_files(stage)
        save(stage/'recovery.json',{'files':'restored','policy':'restored','web':'stopped'})
        return
    if not s['activation'] and p.prop('MainPID')==s['original_pid'] and p.prop('ActiveState')=='active':
        restore_files(stage);p.restore_untouched()
        save(stage/'recovery.json',{'files':'restored','policy':'restored','web':'original process preserved'})
        return
    p.stop_and_quiesce();restore_files(stage);p.restore()
    save(stage/'recovery.json',{'files':'restored','policy':'restored','web':'stopped','automatic_retry':False})

def run(stage):
    verify_package()
    if (stage/'CONTROL_ATTEMPT_USED').exists():raise ValueError('attempt already used')
    (stage/'CONTROL_ATTEMPT_USED').open('x').close()
    observer_path=Path('/run/user')/str(os.getuid())/'atlas-restart-safety/state.json'
    consumer=Consumer(observer_path,Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    consumer.check(time.monotonic())  # no warmup of missing/stale source
    # Inherit the verified web ROS environment only when explicitly launched by owner.
    if os.environ.get('ROS_DOMAIN_ID','0')!='0':raise ValueError('unexpected production safety domain')
    p=policy(stage);errors=[];stop=threading.Event();observer_ready=threading.Event();baseline_ready=threading.Event();last_resource=[None]
    cpu=load('bounded_cpu',Path(__file__).with_name('bounded_process_cpu.py'))
    sys.path.insert(0,str(REVIEW))
    installer=load('reviewed_installer',REVIEW/'install_object_target_once.py')
    installer.STAGE=stage;installer.PKG=REVIEW/'package'
    def safety():return consumer.check(time.monotonic())
    def independent_check():
        safety()
        if errors:raise ValueError('latched observation failure: '+str(errors[0]))
        if last_resource[0] is None or not 0<=time.monotonic()-last_resource[0]<=1.5:raise ValueError('resource monitor missing/stalled')
    def monitor():
        try:
            last=cpu.snapshot();save(stage/'cpu-baseline-counters.json',last);target=sample_deadline(last);baseline_ready.set()
            while not stop.wait(max(0,target-time.monotonic())):
                now=cpu.snapshot();delta=measure_cpu_interval(cpu,last,now,os.sysconf('SC_CLK_TCK'),stage)
                last=now;target=sample_deadline(now)
                mem={x.split(':')[0]:int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines()}
                temps={};required={'cpu-thermal','gpu-thermal','soc0-thermal','soc1-thermal','soc2-thermal','tj-thermal'}
                for z in Path('/sys/class/thermal').glob('thermal_zone*'):
                    k=(z/'type').read_text().strip()
                    if k in required:temps[k]=float((z/'temp').read_text())/1000
                if set(temps)!=required or any(t<=0 for t in temps.values()):raise ValueError('missing/invalid thermal zones: '+str(temps))
                resources=cpu.resource_check(delta['cpu_pct'],mem,{'thermal_zones_c':temps})
                row={'mono':time.monotonic(),'snapshot':now,'delta':delta,'resources':resources,'monitor_cpu_seconds':time.process_time()}
                try:row['safety']=safety()
                except Exception as exc:
                    if observer_ready.is_set():errors.append(str(exc))
                    row['safety_error']=str(exc)  # warmup is NOT safety admission
                if resources['failed']:errors.append('resource guard '+str(resources))
                last_resource[0]=time.monotonic()
                persist_cpu_row(stage,row)
        except BaseException as exc:errors.append(str(exc))
    thread=None
    try:
        thread=threading.Thread(target=monitor,daemon=True);thread.start()
        if not baseline_ready.wait(1):raise ValueError('initial process counters unavailable')
        observer_ready.set()
        deadline=time.monotonic()+2
        while last_resource[0] is None:
            safety()
            if errors or time.monotonic()>=deadline:
                raise ValueError('initial resource monitor unavailable: '+str(errors))
            time.sleep(.05)
        independent_check()
        for _ in range(150):time.sleep(.1);independent_check()
        installer.G.preflight();independent_check()
        # Single runtime policy override; effective no-restart policy verified.
        p.prepare()
        original_check=installer.check
        def check():
            independent_check();r=original_check();independent_check();return r
        installer.check=check
        def restart():
            independent_check()
            phase='rollback' if p.load()['activation'] else 'activation'
            p.restart(phase)
            independent_check()
        installer.restart=restart
        # Keep the independent observer/resources through HTTP outage; don't create
        # the older monitor which knows only aggregate CPU and web safety.
        installer.resource_monitor=lambda *args:None
        original_ready=installer.ready
        def ready(_errors,events,enforce=True):
            independent_check();value=original_ready(errors,events,enforce=True);independent_check();return value
        installer.ready=ready
        rc=installer.main()
        independent_check()
        if rc:raise ValueError('installation rejected; recovery required')
        p.restore_healthy();independent_check()
        save(stage/'controller-result.json',{'result':'PASS','inference':False,'restart_budget':p.load()})
    except BaseException as exc:
        save(stage/'controller-result.json',{'result':'FAIL','error':str(exc),'guard_failures':errors})
        raise
    finally:
        try:
            # Keep independent evidence alive through normal failure recovery.
            # SIGKILL uses ExecStopPost and leaves the restored web stopped.
            recover(stage)
        finally:
            stop.set()
            if thread:thread.join(3)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True);parser.add_argument('--recover',action='store_true');args=parser.parse_args();stage=Path(args.stage).resolve()
    if stage.parent!=Path('/home/jetson/project-atlas-migration') or not stage.name.startswith('web-activation-once-'):raise ValueError('invalid transaction directory')
    stage.mkdir(mode=0o700,exist_ok=True)
    with (stage/'controller.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.recover:recover(stage)
        else:run(stage)
if __name__=='__main__':
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt('deadline/interruption')))
    main()

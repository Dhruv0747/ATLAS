"""Approval-gated supervisor and independent HTTP/resource watcher.
Must run as user systemd service with independent ExecStopPost --cleanup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from restart_policy import save
from recovery_snapshot_runtime import Transaction
from recovery_snapshot_validation import Validation
from snapshot_benchmark_once import ticks,cpu_delta,resources,fetch,validate
from install_verification import verify_camera_off
from rejected_cpu_evidence import record_cpu_rejection

LIVE=Path('/home/jetson/project_atlas')
RUNTIME=Path('/run/user/1000/atlas-restart-safety')
HASHES={'scripts/atlas_sensor_recovery.py':'da83d138053a424d40fbff4a94532b864140953191260a32cc36042b5d51276a','tools/vision3d/existing_safety_snapshot.py':'e37cfd130c716f5bc014b91b6c7cd8c5ebdae85be916718cf07949d9f68f7c9c','tools/vision3d/restart_safety_observer.py':'a26b364f85df17e4fbbe05ff3174972b42180da3d0f44809cece967065dd47c1'}

def stopped(*_):raise KeyboardInterrupt('supervisor interrupted')

def watch(root):
    # Separate process: never waits for systemctl/recovery or reads producer safety.
    baseline=json.loads((root/'watcher-baseline.json').read_text())
    start=time.monotonic();last=baseline['ticks'];stamp=baseline['mono'];count=0
    try:
        while time.monotonic()-start<80:
            time.sleep(max(0,stamp+1-time.monotonic()))
            now=time.monotonic();current=ticks();interval=now-stamp
            if not .9<=interval<=1.1:raise ValueError('CPU interval')
            previous,last_stamp=last,stamp
            cpu=cpu_delta(last,current);last=current;stamp=now
            if cpu>75:
                record_cpu_rejection(root,previous,current,last_stamp,now,cpu)
                raise ValueError('CPU guard '+str(cpu))
            ram,temp=resources();began=time.monotonic();status=fetch('/api/status')
            row=validate(status,cpu,ram,temp,time.monotonic()-began)
            row.update(mono=time.monotonic(),safe=True,interval=interval,watcher_cpu=time.process_time())
            pid=subprocess.check_output(['systemctl','--user','show','atlas-sensor-recovery.service','-p','MainPID','--value'],text=True,timeout=.3).strip()
            row['recovery_pid']=pid
            if pid!='0':
                try:
                    raw=Path('/proc',pid,'stat').read_text();fields=raw[raw.rfind(')')+2:].split()
                    row['recovery_counters']={'user_ticks':int(fields[11]),'system_ticks':int(fields[12]),'start_ticks':int(fields[19]),'rss_pages':int(fields[21]),'hz':os.sysconf('SC_CLK_TCK'),'page_size':os.sysconf('SC_PAGE_SIZE')}
                except FileNotFoundError:row['recovery_counters']='process exited during sample'
            save(root/'health.json',row)
            with (root/'samples.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
            count+=1
            if count>80:raise ValueError('sample bound')
        raise TimeoutError('watcher lifetime')
    except BaseException as exc:
        save(root/'health.json',{'mono':time.monotonic(),'safe':False,'error':str(exc)})
        raise

def health(root):
    data=json.loads((root/'health.json').read_text())
    if data.get('safe') is not True or not 0<=time.monotonic()-data['mono']<=1.5:raise ValueError('independent watcher missing/stale/failed')
    return data

def original_files():
    for rel,h in HASHES.items():
        if hashlib.sha256((LIVE/rel).read_bytes()).hexdigest()!=h:raise ValueError('installed file drift '+rel)

def units():
    raw=subprocess.check_output(['systemctl','--user','show','atlas-*.service','rover-*.service','-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState'],text=True,timeout=3)
    return {v['Id']:v for block in raw.strip().split('\n\n') if (v:=dict(x.split('=',1) for x in block.splitlines() if '=' in x))}

def cleanup(root):
    Transaction(root).cleanup()
    # Only the owned runtime directory is removed, after recovery quiesces.
    intent=root/'runtime-owned.json'
    if intent.exists():
        data=json.loads(intent.read_text());directory=RUNTIME
        if str(directory)!=data['path'] or directory.is_symlink():raise ValueError('runtime ownership mismatch')
        if directory.exists():
            if directory.stat().st_ino!=data['inode']:raise ValueError('runtime directory replaced')
            for name in ('state.json','state.tmp'):
                path=directory/name
                if path.is_symlink():raise ValueError('unexpected runtime symlink')
                path.unlink(missing_ok=True)
            directory.rmdir()

def run(root):
    for line in (root/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1)
        if Path(name).name!=name or hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:raise ValueError('package hash drift')
    (root/'ATTEMPT_USED').open('x').close();original_files()
    before=units();save(root/'services-before.json',before)
    directory=RUNTIME
    if directory.exists():raise ValueError('runtime directory already exists')
    # Disable implicit user-level/global opt-in through either service environment.
    env=subprocess.check_output(['systemctl','--user','show','atlas-sensor-recovery.service','-p','Environment','--value'],text=True,timeout=3)
    if 'ATLAS_RESTART_SNAPSHOT' in env:raise ValueError('existing opt-in configuration')
    hardware=Path.home()/'.config/project-atlas/hardware.env'
    if hardware.exists() and any(x.strip().startswith('ATLAS_RESTART_SNAPSHOT=') for x in hardware.read_text().splitlines()):raise ValueError('EnvironmentFile precedence')
    verify_camera_off(lambda:fetch('/api/vision3d/summary'))
    # Fresh admission BEFORE watcher startup; first watcher CPU window includes
    # its Python initialization. No discarded startup CPU or new ROS participant.
    first=ticks();began=time.monotonic();time.sleep(1);current=ticks()
    if not .9<=time.monotonic()-began<=1.1:raise ValueError('preflight CPU interval')
    cpu=cpu_delta(first,current)
    if cpu>=75:raise ValueError('preflight CPU')
    ram,temps=resources();began=time.monotonic();status=fetch('/api/status')
    row=validate(status,cpu,ram,temps,time.monotonic()-began)
    if ram>=80:raise ValueError('preflight RAM')
    save(root/'preflight.json',row)
    save(root/'watcher-baseline.json',{'ticks':ticks(),'mono':time.monotonic()})
    watcher=subprocess.Popen([sys.executable,'-B',__file__,'--stage',str(root),'--watch'])
    tx=Transaction(root,check=lambda:health(root));result={'result':'FAIL'}
    try:
        deadline=time.monotonic()+2
        while not (root/'health.json').exists():
            if watcher.poll() is not None or time.monotonic()>deadline:raise ValueError('watcher startup')
            time.sleep(.05)
        for _ in range(100):health(root);time.sleep(.1)
        directory.mkdir(mode=0o700)
        save(root/'runtime-owned.json',{'path':str(directory),'inode':directory.stat().st_ino})
        tx.prepare();tx.restart('activation')
        boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        v=Validation(root/'validation-budget.json',directory/'state.json',boot)
        row=health(root);v.independent(time.monotonic(),row);v.reserve_restart('activation',time.monotonic())
        start=time.monotonic()
        while time.monotonic()-start<30:
            row=health(root);now=time.monotonic();v.independent(now,row);state=v.snapshot_check(now)
            save(root/'snapshot-validation.json',dict(state,mono=now))
            time.sleep(.1)
        if not v.ready or v.updates<10:raise ValueError('insufficient real updates')
        tx.remove_optin();tx.restart('rollback')
        for _ in range(30):health(root);time.sleep(.1)
        after=units();save(root/'services-after.json',after)
        if {k:v for k,v in before.items() if k!=tx.unit}!={k:v for k,v in after.items() if k!=tx.unit}:raise ValueError('protected service change')
        pid=tx.prop('MainPID')
        if b'ATLAS_RESTART_SNAPSHOT=1' in Path('/proc',pid,'environ').read_bytes().split(b'\0'):raise ValueError('producer still enabled')
        original_files();health(root);tx.finish()
        result.update(result='PASS',output='DISABLED',updates=v.updates)
    except BaseException as exc:result['error']=str(exc);raise
    finally:
        try:cleanup(root)
        finally:
            watcher.terminate()
            try:watcher.wait(timeout=1)
            except subprocess.TimeoutExpired:watcher.kill();watcher.wait(timeout=1)
            save(root/'result.json',result)

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--cleanup',action='store_true');p.add_argument('--watch',action='store_true');a=p.parse_args()
    root=Path(a.stage).resolve()
    if root.parent!=Path('/home/jetson/project-atlas-migration') or root.name!='snapshot-runtime-once-20261031':raise ValueError('invalid stage')
    if os.getuid()!=1000:raise ValueError('jetson user only')
    if a.cleanup:cleanup(root)
    elif a.watch:watch(root)
    else:run(root)

if __name__=='__main__':
    signal.signal(signal.SIGTERM,stopped);signal.signal(signal.SIGINT,stopped)
    main()

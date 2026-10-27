#!/usr/bin/env python3
"""Explicit PC-only native fake-unit test. Never contacts Jetson, ROS or serial."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--allow-pc-fake-units', action='store_true')
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    if not args.allow_pc_fake_units or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Requires explicit PC WSL fake-unit authorization; never run on Jetson')
    scriptdir = Path(__file__).resolve().parents[1] / 'scripts'
    sys.path.insert(0, str(scriptdir))
    from atlas_b1_interlock import Interlock, Denied
    output = Path(args.output); output.mkdir(parents=True, exist_ok=False)
    tmp = Path(tempfile.mkdtemp(prefix='atlas-b1-native-'))
    unitdir = Path(os.environ['XDG_RUNTIME_DIR']) / 'systemd/user'
    unitdir.mkdir(parents=True, exist_ok=True)
    prefix = 'atlas-b1-fake-' + uuid.uuid4().hex[:10]
    base, other = prefix+'-base.service', prefix+'-other.service'
    names = {base, other}
    events = []
    def ctl(action, name=None, check=True, extra=()):
        if name is not None and name not in names:
            raise RuntimeError('non-fake unit forbidden')
        if action not in {'start','stop','show','reset-failed','daemon-reload','list-jobs'}:
            raise RuntimeError('operation forbidden')
        cmd = ['/usr/bin/systemctl','--user',action] + ([name] if name else []) + list(extra)
        return subprocess.run(cmd, check=check, capture_output=True, text=True, timeout=8)
    def state(name):
        return dict(line.split('=',1) for line in ctl('show',name,extra=('-p','ActiveState','-p','MainPID','-p','NRestarts','-p','Result')).stdout.splitlines())
    def wait(pred, limit=5):
        until=time.monotonic()+limit
        while time.monotonic()<until:
            if pred(): return
            time.sleep(.05)
        raise AssertionError('native transition timeout')
    def count():
        p=tmp/'starts'
        return len(p.read_text().splitlines()) if p.exists() else 0
    safe={'ros':{'control_policy':{'age':0,'value':{'stop_latched':True,'manual_only':True,'commission_armed':False,'source':'STOPPED'}},'cmd_vel':{'age':0,'value':{'lin':0,'ang':0}}}}
    gate=Interlock(tmp/'state'); gate.initialize()
    helper=tmp/'helper.py'
    helper.write_text('import sys,time,os,json\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(scriptdir))+')\nfrom atlas_b1_interlock import Interlock\ng=Interlock('+repr(str(tmp/'state'))+')\nmode=sys.argv[1]\nif mode=="gate":\n try: ok=g.start_gate()\n except Exception: ok=False\n sys.exit(0 if ok else 1)\nif mode=="watch":\n while True:\n  g.heartbeat(sys.argv[2],'+repr(safe)+')\n  time.sleep(.15)\nif mode=="base":\n with open('+repr(str(tmp/'starts'))+',"a") as f: f.write(str(os.getpid())+"\\n")\n while True:\n  if Path('+repr(str(tmp/'fail'))+').exists(): sys.exit(42)\n  time.sleep(.02)\nif mode=="other":\n while True: time.sleep(.1)\n')
    (unitdir/base).write_text('[Unit]\nStartLimitIntervalSec=0\n[Service]\nType=simple\nExecStartPre=/bin/sleep 0.3\nExecCondition=/usr/bin/python3 '+str(helper)+' gate\nExecStart=/usr/bin/python3 '+str(helper)+' base\nRestart=on-failure\nRestartSec=0.1\nTimeoutStartSec=3\nTimeoutStopSec=2\n')
    (unitdir/other).write_text('[Service]\nType=simple\nExecStart=/usr/bin/python3 '+str(helper)+' other\nRestart=on-failure\nTimeoutStopSec=2\n')
    watcher=None
    def startwatch(session):
        p=subprocess.Popen(['/usr/bin/python3',str(helper),'watch',session],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        wait(lambda: gate.load().get('monitor_seen') is True)
        return p
    def stopwatch(p):
        if p and p.poll() is None: p.kill(); p.wait(timeout=3)
    try:
        ctl('daemon-reload'); ctl('start',other); ctl('start',base,extra=('--no-block',))
        wait(lambda: state(base)['ActiveState']=='activating')
        try:
            gate.arm(safe,lambda:base not in ctl('list-jobs',extra=('--no-legend','--no-pager')).stdout)
        except Denied: pass
        else: raise AssertionError('in-flight systemd start admitted')
        events.append({'check':'native in-flight start job rejects maintenance admission'})
        wait(lambda: count()==1)
        before_other=state(other)
        session=gate.arm(safe,lambda: base not in ctl('list-jobs',extra=('--no-legend','--no-pager')).stdout)
        watcher=startwatch(session)
        # Simulate unexpected base failure after maintenance entry, rather than merely stop it.
        (tmp/'fail').touch()
        wait(lambda: state(base)['ActiveState']=='inactive')
        assert count()==1
        events.append({'check':'Restart=on-failure denied by ExecCondition','state':state(base),'exec_count':count()})
        (tmp/'fail').unlink()
        for _ in range(2): ctl('start',base)
        assert count()==1 and state(other)['MainPID']==before_other['MainPID']
        events.append({'check':'repeated external starts denied; unrelated service PID unchanged'})
        gate.begin_read(session)
        with gate.reader(session):
            try: gate.resume(session,safe,True,lambda:True)
            except BlockingIOError: pass
            else: raise AssertionError('restoration during reader allowed')
        assert gate.load()['phase']=='ABORTED'
        stopwatch(watcher); watcher=None
        time.sleep(2.15)
        try: gate.heartbeat(session,safe)
        except Denied: pass
        else: raise AssertionError('crashed supervisor lease revived')
        ctl('start',base); assert count()==1
        events.append({'check':'reader collision, abort, supervisor SIGKILL/expiry retain hold'})
        gate.reconcile(session,safe,True,lambda:True)
        watcher=startwatch(session)
        gate.resume(session,safe,True,lambda:True)
        ctl('start',base); wait(lambda: count()==2)
        assert gate.load()['phase']=='VERIFYING'
        # Failure before verified restoration must not cause a second launch.
        (tmp/'fail').touch(); wait(lambda:state(base)['ActiveState']=='inactive')
        assert count()==2
        events.append({'check':'one restoration launch consumed; failure retry denied','state':state(base)})
        (tmp/'fail').unlink(); stopwatch(watcher); watcher=None
        gate.reconcile(session,safe,True,lambda:True); watcher=startwatch(session)
        gate.resume(session,safe,True,lambda:True); ctl('start',base); wait(lambda:count()==3)
        gate.release(session,safe,lambda:state(base)['ActiveState']=='active',True)
        stopwatch(watcher); watcher=None
        (tmp/'fail').touch(); wait(lambda:count()>=4); (tmp/'fail').unlink()
        wait(lambda:state(base)['ActiveState']=='active')
        events.append({'check':'explicit restoration to IDLE restores normal restart policy','exec_count':count()})
        # Missing/corrupt state denies execution. Independent fake-only rollback removes test gate.
        ctl('stop',base)
        (tmp/'state/state.json').write_text('{invalid')
        n=count(); ctl('start',base); assert count()==n
        original=(unitdir/base).read_bytes()
        (unitdir/base).write_text('[Service]\nType=simple\nExecStart=/usr/bin/python3 '+str(helper)+' base\nTimeoutStopSec=2\n')
        ctl('daemon-reload'); ctl('start',base); wait(lambda:count()==n+1)
        events.append({'check':'corrupt-state denial and independent fake-unit rollback recovery'})
        assert state(other)['MainPID']==before_other['MainPID']
        result={'result':'PASS','systemd':subprocess.check_output(['/usr/bin/systemctl','--version'],text=True).splitlines()[0], 'checks':events,'production_units_touched':False,'hardware_accessed':False}
    except BaseException as exc:
        result={'result':'FAIL','error':repr(exc),'checks':events,'production_units_touched':False}
        raise
    finally:
        stopwatch(watcher)
        for name in names:
            ctl('stop',name,check=False)
            ctl('reset-failed',name,check=False)
            (unitdir/name).unlink(missing_ok=True)
        ctl('daemon-reload')
        result['cleanup']='fake units stopped and definitions removed'
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        # Retain only local fake test files for failure inspection; no recordings.
        print(json.dumps(result,indent=2))

if __name__=='__main__': main()

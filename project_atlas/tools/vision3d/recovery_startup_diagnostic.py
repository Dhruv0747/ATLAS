"""Separately approved original-Recovery start with passive CPU attribution.
No operations on import. Run ONLY under reviewed systemd unit with ExecStopPost.
"""
import hashlib
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from restart_policy import save
from recovery_snapshot_runtime import Transaction
import recovery_attribution_trial as passive
import startup_cpu_attribution as counters

ROOT=Path(__file__).resolve().parent
LIVE=Path('/home/jetson/project_atlas/scripts/atlas_sensor_recovery.py')
ORIGINAL=Path('/home/jetson/project-atlas-migration/snapshot-install-b2519d5/original.py')
OLD='5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a'
POLICY='[Service]\nRestart=no\n'

class DiagnosticTransaction(Transaction):
    def prepare(self):
        self.check()
        if self.state.exists() or self.override.exists():raise ValueError('used transaction/policy conflict')
        if self.prop('MainPID')!='0' or self.prop('ActiveState') not in ('inactive','failed') or self.prop('Job') not in ('','0'):raise ValueError('Recovery not stopped/quiescent')
        original=self.prop('Restart')
        if original!='always':raise ValueError('original policy drift')
        save(self.state,{'unit':self.unit,'original_restart':original,'pid':'0','activation':False,'rollback':False,'restored':False})
        self.override.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.override.with_suffix('.tmp')
        with temporary.open('x') as f:f.write(POLICY);f.flush();os.fsync(f.fileno())
        os.replace(temporary,self.override);self.command('daemon-reload')
        if self.prop('Restart')!='no':raise ValueError('policy not bounded')
    def identify(self,pid):
        if pid=='0':return
        try:value=counters.stat(Path('/proc',pid,'stat').read_text())
        except FileNotFoundError:return
        identity={'pid':pid,'start_ticks':value['start_ticks'],'mono':time.monotonic()}
        path=self.root/'target.json'
        if path.exists():
            old=json.loads(path.read_text())
            if (old['pid'],old['start_ticks'])!=(pid,value['start_ticks']):raise ValueError('unexpected Recovery PID change')
        else:save(path,identity)
    def start_once(self):
        self.check();state=self.load()
        if state['activation'] or state['restored'] or self.prop('Restart')!='no' or self.prop('MainPID')!='0' or self.prop('Job') not in ('','0'):raise ValueError('start budget/policy')
        state['activation']=True;save(self.state,state)
        save(self.root/'start-intent.json',{'mono':time.monotonic(),'wall':time.time(),'budget':1})
        self.command('--no-block','start',self.unit)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            self.check();pid=self.prop('MainPID');self.identify(pid)
            active=self.prop('ActiveState')
            if active=='failed':raise ValueError('Recovery failed')
            if active=='active' and pid!='0' and self.prop('Job') in ('','0'):return pid
            time.sleep(.05)
        raise TimeoutError('Recovery start deadline')
    def finish(self):
        self.check()
        if self.prop('ActiveState')!='active' or self.prop('NRestarts')!='0' or self.override.read_text()!=POLICY:raise ValueError('finish health/policy')
        self.override.unlink();self.command('daemon-reload');self.check()
        if self.prop('Restart')!='always' or self.prop('ActiveState')!='active' or self.prop('NRestarts')!='0':raise ValueError('policy restore failed')
        state=self.load();state['restored']=True;save(self.state,state)

def target_groups(root,groups,proc=Path('/proc')):
    """Refresh only target membership; all PID snapshots independently retain birth ticks."""
    path=root/'target.json'
    if not path.exists():return groups,{'state':'PID_NOT_YET_OBSERVED'}
    identity=json.loads(path.read_text());pid=identity['pid']
    try:
        first=counters.stat((proc/pid/'stat').read_text())
        if first['start_ticks']!=identity['start_ticks']:raise ValueError('target PID reused')
        membership=(proc/pid/'cgroup').read_text()
        second=counters.stat((proc/pid/'stat').read_text())
        if second['start_ticks']!=first['start_ticks']:raise ValueError('PID changed during membership read')
    except FileNotFoundError:return groups,dict(identity,state='TARGET_EXITED')
    for line in membership.splitlines():
        _,controllers,value=line.split(':',2)
        if controllers=='' or 'cpuacct' in controllers.split(','):
            # Reuse mount resolution; no guessed service path or zero baseline.
            selected,_=passive.discover_groups({'atlas-sensor-recovery.service':{'ControlGroup':value}},proc/'self/mountinfo')
            return [x for x in groups if x[0]!='atlas-sensor-recovery.service']+selected,dict(identity,state='MEMBERSHIP_OBSERVED',path=value)
    return groups,dict(identity,state='CPU_MEMBERSHIP_UNAVAILABLE')

def observe(root):
    evidence=root/'evidence';old=json.loads((evidence/'baseline.json').read_text())
    groups=json.loads((evidence/'groups.json').read_text())
    try:
        for index in range(1,46):
            time.sleep(max(0,old['mono']+1-time.monotonic()))
            # Resolve lazily INSIDE collection; prior baseline remains untouched.
            def collect(**_):
                nonlocal groups
                groups,target=target_groups(root,groups)
                data=counters.snapshot(groups=groups,priority_pids=[target['pid']] if target.get('pid') else ());data['target']=target
                return data
            def safety(current,previous):
                status=passive.check(current,previous)
                if current['target']['state']=='TARGET_EXITED':raise ValueError('tracked Recovery exited')
                return status
            old=passive.sample(evidence,index,old,groups,collect=collect,safety=safety)
        raise TimeoutError('observer lifetime')
    except BaseException as exc:
        save(evidence/'health.json',{'safe':False,'mono':time.monotonic(),'error':str(exc)})
        raise

def health(root,child):
    if child.poll() is not None:raise ValueError('independent observer exited')
    row=json.loads((root/'evidence'/'health.json').read_text())
    if row.get('safe') is not True or not 0<=time.monotonic()-row['mono']<=1.8:raise ValueError('independent observer unsafe/stale')
    return row

def verify_original():
    for path in (LIVE,ORIGINAL):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=OLD:raise ValueError('original hash drift '+str(path))
    if Path('/run/user/1000/atlas-restart-safety').exists():raise ValueError('snapshot output exists')
    env=subprocess.check_output(['systemctl','--user','show','atlas-sensor-recovery.service','-p','Environment','--value'],text=True,timeout=2)
    if 'ATLAS_RESTART_SNAPSHOT' in env:raise ValueError('snapshot environment present')
    config=Path.home()/'.config/project-atlas/hardware.env'
    if config.exists() and any(x.strip().startswith('ATLAS_RESTART_SNAPSHOT=') for x in config.read_text().splitlines()):raise ValueError('snapshot config present')

def run(root):
    # External package hash verification is mandatory; internal manifest exhaustive.
    expected={'recovery_startup_diagnostic.py','recovery_snapshot_runtime.py','recovery_attribution_trial.py','startup_cpu_attribution.py','snapshot_benchmark_once.py','stationary_gate.py','install_verification.py','restart_policy.py','atlas-recovery-startup-diagnostic.service'}
    lines=(root/'SHA256SUMS').read_text().splitlines()
    if len(lines)!=len(expected) or {x.split('  ',1)[1] for x in lines}!=expected:raise ValueError('manifest contents')
    for line in lines:
        digest,name=line.split('  ',1)
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('package drift')
    (root/'ATTEMPT_USED').open('x').close();verify_original()
    evidence=root/'evidence';evidence.mkdir(mode=0o700)
    before=passive.units();save(root/'services-before.json',before)
    # Preserve config bytes for manual audit; this transaction never edits them.
    config=subprocess.check_output(['systemctl','--user','cat','atlas-sensor-recovery.service'],text=True,timeout=2)
    (root/'original-unit.txt').write_text(config)
    passive.verify_camera_off(lambda:passive.fetch('/api/vision3d/summary'))
    groups,gaps=passive.discover_groups(before);save(evidence/'groups.json',groups);save(evidence/'group-gaps.json',gaps)
    old=counters.snapshot(groups=groups);counters.persist(evidence,0,{'snapshot':old})
    for i in range(60,63):
        time.sleep(max(0,old['mono']+1-time.monotonic()));old=passive.sample(evidence,i,old,groups)
    last=json.loads((evidence/'062.json').read_text())
    if last['safety']['cpu']>=75 or last['safety']['ram']>=80:raise ValueError('strict admission')
    save(evidence/'baseline.json',old);(evidence/'health.json').unlink()
    child=subprocess.Popen([sys.executable,'-B',__file__,'--watch'])
    tx=DiagnosticTransaction(root,check=lambda:health(root,child));result={'result':'FAIL','original_hash':OLD}
    try:
        deadline=time.monotonic()+1.8
        while not (evidence/'health.json').exists():
            if child.poll() is not None or time.monotonic()>deadline:raise TimeoutError('observer startup')
            time.sleep(.02)
        # Three complete observed windows before start; no counter reset afterward.
        while health(root,child)['index']<3:time.sleep(.02)
        tx.prepare();pid=tx.start_once()
        end=time.monotonic()+20
        while time.monotonic()<end:health(root,child);time.sleep(.05)
        tx.identify(tx.prop('MainPID'))
        since=datetime.datetime.fromtimestamp(json.loads((root/'start-intent.json').read_text())['wall']).strftime('%Y-%m-%d %H:%M:%S')
        journal=subprocess.check_output(['journalctl','--user','--boot=0','--since',since,'_PID='+pid,'--no-pager','-o','cat','-n','80'],text=True,timeout=2)
        (root/'recovery-startup.txt').write_text(journal)
        if 'READY: full bounded fault recovery armed' not in journal:raise ValueError('READY absent')
        if b'ATLAS_RESTART_SNAPSHOT=1' in Path('/proc',pid,'environ').read_bytes().split(b'\0'):raise ValueError('snapshot enabled')
        verify_original();passive.verify_camera_off(lambda:passive.fetch('/api/vision3d/summary'))
        # Read service identity without passive.units()'s intentional stopped check.
        raw=subprocess.check_output(['systemctl','--user','show','atlas-*.service','rover-*.service','-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState','-p','ControlGroup'],text=True,timeout=2)
        after={v['Id']:v for b in raw.strip().split('\n\n') if (v:=dict(x.split('=',1) for x in b.splitlines() if '=' in x))}
        save(root/'services-after.json',after)
        if {k:v for k,v in before.items() if k!=tx.unit}!={k:v for k,v in after.items() if k!=tx.unit}:raise ValueError('protected service changed')
        tx.finish();result.update(result='PASS',pid=pid,policy='RESTORED',producer='DISABLED')
    except BaseException as exc:result['error']=str(exc);raise
    finally:
        try:tx.cleanup()
        finally:
            # Do not kill observer before failed endpoint has had bounded time to flush.
            if child.poll() is None and result['result']!='PASS':
                try:child.wait(timeout=.3)
                except subprocess.TimeoutExpired:pass
            passive.terminate(child);save(root/'result.json',result)

if __name__=='__main__':
    signal.signal(signal.SIGTERM,passive.interrupted);signal.signal(signal.SIGINT,passive.interrupted)
    if len(sys.argv)>1 and sys.argv[1]=='--cleanup':DiagnosticTransaction(ROOT).cleanup()
    elif len(sys.argv)>1 and sys.argv[1]=='--watch':observe(ROOT)
    elif len(sys.argv)>1 and sys.argv[1]=='--approved-once':run(ROOT)
    else:raise SystemExit('separate approval and reviewed systemd unit required')

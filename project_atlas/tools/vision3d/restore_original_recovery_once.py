"""One separately approved ORIGINAL recovery restoration; no producer enablement."""
import hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
from restart_policy import save
from recovery_snapshot_runtime import Transaction
from recovery_snapshot_supervisor import health,watch,units
from snapshot_benchmark_once import ticks,cpu_delta,resources,fetch,validate

ROOT=Path(__file__).resolve().parent
LIVE=Path('/home/jetson/project_atlas/scripts/atlas_sensor_recovery.py')
ORIGINAL=Path('/home/jetson/project-atlas-migration/snapshot-install-b2519d5/original.py')
OLD='5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a'
CANDIDATE='da83d138053a424d40fbff4a94532b864140953191260a32cc36042b5d51276a'
TEXT='[Service]\nRestart=no\n'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def prepare(tx):
    tx.check()
    if tx.state.exists() or tx.override.exists():raise ValueError('already used/policy conflict')
    if tx.prop('MainPID')!='0' or tx.prop('ActiveState') not in ('failed','inactive') or tx.prop('Job') not in ('','0'):raise ValueError('recovery not stopped')
    state={'unit':tx.unit,'original_restart':tx.prop('Restart'),'pid':'0','activation':False,'rollback':False,'restored':False}
    if state['original_restart']!='always':raise ValueError('original restart policy drift')
    save(tx.state,state);tx.override.parent.mkdir(parents=True,exist_ok=True)
    temp=tx.override.with_suffix('.tmp')
    with temp.open('x') as f:f.write(TEXT);f.flush();os.fsync(f.fileno())
    os.replace(temp,tx.override)
    tx.command('daemon-reload')
    if tx.prop('Restart')!='no':raise ValueError('unbounded policy')

def run():
    for line in (ROOT/'SHA256SUMS').read_text().splitlines():
        h,n=line.split('  ',1)
        if Path(n).name!=n or sha(ROOT/n)!=h:raise ValueError('package hash')
    (ROOT/'ATTEMPT_USED').open('x').close()
    if sha(ORIGINAL)!=OLD or sha(LIVE)!=CANDIDATE:raise ValueError('original/candidate hash mismatch')
    if Path('/run/user/1000/atlas-restart-safety').exists():raise ValueError('snapshot runtime present')
    before=units();save(ROOT/'services-before.json',before)
    env=subprocess.check_output(['systemctl','--user','show','atlas-sensor-recovery.service','-p','Environment','--value'],text=True,timeout=3)
    if 'ATLAS_RESTART_SNAPSHOT' in env:raise ValueError('producer environment present')
    hardware=Path.home()/'.config/project-atlas/hardware.env'
    if hardware.exists() and any(x.strip().startswith('ATLAS_RESTART_SNAPSHOT=') for x in hardware.read_text().splitlines()):raise ValueError('producer environment file assignment')
    first=ticks();time.sleep(1);current=ticks();cpu=cpu_delta(first,current);ram,temps=resources();start=time.monotonic();status=fetch('/api/status')
    row=validate(status,cpu,ram,temps,time.monotonic()-start)
    if cpu>=75 or ram>=80:raise ValueError('preflight admission')
    save(ROOT/'preflight.json',row)
    save(ROOT/'watcher-baseline.json',{'ticks':ticks(),'mono':time.monotonic()})
    watcher=subprocess.Popen([sys.executable,'-B',__file__,'--watch'])
    tx=Transaction(ROOT,check=lambda:health(ROOT));result={'result':'FAIL'}
    try:
        deadline=time.monotonic()+2
        while not (ROOT/'health.json').exists():
            if watcher.poll() is not None or time.monotonic()>deadline:raise ValueError('watcher failed')
            time.sleep(.05)
        for _ in range(100):health(ROOT);time.sleep(.1)
        prepare(tx)
        # Exact original source, atomic replace; preserve installed candidate backup.
        save(ROOT/'file-intent.json',{'original':OLD,'candidate':CANDIDATE})
        (ROOT/'candidate-backup.py').write_bytes(LIVE.read_bytes())
        if sha(ROOT/'candidate-backup.py')!=CANDIDATE:raise ValueError('candidate backup')
        temp=LIVE.with_name('.atlas_sensor_recovery.original-restore.tmp')
        with temp.open('xb') as f:f.write(ORIGINAL.read_bytes());f.flush();os.fsync(f.fileno())
        os.chmod(temp,0o644);os.replace(temp,LIVE)
        if sha(LIVE)!=OLD:raise ValueError('original restore mismatch')
        tx.restart('activation')  # One start from STOPPED, never a second attempt.
        for _ in range(200):health(ROOT);time.sleep(.1)
        after=units();save(ROOT/'services-after.json',after)
        if {k:v for k,v in before.items() if k!=tx.unit}!={k:v for k,v in after.items() if k!=tx.unit}:raise ValueError('protected services changed')
        if tx.prop('ActiveState')!='active' or tx.prop('NRestarts')!='0':raise ValueError('recovery not healthy')
        pid=tx.prop('MainPID')
        journal=subprocess.check_output(['journalctl','--user','_PID='+pid,'--no-pager','-o','cat','-n','50'],text=True,timeout=2)
        (ROOT/'recovery-startup.txt').write_text(journal)
        if 'READY: full bounded fault recovery armed' not in journal:raise ValueError('recovery readiness not confirmed')
        if b'ATLAS_RESTART_SNAPSHOT=1' in Path('/proc',pid,'environ').read_bytes().split(b'\0'):raise ValueError('producer unexpectedly enabled')
        if tx.override.read_text()!=TEXT:raise ValueError('override ownership')
        tx.override.unlink();tx.command('daemon-reload');health(ROOT)
        if tx.prop('Restart')!='always' or sha(LIVE)!=OLD:raise ValueError('restoration verification')
        state=tx.load();state['restored']=True;save(tx.state,state)
        result.update(result='PASS',pid=pid,original_hash=sha(LIVE),producer='DISABLED')
    except BaseException as exc:result['error']=str(exc);raise
    finally:
        try:tx.cleanup()
        finally:
            watcher.terminate()
            try:watcher.wait(timeout=1)
            except subprocess.TimeoutExpired:watcher.kill();watcher.wait(timeout=1)
            save(ROOT/'result.json',result)

if __name__=='__main__':
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt('terminated')))
    if len(sys.argv)>1 and sys.argv[1]=='--cleanup':Transaction(ROOT).cleanup()
    elif len(sys.argv)>1 and sys.argv[1]=='--watch':watch(ROOT)
    else:run()

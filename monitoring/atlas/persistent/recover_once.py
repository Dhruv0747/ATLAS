#!/usr/bin/env python3
"""One approved monitoring rearm; reuses guard/sampler, never installs runtime code.

Run only from a root-owned reviewed package. systemd owns timeout and cleanup;
there is no shell retry, ROS participant, guard bypass or second start attempt.
"""
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import queue
import signal
import stat
import subprocess
import sys
import threading
import time

BASE = Path(__file__).resolve().parent
E = Path('/var/lib/atlas-monitoring-recovery-20261031')
GUARD = Path('/usr/local/libexec/atlas-monitoring-guard.py')
GUARD_SHA = '27d4cacae47044a1675cf911aad60a69fc78dd5b85de14bdb6d5480288a560e1'
SAMPLER_SHA = 'a25ff2d8c6a516357d61f4a1d70fadf98b36178b9e547d25d1643b937bdd8969'
EXPECTED_FAULT = '3715b150b880ed06d9e21f25006b81a699693328bb77a80155cf148dcdb1ae97'
EXPECTED_STATE = {
    'FAULT.json': EXPECTED_FAULT,
    'observer-active.json': '574d708ac320bbdce4d5d5c55dfa19158987790b6ccddf6fa982f1edd2d2c52a',
    'firewall-owned.json': '9f1d631e89ac334313bc3df77f868698574a8b979cd63efb54a8fde55459a8a3',
    'last-health.json': '2c4e1c31cfe70c4fed2935ca0e3b514cb808f3c8903f9d9099e353d9e0900a02',
    'operations.lock': hashlib.sha256(b'').hexdigest(),
}
NAMES = tuple('atlas-monitoring-'+n+'.service' for n in ('firewall','watchdog','exporter'))
TX = 'atlas-monitoring-recovery-once-20261031'
EXPIRY = TX+'-expiry'
DROP_NAME = '90-atlas-recovery-once.conf'
DROP_BYTES = b'[Service]\nRestart=no\n'
G = A = None
previous = counts = None
protected = False
PACKAGE_FILES = {'recover_once.py','guard.py','activate_timestamp_retry_once.py',
                 'atlas-monitor.nft','atlas-monitoring-firewall.service',
                 'atlas-monitoring-watchdog.service','atlas-monitoring-exporter.service.in'}


def require(ok, reason):
    if not ok: raise RuntimeError(reason)


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def sync_dir(path):
    fd = os.open(path, os.O_DIRECTORY | os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def write(path, value):
    data = value if isinstance(value, bytes) else json.dumps(value, allow_nan=False, sort_keys=True).encode()
    require(len(data) <= 1048576, 'evidence size limit')
    temp = path.with_name(path.name+'.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(data); out.flush(); os.fsync(out.fileno())
    os.replace(temp, path); sync_dir(path.parent)
    require(path.read_bytes() == data, 'written evidence mismatch')


def run(*args):
    out = subprocess.run(args, check=True, capture_output=True, timeout=3).stdout
    require(len(out) <= 1048576, 'command output oversized')
    return out.decode()


def props(unit):
    return dict(line.split('=',1) for line in run('systemctl','show',unit,
        '-p','ActiveState','-p','SubState','-p','MainPID','-p','NRestarts',
        '-p','Restart','-p','UnitFileState','-p','FragmentPath','-p','DropInPaths').splitlines())


def drop(unit): return Path('/run/systemd/system')/(unit+'.d')/DROP_NAME


def state_hashes():
    paths = list(G.STATE.iterdir())
    require(len(paths) <= 64, 'too many state files')
    total = 0; result = {}
    for p in paths:
        info = p.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not info.st_mode & 0o022, 'untrusted state file')
        total += info.st_size
        require(total <= 1048576, 'state size limit')
        result[p.name] = digest(p)
    return result


def archive_state():
    hashes = state_hashes()
    expected = dict(EXPECTED_STATE)
    if 'evidence.lock' in hashes: expected['evidence.lock'] = hashlib.sha256(b'').hexdigest()
    require(hashes == expected and hashes.get('FAULT.json') == EXPECTED_FAULT, 'retained evidence changed')
    for p in G.STATE.glob('*.json'):
        value = json.loads(p.read_text())
        require(isinstance(value, dict), 'invalid retained evidence')
    dest = E/'original-state'; dest.mkdir(mode=0o700)
    metadata = {}
    for name in hashes:
        info=(G.STATE/name).stat()
        metadata[name] = dict(uid=info.st_uid,gid=info.st_gid,mode=stat.S_IMODE(info.st_mode),
                              mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns)
        write(dest/name, (G.STATE/name).read_bytes())
        os.chmod(dest/name, stat.S_IMODE(info.st_mode))
    sync_dir(dest)
    require(state_hashes() == hashes, 'state changed during archive')
    write(E/'state-metadata.json',metadata)
    write(E/'state-manifest.json', hashes)
    verify_archive()


def verify_archive():
    hashes = json.loads((E/'state-manifest.json').read_text())
    require(set(hashes) == {p.name for p in (E/'original-state').iterdir()}, 'archive members changed')
    for name, sha in hashes.items():
        require(Path(name).name == name and not (E/'original-state'/name).is_symlink(), 'invalid archive name')
        require(digest(E/'original-state'/name) == sha, 'archive checksum mismatch')
    require(hashes.get('FAULT.json') == EXPECTED_FAULT, 'archive fault mismatch')
    return hashes


def rearm():
    require(not (E/'reset-intent.json').exists(), 'attempt already consumed')
    hashes = verify_archive()
    require(state_hashes() == hashes, 'state changed before reset')
    write(E/'reset-intent.json', {'time':time.time(), 'original_cause':'UNKNOWN'})
    for name in ('FAULT.json','observer-active.json'): (G.STATE/name).unlink()
    sync_dir(G.STATE)


def restore_latch():
    verify_archive()
    with evidence_lock():
        if not os.path.lexists(G.STATE/'FAULT.json'):
            write(G.STATE/'FAULT.json', (E/'original-state'/'FAULT.json').read_bytes())
    # Never replace a new (even corrupt) rejection with the old reason.
    require(os.path.lexists(G.STATE/'FAULT.json'), 'failure latch absent')


@contextlib.contextmanager
def evidence_lock():
    fd=os.open(G.STATE/'evidence.lock',os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def load():
    global G, A
    for p in (BASE, *BASE.parents):
        require(p.stat().st_uid == 0 and not p.stat().st_mode & 0o022, 'package ancestor writable')
    require(' ' not in str(BASE), 'systemd package path must not contain spaces')
    manifest = dict(line.split('  ',1)[::-1] for line in (BASE/'RECOVERY_SHA256SUMS').read_text().splitlines())
    require(set(manifest)==PACKAGE_FILES, 'package manifest members differ')
    for name, sha in manifest.items():
        path=BASE/name; info=path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode & 0o022,
                'untrusted package member')
        require(digest(path)==sha, 'package checksum mismatch')
    for path, sha in ((BASE/'guard.py',GUARD_SHA),(BASE/'activate_timestamp_retry_once.py',SAMPLER_SHA)):
        require(not path.is_symlink() and path.stat().st_uid == 0 and not path.stat().st_mode & 0o022,
                'untrusted runtime/helper')
        require(digest(path) == sha, 'runtime/helper hash mismatch')
    # Cleanup uses the frozen reviewed guard, even if a live file changed.
    for name, path in (('G',BASE/'guard.py'),('A',BASE/'activate_timestamp_retry_once.py')):
        spec = importlib.util.spec_from_file_location(name,path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        globals()[name] = module
    G.ACTION = 'recovery-transaction'
    signal.signal(signal.SIGALRM, G.deadline)


def configurations():
    uid = str(pwd.getpwnam('jetson').pw_uid)
    result = {}
    for unit in NAMES:
        path = Path('/etc/systemd/system')/unit
        source = BASE/(unit+'.in' if unit == G.UNIT else unit)
        expected = source.read_text().replace('@JETSON_UID@',uid)
        G.trusted(path)
        require(path.read_text() == expected, 'unit differs: '+unit)
        p = props(unit)
        require(p['FragmentPath'] == str(path) and not p['DropInPaths'], 'unexpected unit override')
        require(p['MainPID']=='0' and p['ActiveState'] in ('inactive','failed'), 'monitoring already running')
        result[unit] = p
    rule = G.CONFIG/'atlas-monitor.nft'; G.trusted(rule)
    require(rule.read_text() == (BASE/'atlas-monitor.nft').read_text(), 'firewall config differs')
    require(result[G.UNIT]['UnitFileState'] == 'enabled', 'unexpected exporter enabled state')
    return result


def config_hashes():
    return {str(p):digest(p) for p in [GUARD, G.EXPORTER, G.CONFIG/'atlas-monitor.nft',
                                     *(Path('/etc/systemd/system')/u for u in NAMES)]}


def sample(admission=False):
    global previous, counts
    previous, counts, observation = A.sample(G,previous,counts,protected)
    if admission:
        require(observation['cpu'] < 75 and observation['ram'] < 80, 'admission resource limit')
    # Bounded append; the file is private and fsynced after every accepted sample.
    path = E/'samples.jsonl'
    require(not path.exists() or path.stat().st_size < 262144, 'sample quota')
    with path.open('a') as out:
        out.write(json.dumps(observation,allow_nan=False)+'\n'); out.flush(); os.fsync(out.fileno())
    return observation


def supervised(action, seconds=10):
    """Keep the existing sampler on the main thread while bounded commands run."""
    results = queue.Queue(maxsize=1)
    def execute():
        try: results.put((True, action()))
        except BaseException as exc: results.put((False, exc))
    thread = threading.Thread(target=execute, daemon=True); thread.start()
    until = time.monotonic()+seconds
    while True:
        sample()
        require(time.monotonic() < until, 'transaction step timeout')
        try: ok, value = results.get_nowait()
        except queue.Empty: continue
        if not ok: raise value
        return value


def prepare_override():
    # Disable boot auto-start before rearming. No --now and no unrelated unit.
    run('systemctl','disable',G.UNIT)
    for unit in NAMES:
        path = drop(unit); path.parent.mkdir(mode=0o755, exist_ok=True)
        require(not os.path.lexists(path), 'override already exists')
        write(path, DROP_BYTES)
    run('systemctl','daemon-reload')
    require(all(props(u)['Restart']=='no' for u in NAMES), 'Restart=no not effective')


def restore_configuration():
    before = json.loads((E/'before.json').read_text())
    for unit in NAMES:
        path = drop(unit)
        if os.path.lexists(path):
            require(not path.is_symlink() and path.read_bytes()==DROP_BYTES, 'override changed; retain')
            path.unlink(); sync_dir(path.parent)
    run('systemctl','daemon-reload')
    if before['enabled']=='enabled': run('systemctl','enable',G.UNIT)  # never --now
    for unit in NAMES:
        require(props(unit)['Restart']==before['units'][unit]['Restart'], 'policy restore failed')
    require(props(G.UNIT)['UnitFileState']==before['enabled'], 'enabled state restore failed')


def baseline_rules():
    return {'v4':A.normalized(run('iptables-save')), 'v6':A.normalized(run('ip6tables-save'))}


def verify_cleanup():
    require(all(props(u)['MainPID']=='0' and props(u)['ActiveState'] in ('inactive','failed') for u in NAMES),
            'monitoring process remains')
    require(not G.listeners() and not G.firewall_present(), 'cleanup listener/table remains')
    before = json.loads((E/'before.json').read_text())
    require(baseline_rules()==before['rules'], 'unrelated firewall drift')
    require(A.services()==before['protected'], 'protected service drift')
    require(config_hashes()==before['config_hashes'], 'live files changed')


def verify_success():
    G.no_fault(); G.verify_firewall(); G.integrity()
    before = json.loads((E/'before.json').read_text())
    identities = json.loads((E/'running.json').read_text())
    require(baseline_rules()==before['rules'] and A.services()==before['protected'], 'protected state drift')
    require(config_hashes()==before['config_hashes'], 'live files changed')
    require(bool(G.listeners()), 'exporter listener missing')
    for unit in NAMES:
        p=props(unit)
        require(p['ActiveState']=='active' and p['NRestarts']==before['units'][unit]['NRestarts'], 'monitoring unhealthy/restarted')
        require(p['MainPID']==identities[unit], 'monitoring PID changed')


def verify_restored_policy():
    before=json.loads((E/'before.json').read_text())
    require(all(props(u)['Restart']==before['units'][u]['Restart'] and not drop(u).exists() for u in NAMES),
            'original restart policy not restored')
    require(props(G.UNIT)['UnitFileState']==before['enabled'], 'original enabled state not restored')


def verify_client():
    receipt=json.loads((E/'client-confirmation.json').read_text())
    require(receipt.get('running_sha256')==digest(E/'running.json') and
            receipt.get('boot_id')==Path('/proc/sys/kernel/random/boot_id').read_text().strip() and
            0 <= time.monotonic()-receipt['monotonic'] <= 310,
            'missing/stale client verification')


def cancel_expiry():
    run('systemctl','stop',EXPIRY+'.timer')


def cleanup():
    """ExecStopPost runs even after SIGKILL/RuntimeMaxSec; no success by absence."""
    if not (E/'mutation-intent.json').exists():
        write(E/'result.json', {'result':'FAIL','cleanup':'NO_MUTATION'}); return
    # An expiry firing after a durable success commit must not undo that commit.
    if (E/'result.json').exists() and json.loads((E/'result.json').read_text()).get('result')=='PASS':
        try:
            verify_success(); verify_restored_policy()
            return
        except Exception: pass
    if (E/'candidate-pass.json').exists() and os.environ.get('SERVICE_RESULT')=='success':
        try:
            verify_success(); verify_client(); verify_restored_policy()
            G.two_samples()
            write(E/'result.json', {'result':'PASS','cleanup':'NOT_NEEDED','grafana':'OWNER_CONFIRMED'})
        except Exception:
            # A post-rename write/fsync error must not leave a false commit marker.
            if (E/'result.json').exists():
                try: (E/'result.json').unlink(); sync_dir(E)
                except OSError: pass  # shutdown still has priority below
        else:
            # Durable commit is terminal. Cancellation failure is not a rollback.
            # The independent expiry rechecks live state/policy before accepting it.
            try: cancel_expiry()
            except Exception: pass
            return
    try:
        # Evidence failure must never prevent requesting shutdown.
        G.rollback()
        verify_cleanup()
        restore_latch()
        restore_configuration()
        write(E/'result.json', {'result':'FAIL','cleanup':'VERIFIED','original_cause':'UNKNOWN'})
        cancel_expiry()
    except BaseException as exc:
        # Best effort re-latch after failed shutdown; retain override/disabled state.
        try: restore_latch()
        except Exception: pass
        write(E/'result.json', {'result':'FAIL','cleanup':'FAILED','error':type(exc).__name__,
                               'action':'Leave monitoring stopped/disabled and protection retained; owner recovery required'})
        raise


def wait_active(unit, seconds):
    end = time.monotonic()+seconds
    while time.monotonic()<end:
        p=props(unit)
        if p['ActiveState']=='active': return
        require(p['ActiveState'] != 'failed', 'startup failed: '+unit)
        time.sleep(.1)
    raise RuntimeError('startup deadline: '+unit)


def worker():
    global previous, counts, protected
    require(bool(os.environ.get('INVOCATION_ID')) and
            run('systemctl','show',TX+'.service','-p','MainPID','--value').strip()==str(os.getpid()),
            'worker must be systemd supervised')
    info=G.STATE.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode & 0o077, 'untrusted state directory')
    G.trusted(GUARD); require(digest(GUARD)==GUARD_SHA, 'live guard changed')
    G.integrity(); before_units = configurations()
    require(not G.listeners() and not G.firewall_present(), 'listener/table already present')
    nft = json.loads(run('nft','-j','list','ruleset'))
    require(all('metainfo' in item for item in nft['nftables']), 'unexpected nft ruleset')
    before = dict(units=before_units, enabled=before_units[G.UNIT]['UnitFileState'],
                  protected=A.services(), rules=baseline_rules(), config_hashes=config_hashes(),
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    write(E/'before.json',before)
    write(E/'journal-before.txt',run('journalctl','-n','150','--no-pager','-o','short-iso',
                                   '-u',G.FIREWALL,'-u',G.WATCHDOG,'-u',G.UNIT).encode())
    # Serialize against both existing guard mutation paths during archival/reset.
    with contextlib.ExitStack() as stack:
        for name in ('operations.lock','evidence.lock'):
            fd=os.open(G.STATE/name,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
            lock=stack.enter_context(os.fdopen(fd,'w'))
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        archive_state()
        # Read-only setup precedes the measured admission interval; every mutation
        # below is then covered by the same continuous sampler.
        previous=G.cpu_counter()
        for _ in range(3): sample(admission=True)
        require(run('systemctl','is-active',EXPIRY+'.timer').strip()=='active', 'independent expiry absent')
        write(E/'mutation-intent.json', {'time':time.time(),'cause':'UNKNOWN'})
        supervised(prepare_override)
        require(all(props(u)['MainPID']=='0' for u in NAMES), 'monitoring started externally')
        rearm()
    start=time.monotonic()
    supervised(lambda: (run('systemctl','--no-block','start',G.FIREWALL),wait_active(G.FIREWALL,8)), 10)
    G.verify_firewall(); protected=True
    supervised(lambda: (run('systemctl','--no-block','start',G.UNIT),wait_active(G.WATCHDOG,20),wait_active(G.UNIT,3)),25)
    write(E/'running.json',{u:props(u)['MainPID'] for u in NAMES})
    while time.monotonic()-start < 300:
        sample()
        require(all(props(u)['ActiveState']=='active' for u in NAMES), 'optional service stopped')
    supervised(verify_success)
    verify_client()
    supervised(restore_configuration)
    supervised(verify_success)
    write(E/'candidate-pass.json',{'time':time.time(),'local_validation':'PASS'})


def transient_command():
    script=str(BASE/'recover_once.py')
    return ['systemd-run','--unit='+TX,'--wait','--collect',
            '--property=Type=exec','--property=RuntimeMaxSec=330','--property=Restart=no',
            '--property=TimeoutStopSec=30','--property=KillMode=control-group',
            '--property=UMask=0077','--property=MemoryMax=96M','--property=TasksMax=24',
            '--property=ExecStopPost=/usr/bin/python3 -I -B '+script+' cleanup',
            '/usr/bin/python3','-I','-B',script,'worker']


def expiry_command():
    # 330 runtime + up to 30 stopping main + up to 30 ExecStopPost. The separate
    # fallback starts after both allowances, avoiding loss to cleanup.lock overlap.
    return ['systemd-run','--unit='+EXPIRY,'--on-active=410s','--timer-property=AccuracySec=1s',
            '--property=Type=oneshot','--property=Restart=no','--property=TimeoutStartSec=30',
            '/usr/bin/python3','-I','-B',str(BASE/'recover_once.py'),'cleanup']


def main():
    require(os.geteuid()==0, 'local administrator authentication required')
    require(len(sys.argv)==2 and sys.argv[1] in ('start','worker','cleanup','confirm-client'), 'invalid action')
    os.umask(0o077); load()
    action=sys.argv[1]
    if action!='start':
        info=E.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode & 0o077,
                'untrusted attempt directory')
    if action=='start':
        E.mkdir(mode=0o700)  # exclusive attempt token; never delete/retry
        write(E/'request.json', {'time':time.time(),'original_cause':'UNKNOWN'})
        def stop_request(signum, frame): raise RuntimeError('owner interrupted')
        signal.signal(signal.SIGTERM,stop_request); signal.signal(signal.SIGINT,stop_request)
        try:
            run(*expiry_command())
            require(run('systemctl','is-active',EXPIRY+'.timer').strip()=='active', 'expiry not armed')
            subprocess.run(transient_command(),check=True,timeout=445)
        except BaseException:
            # Independent expiry remains armed even if this stop request fails.
            run('systemctl','--no-block','stop',TX+'.service')
            raise
        print((E/'result.json').read_text())
    elif action=='confirm-client':
        verify_success()
        require(not (E/'client-confirmation.json').exists(), 'client confirmation already recorded')
        write(E/'client-confirmation.json',{'monotonic':time.monotonic(),
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'running_sha256':digest(E/'running.json')})
    elif action=='cleanup':
        with (E/'cleanup.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            cleanup()
    else:
        def interrupted(signum, frame): raise RuntimeError('transaction interrupted')
        signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
        try: worker()
        except BaseException as exc:
            write(E/'failure.json',{'time':time.time(),'reason':str(exc)[:160], 'evidence':dict(G.EVIDENCE)})
            raise


if __name__=='__main__': main()

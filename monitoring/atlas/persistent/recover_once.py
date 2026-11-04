#!/usr/bin/env python3
"""One approved monitoring rearm that also installs the reviewed transient/violation guard (2026-11-04).

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
# Incident 4f04831f (watchdog API TimeoutError, 2026-11-04 10:59:42, boot 33363f37). Owner sudo read 2026-11-04
# 13:51 IST: eight PRESENT files, including observer-active.json (left by the latched exit). All older
# fault/attempt archives remain untouched.
E = Path('/var/lib/atlas-monitoring-recovery-m2-permanent-20261104')
GUARD = Path('/usr/local/libexec/atlas-monitoring-guard.py')
GUARD_SHA = '188d53db127ceb49e4c1c36fed61caacd05b3ab4f70e190f08f83c3b6fba802a'           # reviewed new guard (package)
PREVIOUS_GUARD_SHA = '27d4cacae47044a1675cf911aad60a69fc78dd5b85de14bdb6d5480288a560e1'  # deployed before this transaction
SAMPLER_SHA = '9982e13a0c963a5a6783a227d0ca974dccfad3d1cfe95b6e06506a187988f5e5'
EXPECTED_FAULT = '4f04831f22623fad52fa28676348153989291f37ca4b1e4f05069e26e79a7dc5'
EMPTY_SHA = hashlib.sha256(b'').hexdigest()
EXPECTED_STATE = {
    'FAULT.json': EXPECTED_FAULT,
    'firewall-owned.json': '2212fe537ee251d867d8d7093effd941ddf5b969b299e3266cf3782358a727e4',
    'rollback.json': '1f188cc96e99b4557a1f62503ad33a3fdc3b4cffc495c483d339576409803527',
    'fault-events.json': 'f23ce63f51d0f795272cc878790a36d44c88322d7944bbab87ec9c627947391f',   # 11 retained events
    'last-health.json': '35bd5fc4a5fe613a1f636d3f466a4aad3f5244489c9e429c86c65f2a2b91a36a',
    'observer-active.json': '3da97cb57e24c8d881e384ab440fa2baf9f5cf25371691eeee658e92a37c3249',  # MUST be present
    'operations.lock': EMPTY_SHA,
    'evidence.lock': EMPTY_SHA,
}
EXPECTED_ABSENT = ()
NAMES = tuple('atlas-monitoring-'+n+'.service' for n in ('firewall','watchdog','exporter'))
TX = 'atlas-monitoring-recovery-once-m2-permanent-20261104'
# Exporter start (systemd Starting->Started, incl. its guarded ExecCondition) measured 3.629 s, 3.623 s (2026-10-30)
# and 3.598 s (2026-10-31 attempt 1, which failed on the old 3 s sub-deadline). 12 s = 3.3x the slowest measured
# start. The 25 s supervised step bound below is unchanged and remains the hard cap for watchdog + exporter.
EXPORTER_START_S = 12.0
WATCHDOG_START_S = 20.0
START_STEP_S = 25
EXPIRY = TX+'-expiry'
DROP_NAME = '90-atlas-recovery-once.conf'
DROP_BYTES = b'[Service]\nRestart=no\n'
G = A = None
previous = counts = None
protected = False
PACKAGE_FILES = {'recover_once.py','guard.py','activate_timestamp_retry_once.py',
                 'atlas-monitor.nft','atlas-monitoring-firewall.service',
                 'atlas-monitoring-watchdog.service','atlas-monitoring-exporter.service.in',
                 'previous-guard.py','previous-atlas-monitoring-watchdog.service',
                 'previous-atlas-monitoring-exporter.service.in'}
# Live file -> (previous package source, new package source). The firewall unit is unchanged.
INSTALL = (('guard', GUARD, 'previous-guard.py', 'guard.py'),
           ('watchdog-unit', Path('/etc/systemd/system/atlas-monitoring-watchdog.service'),
            'previous-atlas-monitoring-watchdog.service', 'atlas-monitoring-watchdog.service'),
           ('exporter-unit', Path('/etc/systemd/system/atlas-monitoring-exporter.service'),
            'previous-atlas-monitoring-exporter.service.in', 'atlas-monitoring-exporter.service.in'))


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


def verify_lineage():
    # This is a new fault, not another recovery of the older October 30 latch.
    # Exact current bytes are verified and archived below; old archives are never touched.
    require(set(EXPECTED_STATE) == {'FAULT.json','firewall-owned.json','rollback.json','fault-events.json',
        'last-health.json','observer-active.json','operations.lock','evidence.lock'},
        'incident state members differ')
    require(EXPECTED_ABSENT == (), 'incident absence differs')
    require(EXPECTED_STATE['FAULT.json'] == EXPECTED_FAULT, 'incident fault differs')
    require(all(len(v) == 64 and all(c in '0123456789abcdef' for c in v)
                for v in EXPECTED_STATE.values()), 'incident hash invalid')


def archive_state():
    verify_lineage()
    require(all(not os.path.lexists(G.STATE/n) for n in EXPECTED_ABSENT), 'required absent evidence exists')
    hashes = state_hashes()
    expected = dict(EXPECTED_STATE)
    if 'evidence.lock' in hashes: expected['evidence.lock'] = hashlib.sha256(b'').hexdigest()
    require(hashes == expected and hashes.get('FAULT.json') == EXPECTED_FAULT, 'retained evidence changed')
    for p in G.STATE.glob('*.json'):
        value = json.loads(p.read_text())
        # The existing guard retains up to 16 later refusals as a list.
        valid = (isinstance(value, list) and len(value) <= 16
                 and all(isinstance(event, dict) for event in value)) if p.name == 'fault-events.json' else isinstance(value, dict)
        require(valid, 'invalid retained evidence')
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
    write(E/'state-absent.json', list(EXPECTED_ABSENT))
    write(E/'state-manifest.json', hashes)
    verify_archive()


def verify_archive():
    hashes = json.loads((E/'state-manifest.json').read_text())
    require(json.loads((E/'state-absent.json').read_text()) == list(EXPECTED_ABSENT), 'archive absence changed')
    require(not set(EXPECTED_ABSENT).intersection(hashes), 'absent evidence archived as present')
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
    # Remove only the two reviewed markers after archiving every original byte.
    for name in ('FAULT.json','observer-active.json'):
        if name in hashes: (G.STATE/name).unlink()
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
    for path, sha in ((BASE/'guard.py',GUARD_SHA),(BASE/'previous-guard.py',PREVIOUS_GUARD_SHA),
                      (BASE/'activate_timestamp_retry_once.py',SAMPLER_SHA)):
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
        source = BASE/{'atlas-monitoring-watchdog.service':'previous-atlas-monitoring-watchdog.service',
                       'atlas-monitoring-exporter.service':'previous-atlas-monitoring-exporter.service.in'}.get(unit, unit)
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


def rendered(name):
    data = (BASE/name).read_bytes()
    return data.replace(b'@JETSON_UID@', str(pwd.getpwnam('jetson').pw_uid).encode()) if name.endswith('.in') else data


def unit_restart(data):
    lines = [l.split('=',1)[1].strip() for l in data.decode().splitlines() if l.startswith('Restart=')]
    return lines[-1] if lines else 'no'


def expected_policy(new):
    before = json.loads((E/'before.json').read_text())
    if not new:
        return {u: before['units'][u]['Restart'] for u in NAMES}
    files = {n.removesuffix('.in'): rendered(n) for _, _, _, n in INSTALL if '.service' in n}
    return {u: unit_restart(files[u]) if u in files else before['units'][u]['Restart'] for u in NAMES}


def install_config():
    # Exact-byte backup of the three previous live files (and their metadata), then atomic replacement with the
    # reviewed files. Runs inside prepare_override(), before its single daemon-reload. Never twice.
    dest = E/'original-config'; dest.mkdir(mode=0o700)
    meta = {}
    for key, path, old, new in INSTALL:
        G.trusted(path)
        live = path.read_bytes()
        require(live == rendered(old), 'live file is not the reviewed previous version: '+key)
        info = path.stat()
        meta[key] = dict(path=str(path), uid=info.st_uid, gid=info.st_gid, mode=stat.S_IMODE(info.st_mode),
                         previous_sha256=digest(path), new_sha256=hashlib.sha256(rendered(new)).hexdigest())
        write(dest/key, live); os.chmod(dest/key, stat.S_IMODE(info.st_mode))
        require(digest(dest/key) == meta[key]['previous_sha256'], 'config backup mismatch: '+key)
    # No temp file may pre-exist, so any found later was left by this attempt (killed inside replace()).
    require(not any(os.path.lexists(tmp_path(p)) for _, p, _, _ in INSTALL), 'temporary file exists')
    sync_dir(dest); write(E/'config-metadata.json', meta)
    for key, path, old, new in INSTALL:
        replace(path, rendered(new), meta[key])
    write(E/'installed-config.json', config_hashes())


def tmp_path(path):
    return path.with_name('.'+path.name+'.atlas-recovery-tmp')


def replace(path, data, m):
    tmp = tmp_path(path)
    require(not os.path.lexists(tmp), 'temporary file exists: '+str(tmp))
    fd = os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, m['mode'])
    try:
        try:
            os.write(fd, data); os.fchown(fd, m['uid'], m['gid']); os.fchmod(fd, m['mode']); os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        if os.path.lexists(tmp): tmp.unlink()
        raise
    sync_dir(path.parent)
    require(path.read_bytes() == data, 'post-write mismatch: '+str(path))


def restore_previous_config():
    # Exact previous bytes and metadata from this attempt's backup. Refuses any third version (retain for review).
    if not (E/'config-metadata.json').exists():
        return False
    meta = json.loads((E/'config-metadata.json').read_text())
    for _, path, _, _ in INSTALL:
        tmp = tmp_path(path)
        if os.path.lexists(tmp):          # only this attempt's own leftover (install refused any pre-existing)
            require(stat.S_ISREG(tmp.lstat().st_mode), 'unexpected temporary entry; retain: '+str(tmp))
            tmp.unlink(); sync_dir(tmp.parent)
    for key, path, old, new in INSTALL:
        m = meta[key]; backup = (E/'original-config'/key).read_bytes()
        require(hashlib.sha256(backup).hexdigest() == m['previous_sha256'], 'config backup corrupt: '+key)
        current = digest(path)
        require(current in (m['previous_sha256'], m['new_sha256']), 'config changed by a third party; retain: '+key)
        if current != m['previous_sha256']:
            replace(path, backup, m)
    return True


def config_hashes():
    return {str(p):digest(p) for p in [GUARD, G.EXPORTER, G.CONFIG/'atlas-monitor.nft',
                                     *(Path('/etc/systemd/system')/u for u in NAMES)]}


def sample(admission=False):
    global previous, counts
    previous, counts, observation = A.sample(G,previous,counts,protected)
    G.EVIDENCE.update(stage='transaction_resource_limit', cpu=G.evidence_scalar(observation['cpu']),
                      cpu_threshold=75, cpu_required_comparison='<',
                      cpu_sample_monotonic=G.evidence_scalar(previous[0]),
                      cpu_sample_age=G.evidence_scalar(time.monotonic()-previous[0]))
    # Strict owner limits apply throughout the transaction, not only admission.
    require(observation['cpu'] < 75 and observation['ram'] < 80, 'resource limit')
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
    # --no-reload: plain disable reloads systemd implicitly; with the explicit reload below that was two
    # back-to-back PID-1 reloads under the strict CPU sampler (m2-permissions rejected here, 2026-11-02).
    # One reload after all changes has the same effect.
    run('systemctl','disable','--no-reload',G.UNIT)
    for unit in NAMES:
        path = drop(unit); path.parent.mkdir(mode=0o755, exist_ok=True)
        require(not os.path.lexists(path), 'override already exists')
        write(path, DROP_BYTES)
    install_config()                       # reviewed guard + units; picked up by the same single reload
    run('systemctl','daemon-reload')
    require(all(props(u)['Restart']=='no' for u in NAMES), 'Restart=no not effective')


def restore_configuration(keep_new=True):
    # keep_new: PASS path keeps the installed reviewed guard/units. FAIL path restores the exact previous bytes
    # first, so the same single reload loads the previous configuration.
    before = json.loads((E/'before.json').read_text())
    if not keep_new:
        restore_previous_config()
    for unit in NAMES:
        path = drop(unit)
        if os.path.lexists(path):
            require(not path.is_symlink() and path.read_bytes()==DROP_BYTES, 'override changed; retain')
            path.unlink(); sync_dir(path.parent)
    # Single reload after both changes (plain enable would reload a second time). never --now
    if before['enabled']=='enabled': run('systemctl','enable','--no-reload',G.UNIT)
    run('systemctl','daemon-reload')
    policy = expected_policy(keep_new)
    for unit in NAMES:
        require(props(unit)['Restart']==policy[unit], 'policy restore failed')
    if not keep_new and (E/'config-metadata.json').exists():
        require(config_hashes()==before['config_hashes'], 'previous config not restored')
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
    require(config_reviewed_mix(before['config_hashes']), 'live files changed')


def config_reviewed_mix(previous):
    # An interrupted install_config() may leave any per-file mix of previous/new reviewed bytes (no
    # installed-config.json yet). Every other file must be unchanged. restore_configuration(keep_new=False)
    # then restores the exact previous set and requires it.
    meta = json.loads((E/'config-metadata.json').read_text()) if (E/'config-metadata.json').exists() else {}
    allowed = {path: {sha} for path, sha in previous.items()}
    for key, path, _, _ in INSTALL:
        if key in meta: allowed[str(path)].add(meta[key]['new_sha256'])
    live = config_hashes()
    return set(live) == set(allowed) and all(live[p] in allowed[p] for p in live)


def verify_success():
    G.no_fault(); G.verify_firewall(); G.integrity()
    before = json.loads((E/'before.json').read_text())
    identities = json.loads((E/'running.json').read_text())
    require(baseline_rules()==before['rules'] and A.services()==before['protected'], 'protected state drift')
    require(config_hashes()==json.loads((E/'installed-config.json').read_text()), 'live files changed')
    require(bool(G.listeners()), 'exporter listener missing')
    for unit in NAMES:
        p=props(unit)
        require(p['ActiveState']=='active' and p['NRestarts']==before['units'][unit]['NRestarts'], 'monitoring unhealthy/restarted')
        require(p['MainPID']==identities[unit], 'monitoring PID changed')


def verify_restored_policy():
    before=json.loads((E/'before.json').read_text())
    policy=expected_policy(True)                      # a PASS keeps the installed reviewed units
    require(all(props(u)['Restart']==policy[u] and not drop(u).exists() for u in NAMES),
            'restart policy not restored')
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
        restore_configuration(keep_new=False)
        write(E/'result.json', {'result':'FAIL','cleanup':'VERIFIED','original_cause':'UNKNOWN','config':'PREVIOUS_RESTORED'})
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
    G.trusted(GUARD); require(digest(GUARD)==PREVIOUS_GUARD_SHA, 'live guard is not the reviewed previous version')
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
    supervised(lambda: (run('systemctl','--no-block','start',G.UNIT),wait_active(G.WATCHDOG,WATCHDOG_START_S),
                        wait_active(G.UNIT,EXPORTER_START_S)),START_STEP_S)
    write(E/'running.json',{u:props(u)['MainPID'] for u in NAMES})
    while time.monotonic()-start < 300:
        sample()
        require(all(props(u)['ActiveState']=='active' for u in NAMES), 'optional service stopped')
    supervised(verify_success)
    verify_client()
    supervised(restore_configuration)
    supervised(verify_success)
    write(E/'candidate-pass.json',{'time':time.time(),'local_validation':'PASS'})


CONFIRM_BY_S = 240     # latest operator confirmation; the worker's own check is ~305 s after start (firewall start + 300 s)
CONFIRM_TARGET_S = 120 # attempts 3-4: monitoring was healthy; confirmation was late/absent. Confirm once both checks pass.


def deadline_message(now):
    """Attempt 3 failed only because confirmation came 34 s late. Information only; no bound changes."""
    t=lambda s: time.strftime('%H:%M:%S',time.localtime(now+s))
    return ('Observation window closes about %s (start + ~305 s). Target confirm-client at about %s (start + %d s) '
            'once Prometheus and Grafana pass; latest %s (start + %d s). Never confirm after the window closes.'
            % (t(305), t(CONFIRM_TARGET_S), CONFIRM_TARGET_S, t(CONFIRM_BY_S), CONFIRM_BY_S))


def stop_if_running():
    try:
        out = subprocess.run(['systemctl','show',TX+'.service','-p','LoadState','-p','ActiveState'],
                             capture_output=True, text=True, timeout=3).stdout
        p = dict(line.split('=',1) for line in out.splitlines() if '=' in line)
        if p.get('LoadState')=='loaded' and p.get('ActiveState') in ('active','activating','deactivating','reloading'):
            subprocess.run(['systemctl','--no-block','stop',TX+'.service'], capture_output=True, timeout=3)
            return 'stop-requested'
        return 'already-finished'
    except Exception:
        return 'unknown'                 # the independent expiry still owns cleanup


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
    require(len(sys.argv)==2 and sys.argv[1] in ('start','worker','cleanup','confirm-client','restore-previous-config'),
            'invalid action')
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
        print(deadline_message(time.time()), flush=True)
        try:
            run(*expiry_command())
            require(run('systemctl','is-active',EXPIRY+'.timer').strip()=='active', 'expiry not armed')
            subprocess.run(transient_command(),check=True,timeout=445)
        except BaseException:
            # Independent expiry remains armed even if this stop request fails. `--wait --collect` has normally
            # already removed a finished unit (attempt 1: stop then failed with exit 5 and masked the real error):
            # stop only a unit that still exists and runs, and never let this replace the original exception.
            stop_if_running()
            raise
        print((E/'result.json').read_text())
    elif action=='confirm-client':
        verify_success()
        require(not (E/'client-confirmation.json').exists(), 'client confirmation already recorded')
        write(E/'client-confirmation.json',{'monotonic':time.monotonic(),
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'running_sha256':digest(E/'running.json')})
    elif action=='restore-previous-config':
        # Owner rollback after a PASS: only with all monitoring stopped and no listener. One reload. Latch untouched.
        require(all(props(u)['MainPID']=='0' and props(u)['ActiveState'] in ('inactive','failed') for u in NAMES)
                and not G.listeners(), 'stop monitoring first (systemctl stop the three units)')
        require(restore_previous_config(), 'no configuration backup in this attempt')
        run('systemctl','daemon-reload')
        require(config_hashes()==json.loads((E/'before.json').read_text())['config_hashes'], 'previous config not restored')
        print('PREVIOUS guard/units restored (exact bytes); monitoring left stopped')
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

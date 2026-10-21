"""Stage32 takeover: install / roll back the NO-RESTART IR diagnostic package on the Jetson.

  python3 stage32_ir_diag_install.py check     read-only: report hashes, integrity, safety; changes nothing
  OWNER_APPROVED=yes python3 stage32_ir_diag_install.py apply
  OWNER_APPROVED=yes python3 stage32_ir_diag_install.py rollback

Touches ONLY two files of the isolated Astra runtime (lib/libastra_camera.so and manifest.json). Restarts NOTHING,
starts no camera, changes no CPU/RAM/thermal policy. Refuses unless E-STOP is latched, manual-only, no Astra driver /
Vision Lab worker / cloud node runs, private domain 77 is free and both live files equal the verified baseline.
After writing it re-runs the worker's own 458-file integrity check so the next Start cannot be refused for integrity, and
proves every user-service identity (PID, NRestarts) is unchanged. Failure after any write restores the backup.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = Path(os.environ.get('ATLAS_IR_DIAG_RUNTIME', '/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2'))
STATE = Path(os.environ.get('ATLAS_IR_DIAG_STATE', '/home/jetson/project-atlas-migration/stage32-takeover-ir-diag'))
ROOT = Path(os.environ.get('ATLAS_ROOT', '/home/jetson/project_atlas'))
API = os.environ.get('ATLAS_API', 'http://127.0.0.1:8088')
SKIP_SAFETY = os.environ.get('ATLAS_IR_DIAG_SKIP_SAFETY') == 'yes'   # rehearsal on a copy only
FILES = ('lib/libastra_camera.so', 'manifest.json')
PROCESS_MARKERS = (b'astra_camera_node', b'atlas_vision3d_runtime.py\x00--worker', b'atlas_vision3d_cloud_node.py')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def package():
    meta = json.loads((HERE / 'package.json').read_text())
    for f in FILES:
        if sha(HERE / 'payload' / f) != meta['files'][f]['candidate']:
            raise RuntimeError('package payload hash mismatch: ' + f)
    return meta


def integrity(root=RUNTIME):
    """Same check the Vision Lab worker runs before opening the camera (atlas_vision3d_runtime.py)."""
    manifest = json.loads((root / 'manifest.json').read_text())
    if len(manifest['files']) != 458:
        return 'runtime manifest count mismatch'
    for f in manifest['files']:
        p = (root / f['path']).resolve()
        if not p.is_relative_to(root.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest() != f['sha256']:
            return 'isolated runtime integrity failure: ' + f['path']
    return 'PASS'


def camera_processes():
    me = {os.getpid(), os.getppid()}
    found = []
    for d in Path('/proc').iterdir():
        if not d.name.isdigit() or int(d.name) in me:
            continue
        try:
            cmd = (d / 'cmdline').read_bytes()
        except OSError:
            continue
        if any(m in cmd for m in PROCESS_MARKERS):
            found.append({'pid': int(d.name), 'cmd': cmd.replace(b'\0', b' ')[:160].decode(errors='replace')})
    return found


def identities():
    names = [x.split()[0] for x in subprocess.check_output(
        ['systemctl', '--user', 'list-units', '--type=service', '--state=active', '--no-legend', '--plain'], text=True).splitlines()]
    raw = subprocess.check_output(['systemctl', '--user', 'show', *names, '-p', 'Id', '-p', 'MainPID', '-p', 'NRestarts'], text=True)
    return {r['Id']: (r['MainPID'], r['NRestarts']) for b in raw.strip().split('\n\n') if (r := dict(x.split('=', 1) for x in b.splitlines()))}


def cpu_record(n=3):
    """Informational 1-s whole-machine samples (/proc/stat). NOT a camera admission; the worker's guard is unchanged."""
    def ticks():
        v = [int(x) for x in open('/proc/stat').readline().split()[1:9]]
        return sum(v), v[3] + v[4]
    out = []
    for _ in range(n):
        a = ticks(); time.sleep(1.0); b = ticks()
        out.append(round(100.0 * (1 - (b[1] - a[1]) / max(1, b[0] - a[0])), 2))
    return out


def safety():
    if SKIP_SAFETY:
        return {'skipped': 'rehearsal on a copy'}
    with urllib.request.urlopen(API + '/api/estop/state', timeout=5) as f:
        estop = json.load(f)
    if estop.get('latched') is not True:
        raise RuntimeError('E-STOP not latched')
    with urllib.request.urlopen(API + '/api/status', timeout=5) as f:
        policy = json.loads(json.load(f)['ros']['control_policy']['value'])
    if not (policy.get('manual_only') is True and policy.get('stop_latched') is True and policy.get('commission_armed') is False):
        raise RuntimeError('control policy not manual-only / stop-latched / disarmed')
    procs = camera_processes()
    if procs:
        raise RuntimeError('camera-side process running: %s' % procs)
    sys.path.insert(0, str(ROOT / 'scripts'))
    import atlas_vision3d_runtime as R
    if R.domain_in_use(77):
        raise RuntimeError('private domain 77 in use')
    return {'estop_latched': True, 'policy': policy, 'camera_processes': [], 'domain77_free': True}


def atomic(src, dst):
    tmp = dst.with_name(dst.name + '.s32diag.tmp')
    if tmp.exists():
        raise RuntimeError('stale temp file ' + str(tmp))
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def main(cmd):
    meta = package()
    live = {f: sha(RUNTIME / f) for f in FILES}
    result = {'cmd': cmd, 'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'live_before': live, 'restart': False, 'camera_started': False}
    state = {f: 'baseline' if live[f] == meta['files'][f]['baseline'] else 'candidate' if live[f] == meta['files'][f]['candidate'] else 'UNKNOWN'
             for f in FILES}
    result['state_before'] = state
    if cmd == 'check':
        result.update(integrity=integrity(), safety_preview=None if SKIP_SAFETY else _try(safety), camera_processes=camera_processes())
        return result
    if os.environ.get('OWNER_APPROVED') != 'yes':
        raise SystemExit('REFUSE: set OWNER_APPROVED=yes only after the owner approved this exact step')
    want_from, want_to = ('baseline', 'candidate') if cmd == 'apply' else ('candidate', 'baseline')
    if set(state.values()) != {want_from}:
        raise SystemExit('REFUSE: live files are %s, expected all %s' % (state, want_from))
    result['safety'] = safety()
    result['identities_before'] = None if SKIP_SAFETY else identities()
    result['cpu_record_before'] = cpu_record()
    STATE.mkdir(parents=True, exist_ok=True)
    backup = STATE / 'backup'
    if cmd == 'apply':
        if backup.exists():
            raise SystemExit('REFUSE: a backup already exists at %s (already applied once?)' % backup)
        for f in FILES:
            (backup / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(RUNTIME / f, backup / f)
            if sha(backup / f) != meta['files'][f]['baseline']:
                raise RuntimeError('backup verification failed ' + f)
        source = HERE / 'payload'
    else:
        for f in FILES:
            if sha(backup / f) != meta['files'][f]['baseline']:
                raise SystemExit('REFUSE: backup corrupt ' + f)
        source = backup
    written = []
    try:
        for f in FILES:                       # library first; the manifest makes it admissible
            atomic(source / f, RUNTIME / f); written.append(f)
            if sha(RUNTIME / f) != meta['files'][f][want_to]:
                raise RuntimeError('post-write hash mismatch ' + f)
        result['integrity_after'] = integrity()
        if result['integrity_after'] != 'PASS':
            raise RuntimeError(result['integrity_after'])
        result['identities_unchanged'] = SKIP_SAFETY or identities() == result['identities_before']
        if not result['identities_unchanged']:
            raise RuntimeError('a user-service identity changed (nothing should restart)')
        result['result'] = 'APPLIED' if cmd == 'apply' else 'ROLLED_BACK'
    except Exception as e:
        result['failure'] = str(e)
        if cmd == 'apply' and written:
            for f in reversed(written):
                atomic(backup / f, RUNTIME / f)
            result['restored'] = {f: sha(RUNTIME / f) for f in FILES}
            result['integrity_after_restore'] = integrity()
        result['result'] = 'FAILED'
    result['live_after'] = {f: sha(RUNTIME / f) for f in FILES}
    result['cpu_record_after'] = cpu_record()
    (STATE / ('%s-%s.json' % (cmd, time.strftime('%Y%m%d_%H%M%S')))).write_text(json.dumps(result, indent=2))
    return result


def _try(fn):
    try:
        return fn()
    except Exception as e:
        return {'not_admissible': str(e)}


if __name__ == '__main__':
    r = main(sys.argv[1] if len(sys.argv) > 1 else 'check')
    print(json.dumps(r, indent=2, default=str))
    sys.exit(0 if r.get('result', 'CHECKED') in ('APPLIED', 'ROLLED_BACK', 'CHECKED') or r['cmd'] == 'check' else 1)

"""Explicitly approved one-file deployment. Strict guards, no camera/control calls."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

LIVE = Path('/home/jetson/project_atlas')
BASE = 'cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b'
NEW = '58e5d86b21e59546cd44e5fcc87d99df910e4e9e9220d1701e24080de393a4da'
UNIT = 'atlas-localization-monitor.service'
CHECK = {
    'scripts/atlas_safety_status.py': '94f52bcc1d535378adf6d4f54f6d29fc52f0cd7b12b11a8da0df39117f510bd4',
    'scripts/atlas_dashboard_executor.py': '2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab',
    'scripts/atlas_dashboard_executor_impl.py': '543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1',
    'scripts/atlas_voice_companion.py': 'a88ff78df1ae2dded4f9984cdcf5e94d5335d1d12c77fd9c9131219725298870',
    'scripts/atlas_status_web.py': 'acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439',
    'web/v2/material.css': 'ea6a213b8a7b5aa5f4777af64259a75589799ebd151e39acf4723fc6fb6368d5',
    'tools/vision3d/stationary_gate.py': '0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9',
    'tools/vision3d/stationary_ros_probe.py': 'f8a24e2a9fe92f505f52e96572a00691b0ebcfe92b092ba1c98ee052c18ed9dd',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cpu_report_only(args):
    if not args:
        return False
    if args == ['--installation-cpu-report-only']:
        return True
    raise ValueError('Unknown installation arguments')


def validate_cpu_sample(cpu, report_only, require_cpu):
    if not math.isfinite(cpu) or not 0 <= cpu <= 100:
        raise RuntimeError('Invalid CPU measurement')
    if not report_only:
        require_cpu(cpu)


def audit_sensor_check(ros, check, emit, phase, snapshot_started, clock=time.monotonic):
    """Persist bounded receipt evidence before the unchanged fail-closed check.

    Dashboard age is receipt age, not proof of source publication timing.
    Never refetch a failed snapshot or turn an exception into a passing result.
    """
    keys = ('lidar', 'imu_full', 'enc_m1', 'enc_m2', 'enc_m3', 'enc_m4',
            'camera_info', 'drive_pid', 'mission_status', 'motor_speed')
    def age(key):
        value = ros.get(key, {})
        raw = value.get('age') if isinstance(value, dict) else None
        if isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(raw):
            return raw
        return None
    mission = ros.get('mission_status', {})
    def mission_number(key):
        raw = mission.get(key) if isinstance(mission, dict) else None
        return raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(raw) else None
    row = dict(kind='sensor_check', phase=phase, monotonic=clock(),
               snapshot_started=snapshot_started, receipt_ages={k: age(k) for k in keys},
               mission_sample_time=mission_number('sample_time'),
               mission_observed_hz=mission_number('observed_hz'),
               mission_ready=isinstance(mission, dict) and mission.get('value') == 'READY')
    emit(dict(row, outcome='PENDING'))
    try:
        result = check(ros)
    except Exception as exc:
        emit(dict(row, outcome='FAILED', error=str(exc), completed_monotonic=clock()))
        raise
    emit(dict(row, outcome='PASSED', completed_monotonic=clock()))
    return result


def main():
    report_only = cpu_report_only(sys.argv[1:])
    stage = Path(__file__).resolve().parent
    evidence = Path(tempfile.mkdtemp(prefix='evidence-', dir=stage))
    result = dict(status='ABORTED', evidence=str(evidence), restart_units=[], camera_started=False,
                  movement=False, limits={'cpu': 75, 'ram': 80, 'temperature': 70},
                  installation_cpu_policy='OWNER REPORT ONLY' if report_only else 'STRICT 75%',
                  production_limits_changed=False)
    trace = (evidence / 'trace.jsonl').open('x')
    lock = threading.Lock()
    stop = threading.Event()
    failure = []
    latest = {}
    phase = 'preflight'
    installed = False
    monitor_thread = None
    target = LIVE / 'scripts/atlas_localization_monitor.py'

    def emit(row):
        with lock:
            trace.write(json.dumps({'monotonic': time.monotonic(), **row}) + '\n')
            trace.flush()

    def identity(unit):
        return dict(line.split('=', 1) for line in subprocess.check_output(
            ['systemctl', '--user', 'show', unit, '-p', 'MainPID', '-p', 'NRestarts', '-p', 'ActiveState'],
            text=True, timeout=3).splitlines())

    def check_hashes():
        for path, expected in CHECK.items():
            if sha(LIVE / path) != expected:
                raise RuntimeError('Protected file hash mismatch: ' + path)

    def monitor():
        a = G.ticks()
        last = time.monotonic()
        while not stop.wait(1):
            try:
                b = G.ticks()
                now = time.monotonic()
                latest.update(cpu=G.cpu_delta(a, b), monotonic=now, interval=now-last)
                emit(dict(kind='cpu', phase=phase, **latest))
                validate_cpu_sample(latest['cpu'], report_only, G.require_cpu)
                a, last = b, now
            except Exception as exc:
                failure.append(str(exc))
                return

    def health(enforce_cpu=True):
        if enforce_cpu:
            if failure:
                raise RuntimeError(failure[0])
            if 'cpu' not in latest or time.monotonic()-latest['monotonic'] > 2 or latest['interval'] > 1.5:
                raise RuntimeError('CPU observer missing/stale')
        snapshot_started = time.monotonic()
        snap = P.safety_snapshot()
        checked = G.check(latest['cpu'] if enforce_cpu and not report_only else None, snap)
        checked['cpu_percent'] = latest.get('cpu')
        checked['installation_cpu_report_only'] = report_only
        audit_sensor_check(snap['ros'], P.extra_safety, emit, phase, snapshot_started)
        with urllib.request.urlopen('http://127.0.0.1:8088/api/vision3d/summary', timeout=3) as r:
            camera = json.load(r)
        require_off(camera, subprocess.run(['pgrep', '-x', 'astra_camera_no'], stdout=subprocess.DEVNULL).returncode)
        if protected() != before:
            raise RuntimeError('Protected service changed')
        if muted.exists() != muted_before:
            raise RuntimeError('Voice privacy changed')
        ident = identity(UNIT)
        if ident['ActiveState'] != 'active' or int(ident['MainPID']) <= 1:
            raise RuntimeError('Localization monitor inactive')
        emit(dict(kind='health', phase=phase, health=checked))
        return checked

    def process_ticks(pid):
        parts = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
        return int(parts[11]) + int(parts[12])

    def window(label):
        nonlocal phase
        phase = label
        ident = identity(UNIT)
        pid = int(ident['MainPID'])
        start = time.monotonic()
        ticks = process_ticks(pid)
        rows = []
        for _ in range(20):
            time.sleep(1)
            rows.append(health())
            if identity(UNIT) != ident:
                raise RuntimeError('Localization monitor restarted during window')
        elapsed = time.monotonic()-start
        return dict(rows=rows, elapsed=elapsed, identity=ident,
                    system_cpu_mean=sum(r['cpu_percent'] for r in rows)/len(rows),
                    system_cpu_peak=max(r['cpu_percent'] for r in rows),
                    monitor_one_core_cpu=100*(process_ticks(pid)-ticks)/os.sysconf('SC_CLK_TCK')/elapsed)

    def restart():
        result['restart_units'].append(UNIT)
        subprocess.run(['systemctl', '--user', 'restart', UNIT], check=True, timeout=30)

    try:
        check_hashes()
        raw = target.read_bytes()
        old = b'        rclpy.spin(node)'
        if raw.count(old) != 1:
            raise RuntimeError('Ambiguous spin replacement')
        candidate = raw.replace(old, b'        from atlas_dashboard_executor import spin as private_spin\n        private_spin(node)')
        compile(candidate, str(target), 'exec')
        if sha(target) != BASE or hashlib.sha256(candidate).hexdigest() != NEW:
            raise RuntimeError('Baseline/candidate hash mismatch')
        sys.path.insert(0, str(LIVE / 'tools/vision3d'))
        import stationary_gate as G
        import stationary_ros_probe as P
        sys.path.insert(0, '/home/jetson/project-atlas-migration/native-cpu-20261023')
        from native_dashboard_cpu_once import require_off
        def protected():
            return dict(G.services(), dashboard=identity('rover-status-web'), voice=identity('atlas-voice-companion.service'), safety=identity('atlas-safety-status.service'), mission=identity('atlas-mission-control.service'))
        before = protected()
        result['services_before'] = before
        if any(v['ActiveState'] != 'active' or int(v['MainPID']) <= 1 for v in before.values()):
            raise RuntimeError('Protected service inactive')
        muted = Path('/home/jetson/.local/state/atlas-voice/microphone-muted')
        muted_before = muted.exists()
        result['privacy_muted'] = muted_before
        result['disk_free_bytes'] = shutil.disk_usage(LIVE).free
        if result['disk_free_bytes'] < 512*1024*1024:
            raise RuntimeError('Insufficient disk')
        backup = evidence / 'atlas_localization_monitor.original'
        shutil.copy2(target, backup)
        if sha(backup) != BASE:
            raise RuntimeError('Backup hash mismatch')
        result['backup'] = str(backup)
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
        time.sleep(1.1)
        result['baseline'] = window('baseline')
        health()
        check_hashes()
        if sha(target) != BASE:
            raise RuntimeError('Live source changed before installation')
        temporary = target.with_name(target.name + '.scan-candidate-tmp')
        with temporary.open('xb') as f:
            f.write(candidate)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
        if sha(temporary) != NEW:
            raise RuntimeError('Temporary hash mismatch')
        health()
        os.replace(temporary, target)
        installed = True
        phase = 'restart'
        restart()
        phase = 'settling'
        for _ in range(10):
            time.sleep(1)
            health()
        result['post'] = window('post')
        check_hashes()
        health()
        if sha(target) != NEW:
            raise RuntimeError('Installed hash mismatch')
        result.update(status='DEPLOYED_HEALTH_VERIFIED', installed_hash=sha(target), services_after=protected())
    except BaseException as exc:
        result['error'] = str(exc)
        emit(dict(kind='failure', error=str(exc)))
        if installed:
            try:
                if sha(target) != NEW or sha(backup) != BASE:
                    raise RuntimeError('Rollback ownership/hash mismatch')
                phase = 'rollback'
                shutil.copy2(backup, target)
                restart()
                time.sleep(3)
                # Restoration is not blocked by the CPU failure that caused it.
                # Preserve that failure and do not report a resource pass.
                result.update(status='ROLLED_BACK', rollback_hash=sha(target),
                              rollback_health=health(False), services_after=protected())
            except BaseException as rollback_exc:
                result.update(status='ROLLBACK_NEEDS_ATTENTION', rollback_error=str(rollback_exc))
    finally:
        stop.set()
        if monitor_thread:
            monitor_thread.join(3)
        (evidence / 'result.json').write_text(json.dumps(result, indent=2))
        trace.close()
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

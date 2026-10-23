#!/usr/bin/env python3
"""Owner-run single-PID native profile. No production changes or ROS participants.

Root is used only to launch/stop the owned perf group and return evidence to
jetson. Safety checks run as jetson. Raw DWARF stack snippets stay private.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import pwd
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

LIVE = Path('/home/jetson/project_atlas')
STAGE = Path('/home/jetson/project-atlas-migration/native-cpu-20261023')
PERF = STAGE/'extracted/usr/lib/linux-tools-5.15.0-198/perf'
PERF_SHA = 'd51e7c1b3051d529e9a55c610d3d9e70e3b99ae89eebb477fae23a274e7311ca'
HASHES = {
    'scripts/atlas_status_web.py': '98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79',
    'web/v2/material.css': 'ea6a213b8a7b5aa5f4777af64259a75589799ebd151e39acf4723fc6fb6368d5',
    'tools/vision3d/stationary_gate.py': '0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9',
    'tools/vision3d/stationary_ros_probe.py': 'f8a24e2a9fe92f505f52e96572a00691b0ebcfe92b092ba1c98ee052c18ed9dd',
}


def verify(path, expected):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError('Hash mismatch: '+str(path))
    return actual


def as_root():
    os.setresuid(0, 0, 0)


def as_user(account):
    # systemd user-bus clients inspect real UID, not just effective UID.
    # Retain saved root only for the owned perf process and evidence cleanup.
    os.setresgid(account.pw_gid, account.pw_gid, 0)
    os.setresuid(account.pw_uid, account.pw_uid, 0)
    if (os.getuid(), os.geteuid(), os.getgid(), os.getegid()) != (
            account.pw_uid, account.pw_uid, account.pw_gid, account.pw_gid):
        raise RuntimeError('Incomplete user identity transition')


def service_output(args, emit):
    result = subprocess.run(args, text=True, capture_output=True, timeout=2)
    if result.returncode:
        detail = dict(operation='service_identity', argv=args, returncode=result.returncode,
                      stdout=result.stdout, stderr=result.stderr, monotonic=time.monotonic(),
                      uid=os.getuid(), euid=os.geteuid())
        emit(detail)
        raise RuntimeError('Service identity failed: '+json.dumps(detail))
    return result.stdout


def checked_cpu(cpu, report_only=False):
    if not isinstance(cpu, (int, float)) or not math.isfinite(cpu) or not 0 <= cpu <= 100:
        raise RuntimeError('Invalid CPU measurement')
    return None if report_only else cpu


def cpu_exception(arguments):
    if arguments not in ([], ['--diagnostic-cpu-report-only']):
        raise ValueError('Unknown arguments; CPU exception requires exact owner-approved flag')
    return bool(arguments)


def select_hot_threads(before, after, count=2):
    """Select stable native TIDs by actual tick deltas, never Python addresses."""
    ranked = []
    for tid, row in after.items():
        old = before.get(tid)
        if old is not None and row['birth'] == old['birth']:
            delta = row['ticks']-old['ticks']
            if delta > 0:
                ranked.append((delta, int(tid), row['birth']))
    ranked.sort(reverse=True)
    if len(ranked) < count:
        raise RuntimeError('Insufficient stable CPU-active target threads')
    return {str(tid): birth for _, tid, birth in ranked[:count]}


def require_target_threads(current, selected):
    if any(current.get(tid, {}).get('birth') != birth for tid, birth in selected.items()):
        raise RuntimeError('Selected profiling thread exited or changed identity')


def command(pid, output, tids):
    if not isinstance(pid, int) or pid <= 1:
        raise ValueError('invalid target PID')
    if len(tids) != 2 or len(set(tids)) != 2 or any(not isinstance(t, int) or t <= 1 for t in tids):
        raise ValueError('exactly two distinct native target TIDs required')
    return ['/usr/bin/timeout', '--signal=INT', '--kill-after=2s', '13s', str(PERF),
            'record', '-t', ','.join(map(str, tids)), '--no-inherit', '--per-thread',
            '--no-bpf-event', '--num-thread-synthesize', '1', '-e', 'cpu-clock:u',
            '-F', '19', '--strict-freq', '--call-graph', 'dwarf,4096',
            '-m', '64', '--no-buildid', '--no-buildid-cache', '-k', 'CLOCK_MONOTONIC',
            '-o', str(output), '--', '/usr/bin/sleep', '10']


def require_off(status, process_code):
    if not (status.get('state') == 'OFF' or
            status.get('state') == 'RESOURCE BLOCKED' and status.get('driver_stopped') is True):
        raise RuntimeError('Astra not OFF')
    if process_code != 1:
        raise RuntimeError('Astra process present or query failed')


def thread_snapshot(pid):
    result = {}
    for task in Path('/proc', str(pid), 'task').iterdir():
        try:
            fields = (task/'stat').read_text().rsplit(')', 1)[1].split()
            result[task.name] = dict(ticks=int(fields[11])+int(fields[12]),
                birth=int(fields[19]), name=(task/'comm').read_text().strip(),
                schedstat=(task/'schedstat').read_text().strip())
        except FileNotFoundError:
            pass
    return result


def stop_owned(process):
    if process is None or process.poll() is not None:
        return
    as_root()
    try:
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            process.wait(timeout=2)
            return
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
    finally:
        as_user(pwd.getpwnam('jetson'))


def main():
    report_only = cpu_exception(sys.argv[1:])
    if os.geteuid() != 0 or os.environ.get('SUDO_USER') != 'jetson':
        raise SystemExit('Run once with sudo as jetson; do not change global permissions.')
    account = pwd.getpwnam('jetson')
    os.umask(0o077)
    os.initgroups(account.pw_name, account.pw_gid)
    as_user(account)
    os.environ.update(HOME=account.pw_dir, XDG_RUNTIME_DIR=f'/run/user/{account.pw_uid}',
                      DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{account.pw_uid}/bus')
    directory = Path(tempfile.mkdtemp(prefix='evidence-', dir=STAGE))
    report = dict(status='ABORTED', evidence=str(directory), camera_started=False,
                  services_restarted=False, production_changed=False,
                  cpu_policy='OWNER DIAGNOSTIC REPORT ONLY' if report_only else 'STOP >75%')
    process = None
    log = None
    trace = (directory/'telemetry.jsonl').open('x', buffering=1)
    def emit(row):
        trace.write(json.dumps(row, allow_nan=False)+'\n')
        trace.flush()
        os.fsync(trace.fileno())
    try:
        for name, digest in HASHES.items():
            verify(LIVE/name, digest)
        verify(PERF, PERF_SHA)
        if shutil.disk_usage(directory).free < 256*1024*1024:
            raise RuntimeError('Insufficient disk headroom')
        sys.path.insert(0, str(LIVE/'tools/vision3d'))
        import stationary_gate as G
        import stationary_ros_probe as P
        def identities():
            result = G.parse_services(service_output(['systemctl', '--user', 'show', *G.UNITS,
                '-p', 'Id', '-p', 'MainPID', '-p', 'NRestarts', '-p', 'ActiveState'], emit))
            raw = service_output(['systemctl', '--user', 'show', 'rover-status-web',
                '-p', 'MainPID', '-p', 'NRestarts', '-p', 'ActiveState'], emit)
            result['rover-status-web'] = dict(line.split('=', 1) for line in raw.strip().splitlines())
            if any(v['ActiveState'] != 'active' or int(v['MainPID']) <= 1 for v in result.values()):
                raise RuntimeError('Protected service unhealthy')
            return result
        before = identities()
        pid = int(before['rover-status-web']['MainPID'])
        report.update(pid=pid, services_before=before, hz=os.sysconf('SC_CLK_TCK'))
        if Path('/proc', str(pid)).stat().st_uid != account.pw_uid:
            raise RuntimeError('Wrong process owner')
        if b'/home/jetson/project_atlas/scripts/atlas_status_web.py' not in Path('/proc', str(pid), 'cmdline').read_bytes().split(b'\0'):
            raise RuntimeError('Not the reviewed Dashboard command')
        birth = thread_snapshot(pid)[str(pid)]['birth']
        baseline_threads = thread_snapshot(pid)
        selected = {}
        previous, last = G.ticks(), time.monotonic()
        def sample(phase):
            nonlocal previous, last
            time.sleep(max(0, last+1-time.monotonic()))
            now = time.monotonic()
            ticks = G.ticks()
            cpu, dt = G.cpu_delta(previous, ticks), now-last
            previous, last = ticks, now
            threads = thread_snapshot(pid)
            emit(dict(phase=phase, monotonic=now, cpu=cpu, interval_s=dt,
                      threads=threads, observer_cpu_s=time.process_time()))
            if selected:
                require_target_threads(threads, selected)
            admitted_cpu = checked_cpu(cpu, report_only)
            G.require_cpu(admitted_cpu)
            if dt > 1.5:
                raise RuntimeError('Sampling deadline missed')
            snap = P.safety_snapshot()
            health = G.check(admitted_cpu, snap)
            health['cpu_percent'] = cpu
            health['diagnostic_cpu_report_only'] = report_only
            extra = P.extra_safety(snap['ros'])
            with urllib.request.urlopen('http://127.0.0.1:8088/api/vision3d/summary', timeout=2) as response:
                camera = json.load(response)
            require_off(camera, subprocess.run(['pgrep', '-x', 'astra_camera_no'],
                        stdout=subprocess.DEVNULL, timeout=2).returncode)
            if thread_snapshot(pid)[str(pid)]['birth'] != birth:
                raise RuntimeError('Target process changed')
            emit(dict(phase=phase, monotonic=time.monotonic(), health=health, extra=extra))
            if time.monotonic()-now > 1.5:
                raise RuntimeError('Safety check deadline missed')
        for _ in range(5):
            sample('baseline')
        if identities() != before:
            raise RuntimeError('Service changed before profile')
        selected = select_hot_threads(baseline_threads, thread_snapshot(pid))
        report['selected_native_threads'] = selected
        require_target_threads(thread_snapshot(pid), selected)
        # Root is needed only for perf_event_open on this existing target.
        log = (directory/'perf.log').open('xb')
        as_root()
        try:
            process = subprocess.Popen(command(pid, directory/'perf.data', [int(t) for t in selected]), stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True, cwd=directory,
                env={'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C'})
        finally:
            as_user(account)
        emit(dict(phase='profile_start', monotonic=time.monotonic(), profiler_pid=process.pid))
        deadline = time.monotonic()+12
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise RuntimeError('Profiler deadline exceeded')
            sample('profile')
        report['profiler_returncode'] = process.returncode
        if process.returncode != 0:
            raise RuntimeError('perf failed; preserve perf.log; no retry')
        for _ in range(5):
            sample('postflight')
        report['services_after'] = identities()
        if report['services_after'] != before:
            raise RuntimeError('Protected service identity changed')
        for name, digest in HASHES.items():
            verify(LIVE/name, digest)
        report['status'] = 'CAPTURE_COMPLETE_NOT_YET_ANALYZED'
    except BaseException as exc:
        report['error'] = str(exc)
        if hasattr(exc, 'evidence'):
            report['guard_failure'] = exc.evidence
    finally:
        stop_owned(process)
        if log:
            log.close()
        trace.close()
        as_root()
        try:
            for path in directory.iterdir():
                if path.is_file() and not path.is_symlink():
                    os.chown(path, account.pw_uid, account.pw_gid)
                    os.chmod(path, 0o600)
        finally:
            as_user(account)
        data = directory/'perf.data'
        if data.exists():
            report.update(perf_bytes=data.stat().st_size, perf_sha256=hashlib.sha256(data.read_bytes()).hexdigest())
        with (directory/'result.json').open('x') as output:
            json.dump(report, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        print(json.dumps(report, indent=2), flush=True)
    return 0 if report['status'] == 'CAPTURE_COMPLETE_NOT_YET_ANALYZED' else 1


if __name__ == '__main__':
    sys.exit(main())

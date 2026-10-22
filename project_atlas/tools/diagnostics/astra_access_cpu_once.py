#!/usr/bin/env python3
"""Owner-run, bounded ACL recovery and nonblocking Python stack sampling.

No ROS participant, device reset, camera Start, service restart or safety change.
Run as root from the reviewed staging folder; most work uses jetson effective UID.
Temporary ACL recovery only: no udev rules/group changes. No automatic retries.
"""
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import pwd
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request

LIVE = Path('/home/jetson/project_atlas')
HASHES = {
    'tools/vision3d/stationary_gate.py': '0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9',
    'tools/vision3d/stationary_ros_probe.py': 'f6321da4961482064a6d278e368efbb25540d5a3178ee14900255972b269a384',
    'scripts/atlas_status_web.py': '98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79',
}
PROFILER_SHA = '972918b5d6af92649ec086ffdd89cefa0d725fd14844434c766f58494a1c4f8e'
DEVICES = {'1-2.3.1.2': ('0403', '/dev/bus/usb/001/014'),
           '1-2.3.1.1': ('0501', '/dev/bus/usb/001/011')}


def verified_hash(path, expected):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError('Hash mismatch: ' + str(path))
    return actual


def usb_identity(sysroot=Path('/sys/bus/usb/devices'), inspect=os.stat):
    """Fail on ambiguity or renumbering; never grant access to a substituted node."""
    found = {}
    for path in sysroot.iterdir():
        if not (path / 'idVendor').exists():
            continue
        vid = (path / 'idVendor').read_text().strip()
        pid = (path / 'idProduct').read_text().strip()
        if vid == '2bc5' and pid in ('0403', '0501'):
            if path.name not in DEVICES or pid != DEVICES[path.name][0]:
                raise RuntimeError('Unexpected/ambiguous Astra topology')
            node = '/dev/bus/usb/%03d/%03d' % (int((path/'busnum').read_text()),
                                               int((path/'devnum').read_text()))
            if node != DEVICES[path.name][1]:
                raise RuntimeError('Astra renumbered; review required before grant')
            st = inspect(node)
            if not stat.S_ISCHR(st.st_mode):
                raise RuntimeError('USB node is not a character device')
            expected_minor = (int((path/'busnum').read_text())-1)*128 + int((path/'devnum').read_text())-1
            if os.major(st.st_rdev) != 189 or os.minor(st.st_rdev) != expected_minor:
                raise RuntimeError('USB device number mismatch')
            found[node] = [path.name, vid, pid, st.st_ino, st.st_rdev]
    if len(found) != 2:
        raise RuntimeError('Both verified Astra interfaces required')
    return found


def require_sensors(ros):
    # Same sensor requirements as the deployed probe, before the separate ACL repair.
    for key in ('lidar','imu_full','enc_m1','enc_m2','enc_m3','enc_m4',
                'camera_info','drive_pid','mission_status','motor_speed'):
        age = ros.get(key, {}).get('age')
        if not isinstance(age, (int, float)) or not math.isfinite(age) or not 0 <= age <= 2:
            raise RuntimeError('Stale required sensor: ' + key)
    drive = ros['drive_pid']['value']
    drive = json.loads(drive) if isinstance(drive, str) else drive
    if len(drive.get('wheels', [])) != 4 or any(w.get('output') != 0 or w.get('target_mps') != 0 for w in drive['wheels']):
        raise RuntimeError('Nonzero or unknown wheel commands')
    if ros['mission_status']['value'] != 'READY' or ros['motor_speed']['value'] != 0:
        raise RuntimeError('Mission/motor not idle')
    if ros['camera_info']['value'].get('publisher_count', 1) < 1:
        raise RuntimeError('Pi camera publisher missing')


def require_camera_off(status, process_returncode):
    stopped = status.get('state') == 'OFF' or (
        status.get('state') == 'RESOURCE BLOCKED' and status.get('driver_stopped') is True)
    if not stopped or process_returncode != 1:
        raise RuntimeError('Astra not confirmed OFF')


def profiler_command(binary, pid, output):
    return ['/usr/bin/timeout', '--signal=INT', '--kill-after=2s', '12s', str(binary),
            'record', '--pid', str(pid), '--duration', '10', '--rate', '20',
            '--threads', '--nonblocking', '--format', 'speedscope', '--output', str(output)]


def thread_ticks(pid):
    result = {}
    for path in Path('/proc', str(pid), 'task').iterdir():
        try:
            fields = (path/'stat').read_text().rsplit(')', 1)[1].split()
            result[path.name] = {'ticks': int(fields[11])+int(fields[12]),
                                 'birth': int(fields[19]),
                                 'schedstat': (path/'schedstat').read_text().strip()}
        except FileNotFoundError:
            pass  # An exited thread is absent, not zero CPU.
    return result


def profiler_ticks(process):
    """Separate profiler/timeout CPU from target CPU; missing PID is not zero."""
    if process is None:
        return {}
    pending = [process.pid]
    found = {}
    while pending:
        pid = pending.pop()
        if str(pid) in found:
            continue
        try:
            directory = Path('/proc', str(pid))
            fields = (directory/'stat').read_text().rsplit(')', 1)[1].split()
            found[str(pid)] = {'ticks': int(fields[11])+int(fields[12]), 'birth': int(fields[19])}
            pending.extend(map(int, (directory/'task'/str(pid)/'children').read_text().split()))
        except FileNotFoundError:
            pass
    return found


def main():
    if os.getuid() != 0 or os.environ.get('SUDO_USER') != 'jetson':
        raise RuntimeError('Run via sudo as jetson; no automatic privilege changes')
    os.umask(0o077)
    user = pwd.getpwnam('jetson')
    os.initgroups('jetson', user.pw_gid)
    os.setresgid(user.pw_gid, user.pw_gid, 0)
    os.setresuid(user.pw_uid, user.pw_uid, 0)
    os.environ.update(HOME=user.pw_dir, XDG_RUNTIME_DIR='/run/user/'+str(user.pw_uid),
                      DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(user.pw_uid)+'/bus')
    stage = Path(__file__).resolve().parent
    out = Path(tempfile.mkdtemp(prefix='evidence-', dir=stage))
    os.chmod(out, 0o700)
    print('Evidence: ' + str(out), flush=True)
    log = (out/'telemetry.jsonl').open('x')
    report = {'status': 'NOT_STARTED', 'camera_started': False, 'services_restarted': False}
    process = None
    changed = False
    identities = None
    services = None

    def event(**data):
        log.write(json.dumps({'monotonic': time.monotonic(), **data})+'\n')
        log.flush()

    def root_call(args):
        os.setresuid(0, 0, 0)
        try:
            return subprocess.check_output(args, text=True, timeout=5)
        finally:
            os.setresuid(user.pw_uid, user.pw_uid, 0)

    def stop_profiler():
        if process is not None and process.poll() is None:
            os.setresuid(0, 0, 0)
            try:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
            finally:
                os.setresuid(user.pw_uid, user.pw_uid, 0)

    try:
        for rel, digest in HASHES.items():
            verified_hash(LIVE/rel, digest)
        binary = stage/'py-spy'
        verified_hash(binary, PROFILER_SHA)
        sys.path.insert(0, str(LIVE/'tools/vision3d'))
        G = importlib.import_module('stationary_gate')
        P = importlib.import_module('stationary_ros_probe')
        services = G.services()
        if any(v['ActiveState'] != 'active' or v['MainPID'] == '0' for v in services.values()):
            raise RuntimeError('Protected service not active')
        pid = int(subprocess.check_output(['systemctl','--user','show','rover-status-web',
                                          '-p','MainPID','--value'], text=True, timeout=2))
        if pid <= 1 or 'atlas_status_web.py' not in Path('/proc',str(pid),'cmdline').read_text():
            raise RuntimeError('Unexpected dashboard PID')
        birth = thread_ticks(pid)[str(pid)]['birth']
        report.update(pid=pid, hz=os.sysconf('SC_CLK_TCK'), services_before=services)
        previous = G.ticks()
        last = time.monotonic()

        def sample(phase, usb=False):
            nonlocal previous, last
            time.sleep(max(0, last+1-time.monotonic()))
            now = time.monotonic()
            ticks = G.ticks()
            cpu = G.cpu_delta(previous, ticks)
            interval = now-last
            previous, last = ticks, now
            event(phase=phase, cpu=cpu, interval_s=interval, threads=thread_ticks(pid),
                  observer_cpu_s=time.process_time(), profiler_ticks=profiler_ticks(process))
            G.require_cpu(cpu)
            if interval > 1.5:
                raise RuntimeError('Sampling deadline missed')
            if thread_ticks(pid)[str(pid)]['birth'] != birth:
                raise RuntimeError('Dashboard process identity changed')
            j = P.safety_snapshot()
            health = G.check(cpu, j)
            require_sensors(j['ros'])
            status = json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/vision3d/summary', timeout=2))
            require_camera_off(status, subprocess.run(['pgrep','-x','astra_camera_no'],
                               stdout=subprocess.DEVNULL, timeout=2).returncode)
            if usb:
                if usb_identity() != identities:
                    raise RuntimeError('Astra identity changed')
                for node in identities:
                    if not os.access(node, os.R_OK|os.W_OK, effective_ids=True):
                        raise RuntimeError('Astra access lost')
            event(phase=phase, health=health)
            if time.monotonic()-now > 1:
                raise RuntimeError('Health callback deadline missed')

        for _ in range(3):
            sample('admission')
        identities = usb_identity()
        nodes = sorted(identities)
        acl = subprocess.check_output(['/usr/bin/getfacl','-p',*nodes], text=True, timeout=2)
        (out/'before.acl').write_text(acl)
        report['usb_identities'] = identities
        if usb_identity() != identities:
            raise RuntimeError('Astra changed before grant')
        changed = True  # Roll back even if setfacl only partially succeeds.
        root_call(['/usr/bin/setfacl','-m','u:jetson:rw',*nodes])
        for node in nodes:
            fd = os.open(node, os.O_RDWR | os.O_CLOEXEC)
            os.close(fd)  # No read/write/ioctl or interface claim.
        (out/'after.acl').write_text(subprocess.check_output(['/usr/bin/getfacl','-p',*nodes], text=True, timeout=2))
        report['access_recovered'] = True
        for _ in range(5):
            sample('baseline', True)
        # CPU interval covers launch, not just steady sampling.
        errorlog = (out/'profiler.log').open('x')
        os.setresuid(0, 0, 0)
        try:
            process = subprocess.Popen(profiler_command(binary, pid, out/'stacks.json'),
                                       stdout=errorlog, stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            os.setresuid(user.pw_uid, user.pw_uid, 0)
        event(phase='profile_start', profiler_supervisor_pid=process.pid)
        while process.poll() is None:
            sample('profile', True)
        if process.returncode != 0:
            raise RuntimeError('Profiler failed: '+str(process.returncode))
        os.setresuid(0, 0, 0)
        try:
            profile = out/'stacks.json'
            if not profile.is_file() or profile.is_symlink():
                raise RuntimeError('Missing or unsafe profiler output')
            os.chown(profile, user.pw_uid, user.pw_gid)
            os.chmod(profile, 0o600)
        finally:
            os.setresuid(user.pw_uid, user.pw_uid, 0)
        for _ in range(5):
            sample('postflight', True)
        payload = json.loads((out/'stacks.json').read_text())
        if not payload.get('profiles'):
            raise RuntimeError('No thread profiles captured')
        if G.services() != services:
            raise RuntimeError('Protected service identities changed')
        report.update(status='PASS', acl_state='targeted temporary jetson RW grants retained',
                      profile_sha256=hashlib.sha256((out/'stacks.json').read_bytes()).hexdigest(),
                      services_after=G.services())
    except BaseException as exc:
        stop_profiler()
        report.update(status='ABORTED', error=repr(exc))
        if changed:
            try:
                if usb_identity() != identities:
                    raise RuntimeError('Do not restore ACL onto changed device identity')
                root_call(['/usr/bin/setfacl','--restore='+str(out/'before.acl')])
                report['acl_state'] = 'saved ACL restored after failed operation'
            except Exception as rollback_error:
                report['rollback_error'] = repr(rollback_error)
        if services is not None:
            try:
                report['services_after'] = G.services()
                report['services_unchanged'] = report['services_after'] == services
            except Exception as post_error:
                report['postflight_error'] = repr(post_error)
    finally:
        stop_profiler()
        # Profiler output is private; only fix ownership of this run's own regular files.
        os.setresuid(0, 0, 0)
        try:
            for item in out.iterdir():
                if item.is_file() and not item.is_symlink():
                    os.chown(item, user.pw_uid, user.pw_gid)
                    os.chmod(item, 0o600)
        finally:
            os.setresuid(user.pw_uid, user.pw_uid, 0)
        (out/'result.json').write_text(json.dumps(report, indent=2))
        log.close()
        print(json.dumps(report, indent=2), flush=True)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())

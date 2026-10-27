#!/usr/bin/env python3
"""B1-only durable maintenance interlock. Never opens serial or commands motors.

Provision/init and all CLI mutations require separate deployment/operation approval.
Missing/corrupt state denies base starts/recovery. No timeout automatically releases.
"""
import argparse
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import subprocess
import time
import uuid
import urllib.request

BASE = 'rover-base-telemetry.service'
ROOT = Path.home() / '.local/state/project_atlas/b1_interlock'
MAX_SESSION = 900.0
MAX_READ = 180.0
HEARTBEAT_MAX = 2.0


class Denied(RuntimeError):
    pass


class Interlock:
    def __init__(self, root=ROOT, clock=time.monotonic, boot=None):
        self.root = Path(root)
        self.clock = clock
        self.boot = boot if boot is not None else Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    @contextlib.contextmanager
    def lock(self, name='dispatch', blocking=True):
        # Never create a missing installation implicitly.
        fd = os.open(self.root / (name + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            deadline = time.monotonic() + 2
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if not blocking or time.monotonic() >= deadline:
                        raise
                    time.sleep(.01)
            yield
        finally:
            os.close(fd)

    def load(self):
        try:
            d = json.loads((self.root / 'state.json').read_text())
            if d['version'] != 1 or d['phase'] not in {'IDLE', 'ARMED', 'READING', 'ABORTED', 'RESUMING', 'VERIFYING'}:
                raise ValueError('invalid state')
            if d['phase'] == 'IDLE':
                if set(d) - {'version', 'phase', 'completed_session'}:
                    raise ValueError('ambiguous idle state')
            else:
                if not isinstance(d.get('session'), str) or len(d['session']) != 32 or any(c not in '0123456789abcdef' for c in d['session']):
                    raise ValueError('invalid session')
                if not isinstance(d.get('boot'), str) or not d['boot'] or type(d.get('monitor_seen')) is not bool:
                    raise ValueError('invalid boot/monitor evidence')
                for k in ('heartbeat', 'deadline'):
                    if type(d.get(k)) not in (int, float) or not math.isfinite(d[k]):
                        raise ValueError('invalid deadline')
                if d['phase'] == 'READING' and (type(d.get('read_deadline')) not in (int, float) or not math.isfinite(d['read_deadline'])):
                    raise ValueError('invalid read deadline')
            return d
        except Exception as exc:
            raise Denied('missing/ambiguous maintenance state') from exc

    def save(self, d):
        p = self.root / ('state.' + uuid.uuid4().hex + '.tmp')
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(d, f); f.flush(); os.fsync(f.fileno())
        os.replace(p, self.root / 'state.json')
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def initialize(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.save({'version': 1, 'phase': 'IDLE'})

    @staticmethod
    def safe(status, elapsed=0.0):
        try:
            ros = status['ros']
            p, c = ros['control_policy'], ros['cmd_vel']
            for item in (p, c):
                age = item['age']
                if type(age) not in (float, int) or not math.isfinite(age) or not 0 <= age or age + elapsed > 1:
                    return False
            policy = json.loads(p['value']) if isinstance(p['value'], str) else p['value']
            cmd = c['value']
            return (policy['stop_latched'] is True and policy['manual_only'] is True
                    and policy['commission_armed'] is False and policy['source'] == 'STOPPED'
                    and all(type(cmd[k]) in (int, float) and cmd[k] == 0 for k in ('lin', 'ang')))
        except Exception:
            return False

    def owned(self, d, session):
        if d.get('session') != session or not session or d.get('boot') != self.boot:
            raise Denied('wrong session/boot; manual reconciliation required')

    def arm(self, status, no_jobs):
        # Serializes with recovery dispatch through systemctl completion.
        sampled = time.monotonic()
        with self.lock(blocking=False), self.lock('state'):
            d = self.load()
            if d['phase'] != 'IDLE' or not no_jobs() or not self.safe(status, time.monotonic() - sampled):
                raise Denied('unsafe, already armed or in-flight systemd job')
            now = self.clock()
            d = dict(version=1, phase='ARMED', session=uuid.uuid4().hex,
                     boot=self.boot, deadline=now + MAX_SESSION, heartbeat=now, monitor_seen=False)
            self.save(d)
            return d['session']

    def heartbeat(self, session, status):
        sampled = time.monotonic()
        with self.lock('state'):
            d = self.load(); self.owned(d, session)
            self.fresh(d)
            now = self.clock()
            if not self.safe(status, time.monotonic() - sampled) or now >= d['deadline']:
                d['phase'] = 'ABORTED'; self.save(d)
                raise Denied('safety/deadline failure; interlock retained')
            d['heartbeat'] = now; d['monitor_seen'] = True; self.save(d)

    def fresh(self, d):
        now = self.clock()
        if not (0 <= now - d.get('heartbeat', -1e9) <= HEARTBEAT_MAX and now < d.get('deadline', 0)):
            d['phase'] = 'ABORTED'; self.save(d)
            raise Denied('maintenance supervisor stale/expired; interlock retained')

    def begin_read(self, session):
        with self.lock('state'):
            d = self.load(); self.owned(d, session); self.fresh(d)
            if d['phase'] != 'ARMED' or d.get('monitor_seen') is not True:
                raise Denied('one read attempt only')
            d.update(phase='READING', read_deadline=min(self.clock() + MAX_READ, d['deadline']))
            self.save(d)

    def check_read(self, session):
        with self.lock('state'):
            d = self.load(); self.owned(d, session); self.fresh(d)
            if d['phase'] != 'READING' or self.clock() >= d['read_deadline']:
                d['phase'] = 'ABORTED'; self.save(d)
                raise Denied('read permission absent/expired')

    @contextlib.contextmanager
    def reader(self, session):
        # Held until the serial descriptor closes. One durable claim per attempt.
        with self.lock('reader', blocking=False):
            self.check_read(session)
            with self.lock('state'):
                d = self.load(); self.owned(d, session); self.fresh(d)
                if d['phase'] != 'READING' or d.get('reader_claimed'):
                    raise Denied('read attempt already consumed')
                d['reader_claimed'] = True; self.save(d)
            try:
                yield
            finally:
                self.abort(session)

    @contextlib.contextmanager
    def recovery_dispatch(self):
        with self.lock():
            if self.load()['phase'] != 'IDLE':
                raise Denied('B1 maintenance blocks base recovery; fault reporting remains active')
            yield

    def start_gate(self):
        # Separate lock: recovery holds dispatch while systemctl runs this gate.
        with self.lock('state'):
            d = self.load()
            if d['phase'] == 'IDLE':
                return True
            if d['phase'] == 'RESUMING' and d.get('boot') == self.boot:
                self.fresh(d)
                d['phase'] = 'VERIFYING'; self.save(d)
                return True  # exactly one restoration start, no automatic retry
            return False

    def abort(self, session):
        with self.lock('state'):
            d = self.load(); self.owned(d, session)
            d['phase'] = 'ABORTED'; self.save(d)

    def resume(self, session, status, reset_confirmed, port_free):
        sampled = time.monotonic()
        with self.lock(), self.lock('reader', blocking=False), self.lock('state'):
            d = self.load(); self.owned(d, session); self.fresh(d)
            if d['phase'] not in {'READING', 'ABORTED', 'ARMED'} or not reset_confirmed or not port_free() or not self.safe(status, time.monotonic() - sampled):
                raise Denied('restoration prerequisites not satisfied')
            self.fresh(d)
            d['phase'] = 'RESUMING'; self.save(d)

    def reconcile(self, session, status, reset_confirmed, port_free):
        """Explicit recovery-only renewal after timeout; never authorizes another read."""
        sampled = time.monotonic()
        with self.lock(blocking=False), self.lock('reader', blocking=False), self.lock('state'):
            d = self.load()
            if d.get('session') != session or not session or d['phase'] == 'IDLE':
                raise Denied('session reconciliation refused')
            if not reset_confirmed or not port_free() or not self.safe(status, time.monotonic() - sampled):
                raise Denied('physical normal-reset and released port required')
            now = self.clock()
            d.update(phase='ABORTED', boot=self.boot, heartbeat=now, deadline=now + MAX_READ, monitor_seen=False)
            self.save(d)

    def release(self, session, status, restored, operator_confirmed):
        with self.lock(), self.lock('state'):
            d = self.load(); self.owned(d, session); self.fresh(d)
            if d['phase'] != 'VERIFYING' or not operator_confirmed or not self.safe(status) or not restored():
                raise Denied('restoration not verified; interlock retained')
            self.save({'version': 1, 'phase': 'IDLE', 'completed_session': session})


def live_status():
    with urllib.request.urlopen('http://127.0.0.1:8088/api/status', timeout=1) as r:
        return json.load(r)


def no_base_jobs():
    result = subprocess.run(['systemctl', '--user', 'list-jobs', '--no-legend', '--no-pager'],
                            capture_output=True, text=True, check=True, timeout=3)
    return not any(BASE in line.split() for line in result.stdout.splitlines())


def verified_port_free(port):
    """One read-only ownership query; never probe serial or retry fuser."""
    from serial.tools import list_ports
    matches = [p for p in list_ports.comports() if os.path.realpath(p.device) == os.path.realpath(port)]
    if len(matches) != 1 or (matches[0].vid, matches[0].pid, matches[0].location) != (0x1a86, 0x7523, '1-2.2.3'):
        raise Denied('Yahboom USB identity not verified')
    result = subprocess.run(['fuser', port], capture_output=True, timeout=2)
    if result.returncode == 0:
        return False
    if result.returncode != 1 or result.stderr.strip():
        raise Denied('serial ownership ambiguous')
    return True


def base_state():
    result = subprocess.run(['systemctl', '--user', 'show', BASE,
                             '-p', 'ActiveState', '-p', 'MainPID', '-p', 'ControlPID', '-p', 'NRestarts'],
                            capture_output=True, text=True, check=True, timeout=3)
    return dict(line.split('=', 1) for line in result.stdout.splitlines())


def require_inactive():
    state = base_state()
    if state.get('ActiveState') != 'inactive' or state.get('MainPID') != '0' or state.get('ControlPID') != '0' or not no_base_jobs():
        raise Denied('base not quiescent; do not touch BOOT0/RESET')


def packet_counter(status):
    """Use actual serial packet progression, not wheel rotation or an old ready log."""
    if not Interlock.safe(status):
        raise Denied('fresh stop policy/zero commands absent')
    item = status['ros']['encoder_health']
    age = item['age']
    v = json.loads(item['value']) if isinstance(item['value'], str) else item['value']
    packet_age = v['packet_age_s']
    if any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1 for x in (age, packet_age)):
        raise Denied('encoder packets stale')
    count = v['serial_encoder_packets']
    if v['packet_fresh'] is not True or type(count) is not int or count <= 0:
        raise Denied('encoder packet evidence invalid')
    return count


def verify_restored(status_reader=live_status, state_reader=base_state, sleep=time.sleep):
    initial = state_reader()
    if initial.get('ActiveState') != 'active' or int(initial.get('MainPID', '0')) <= 0:
        raise Denied('base not active')
    first = previous = packet_counter(status_reader())
    for _ in range(5):
        sleep(1)
        current = packet_counter(status_reader())
        if current < previous:
            raise Denied('serial packet counter reset')
        previous = current
    final = state_reader()
    if any(final.get(k) != initial.get(k) for k in ('ActiveState', 'MainPID', 'NRestarts')) or previous <= first:
        raise Denied('stable live telemetry not proven')
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['start-gate', 'status', 'watch', 'arm', 'begin-read', 'check-read', 'abort', 'reconcile', 'resume', 'release'])
    p.add_argument('--session')
    p.add_argument('--port')
    p.add_argument('--confirm-normal-reset', action='store_true')
    p.add_argument('--confirm-restored', action='store_true')
    a = p.parse_args(); gate = Interlock()
    try:
        if a.action == 'start-gate':
            return 0 if gate.start_gate() else 1
        if a.action == 'status':
            print(json.dumps(gate.load())); return 0
        if a.action == 'arm':
            print(gate.arm(live_status(), no_base_jobs), flush=True); return 0
        if a.action == 'abort':
            gate.abort(a.session); return 0
        if a.action == 'check-read':
            gate.check_read(a.session); return 0
        if a.action == 'begin-read':
            require_inactive()
            if not a.port or not verified_port_free(a.port):
                raise Denied('verified port not free')
            gate.begin_read(a.session); return 0
        if a.action in ('reconcile', 'resume'):
            require_inactive()
            if not a.port or not a.confirm_normal_reset:
                raise Denied('port and physical normal-reset confirmation required')
            method = gate.reconcile if a.action == 'reconcile' else gate.resume
            method(a.session, live_status(), True, lambda: verified_port_free(a.port))
            return 0  # never issues a service start
        if a.action == 'release':
            if not a.confirm_restored:
                raise Denied('operator confirmation required')
            verify_restored()
            gate.release(a.session, live_status(), lambda: True, True)
            return 0
        # Watch only; admission/restoration are deliberately not unattended CLI actions.
        deadline = time.monotonic() + MAX_SESSION
        while time.monotonic() < deadline:
            gate.heartbeat(a.session, live_status())
            time.sleep(0.5)
        gate.abort(a.session)
        return 1
    except Exception as exc:
        print('B1 INTERLOCK REFUSED:', exc, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

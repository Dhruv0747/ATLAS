#!/usr/bin/env python3
"""ATLAS Stage 28: bounded, base-only maintenance window for rover-base-telemetry.service.

Purpose: let ONE owner-approved, supervised restart of the Yahboom base happen without a competing
restart from atlas-sensor-recovery, from systemd's own Restart=on-failure, or from anything else.

Design (reuses the Stage 28 B1 interlock safeguards; differs where B1 was unsafe for normal boots):
  * State lives ONLY in /run/user/<uid>/atlas-base-maintenance (tmpfs). A reboot always returns to normal.
    No persistent file can ever stop the base from starting at boot (the B1 design could).
  * lease.json is written atomically (O_EXCL temp, fsync, rename, directory fsync), mode 0600, never followed
    through a symlink, size-capped, bound to this boot_id, to the owner PID *and* its kernel start time
    (no PID-reuse ambiguity), and to a CLOCK_BOOTTIME deadline (immune to wall-clock jumps at boot).
  * Verdict NONE    : no lease -> recovery and systemd behave exactly as today.
    Verdict ACTIVE  : valid lease -> recovery withholds base restarts (fault reporting stays on);
                      the runtime ExecCondition gate admits only explicitly authorised starts (one each).
    Verdict INVALID : anything ambiguous (corrupt, expired, owner gone, wrong boot, bad mode/owner) ->
                      FAIL CLOSED: base restarts stay withheld and the reason is reported until an operator
                      runs `release`/`abandon` or the Jetson reboots. Nothing auto-releases on a timeout.
  * dispatch.lock serialises recovery's base restart with arming: recovery holds it from its final lease
    check until `systemctl restart` returns, so a lease can never be armed "between" check and restart.
  * ack.json: recovery's proof that the *running* recovery process saw this session and whether a base
    restart of its own is still in flight. The deployer never restarts the base without a fresh ack.

This module never opens a serial port, never publishes ROS messages and never commands motors.
CLI mutations other than start-gate are for the reviewed deployer only.
"""
import argparse
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
import uuid

BASE = 'rover-base-telemetry.service'
VERSION = 1
MAX_LEASE_S = 600.0
MAX_TOKENS = 2            # one deployment start + at most one rollback start, never more
MAX_FILE_BYTES = 4096
PHASES = ('HOLD', 'AUTHORIZED', 'STARTED', 'RELEASED')
NONE, ACTIVE, INVALID = 'NONE', 'ACTIVE', 'INVALID'


def boottime():
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def current_boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def proc_start_ticks(pid):
    """Kernel start time of pid (field 22 of /proc/<pid>/stat) or None if the process is gone."""
    try:
        raw = Path(f'/proc/{int(pid)}/stat').read_text()
        return int(raw[raw.rindex(')') + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def default_root():
    return Path(f'/run/user/{os.getuid()}') / 'atlas-base-maintenance'


class Refused(RuntimeError):
    pass


class Verdict:
    __slots__ = ('state', 'reason', 'lease')

    def __init__(self, state, reason='', lease=None):
        self.state, self.reason, self.lease = state, reason, lease

    @property
    def hold(self):
        return self.state != NONE

    def __repr__(self):
        return f'Verdict({self.state}, {self.reason!r})'


def _finite(x):
    return type(x) in (int, float) and math.isfinite(x)


class Maintenance:
    def __init__(self, root=None, clock=boottime, boot=None, start_ticks=proc_start_ticks, uid=None):
        self.root = Path(root) if root is not None else default_root()
        self.clock = clock
        self.boot = boot if boot is not None else current_boot_id()
        self.start_ticks = start_ticks
        self.uid = os.getuid() if uid is None else uid
        self.lease_path = self.root / 'lease.json'
        self.ack_path = self.root / 'ack.json'

    # ---------- filesystem primitives ----------
    def _check_root(self, create=False):
        """Returns False when the root is absent (and not created). Raises Refused if it is unsafe."""
        try:
            st = os.lstat(self.root)
        except FileNotFoundError:
            if not create:
                return False
            try:
                os.mkdir(self.root, 0o700)
            except FileExistsError:
                pass
            st = os.lstat(self.root)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise Refused('maintenance root is not a real directory')
        if st.st_uid != self.uid or st.st_mode & 0o077:
            raise Refused('maintenance root owner/mode unsafe')
        return True

    @contextlib.contextmanager
    def lock(self, name, timeout=2.0):
        """flock on <root>/<name>.lock. timeout=0 -> non-blocking. Raises Refused when busy."""
        self._check_root(create=True)
        fd = os.open(self.root / f'{name}.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise Refused(f'{name} lock busy')
                    time.sleep(0.01)
            yield
        finally:
            os.close(fd)   # closing releases the flock

    def _read(self, path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != self.uid or st.st_mode & 0o077:
                raise ValueError('file type/owner/mode unsafe')
            if st.st_size > MAX_FILE_BYTES:
                raise ValueError('file too large')
            data = os.read(fd, MAX_FILE_BYTES + 1)
        finally:
            os.close(fd)
        d = json.loads(data.decode('utf-8'))
        if not isinstance(d, dict):
            raise ValueError('not an object')
        return d

    def _write(self, path, d):
        tmp = self.root / f'.{path.name}.{uuid.uuid4().hex}.tmp'
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(d, f, separators=(',', ':'))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        dfd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)

    # ---------- verdict ----------
    def evaluate(self):
        try:
            if not self._check_root():
                return Verdict(NONE, 'no maintenance directory')
        except Refused as exc:
            return Verdict(INVALID, str(exc))
        try:
            d = self._read(self.lease_path)
        except FileNotFoundError:
            return Verdict(NONE, 'no lease')
        except Exception as exc:   # corrupt, symlink, wrong owner/mode, oversized
            return Verdict(INVALID, f'unreadable lease ({type(exc).__name__}: {exc})')
        try:
            self._validate(d)
        except ValueError as exc:
            return Verdict(INVALID, str(exc), d)
        if d['phase'] == 'RELEASED':
            return Verdict(NONE, 'released', d)
        now = self.clock()
        if self.start_ticks(d['owner_pid']) != d['owner_start']:
            return Verdict(INVALID, 'maintenance owner process is gone', d)
        if not d['created'] - 1.0 <= now:
            return Verdict(INVALID, 'lease created in the future', d)
        if now >= d['deadline']:
            return Verdict(INVALID, 'lease deadline passed without release', d)
        return Verdict(ACTIVE, d['phase'], d)

    def _validate(self, d):
        if d.get('version') != VERSION or d.get('service') != BASE:
            raise ValueError('wrong lease version/service')
        s = d.get('session')
        if not isinstance(s, str) or len(s) != 32 or any(c not in '0123456789abcdef' for c in s):
            raise ValueError('invalid session')
        if d.get('boot') != self.boot:
            raise ValueError('lease belongs to another boot')
        if d.get('phase') not in PHASES:
            raise ValueError('invalid phase')
        for k in ('owner_pid', 'owner_start', 'tokens', 'used'):
            if type(d.get(k)) is not int or d[k] < 0:
                raise ValueError(f'invalid {k}')
        if d['owner_pid'] <= 1 or not d['used'] <= d['tokens'] <= MAX_TOKENS:
            raise ValueError('invalid owner/tokens')
        if not (_finite(d.get('created')) and _finite(d.get('deadline'))):
            raise ValueError('invalid timing')
        if not 0 < d['deadline'] - d['created'] <= MAX_LEASE_S:
            raise ValueError('lease longer than allowed')
        if not isinstance(d.get('purpose'), str) or not 0 < len(d['purpose']) <= 200:
            raise ValueError('invalid purpose')

    # ---------- deployer operations ----------
    def arm(self, purpose, duration_s, owner_pid=None, wait_s=0.0):
        """Create the lease. Recovery holds dispatch for its whole base attempt (restart + confirm loop); wait at
        most wait_s for that attempt to finish, then refuse. Never waits *into* a restart."""
        if not 0 < duration_s <= MAX_LEASE_S:
            raise Refused('duration outside 0..%d s' % MAX_LEASE_S)
        owner_pid = os.getpid() if owner_pid is None else owner_pid
        start = self.start_ticks(owner_pid)
        if start is None:
            raise Refused('owner process not found')
        self._check_root(create=True)
        with self.lock('dispatch', timeout=max(0.0, float(wait_s))), self.lock('state'):
            v = self.evaluate()
            if v.state != NONE:
                raise Refused(f'existing maintenance state {v.state}: {v.reason}')
            with contextlib.suppress(FileNotFoundError):
                os.unlink(self.ack_path)
            now = self.clock()
            d = dict(version=VERSION, service=BASE, session=uuid.uuid4().hex, boot=self.boot,
                     owner_pid=owner_pid, owner_start=start, created=now, deadline=now + duration_s,
                     phase='HOLD', tokens=0, used=0, purpose=purpose)
            self._write(self.lease_path, d)
            return d['session']

    def _owned(self, session):
        v = self.evaluate()
        if v.state != ACTIVE or v.lease.get('session') != session:
            raise Refused(f'session not active ({v.state}: {v.reason})')
        return v.lease

    def authorize_start(self, session):
        with self.lock('state'):
            d = self._owned(session)
            if d['phase'] not in ('HOLD', 'STARTED') or d['used'] != d['tokens'] or d['tokens'] >= MAX_TOKENS:
                raise Refused('start authorisation refused (pending token or budget exhausted)')
            d.update(phase='AUTHORIZED', tokens=d['tokens'] + 1)
            self._write(self.lease_path, d)
            return d['tokens']

    def revoke_unused(self, session):
        """Withdraw a token the start never consumed (e.g. systemctl failed before ExecCondition ran)."""
        with self.lock('state'):
            d = self._owned(session)
            if d['phase'] == 'AUTHORIZED' and d['used'] < d['tokens']:
                d.update(phase='HOLD', tokens=d['used'])
                self._write(self.lease_path, d)
                return True
            return False

    def start_gate(self):
        """ExecCondition: True admits the start. Any doubt -> False (systemd skips the start, no restart loop)."""
        try:
            with self.lock('state', timeout=2.0):
                v = self.evaluate()
                if v.state == NONE:
                    return True, 'no maintenance lease: normal start'
                if v.state == INVALID:
                    return False, f'maintenance lease INVALID ({v.reason}); start withheld'
                d = v.lease
                if d['phase'] == 'AUTHORIZED' and d['used'] < d['tokens']:
                    d.update(phase='STARTED', used=d['used'] + 1)
                    self._write(self.lease_path, d)
                    return True, f'authorised start {d["used"]}/{d["tokens"]} session={d["session"]}'
                return False, f'maintenance active ({d["phase"]}); unauthorised start withheld'
        except Exception as exc:
            return False, f'gate error {type(exc).__name__}: {exc}; start withheld'

    def read_ack(self):
        try:
            return self._read(self.ack_path)
        except FileNotFoundError:
            return None

    def release(self, session):
        """Mark RELEASED (gate and recovery treat it as NONE). Caller then removes the drop-in, then clear()."""
        with self.lock('dispatch', timeout=5.0), self.lock('state'):
            d = self._owned(session)
            if d['used'] != d['tokens']:
                raise Refused('an authorised start is still pending')
            d['phase'] = 'RELEASED'
            self._write(self.lease_path, d)

    def clear(self, session=None, force=False):
        """Remove lease/ack. Without force only a RELEASED lease of this session is removed."""
        with self.lock('state'):
            if not force:
                d = self._read(self.lease_path)
                if d.get('phase') != 'RELEASED' or d.get('session') != session:
                    raise Refused('refusing to clear a lease that was not released by this session')
            for p in (self.lease_path, self.ack_path):
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(p)

    # ---------- recovery side ----------
    def write_ack(self, session, in_flight, recovery_pid, detail=''):
        with self.lock('state', timeout=0.5):
            self._write(self.ack_path, dict(version=VERSION, session=session, in_flight=bool(in_flight),
                                            recovery_pid=int(recovery_pid),
                                            recovery_start=self.start_ticks(recovery_pid),
                                            written=self.clock(), detail=str(detail)[:200]))

    @contextlib.contextmanager
    def recovery_dispatch(self, timeout=2.0):
        """Held by recovery from its last lease check until `systemctl restart` returns.

        Yields the Verdict evaluated INSIDE the lock; the caller must not restart when verdict.hold.
        Raises Refused (caller must cancel the restart) when the lock or directory is unusable.
        """
        with self.lock('dispatch', timeout=timeout):
            yield self.evaluate()


def main(argv=None):
    p = argparse.ArgumentParser(description='ATLAS base maintenance window (Stage 28).')
    p.add_argument('action', choices=['start-gate', 'status'])
    a = p.parse_args(argv)
    if a.action == 'start-gate':
        ok, why = Maintenance().start_gate()
        print(('ATLAS BASE GATE ADMIT: ' if ok else 'ATLAS BASE GATE WITHHOLD: ') + why, file=sys.stderr, flush=True)
        return 0 if ok else 1
    v = Maintenance().evaluate()
    m = Maintenance()
    print(json.dumps({'state': v.state, 'reason': v.reason, 'lease': v.lease, 'ack': _safe(m.read_ack)}))
    return 0


def _safe(fn):
    try:
        return fn()
    except Exception as exc:
        return {'error': f'{type(exc).__name__}: {exc}'}


if __name__ == '__main__':
    raise SystemExit(main())

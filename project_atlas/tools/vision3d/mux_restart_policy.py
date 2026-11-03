"""Offline Mux policy binding. Production admission rejects absent maintenance authority.

The transaction owner serializes worker/cleanup processes and supplies a hard outer
timeout. This class also limits every systemctl client to the same durable time line.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import time

from restart_policy import Policy, save
from mux_maintenance_protection import Unavailable

UNIT = 'atlas-cmd-vel-mux.service'
SCRIPT = '/home/jetson/project_atlas/scripts/atlas_cmd_vel_mux.py'
FRAGMENT = '/home/jetson/.config/systemd/user/' + UNIT
FRAGMENT_SHA256 = 'eea525252a43db483387f606ae1cbe6e171aa9928095541ac2ad418c877063ad'
CGROUP = '/user.slice/user-1000.slice/user@1000.service/app.slice/' + UNIT
DROPIN = b'[Service]\nRestart=no\n'


class MuxPolicy(Policy):
    WORKER_SECONDS = 60
    CLEANUP_SECONDS = 30

    def __init__(self, root, unit_root, protection=None):
        super().__init__(root, UNIT, unit_root, user=True)
        self.protection = Unavailable() if protection is None else protection
        self.deadline = None
        self.cleaning = False
        self._can_queue_restart = False
        self._accepted_identity = None
        self.budget_file = self.root / 'mux-budget.json'
        self._temp_dropin = self.path.with_suffix('.mux-pending')

    @staticmethod
    def now():
        return time.clock_gettime(time.CLOCK_BOOTTIME)

    @staticmethod
    def boot():
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    @staticmethod
    def resources(cpu, ram, temp):
        for value, limit in ((cpu, 75), (ram, 80), (temp, 70)):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value < limit:
                raise ValueError('strict resource admission')

    def independent_check(self):
        # Fail closed unless reviewed, boot-bound electrical isolation evidence covers now.
        self.protection.verify(self.now(), self.boot())

    def checkpoint(self):
        if self.deadline is None or self.now() >= self.deadline:
            raise TimeoutError('Mux transaction deadline')
        if not self.cleaning:
            self.independent_check()
        if self.now() >= self.deadline:
            raise TimeoutError('Mux transaction deadline')

    def _create_stamp(self, path, stamp):
        # Publish a complete immutable record exactly once. A crash before link
        # leaves evidence in the private transaction directory and consumes no job.
        temp = path.with_suffix('.new')
        with temp.open('x') as out:
            json.dump({'unit': UNIT, 'boot': self.boot(), 'start': stamp}, out, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.link(temp, path)
        temp.unlink()
        self._sync_directory(self.root)

    @staticmethod
    def _sync_directory(directory):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _read_stamp(self, path):
        if path.is_symlink() or not path.is_file():
            raise ValueError('missing or unsafe Mux budget')
        record = json.loads(path.read_text())
        start = record['start']
        if (record['unit'] != UNIT or record['boot'] != self.boot() or
                type(start) not in (int, float) or not math.isfinite(start) or
                not 0 <= start <= self.now()):
            raise ValueError('invalid Mux transaction clock or binding')
        return start

    def begin_budget(self, started=None):
        now = self.now()
        start = now if started is None else started
        if type(start) not in (float, int) or not math.isfinite(start) or not 0 <= start <= now:
            raise ValueError('invalid outer CLOCK_BOOTTIME start')
        if now - start >= self.WORKER_SECONDS:
            raise TimeoutError('Mux worker deadline')
        if self.budget_file.exists() or self._cleanup_start() is not None or self.state.exists():
            raise ValueError('Mux transaction already used')
        self._create_stamp(self.budget_file, start)
        self.deadline = start + self.WORKER_SECONDS
        self.checkpoint()

    def _cleanup_start(self):
        # Atomic directory creation commits the *whole* timestamp in the name.
        # A killed writer never leaves a truncated timestamp file. The outer
        # transaction lock serializes worker and crash-cleanup launchers.
        prefix = 'mux-cleanup-start-ns-'
        markers = list(self.root.glob(prefix + '*'))
        if not markers:
            return None
        if len(markers) != 1:
            raise ValueError('ambiguous Mux cleanup budget')
        marker = markers[0]
        stamp = marker.name[len(prefix):]
        if not stamp.isascii() or not stamp.isdigit() or len(stamp) > 22 or marker.is_symlink() or not marker.is_dir():
            raise ValueError('invalid Mux cleanup marker')
        return int(stamp) / 1e9

    def limits(self):
        start = self._read_stamp(self.budget_file)
        return start + self.WORKER_SECONDS, start + self.WORKER_SECONDS + self.CLEANUP_SECONDS

    def resume_budget(self, cleanup=False, cleanup_started=None):
        # A reconstructed worker may only clean up. A fresh activation cannot
        # adopt a previous worker budget or consume a second service start.
        if not cleanup:
            raise ValueError('Mux transaction cannot be resumed for activation')
        start = self._read_stamp(self.budget_file)
        total_end = start + self.WORKER_SECONDS + self.CLEANUP_SECONDS
        if self.now() >= total_end:
            raise TimeoutError('Mux transaction deadline')
        cleanup_start = self._cleanup_start()
        if cleanup_start is None:
            now = self.now()
            entered = now if cleanup_started is None else cleanup_started
            if type(entered) not in (int, float) or not math.isfinite(entered) or not start <= entered <= now:
                raise ValueError('invalid outer cleanup CLOCK_BOOTTIME start')
            stamp = math.ceil(entered * 1e9)
            (self.root / f'mux-cleanup-start-ns-{stamp}').mkdir(mode=0o700)
            self._sync_directory(self.root)
            cleanup_start = stamp / 1e9
        if cleanup_start < start or cleanup_start > self.now() + 1e-9:
            raise ValueError('invalid cleanup timestamp')
        self.deadline = min(total_end, cleanup_start + self.CLEANUP_SECONDS)
        self.cleaning = True
        self.checkpoint()

    def _pid_identity(self, pid):
        if not str(pid).isdigit() or int(pid) <= 0:
            raise ValueError('missing Mux PID')
        proc = Path('/proc', str(pid))

        def start_ticks():
            stat = (proc/'stat').read_text()
            return int(stat[stat.rfind(')') + 2:].split()[19])

        first = start_ticks()
        if ((proc/'cmdline').read_bytes().split(b'\0') != [b'/usr/bin/python3', SCRIPT.encode(), b'']
                or (proc/'exe').resolve(strict=True) != Path('/usr/bin/python3').resolve(strict=True)
                or proc.stat().st_uid != os.getuid()):
            raise ValueError('Mux executable/UID mismatch')
        group = self.prop('ControlGroup')
        if group != CGROUP or '0::' + group not in (proc/'cgroup').read_text().splitlines():
            raise ValueError('Mux cgroup identity mismatch')
        if start_ticks() != first or self.prop('MainPID') != str(pid):
            raise ValueError('Mux identity changed during observation')
        return [int(pid), first]

    def _service_identity(self):
        if self.prop('Id') != UNIT or self.prop('FragmentPath') != FRAGMENT:
            raise ValueError('Mux unit identity mismatch')
        fragment = Path(FRAGMENT)
        if fragment.is_symlink() or hashlib.sha256(fragment.read_bytes()).hexdigest() != FRAGMENT_SHA256:
            raise ValueError('Mux unit fragment drift')

    def prepare(self):
        self.independent_check()
        self.checkpoint()
        if self.cleaning or self._cleanup_start() is not None:
            raise ValueError('Mux transaction already cleaning')
        if (self.state.exists() or self.path.exists() or self.path.is_symlink()
                or self._temp_dropin.exists() or self._temp_dropin.is_symlink()):
            raise ValueError('Mux policy not pristine')
        self._service_identity()
        if (self.prop('ActiveState') != 'active' or self.prop('Restart') != 'always'
                or self.prop('Job') not in ('', '0')):
            raise ValueError('Mux service state drift')
        identity = self._pid_identity(self.prop('MainPID'))
        state = dict(unit=UNIT, original_restart='always', original_pid=str(identity[0]),
                     original_identity=identity, activation=False, rollback=False, restored=False)
        self.checkpoint()
        save(self.state, state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint()
        self._install_owned_dropin(state)
        self.command('daemon-reload')
        if self.prop('Restart') != 'no':
            raise ValueError('Mux temporary restart policy refused')

    def _install_owned_dropin(self, state):
        # Require the native Linux anonymous-file facility. Before the journal is
        # durable the new inode has no name and disappears if the worker dies.
        directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open('.', os.O_TMPFILE | os.O_WRONLY, 0o600, dir_fd=directory)
            with os.fdopen(fd, 'wb') as out:
                out.write(DROPIN)
                out.flush()
                os.fsync(fd)
                info = os.fstat(fd)
                state['dropin_inode'] = [info.st_dev, info.st_ino]
                self.checkpoint()
                save(self.state, state)
                self.checkpoint()
                # linkat follows only our own open descriptor. Both names are
                # installed exclusively on the same filesystem, never replaced.
                descriptors = os.open('/proc/self/fd', os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.link(str(fd), self._temp_dropin.name, src_dir_fd=descriptors,
                            dst_dir_fd=directory, follow_symlinks=True)
                finally:
                    os.close(descriptors)
                self.checkpoint()
                os.link(self._temp_dropin.name, self.path.name, src_dir_fd=directory,
                        dst_dir_fd=directory, follow_symlinks=False)
                os.fsync(directory)
        finally:
            os.close(directory)

    def command(self, *args):
        show = len(args) == 5 and args[:2] == ('show', UNIT) and args[2] == '-p' and args[4] == '--value'
        if not (show or args in (('daemon-reload',), ('stop', UNIT), ('restart', UNIT))):
            raise ValueError('non-Mux command refused')
        if args == ('restart', UNIT) and (self.cleaning or not self._can_queue_restart):
            raise ValueError('unreserved Mux restart prohibited')
        self.checkpoint()
        command = list(args)
        if command[0] in ('stop', 'restart'):
            command.insert(0, '--no-block')
        proc = subprocess.Popen(['/usr/bin/systemctl', '--user', *command], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        end = min(self.deadline, self.now() + 3)
        try:
            while True:
                self.checkpoint()
                left = end - self.now()
                if left <= 0:
                    raise TimeoutError('systemctl client deadline')
                try:
                    out, err = proc.communicate(timeout=min(.05, left))
                    break
                except subprocess.TimeoutExpired:
                    continue
            self.checkpoint()
            if proc.returncode:
                raise RuntimeError(err.strip())
            return out.strip()
        finally:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=min(.2, max(0, self.deadline - self.now())))
                except subprocess.TimeoutExpired:
                    pass
            proc.stdout.close()
            proc.stderr.close()

    def _bound_state(self):
        state = self.load()
        if (state.get('unit') != UNIT or state.get('original_restart') != 'always'
                or state.get('rollback') is not False
                or type(state.get('activation')) is not bool or type(state.get('restored')) is not bool):
            raise ValueError('invalid Mux rollback journal')
        return state

    def restart(self, phase):
        if phase != 'activation':
            raise ValueError('automatic restoration restart prohibited')
        if self.cleaning or self._cleanup_start() is not None:
            raise ValueError('activation after cleanup prohibited')
        self.checkpoint()
        self._service_identity()
        state = self._bound_state()
        if self._pid_identity(self.prop('MainPID')) != state['original_identity']:
            raise ValueError('original Mux process identity drift')
        # Parent persists the activation reservation before queueing the systemd job.
        self._can_queue_restart = True
        try:
            super().restart(phase)
        finally:
            self._can_queue_restart = False
        while True:
            self.checkpoint()
            if self.prop('ActiveState') == 'failed':
                raise ValueError('Mux failed')
            if self.prop('ActiveState') == 'active' and self.prop('Job') in ('', '0'):
                identity = self._pid_identity(self.prop('MainPID'))
                if identity == state['original_identity']:
                    raise ValueError('replacement Mux identity missing')
                return identity
            time.sleep(.05)

    def accept_new_process(self, pid):
        self.checkpoint()
        if self.cleaning or not self._bound_state()['activation']:
            raise ValueError('no Mux activation to accept')
        identity = self._pid_identity(pid)
        if identity == self.load()['original_identity'] or self.prop('ActiveState') != 'active':
            raise ValueError('new Mux identity not established')
        self._accepted_identity = identity

    def restore_healthy(self):
        if self.cleaning or self._accepted_identity is None:
            raise ValueError('live Mux policy restoration not authorized')
        self.checkpoint()
        if self._pid_identity(self.prop('MainPID')) != self._accepted_identity:
            raise ValueError('accepted Mux identity drift')
        state = self._bound_state()
        if (not state['activation'] or state['restored'] or self.prop('Restart') != 'no'
                or self.prop('ActiveState') != 'active' or self.prop('Job') not in ('', '0')):
            raise ValueError('Mux acceptance/policy state drift')
        self._remove_owned_dropin(required=True)
        self.command('daemon-reload')
        if (self.prop('Restart') != state['original_restart'] or self.prop('Job') not in ('', '0')
                or self.prop('ActiveState') != 'active'
                or self._pid_identity(self.prop('MainPID')) != self._accepted_identity):
            raise ValueError('post-reload Mux acceptance failed')
        self.checkpoint()
        state['restored'] = True
        save(self.state, state)
        self.checkpoint()

    def restore_untouched(self):
        raise ValueError('use guarded Mux rollback sequence')

    def stop_and_quiesce(self):
        self.checkpoint()
        if self.prop('MainPID') != '0' or self.prop('Job') not in ('', '0') or self.prop('ActiveState') not in ('inactive', 'failed'):
            self.command('stop', UNIT)
        while True:
            self.checkpoint()
            if (self.prop('MainPID') == '0' and self.prop('Job') in ('', '0')
                    and self.prop('ActiveState') in ('inactive', 'failed')):
                return
            time.sleep(.05)

    def quiesce_for_rollback(self):
        self.checkpoint()
        if not self.cleaning:
            raise ValueError('Mux cleanup not armed')
        if not self.state.exists():
            return
        self._service_identity()
        state = self._bound_state()
        if state['activation']:
            self.stop_and_quiesce()
        elif (self.prop('ActiveState') != 'active'
              or self._pid_identity(self.prop('MainPID')) != state['original_identity']
              or self.prop('Job') not in ('', '0')):
            raise ValueError('original Mux identity changed; manual recovery required')

    def _remove_owned_dropin(self, required):
        identity = self._bound_state().get('dropin_inode')
        self.checkpoint()
        # Verify both names BEFORE removing either. The pending hard link keeps
        # the inode alive and excludes same-byte inode substitution on resume.
        found = []
        for path in (self.path, self._temp_dropin):
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                if required:
                    raise ValueError('missing owned Mux drop-in')
                continue
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_nlink not in (1, 2) or info.st_mode & 0o022
                        or identity != [info.st_dev, info.st_ino]
                        or os.read(fd, len(DROPIN) + 1) != DROPIN):
                    raise ValueError('Mux drop-in ownership mismatch')
                found.append((path, info))
            finally:
                os.close(fd)
        for path, info in found:
            self.checkpoint()
            if not os.path.samestat(info, path.lstat()):
                raise ValueError('Mux drop-in changed during cleanup')
            path.unlink()
            self._sync_directory(path.parent)
    def restore(self):
        raise ValueError('use guarded Mux rollback sequence')

    def cleanup(self):
        self.resume_budget(cleanup=True)
        self.quiesce_for_rollback()
        if not self.state.exists():
            return
        state = self._bound_state()
        self._remove_owned_dropin(required=False)
        # Idempotent even after interruption between unlink and reload.
        self.command('daemon-reload')
        if self.prop('Restart') != state['original_restart']:
            raise ValueError('Mux restart policy restoration failed')
        self.quiesce_for_rollback()
        state['restored'] = True
        self.checkpoint()
        save(self.state, state)
        self.checkpoint()

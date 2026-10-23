import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

FILE = Path(__file__).resolve().parents[1]/'tools/diagnostics/native_dashboard_cpu_once.py'
spec = importlib.util.spec_from_file_location('native_cpu', FILE)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class NativeProfileTests(unittest.TestCase):
    def test_target_and_bounds(self):
        c = M.command(1973, Path('/tmp/private/perf.data'))
        self.assertEqual(c[c.index('-p')+1], '1973')
        self.assertIn('13s', c)
        self.assertEqual(c[-2:], ['/usr/bin/sleep', '10'])
        self.assertEqual(c[c.index('-F')+1], '19')
        self.assertEqual(c[c.index('-e')+1], 'cpu-clock:u')
        self.assertIn('--no-inherit', c)
        self.assertNotIn('-a', c)
        self.assertIn('dwarf,4096', c)
        self.assertIn('--no-buildid-cache', c)

    def test_invalid_pid(self):
        for pid in (0, -1, 1, '1973', None):
            with self.assertRaises(ValueError):
                M.command(pid, Path('/tmp/x'))

    def test_camera_off(self):
        M.require_off({'state': 'OFF'}, 1)
        M.require_off({'state': 'RESOURCE BLOCKED', 'driver_stopped': True}, 1)
        for state, code in [({'state': 'OFF'}, 0), ({'state': 'OFF'}, 2),
                            ({'state': 'DEPTH'}, 1), ({'state': 'RESOURCE BLOCKED'}, 1)]:
            with self.assertRaises(RuntimeError):
                M.require_off(state, code)

    def test_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'file'
            path.write_bytes(b'x')
            M.verify(path, M.hashlib.sha256(b'x').hexdigest())
            with self.assertRaises(RuntimeError):
                M.verify(path, 'wrong')

    def test_cleanup_targets_owned_group_only(self):
        proc = Mock(pid=999)
        proc.poll.return_value = None
        with patch.object(M, 'as_root'), patch.object(M, 'as_user'), patch.object(M.os, 'killpg') as kill, \
                patch.object(M.pwd, 'getpwnam', return_value=Mock(pw_uid=1000)):
            M.stop_owned(proc)
            kill.assert_called_once_with(999, M.signal.SIGINT)

    def test_cleanup_escalation(self):
        proc = Mock(pid=999)
        proc.poll.return_value = None
        proc.wait.side_effect = [M.subprocess.TimeoutExpired('perf', 2), 0]
        with patch.object(M, 'as_root'), patch.object(M, 'as_user'), patch.object(M.os, 'killpg') as kill, \
                patch.object(M.pwd, 'getpwnam', return_value=Mock(pw_uid=1000)):
            M.stop_owned(proc)
            self.assertEqual([c.args for c in kill.call_args_list],
                             [(999, M.signal.SIGINT), (999, M.signal.SIGKILL)])

    def test_dead_profiler_not_signalled(self):
        proc = Mock()
        proc.poll.return_value = 0
        with patch.object(M.os, 'killpg') as kill:
            M.stop_owned(proc)
            M.stop_owned(None)
            kill.assert_not_called()

    def test_cleanup_exit_race(self):
        proc = Mock(pid=999)
        proc.poll.return_value = None
        with patch.object(M, 'as_root'), patch.object(M, 'as_user') as uid, \
                patch.object(M.os, 'killpg', side_effect=ProcessLookupError), \
                patch.object(M.pwd, 'getpwnam', return_value=Mock(pw_uid=1000)):
            M.stop_owned(proc)
            uid.assert_called_once()

    def test_real_effective_and_saved_identity(self):
        account = Mock(pw_uid=1000, pw_gid=1001)
        with patch.object(M.os, 'setresuid') as uid, patch.object(M.os, 'setresgid') as gid, \
                patch.object(M.os, 'getuid', return_value=1000), \
                patch.object(M.os, 'geteuid', return_value=1000), \
                patch.object(M.os, 'getgid', return_value=1001), \
                patch.object(M.os, 'getegid', return_value=1001):
            M.as_user(account)
            uid.assert_called_once_with(1000, 1000, 0)
            gid.assert_called_once_with(1001, 1001, 0)

    def test_incomplete_transition_fails(self):
        with patch.object(M.os, 'setresuid'), patch.object(M.os, 'setresgid'), \
                patch.object(M.os, 'getuid', return_value=0):
            with self.assertRaises(RuntimeError):
                M.as_user(Mock(pw_uid=1000, pw_gid=1000))

    def test_service_stderr_preserved(self):
        emit = Mock()
        with patch.object(M.subprocess, 'run', return_value=Mock(
                returncode=1, stdout='', stderr='Failed to connect to bus')):
            with self.assertRaisesRegex(RuntimeError, 'Failed to connect to bus'):
                M.service_output(['systemctl', '--user', 'show'], emit)
        self.assertEqual(emit.call_args.args[0]['stderr'], 'Failed to connect to bus')

    def test_service_success(self):
        with patch.object(M.subprocess, 'run', return_value=Mock(returncode=0, stdout='ok')):
            self.assertEqual(M.service_output(['systemctl'], Mock()), 'ok')

    def test_preserved_gate_and_no_control_operations(self):
        source = FILE.read_text()
        self.assertIn('G.require_cpu(cpu)', source)
        self.assertIn('G.check(cpu, snap)', source)
        self.assertIn("P.extra_safety(snap['ros'])", source)
        for forbidden in ('setfacl', 'chmod 777', 'systemctl restart', 'rclpy.init',
                          'resource_check', 'report_only', 'apt-get install'):
            self.assertNotIn(forbidden, source)

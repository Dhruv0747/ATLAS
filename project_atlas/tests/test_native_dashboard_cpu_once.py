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
        c = M.command(1973, Path('/tmp/private/perf.data'), [5549, 5729])
        self.assertEqual(c[c.index('-t')+1], '5549,5729')
        self.assertNotIn('-p', c)
        self.assertIn('--per-thread', c)
        self.assertIn('--no-bpf-event', c)
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
                M.command(pid, Path('/tmp/x'), [2, 3])

    def test_invalid_tids(self):
        for tids in ([], [2], [2, 2], [0, 3], ['2', 3], [2, 3, 4]):
            with self.assertRaises(ValueError):
                M.command(1973, Path('/tmp/x'), tids)

    def test_selection_uses_ticks_and_birth(self):
        a = {str(i): dict(ticks=100, birth=i) for i in range(2, 6)}
        b = {str(i): dict(ticks=100+i*10, birth=i) for i in range(2, 6)}
        b['5']['birth'] = 99
        self.assertEqual(M.select_hot_threads(a, b), {'4': 4, '3': 3})

    def test_insufficient_stable_threads_fails(self):
        with self.assertRaises(RuntimeError):
            M.select_hot_threads({}, {'7': dict(ticks=99, birth=1)})

    def test_selected_thread_identity_change_fails(self):
        M.require_target_threads({'7': dict(birth=4)}, {'7': 4})
        for current in ({}, {'7': dict(birth=5)}):
            with self.assertRaises(RuntimeError):
                M.require_target_threads(current, {'7': 4})

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
        self.assertIn('G.require_cpu(admitted_cpu)', source)
        self.assertIn('G.check(admitted_cpu, snap)', source)
        self.assertIn("P.extra_safety(snap['ros'])", source)
        for forbidden in ('setfacl', 'chmod 777', 'systemctl restart', 'rclpy.init',
                          'resource_check', 'apt-get install'):
            self.assertNotIn(forbidden, source)

    def test_cpu_exception_is_explicit_only(self):
        self.assertFalse(M.cpu_exception([]))
        self.assertTrue(M.cpu_exception(['--diagnostic-cpu-report-only']))
        with self.assertRaises(ValueError):
            M.cpu_exception(['--ignore-everything'])
        self.assertEqual(M.checked_cpu(77), 77)
        self.assertIsNone(M.checked_cpu(77, True))

    def test_cpu_exception_does_not_accept_invalid_measurements(self):
        for cpu in (float('nan'), float('inf'), -1, 101, None):
            with self.assertRaises(RuntimeError):
                M.checked_cpu(cpu, True)

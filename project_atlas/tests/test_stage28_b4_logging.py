"""Native Windows/offline tests: simulated serial only, no COM port opened."""
import contextlib
import ctypes
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools/flysky'
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parents[1] / 'scripts'))
from passive_evidence import Evidence, read_status
from atlas_yahboom_rc_report import build_packet


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.d = Path(self.temp.name)
        self.e = Evidence(self.d)

    def test_fresh_and_expired(self):
        p = self.e.save({'status': 'MONITORING', 'drive_disabled': True})
        now = json.loads(p.read_text())['observed_wall']
        self.assertTrue(read_status(self.d, now=now)['live'])
        self.assertFalse(read_status(self.d, now=now+2.01)['live'])
        self.assertFalse(read_status(self.d, now=now-1)['live'])

    def test_abort_supersedes_live(self):
        self.e.save({'status': 'MONITORING', 'drive_disabled': True})
        self.e.save({'status': 'ABORTED', 'port_closed': True, 'error': 'failure'})
        self.assertEqual(read_status(self.d)['status'], 'ABORTED')
        self.assertFalse(read_status(self.d)['live'])

    def test_legacy_result_wins(self):
        self.e.save({'status': 'MONITORING', 'drive_disabled': True})
        (self.d/'result.json').write_text('{"status":"ABORTED"}')
        self.assertFalse(read_status(self.d)['live'])

    def test_missing_malformed_and_pending(self):
        self.assertFalse(read_status(self.d)['live'])
        (self.d/'status-999999.pending').write_text('{}')
        self.assertFalse(read_status(self.d)['live'])
        self.e.save({'status': 'MONITORING', 'drive_disabled': True})
        (self.d/'status-000002.json').write_text('{')
        self.assertEqual(read_status(self.d)['status'], 'EVIDENCE_UNAVAILABLE')

    def test_missing_safety_flag(self):
        self.e.save({'status': 'MONITORING'})
        self.assertFalse(read_status(self.d)['live'])

    def test_write_failure_not_hidden(self):
        with patch('passive_evidence.os.fsync', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.e.save({'status': 'MONITORING'})
        self.assertFalse(read_status(self.d)['live'])

    def test_collision_not_overwritten(self):
        self.e.save({'status': 'ABORTED'})
        with self.assertRaises(FileExistsError):
            Evidence(self.d).save({'status': 'MONITORING'})
        self.assertEqual(read_status(self.d)['status'], 'ABORTED')

    @unittest.skipUnless(os.name == 'nt', 'native Windows file sharing required')
    def test_native_windows_locked_snapshot(self):
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                 ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        k.CreateFileW.restype = ctypes.c_void_p
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        old = self.e.save({'status': 'MONITORING', 'drive_disabled': True})
        handle = k.CreateFileW(str(old), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            replacement = self.d/'old-method.tmp'
            replacement.write_text('{}')
            with self.assertRaises(PermissionError):
                os.replace(replacement, old)
            # New publication succeeds while the previous snapshot remains locked.
            self.e.save({'status': 'ABORTED', 'port_closed': True})
            self.assertFalse(read_status(self.d)['live'])
            self.assertEqual(read_status(self.d)['status'], 'ABORTED')
        finally:
            k.CloseHandle(handle)

    def run_fake(self, corrupt=False, evidence_error=False):
        directory = self.d
        class FakeSerial:
            in_waiting = 32
            def __init__(self): self.closed=False; self.reads=0
            def open(self): pass
            def close(self): self.closed=True
            def write(self, *args): raise AssertionError('serial writes forbidden')
            def read(self, n):
                self.reads+=1
                if self.reads > 1:
                    (directory/'stop.request').touch()
                packet = bytearray(build_packet(None, 0, None))
                if corrupt: packet[-1]^=1
                return bytes(packet)
        fake=FakeSerial()
        args=['monitor', '--run-approved-session', '--evidence-dir', str(directory)]
        with patch.dict(sys.modules, {'serial': types.SimpleNamespace(Serial=lambda: fake)}), \
             patch.object(sys, 'argv', args), contextlib.redirect_stdout(io.StringIO()):
            if evidence_error:
                original=Evidence.save
                calls=[]
                def fail_once(self, state):
                    calls.append(1)
                    if len(calls)==1: raise PermissionError('simulated evidence denial')
                    return original(self,state)
                with patch.object(Evidence, 'save', fail_once):
                    runpy.run_path(str(TOOLS/'passive_sbus_monitor.py'),run_name='__main__')
            else:
                runpy.run_path(str(TOOLS/'passive_sbus_monitor.py'),run_name='__main__')
        self.assertTrue(fake.closed)
        self.assertEqual(read_status(directory)['writes'],0)
        self.assertFalse(read_status(directory)['live'])
        return read_status(directory)

    def test_fake_session_clean_stop(self):
        self.assertEqual(self.run_fake()['status'],'OPERATOR_STOP')

    def test_fake_checksum_abort(self):
        self.assertEqual(self.run_fake(corrupt=True)['status'],'ABORTED')

    def test_fake_evidence_failure_closes_port(self):
        self.assertEqual(self.run_fake(evidence_error=True)['status'],'ABORTED')

    def test_no_automatic_retry(self):
        self.run_fake()
        with self.assertRaises(FileExistsError):
            self.run_fake()


if __name__ == '__main__':
    unittest.main()

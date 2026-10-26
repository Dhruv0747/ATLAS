"""26 Oct 2026 (Issue #12 M1): Astra USB guard must ignore device-node timestamps (normal usbfs I/O) but still fail
closed on a genuine disconnect, replacement, renumbering, permission change or access loss. Hermetic: fake sysfs and
fake /dev in a temp dir; no USB access, no stream, no permission changes on the host."""
import os, stat as statmod, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vision3d')); sys.path.insert(0, str(ROOT / 'scripts'))
import stationary_ros_probe as P

HUB, DEPTH, RGB = ('05e3', '0608'), ('2bc5', '0403'), ('2bc5', '0501')


class Rig:
    """Astra at hub port 2.3.1 (RGB .1 = devnum 11, depth .2 = devnum 14) on the Jetson controller."""
    def __init__(self):
        self.root = Path(tempfile.mkdtemp())
        plat = self.root / 'sys/devices/platform/3610000.usb/usb1'; self.sysfs = self.root / 'sys/bus/usb/devices'
        self.sysfs.mkdir(parents=True); self.dev = self.root / 'dev'; (self.dev / 'bus/usb/001').mkdir(parents=True)
        for dp, ids, num in (('2.3.1', HUB, 9), ('2.3.1.1', RGB, 11), ('2.3.1.2', DEPTH, 14)):
            d = plat / ('1-' + dp); d.mkdir(parents=True)
            for k, v in (('idVendor', ids[0]), ('idProduct', ids[1]), ('devpath', dp), ('busnum', '1'),
                         ('devnum', str(num)), ('dev', '0:0')):
                (d / k).write_text(v + '\n')
            os.symlink(d, self.sysfs / ('1-' + dp))
            node = self.dev / 'bus/usb/001' / ('%03d' % num); node.write_bytes(b'')
        for alias, num in (('atlas-astra-depth-usb', 14), ('atlas-astra-rgb-usb', 11)):
            os.symlink(self.dev / 'bus/usb/001' / ('%03d' % num), self.dev / alias)

    def node(self, num): return self.dev / 'bus/usb/001' / ('%03d' % num)

    def run(self, during=None, access=None):
        """during(): called between the two identity reads of each device (inside the check, via os.access)."""
        real_access = os.access
        def hooked(path, mode, **kw):
            if during: during(Path(path))
            return real_access(path, mode) if access is None else access(Path(path))
        with patch.object(P.stat, 'S_ISCHR', return_value=True), patch.object(P.os, 'access', side_effect=hooked):
            return P.verify_astra_usb_access(sysfs_root=self.sysfs, dev_root=self.dev)


class GuardIdentity(unittest.TestCase):
    def setUp(self): self.r = Rig()

    def test_healthy_camera_passes(self):
        rows = self.r.run()
        self.assertEqual([x['vid_pid'] for x in rows], ['2bc5:0403', '2bc5:0501'])

    def test_timestamp_change_from_driver_io_is_not_a_failure(self):
        # Field case 26 Oct 22:58:45: atime/mtime of the depth node ticked during the check at 320x240@30.
        def io(path):
            t = time.time() + 5; os.utime(path, (t, t))
        rows = self.r.run(during=io)
        self.assertEqual(len(rows), 2)

    def test_node_replaced_during_check_fails(self):
        def replace(path):
            if path.name == '014':                                  # a different device node takes the old path
                os.rename(path, str(path) + '.old'); path.write_bytes(b'')
        with self.assertRaisesRegex(RuntimeError, 'identity/access changed'):
            self.r.run(during=replace)

    def test_disconnect_during_check_fails_closed(self):
        def unplug(path):
            if path.name == '014': path.unlink()
        with self.assertRaisesRegex(RuntimeError, 'access denied|query failed|changed'):   # any fail-closed reason
            self.r.run(during=unplug)

    def test_renumbered_during_check_fails(self):
        def renumber(path):
            if path.name == '014': (self.r.sysfs / '1-2.3.1.2' / 'devnum').write_text('15\n')
        with self.assertRaisesRegex(RuntimeError, 'identity/access changed'):
            self.r.run(during=renumber)

    def test_permission_change_during_check_fails(self):
        def chmod(path):
            if path.name == '014': os.chmod(path, 0o600)
        with self.assertRaisesRegex(RuntimeError, 'identity/access changed'):
            self.r.run(during=chmod)

    def test_access_denied_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'access denied.*014'):
            self.r.run(access=lambda p: False)

    def test_access_lost_after_first_check_fails(self):
        calls = {'n': 0}
        def flaky(p):
            calls['n'] += 1; return calls['n'] == 1          # depth: first check ok, re-check after identity denied
        with self.assertRaisesRegex(RuntimeError, 'access denied.*014'):
            self.r.run(access=flaky)

    def test_camera_absent_fails(self):
        for d in ('1-2.3.1.1', '1-2.3.1.2'): os.unlink(self.r.sysfs / d)
        with self.assertRaisesRegex(RuntimeError, 'missing|ambiguous'):
            self.r.run()

    def test_wrong_alias_fails(self):
        os.unlink(self.r.dev / 'atlas-astra-depth-usb'); os.symlink(self.r.node(11), self.r.dev / 'atlas-astra-depth-usb')
        with self.assertRaisesRegex(RuntimeError, 'alias mismatch'):
            self.r.run()

    def test_identity_fields_exclude_only_timestamps(self):
        self.assertEqual(set(P.NODE_IDENTITY_FIELDS), {'st_dev', 'st_ino', 'st_mode', 'st_rdev', 'st_uid', 'st_gid', 'st_nlink'})
        for f in ('st_atime', 'st_mtime', 'st_ctime', 'st_atime_ns', 'st_mtime_ns', 'st_ctime_ns'):
            self.assertNotIn(f, P.NODE_IDENTITY_FIELDS)

    def test_live_defaults_unchanged(self):
        src = (ROOT / 'tools/vision3d/stationary_ros_probe.py').read_text()
        self.assertIn("Path(sysfs_root or '/sys/bus/usb/devices')", src); self.assertIn("Path(dev_root or '/dev')", src)
        self.assertIn('verify_astra_usb_access()', src)          # extra_safety still calls it with live defaults


if __name__ == '__main__':
    unittest.main()

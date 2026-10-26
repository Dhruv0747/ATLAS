"""Offline tests for port-independent Astra identity (fake sysfs trees; no hardware)."""
import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_astra_usb as A


def tree(devs, controller='3610000.usb'):
    """devs: {devpath: (vid, pid)} on bus 1. Builds /sys/devices/platform/<controller>/... and /sys/bus/usb/devices links."""
    root = Path(tempfile.mkdtemp()); plat = root / 'devices/platform' / controller / 'usb1'; bus = root / 'bus/usb/devices'
    bus.mkdir(parents=True)
    for i, (dp, (v, p)) in enumerate(sorted(devs.items())):
        d = plat / ('1-' + dp); d.mkdir(parents=True, exist_ok=True)
        for k, val in (('idVendor', v), ('idProduct', p), ('devpath', dp), ('busnum', '1'), ('devnum', str(10 + i))):
            (d / k).write_text(val + '\n')
        os.symlink(d, bus / ('1-' + dp))
    return bus


HUB, DEPTH, RGB = ('05e3', '0608'), ('2bc5', '0403'), ('2bc5', '0501')
OTHER = {'2': ('0bda', '5489'), '2.3': ('214b', '7260'), '2.4.2': ('1a86', '7523')}


def astra_at(port):
    return {port: HUB, port + '.1': RGB, port + '.2': DEPTH}


class T(unittest.TestCase):
    def check(self, devs, state, port=None, **kw):
        r = A.presence(tree(devs, **kw), dev_check=False)
        self.assertEqual(r['state'], state, r)
        if port: self.assertEqual(r['port'], port)
        return r

    def test_old_fixed_port_still_accepted(self):
        r = self.check({**OTHER, **astra_at('2.3.1')}, 'CONNECTED', '2.3.1'); self.assertTrue(r['on_known_port'])

    def test_new_port_today_accepted(self):
        r = self.check({**OTHER, **astra_at('2.3.4')}, 'CONNECTED', '2.3.4'); self.assertFalse(r['on_known_port'])
        f = A.find_astra(tree({**OTHER, **astra_at('2.3.4')}))
        self.assertEqual((f['depth_port'], f['rgb_port']), ('2.3.4.2', '2.3.4.1'))

    def test_any_other_port(self):
        self.check({**OTHER, **astra_at('2.4.1')}, 'CONNECTED', '2.4.1')
        self.check({'2': OTHER['2'], **astra_at('2.1')}, 'CONNECTED', '2.1')

    def test_unplugged(self):
        self.check(OTHER, 'NOT_DETECTED')

    def test_two_cameras_refused(self):
        self.check({**OTHER, **astra_at('2.3.1'), **astra_at('2.4.1')}, 'AMBIGUOUS')

    def test_lone_half_refused(self):
        self.check({**OTHER, '2.3.4': HUB, '2.3.4.2': DEPTH}, 'PARTIAL')
        self.check({**OTHER, '2.3.4': HUB, '2.3.4.1': RGB}, 'PARTIAL')

    def test_swapped_or_split_halves_refused(self):
        self.check({**OTHER, '2.3.4': HUB, '2.3.4.1': DEPTH, '2.3.4.2': RGB}, 'MISMATCH')
        self.check({**OTHER, '2.3.4': HUB, '2.3.4.2': DEPTH, '2.4.1': HUB, '2.4.1.1': RGB}, 'MISMATCH')

    def test_wrong_hub_refused(self):
        self.check({**OTHER, '2.3.4': ('1a40', '0101'), '2.3.4.1': RGB, '2.3.4.2': DEPTH}, 'MISMATCH')

    def test_other_controller_ignored(self):
        self.check({**OTHER, **astra_at('2.3.4')}, 'NOT_DETECTED', controller='3550000.usb')

    def test_find_raises_for_probe(self):
        with self.assertRaises(A.AstraUsbError):
            A.find_astra(tree(OTHER))

    def test_access_flags_without_rule(self):
        r = A.presence(tree({**OTHER, **astra_at('2.3.4')}), dev_check=True)   # /dev/bus/usb nodes absent in test
        self.assertEqual(r['state'], 'NO_ACCESS'); self.assertFalse(r['access']['depth']['read_write'])


# 26 Oct 2026: read-only explanation of a USB device that never finished starting (field log, hub 1-2.3 port 1).
FIELD_LOG = """1793011987.10 jetsan-desktop kernel: usb 1-2.3: USB disconnect, device number 6
1793011992.20 jetsan-desktop kernel: usb 1-2.3.1: new high-speed USB device number 20 using tegra-xusb
1793011992.30 jetsan-desktop kernel: usb 1-2.3.1: device descriptor read/64, error -71
1793011992.40 jetsan-desktop kernel: usb 1-2.3.1: device descriptor read/64, error -71
1793011992.90 jetsan-desktop kernel: usb 1-2.3-port1: attempt power cycle
1793011993.50 jetsan-desktop kernel: usb 1-2.3.1: Device not responding to setup address.
1793011993.60 jetsan-desktop kernel: usb 1-2.3.1: device not accepting address 22, error -71
1793011994.70 jetsan-desktop kernel: usb 1-2.3-port1: unable to enumerate USB device
1793011988.00 jetsan-desktop kernel: usb 1-2.4.2: failed to send control message: -32
"""


class Enumeration(unittest.TestCase):
    def run_log(self, text):
        calls = []
        def runner(cmd, **kw):
            calls.append(cmd); return type('R', (), {'stdout': text})()
        return runner, calls

    def test_parse_field_log(self):
        f = A.parse_enumeration_failures(FIELD_LOG)
        self.assertEqual(set(f), {'2.3.1'}); self.assertTrue(f['2.3.1']['gave_up']); self.assertEqual(f['2.3.1']['errors'], 6)

    def test_not_detected_explains_failed_port(self):
        runner, calls = self.run_log(FIELD_LOG)
        orig = A.recent_enumeration_failure
        A.recent_enumeration_failure = lambda sysfs: orig(sysfs, now=1793012000.0, runner=runner)
        try:
            r = A.presence(tree(OTHER), dev_check=False)
        finally:
            A.recent_enumeration_failure = orig
        self.assertEqual(r['state'], 'NOT_DETECTED'); self.assertEqual(r['enumeration_failure']['port'], '2.3.1')
        self.assertIn('port 2.3.1 failed to start', r['detail']); self.assertIn('powered USB hub', r['detail'])
        self.assertEqual(calls[0][:2], ['journalctl', '-k'])                   # read-only kernel log query only

    def test_old_failure_or_device_now_present_is_ignored(self):
        runner, _ = self.run_log(FIELD_LOG)
        self.assertIsNone(A.recent_enumeration_failure(tree(OTHER), now=1793011994.7 + A.ENUM_WINDOW_S + 1, runner=runner))
        present = tree({**OTHER, '2.3.1': ('1234', '5678')})
        self.assertIsNone(A.recent_enumeration_failure(present, now=1793012000.0, runner=runner))

    def test_retries_without_giving_up_are_not_reported(self):
        text = '\n'.join(l for l in FIELD_LOG.splitlines() if 'unable to enumerate' not in l)
        runner, _ = self.run_log(text)
        self.assertIsNone(A.recent_enumeration_failure(tree(OTHER), now=1793012000.0, runner=runner))

    def test_journal_unavailable_keeps_plain_message(self):
        def boom(*a, **k): raise OSError('no journal')
        self.assertIsNone(A.recent_enumeration_failure(tree(OTHER), runner=boom))
        orig = A.recent_enumeration_failure
        A.recent_enumeration_failure = lambda sysfs: orig(sysfs, runner=boom)
        try:
            r = A.presence(tree(OTHER), dev_check=False)
        finally:
            A.recent_enumeration_failure = orig
        self.assertEqual(r['detail'], 'Astra not detected on USB'); self.assertNotIn('enumeration_failure', r)

    def test_connected_never_queries_journal(self):
        runner, calls = self.run_log(FIELD_LOG)
        orig = A.recent_enumeration_failure
        A.recent_enumeration_failure = lambda sysfs: orig(sysfs, runner=runner)
        try:
            self.assertEqual(A.presence(tree({**OTHER, **astra_at('2.3.4')}), dev_check=False)['state'], 'CONNECTED')
        finally:
            A.recent_enumeration_failure = orig
        self.assertEqual(calls, [])

    def test_module_never_writes_or_resets(self):
        src = (Path(A.__file__)).read_text()
        for bad in ("'authorized'", 'unbind', 'usbreset', 'USBDEVFS', "write_text", "open(", 'power/'):
            self.assertNotIn(bad, src, bad)


if __name__ == '__main__':
    unittest.main()

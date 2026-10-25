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


if __name__ == '__main__':
    unittest.main()

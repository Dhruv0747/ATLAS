"""USB power-health monitor (2026-11-21): kernel-line parsing, hub mapping, health levels, snapshot."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_usb_power_monitor as m  # noqa: E402


def make_dev(root, path, vid, pid, product='', cls='00', maxp='100mA', ttys=()):
    d = Path(root) / path
    d.mkdir(parents=True)
    for name, value in (('idVendor', vid), ('idProduct', pid), ('product', product),
                        ('bDeviceClass', cls), ('bMaxPower', maxp)):
        (d / name).write_text(value + '\n')
    for t in ttys:
        (d / f'{path}:1.0' / t).mkdir(parents=True)


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class ParseTests(unittest.TestCase):
    def test_real_kernel_lines(self):
        cases = {
            'usb 1-2.4.1: USB disconnect, device number 51': ('disconnect', '1-2.4.1'),
            'usb 1-2.4.1: new high-speed USB device number 52 using tegra-xusb': ('reconnect', '1-2.4.1'),
            'usb 1-2.1: device descriptor read/64, error -71': ('enum_error', '1-2.1'),
            'usb 1-2.1: device not accepting address 50, error -71': ('enum_error', '1-2.1'),
            'usb 1-2.4.2: failed to send control message: -32': ('io_error', '1-2.4.2'),
        }
        for line, want in cases.items():
            self.assertEqual(m.parse_kernel_line(line), want, line)

    def test_tty_error_mapped_to_device(self):
        line = 'ch341-uart ttyUSB2: usb_serial_generic_read_bulk_callback - urb stopped: -32'
        self.assertEqual(m.parse_kernel_line(line, {'ttyUSB2': '1-2.4.2'}), ('io_error', '1-2.4.2'))
        self.assertIsNone(m.parse_kernel_line(line, {}))

    def test_unrelated_lines_ignored(self):
        self.assertIsNone(m.parse_kernel_line('rndis_host 1-2.2.1:1.0 usb0: register rndis_host'))
        self.assertIsNone(m.parse_kernel_line('audit: type=1326'))

    def test_parent_hub(self):
        self.assertEqual(m.parent_hub('1-2.4.1'), '1-2.4')
        self.assertEqual(m.parent_hub('1-2.3.3.1'), '1-2.3.3')
        self.assertEqual(m.parent_hub('1-2'), '1')


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        make_dev(root, '1-2.4', '214b', '7260', 'USB2.0 HUB', cls='09')
        make_dev(root, '1-2.4.1', '1e0e', '907b', 'SDXBAAGHA-IDP', maxp='500mA', ttys=('ttyUSB4',))
        make_dev(root, '1-2.4.2', '1a86', '7523', 'USB Serial', maxp='102mA', ttys=('ttyUSB2',))
        make_dev(root, '1-2.2', '214b', '7260', 'USB2.0 Hub', cls='09')
        make_dev(root, '1-2.2.4', '10c4', 'ea60', 'CP2102', ttys=('ttyUSB0',))
        hw = Path(root) / 'hwmon'
        hw.mkdir()
        (hw / 'in1_input').write_text('4872\n')
        (hw / 'curr1_input').write_text('1720\n')
        self.clock = Clock()
        self.state = str(Path(root) / 'history.json')
        self.battery = {'soc': 35.0, 'current_a': 1.7, 'voltage_v': 13.3}
        self.mon = m.UsbPowerMonitor(usb_root=root, hwmon=str(hw), clock=self.clock, start_threads=False,
                                     extra_fn=lambda: self.battery, state_path=self.state,
                                     boot={'id': 'boot-A', 'unix': 900.0})
        self.mon.owners_at = 1e12        # skip /proc scanning in tests
        self.mon.owners = {'ttyUSB2': 'python3 gnss_node --ros-args'}
        self.root = root

    def tearDown(self):
        self.tmp.cleanup()

    def tick(self, n=1):
        for _ in range(n):
            self.mon.sample_once()
            self.clock.t += 1.0

    def test_roles_hubs_and_rail(self):
        self.tick()
        s = self.mon.snapshot()
        self.assertEqual(s['vin_v'][-1], 4.872)
        self.assertEqual(s['iin_a'][-1], 1.72)
        self.assertEqual(s['devices']['1-2.4.1']['role'], '4G modem (SIM8230G)')
        self.assertEqual(s['devices']['1-2.4.2']['role'], 'Hiwonder GPS V1 USB (CH340)')
        self.assertEqual(s['devices']['1-2.2.4']['hub'], '1-2.2')
        self.assertNotIn('1-2.4', s['devices'])               # hubs are not plotted as devices
        self.assertEqual(sorted(s['hubs']['1-2.4']['devices']), ['1-2.4.1', '1-2.4.2'])
        self.assertEqual(s['hubs']['1-2.4']['requested_ma'], 602)
        self.assertIsNone(s['suspect_hub'])

    def test_disconnect_and_errors_lower_health_and_pick_suspect_hub(self):
        self.tick(2)
        self.mon.note_event('disconnect', '1-2.4.1', t=self.clock.t)
        self.mon.note_event('reconnect', '1-2.4.1', t=self.clock.t)
        self.tick()
        self.mon.note_event('io_error', '1-2.4.2', t=self.clock.t)
        self.tick()
        self.tick()
        s = self.mon.snapshot()
        self.assertEqual(s['devices']['1-2.4.1']['health'], [1.0, 1.0, 0.0, 1.0, 1.0])
        self.assertEqual(s['devices']['1-2.4.2']['health'], [1.0, 1.0, 1.0, 0.5, 1.0])
        self.assertEqual(s['devices']['1-2.4.1']['events_10min'], 1)   # reconnect is not counted as a fault
        self.assertEqual(s['hubs']['1-2.4']['events_10min'], 2)
        self.assertEqual(s['hubs']['1-2.2']['events_10min'], 0)
        self.assertEqual(s['suspect_hub'], '1-2.4')

    def test_unplugged_device_shows_zero_then_recovers(self):
        self.tick()
        gone = Path(self.root) / '1-2.2.4'
        os.rename(gone, str(gone) + '.x')
        self.tick()
        self.assertFalse(self.mon.snapshot()['devices']['1-2.2.4']['present'])
        os.rename(str(gone) + '.x', gone)
        self.tick()
        s = self.mon.snapshot()
        self.assertEqual(s['devices']['1-2.2.4']['health'], [1.0, 0.0, 1.0])
        self.assertTrue(s['devices']['1-2.2.4']['present'])

    def test_missing_ina3221_is_reported_not_faked(self):
        mon = m.UsbPowerMonitor(usb_root=self.root, hwmon='', clock=self.clock, start_threads=False, state_path=None)
        mon.owners_at = 1e12
        mon.sample_once()
        s = mon.snapshot()
        self.assertIsNone(s['rail'])
        self.assertEqual(s['vin_v'], [None])

    def test_history_is_bounded(self):
        self.tick(m.HISTORY_S + 20)
        self.assertEqual(len(self.mon.snapshot()['t']), m.HISTORY_S)


    # ---- since power-on history (2026-11-22) ----
    def test_minute_buckets_hold_rail_and_battery(self):
        self.clock.t = 1020.0
        self.tick(90)                                   # 1020..1109 s -> minutes 1020 and 1080
        L = self.mon.long_snapshot()
        self.assertEqual([b['t'] for b in L['minutes']], [1020, 1080])
        first = L['minutes'][0]
        self.assertEqual((first['vin_min'], first['vin_avg'], first['vin_max']), (4.872, 4.872, 4.872))
        self.assertEqual(first['iin_avg'], 1.72)
        self.assertEqual((first['bat_soc'], first['bat_a'], first['bat_v']), (35.0, 1.7, 13.3))
        self.assertEqual(L['boot_unix'], 900.0)
        self.assertEqual(L['faults_total'], 0)

    def test_faults_counted_per_minute_and_hub_not_reconnects(self):
        self.tick()
        self.mon.note_event('disconnect', '1-2.4.1', t=1030.0)
        self.mon.note_event('reconnect', '1-2.4.1', t=1030.5)
        self.mon.note_event('io_error', '1-2.4.2', t=1031.0)
        self.mon.note_event('enum_error', '1-2.2.4', t=1100.0)
        L = self.mon.long_snapshot()
        by_t = {b['t']: b for b in L['minutes']}
        self.assertEqual(by_t[1020]['faults'], 2)
        self.assertEqual(by_t[1020]['faults_by_hub'], {'1-2.4': 2})
        self.assertEqual(by_t[1080]['faults'], 1)
        self.assertEqual(L['faults_by_hub'], {'1-2.4': 2, '1-2.2': 1})
        self.assertEqual(L['faults_total'], 3)

    def test_kernel_backfill_counts_only_before_live_start(self):
        self.mon.live_since = 1000.0
        lines = ['950.5 jetsan-desktop kernel: usb 1-2.4.1: USB disconnect, device number 51',
                 '951.0 jetsan-desktop kernel: usb 1-2.4.1: new high-speed USB device number 52 using tegra-xusb',
                 '960.0 jetsan-desktop kernel: usb 1-2.1: device descriptor read/64, error -71',
                 '1005.0 jetsan-desktop kernel: usb 1-2.4.1: USB disconnect, device number 53',
                 'garbage line']
        self.mon.backfill_kernel(lines)
        L = self.mon.long_snapshot()
        self.assertEqual(L['faults_total'], 2)            # the 1005 s one belongs to the live reader
        self.assertEqual(L['faults_by_hub'], {'1-2.4': 1, '1-2': 1})

    def test_history_survives_dashboard_restart_same_boot_only(self):
        self.tick(3)
        self.mon.save()
        again = m.UsbPowerMonitor(usb_root=self.root, hwmon='', clock=self.clock, start_threads=False,
                                  state_path=self.state, boot={'id': 'boot-A', 'unix': 900.0})
        self.assertEqual(len(again.long_snapshot()['minutes']), 1)
        self.assertEqual(again.long_snapshot()['minutes'][0]['bat_soc'], 35.0)
        other = m.UsbPowerMonitor(usb_root=self.root, hwmon='', clock=self.clock, start_threads=False,
                                  state_path=self.state, boot={'id': 'boot-B', 'unix': 900.0})
        self.assertEqual(other.long_snapshot()['minutes'], [])

    def test_long_history_is_bounded_to_24h(self):
        for i in range(m.LONG_MINUTES + 30):
            self.mon.note_event('disconnect', '1-2.4.1', t=1000.0 + 60 * i)
        self.assertEqual(len(self.mon.long_snapshot()['minutes']), m.LONG_MINUTES)

    def test_bad_battery_reading_is_ignored(self):
        self.battery = {'soc': None, 'current_a': 'x'}
        self.tick()
        b = self.mon.long_snapshot()['minutes'][0]
        self.assertIsNone(b['bat_soc'])
        self.assertIsNone(b['bat_a'])


if __name__ == '__main__':
    unittest.main()

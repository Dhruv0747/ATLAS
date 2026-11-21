#!/usr/bin/env python3
"""Read-only USB power-health monitor for the dashboard (2026-11-21 owner request).

What it CAN measure (no extra hardware):
  * Jetson input rail VDD_IN voltage/current/power (INA3221 hwmon), sampled once per second.
  * For every USB device on the rover: present / gone, plus kernel USB events that follow a supply
    sag or a bad link (USB disconnect, re-enumeration, error -32/-71/-110, over-current), mapped to
    the device and to the hub it hangs on.
What it can NOT measure: per-port USB current. Linux and USB 2.0 hubs do not report it. Real per-hub
current needs an INA219/INA226 module on each hub's 5 V line.

Never writes to devices, never resets a port, never publishes ROS messages. One sysfs scan per second,
one `journalctl -k -f` reader thread.
"""
import collections
import glob
import os
import re
import subprocess
import threading
import time

USB_ROOT = '/sys/bus/usb/devices'
HISTORY_S = 600            # ring buffer length (1 Hz samples)
EVENT_KEEP_S = 3600        # kernel events kept for the per-hub counters
ROLE_BY_ID = {             # vendor:product -> human role
    '1e0e:907b': '4G modem (SIM8230G)',
    '10c4:ea60': 'LiDAR (RPLIDAR, CP2102)',
    '2341:006d': 'UNO R4 (ultrasonic/radar hub)',
    '303a:1001': 'ESP32',
    '045e:028e': 'Xbox controller receiver',
    '2bc5:0403': 'Astra Pro depth',
    '2bc5:0501': 'Astra Pro HD camera',
    '2109:8817': 'USB-C billboard',
}
ROLE_BY_PROCESS = (        # who holds a CH340 tty -> role
    ('yahboom_base', 'Motor base (Yahboom, CH340)'),
    ('im10a', 'IM10A IMU (CH340)'),
    ('gnss_node', 'Hiwonder GPS V1 USB (CH340)'),
)
HUB_CLASS = '09'
EVENT_RES = (
    ('disconnect', re.compile(r'usb (\d+-[\d.]+): USB disconnect')),
    ('reconnect', re.compile(r'usb (\d+-[\d.]+): new \S+ USB device')),
    ('enum_error', re.compile(r'usb (\d+-[\d.]+): (?:device descriptor read\S*, error -\d+|device not accepting address|'
                              r'Device not responding|device not responding)')),
    ('io_error', re.compile(r'usb (\d+-[\d.]+): failed to (?:send|receive) control message: -\d+')),
    ('over_current', re.compile(r'(?:usb|hub) (\d+-[\d.]+)\S*.*over-current', re.I)),
)
TTY_ERROR_RE = re.compile(r'(?:ch341-uart|cp210x|option1|cdc_acm) (ttyUSB\d+|ttyACM\d+):.*(?:-32|-71|-110|error)', re.I)


def parent_hub(path):
    """'1-2.4.1' -> '1-2.4'; '1-2' -> '1'."""
    return path.rsplit('.', 1)[0] if '.' in path else path.split('-', 1)[0]


def parse_kernel_line(line, tty_to_device=None):
    """(kind, device_path) for a USB-health kernel line, else None. Pure: used by the tests."""
    for kind, regex in EVENT_RES:
        m = regex.search(line)
        if m:
            return kind, m.group(1)
    m = TTY_ERROR_RE.search(line)
    if m and tty_to_device:
        dev = tty_to_device.get(m.group(1))
        if dev:
            return 'io_error', dev
    return None


def _read(path, default=''):
    try:
        with open(path, encoding='ascii', errors='replace') as stream:
            return stream.read().strip()
    except OSError:
        return default


def scan_devices(root=USB_ROOT):
    """{path: {id, product, hub(bool), maxpower_ma, ttys:[...]}} for real USB devices (not interfaces)."""
    out = {}
    for d in glob.glob(os.path.join(root, '*')):
        name = os.path.basename(d)
        if ':' in name or name.startswith('usb'):
            continue
        vid, pid = _read(os.path.join(d, 'idVendor')), _read(os.path.join(d, 'idProduct'))
        if not vid:
            continue
        ttys = sorted({os.path.basename(t) for t in glob.glob(os.path.join(d, name + ':*', 'tty*'))
                       if re.match(r'tty(USB|ACM)\d+$', os.path.basename(t))}
                      | {os.path.basename(t) for t in glob.glob(os.path.join(d, name + ':*', 'tty', 'tty*'))})
        maxp = _read(os.path.join(d, 'bMaxPower')).replace('mA', '')
        out[name] = {'id': f'{vid}:{pid}', 'product': _read(os.path.join(d, 'product'))[:40],
                     'hub': _read(os.path.join(d, 'bDeviceClass')) == HUB_CLASS,
                     'maxpower_ma': int(maxp) if maxp.isdigit() else None, 'ttys': ttys}
    return out


def tty_owners(uid=None):
    """{ttyUSBn: process cmdline} for this user's processes (no root needed)."""
    uid = os.getuid() if uid is None else uid
    owners = {}
    for proc in glob.glob('/proc/[0-9]*'):
        try:
            if os.stat(proc).st_uid != uid:
                continue
            cmd = _read(os.path.join(proc, 'cmdline')).replace('\0', ' ')
            for fd in os.listdir(os.path.join(proc, 'fd')):
                target = os.readlink(os.path.join(proc, 'fd', fd))
                if target.startswith('/dev/tty'):
                    owners[os.path.basename(target)] = cmd
        except OSError:
            continue
    return owners


def role_for(dev, owners):
    for tty in dev.get('ttys', []):
        cmd = owners.get(tty, '')
        for key, role in ROLE_BY_PROCESS:
            if key in cmd:
                return role
    if dev.get('hub'):
        return 'USB hub'
    return ROLE_BY_ID.get(dev.get('id'), dev.get('product') or dev.get('id') or 'USB device')


def find_ina3221(pattern='/sys/class/hwmon/hwmon*'):
    for root in glob.glob(pattern):
        if _read(os.path.join(root, 'name')) == 'ina3221':
            return root
    return None


class UsbPowerMonitor:
    def __init__(self, usb_root=USB_ROOT, hwmon=None, clock=time.time, start_threads=True):
        self.usb_root, self.clock = usb_root, clock
        self.hwmon = hwmon if hwmon is not None else find_ina3221()
        self.lock = threading.Lock()
        self.samples = collections.deque(maxlen=HISTORY_S)    # (t, vin_v, iin_a, {path: state})
        self.events = collections.deque(maxlen=5000)           # (t, kind, path)
        self.known = {}                                         # path -> latest info (also gone devices)
        self.owners, self.owners_at = {}, 0.0
        self.tty_map = {}
        self.pending = {}                                       # path -> worst event kind since last sample
        self.started = False
        if start_threads:
            self.start()

    def start(self):
        if self.started:
            return
        self.started = True
        threading.Thread(target=self._sample_loop, name='usb-power-sample', daemon=True).start()
        threading.Thread(target=self._kernel_loop, name='usb-power-kmsg', daemon=True).start()

    # ---- inputs --------------------------------------------------------------------------------
    def _rail(self):
        if not self.hwmon:
            return None, None
        v, i = _read(os.path.join(self.hwmon, 'in1_input')), _read(os.path.join(self.hwmon, 'curr1_input'))
        try:
            return round(int(v) / 1000.0, 3), round(int(i) / 1000.0, 3)
        except ValueError:
            return None, None

    def note_event(self, kind, path, t=None):
        t = self.clock() if t is None else t
        with self.lock:
            self.events.append((t, kind, path))
            rank = {'reconnect': 1, 'io_error': 2, 'enum_error': 2, 'over_current': 3, 'disconnect': 3}
            if rank.get(kind, 0) >= rank.get(self.pending.get(path), 0):
                self.pending[path] = kind

    def sample_once(self):
        now = self.clock()
        devices = scan_devices(self.usb_root)
        if now - self.owners_at > 10.0:
            self.owners, self.owners_at = tty_owners(), now
        vin, iin = self._rail()
        with self.lock:
            for path, dev in devices.items():
                dev = dict(dev, role=role_for(dev, self.owners), hub_path=parent_hub(path), present=True)
                self.known[path] = dev
            for path, dev in self.known.items():
                if path not in devices:
                    dev['present'] = False
            self.tty_map = {t: p for p, d in devices.items() for t in d['ttys']}
            states = {}
            for path, dev in self.known.items():
                event = self.pending.pop(path, None)
                if not dev['present']:
                    states[path] = 0.0
                elif event in ('disconnect', 'over_current'):
                    states[path] = 0.0
                elif event in ('io_error', 'enum_error'):
                    states[path] = 0.5
                elif event == 'reconnect':
                    states[path] = 0.75
                else:
                    states[path] = 1.0
            self.samples.append((now, vin, iin, states))

    def _sample_loop(self):
        while True:
            try:
                self.sample_once()
            except Exception as exc:   # never take the dashboard down
                print('usb power monitor sample failed: ' + str(exc), flush=True)
            time.sleep(1.0)

    def _kernel_loop(self):
        while True:
            try:
                proc = subprocess.Popen(['journalctl', '-k', '-f', '-n', '0', '-o', 'cat', '--no-pager'],
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
                for line in proc.stdout:
                    hit = parse_kernel_line(line, self.tty_map)
                    if hit:
                        self.note_event(*hit)
            except Exception as exc:
                print('usb power monitor kernel reader failed: ' + str(exc), flush=True)
            time.sleep(5.0)

    # ---- output --------------------------------------------------------------------------------
    def snapshot(self, window_s=HISTORY_S):
        now = self.clock()
        with self.lock:
            samples = [s for s in self.samples if now - s[0] <= window_s]
            events = [e for e in self.events if now - e[0] <= EVENT_KEEP_S]
            known = {p: dict(d) for p, d in self.known.items()}
        devices = {}
        for path, dev in sorted(known.items()):
            if dev.get('hub'):
                continue
            evs = [e for e in events if e[2] == path]
            devices[path] = {
                'role': dev['role'], 'id': dev['id'], 'hub': dev['hub_path'], 'present': dev['present'],
                'requested_ma': dev.get('maxpower_ma'), 'ttys': dev.get('ttys', []),
                'health': [s[3].get(path, 0.0) for s in samples],
                'events_10min': sum(1 for e in evs if now - e[0] <= 600 and e[1] != 'reconnect'),
                'events_1h': sum(1 for e in evs if e[1] != 'reconnect'),
                'last_event': ({'kind': evs[-1][1], 'age_s': round(now - evs[-1][0], 1)} if evs else None),
            }
        hubs = {}
        for path, dev in devices.items():
            h = hubs.setdefault(dev['hub'], {'devices': [], 'events_10min': 0, 'events_1h': 0, 'requested_ma': 0})
            h['devices'].append(path)
            h['events_10min'] += dev['events_10min']
            h['events_1h'] += dev['events_1h']
            h['requested_ma'] += dev['requested_ma'] or 0
        for path, h in hubs.items():
            info = known.get(path, {})
            h['name'] = info.get('product') or ('Jetson root' if '.' not in path and '-' not in path else path)
        worst = max(hubs.items(), key=lambda kv: kv[1]['events_10min'], default=(None, {'events_10min': 0}))
        return {
            'schema': 1, 'now': round(now, 1), 'window_s': window_s,
            't': [round(s[0] - now, 1) for s in samples],
            'vin_v': [s[1] for s in samples], 'iin_a': [s[2] for s in samples],
            'rail': 'Jetson VDD_IN (INA3221)' if self.hwmon else None,
            'devices': devices, 'hubs': hubs,
            'suspect_hub': worst[0] if worst[1]['events_10min'] > 0 else None,
            'note': 'Per-device USB current is not measurable on ATLAS: health = link up (1) / '
                    're-enumerated (0.75) / USB error (0.5) / gone (0). VDD_IN is the whole Jetson input rail.',
        }


_MONITOR = None
_MONITOR_LOCK = threading.Lock()


def monitor():
    global _MONITOR
    with _MONITOR_LOCK:
        if _MONITOR is None:
            _MONITOR = UsbPowerMonitor()
        return _MONITOR

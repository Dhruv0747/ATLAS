"""Port-independent Astra Pro USB identity (25 Oct 2026). Read-only sysfs; never opens, resets or streams the camera.

The Astra Pro contains its own USB 2.0 hub (Genesys 05e3:0608). Its RGB camera (2bc5:0501) sits on port .1 and its
depth sensor (2bc5:0403) on port .2 of that hub. The camera is identified by that structure on the Jetson's USB
controller, so it can be plugged into ANY port. Two Astras, a lone half, or a depth/RGB pair that are not siblings
on one Genesys hub are refused (ambiguous), as the fixed-port check did.
"""
import os
import re
import subprocess
import time
from pathlib import Path

SYSFS = Path('/sys/bus/usb/devices')
CONTROLLER = '3610000.usb'               # Jetson Orin Nano USB controller (same as the fixed-port check)
DEPTH = ('2bc5', '0403')
RGB = ('2bc5', '0501')
ASTRA_HUB = ('05e3', '0608')
KNOWN_PORT = '2.3.1'                      # port verified on 21 Oct (reported only; not required)
ALIASES = {'depth': '/dev/atlas-astra-depth-usb', 'rgb': '/dev/atlas-astra-rgb-usb'}


class AstraUsbError(RuntimeError):
    def __init__(self, state, message):
        super().__init__(message)
        self.state = state


def _read(path, name):
    return (path / name).read_text().strip()


def _ids(path):
    try:
        return (_read(path, 'idVendor'), _read(path, 'idProduct'))
    except OSError:
        return None


def _on_controller(path):
    try:
        return CONTROLLER in path.resolve(strict=True).parts
    except OSError:
        return False


def find_astra(sysfs=SYSFS):
    """Exactly one Astra Pro on the Jetson controller -> {'depth': Path, 'rgb': Path, 'hub_port', ...}; else raise."""
    devices = [p for p in sysfs.iterdir() if ':' not in p.name and (p / 'idVendor').exists()]
    depth = [p for p in devices if _ids(p) == DEPTH and _on_controller(p)]
    rgb = [p for p in devices if _ids(p) == RGB and _on_controller(p)]
    if not depth and not rgb:
        raise AstraUsbError('NOT_DETECTED', 'Astra not detected on USB')
    if len(depth) > 1 or len(rgb) > 1:
        raise AstraUsbError('AMBIGUOUS', 'more than one Astra depth/RGB device on USB (%d depth, %d RGB)' % (len(depth), len(rgb)))
    if len(depth) != 1 or len(rgb) != 1:
        raise AstraUsbError('PARTIAL', 'only the Astra %s half is visible on USB' % ('depth' if depth else 'RGB'))
    d, r = depth[0], rgb[0]
    dpath, rpath, bus = _read(d, 'devpath'), _read(r, 'devpath'), _read(d, 'busnum')
    parent = dpath.rsplit('.', 1)[0] if '.' in dpath else None
    if (parent is None or not dpath.endswith('.2') or not rpath.endswith('.1')
            or rpath.rsplit('.', 1)[0] != parent or _read(r, 'busnum') != bus):
        raise AstraUsbError('MISMATCH', 'Astra depth (%s) and RGB (%s) are not the two halves of one camera' % (dpath, rpath))
    hub = sysfs / ('%s-%s' % (bus, parent))
    if _ids(hub) != ASTRA_HUB:
        raise AstraUsbError('MISMATCH', 'Astra internal hub not found at %s' % parent)
    return {'depth': d, 'rgb': r, 'hub_port': parent, 'depth_port': dpath, 'rgb_port': rpath}


def _node(path):
    bus, num = int(_read(path, 'busnum')), int(_read(path, 'devnum'))
    return Path('/dev/bus/usb') / ('%03d' % bus) / ('%03d' % num)


# 26 Oct 2026: explain a USB device that was plugged in but never started (seen on the Jetson at 17:03: hub 1-2.3
# port 1 "device descriptor read/64, error -71" ... "unable to enumerate USB device"). Read-only kernel-log query, only
# when the Astra is NOT_DETECTED; it never resets, power-cycles or retries a port and changes no recovery behaviour.
ENUM_WINDOW_S = 900
_ENUM_DEV = re.compile(r'usb (\d+)-([\d.]+): (device descriptor read/\d+, error -?\d+|device not accepting address \d+, '
                       r'error -?\d+|Device not responding to setup address|unable to enumerate USB device)')
_ENUM_PORT = re.compile(r'usb (\d+)-([\d.]+)-port(\d+): (unable to enumerate USB device|attempt power cycle)')


def parse_enumeration_failures(text):
    """Kernel lines (journalctl -o short-unix) -> {port: {'last_unix', 'errors', 'gave_up'}} for USB start-up failures."""
    out = {}
    for line in text.splitlines():
        stamp = line.split(' ', 1)[0]
        try:t = float(stamp)
        except ValueError:continue
        m = _ENUM_PORT.search(line)
        if m:
            port, what = '%s.%s' % (m.group(2), m.group(3)), m.group(4)
        else:
            m = _ENUM_DEV.search(line)
            if not m:continue
            port, what = m.group(2), m.group(3)
        row = out.setdefault(port, {'last_unix': t, 'errors': 0, 'gave_up': False})
        row['last_unix'] = max(row['last_unix'], t); row['errors'] += 1
        row['gave_up'] = row['gave_up'] or what == 'unable to enumerate USB device'
    return out


def recent_enumeration_failure(sysfs=SYSFS, now=None, runner=subprocess.run, window_s=ENUM_WINDOW_S):
    """Newest port whose device gave up starting within window_s and still has nothing attached; else None."""
    now = time.time() if now is None else now
    try:
        text = runner(['journalctl', '-k', '-o', 'short-unix', '--no-pager', '-q', '--since', '-%ds' % int(window_s)],
                      capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return None
    best = None
    for port, row in parse_enumeration_failures(text).items():
        if not row['gave_up'] or not 0 <= now - row['last_unix'] <= window_s:continue
        try:
            if (sysfs / ('1-%s' % port) / 'idVendor').exists() or any(
                    (p / 'idVendor').exists() and _read(p, 'devpath') == port for p in sysfs.iterdir() if ':' not in p.name):
                continue                      # something started on that port since then
        except OSError:
            pass
        if best is None or row['last_unix'] > best['last_unix']:
            best = dict(row, port=port)
    return best


def presence(sysfs=SYSFS, dev_check=True):
    """Dashboard status; never raises. state: CONNECTED | NO_ACCESS | NOT_DETECTED | PARTIAL | AMBIGUOUS | MISMATCH | UNKNOWN."""
    out = {'checked_unix': round(time.time(), 1), 'known_port': KNOWN_PORT}
    try:
        found = find_astra(sysfs)
    except AstraUsbError as exc:
        out.update(state=exc.state, detail=str(exc))
        if exc.state == 'NOT_DETECTED':
            failed = recent_enumeration_failure(sysfs)
            if failed:
                out['enumeration_failure'] = failed
                out['detail'] = ('A USB device plugged into port %s failed to start at %s (power or contact problem) and '
                                 'is not visible on USB. If that was the Astra: unplug it, then use a different port or a '
                                 'powered USB hub.' % (failed['port'], time.strftime('%H:%M', time.localtime(failed['last_unix']))))
        return out
    except OSError as exc:
        out.update(state='UNKNOWN', detail='USB query failed: %s' % exc)
        return out
    out.update(port=found['hub_port'], depth_port=found['depth_port'], rgb_port=found['rgb_port'],
               on_known_port=found['hub_port'] == KNOWN_PORT)
    access = {}
    if dev_check:
        for k in ('depth', 'rgb'):
            node = _node(found[k])
            alias = Path(ALIASES[k])
            try:
                alias_ok = os.path.lexists(alias) and alias.resolve(strict=True) == node
            except OSError:
                alias_ok = False
            access[k] = {'read_write': os.access(node, os.R_OK | os.W_OK), 'alias': alias_ok}
        out['access'] = access
        ok = all(v['read_write'] and v['alias'] for v in access.values())
        out['state'] = 'CONNECTED' if ok else 'NO_ACCESS'
        out['detail'] = ('Astra connected on USB %s' % found['hub_port']) if ok else (
            'Astra connected on USB %s but the access rule does not cover it' % found['hub_port'])
    else:
        out.update(state='CONNECTED', detail='Astra connected on USB %s' % found['hub_port'])
    return out

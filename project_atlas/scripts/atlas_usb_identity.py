"""Passive CH340 role discovery. No serial writes, queries or reset commands.

USB identity cannot distinguish ATLAS's three serial-number-less CH340 devices.
Never infer a motor controller from its tty number, connector or shared by-id.
Return the SAME verified open handle, not a path to reopen without validation.
"""
import os
from pathlib import Path
import subprocess
import time


def protocol_matches(data, role):
    if role == 'gps':
        kinds = []
        for line in data.splitlines():
            if not line.startswith(b'$') or b'*' not in line:
                continue
            body, check = line[1:].split(b'*', 1)
            checksum = 0
            for value in body:
                checksum ^= value
            try:
                good = len(check.strip()) == 2 and checksum == int(check[:2], 16)
            except ValueError:
                good = False
            if good and len(body) >= 6 and body[5:6] == b',':
                kinds.append(body[2:5])
        return len(kinds) >= 3 and b'GGA' in kinds and b'RMC' in kinds
    if role == 'imu':
        kinds = []
        i = 0
        while i + 11 <= len(data):
            p = data[i:i+11]
            if p[0] == 0x55 and p[1] in (0x51, 0x52, 0x53, 0x54) and sum(p[:10]) % 256 == p[10]:
                kinds.append(p[1])
                i += 11
            else:
                i += 1
        return len(kinds) >= 6 and 0x51 in kinds and 0x52 in kinds
    if role == 'yahboom':
        kinds = []
        i = 0
        while i + 5 <= len(data):
            length = data[i+2]
            total = length + 2
            if data[i:i+2] == b'\xff\xfb' and 4 <= length <= 64 and i + total <= len(data):
                p = data[i:i+total]
                if sum(p[2:-1]) % 256 == p[-1] and p[3] in (0x0A, 0x0B, 0x0C, 0x0D, 0x0E):
                    kinds.append(p[3])
                    i += total
                    continue
            i += 1
        return len(kinds) >= 4 and 0x0D in kinds and len(set(kinds)) >= 2
    raise ValueError('Unknown USB role')


def candidates():
    from serial.tools import list_ports
    return sorted({p.device for p in list_ports.comports()
                   if (p.vid, p.pid) == (0x1A86, 0x7523)})


def in_use(path):
    # Includes old non-flocking drivers. Never read their streams or alter baud.
    result = subprocess.run(['fuser', path], capture_output=True, timeout=2)
    if result.returncode == 0:
        return True
    if result.returncode != 1 or result.stderr.strip():
        raise OSError('Cannot establish serial ownership')
    return False


def open_verified(role, preferred='', duration=1.6):
    import fcntl
    import serial
    if role not in ('gps', 'imu', 'yahboom'):
        raise ValueError('Unknown USB role')
    folder = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    # All auto-discovery users serialize their passive probes. Do not queue in
    # a ROS callback; callers retry later if another discovery is in progress.
    lock_path = folder / 'atlas-usb-discovery.lock'
    with lock_path.open('a') as lock:
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OSError('USB discovery busy; retry later') from None
        paths = candidates()
        if len(paths) > 8:
            raise OSError('Unexpected number of CH340 devices; refusing broad scan')
        paths.sort(key=lambda p: (p != os.path.realpath(preferred), p))
        matches = []
        try:
            for path in paths:
                if in_use(path):
                    continue
                link = None
                try:
                    link = serial.Serial(port=None, baudrate=115200 if role == 'yahboom' else 9600,
                                         timeout=.05, write_timeout=.2, exclusive=True)
                    link.dtr = False
                    link.rts = False
                    link.port = path
                    link.open()
                    data = bytearray()
                    until = time.monotonic() + duration
                    while time.monotonic() < until:
                        data.extend(link.read(2048))
                        if len(data) > 32768:
                            del data[:-32768]
                        if protocol_matches(data, role):
                            matches.append(link)
                            link = None
                            break
                except (OSError, serial.SerialException):
                    pass
                finally:
                    if link is not None:
                        link.close()
            if len(matches) != 1:
                raise OSError(f'{role}: expected one unclaimed verified device, found {len(matches)}')
            result = matches.pop()
            result.timeout = None if role == 'yahboom' else 0
            return result
        finally:
            for link in matches:
                link.close()

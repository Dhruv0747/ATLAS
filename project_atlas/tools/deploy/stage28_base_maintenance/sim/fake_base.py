#!/usr/bin/env python3
"""SIMULATION ONLY. Fake Type=notify rover-base-telemetry for the container systemd user manager.

Board discovery delay, READY=1, watchdog pings, a heartbeat file standing in for /atlas/encoder_health and the
serial packet counter, and failure injection. Emulates the RC hook: when the installed yahboom_base.py contains
the Stage 28 RC marker, it "publishes" /atlas/rc/frames (rc_publisher file with its pid).
"""
import json
import os
import signal
from pathlib import Path
import socket
import sys
import time

SIM = Path(os.environ['SIM_STATE'])
SCRIPTS = Path(os.environ['SIM_SCRIPTS'])
INV = os.environ.get('INVOCATION_ID', '-')


def log(msg):
    print(f'{INV} {time.time():.3f} {msg}', flush=True)


def notify(m):
    a = os.environ.get('NOTIFY_SOCKET')
    if a:
        a = '\0' + a[1:] if a.startswith('@') else a
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(a)
            s.sendall(m.encode())


def flag(name):
    return (SIM / name).exists()


def num(name, default):
    try:
        return float((SIM / name).read_text())
    except (OSError, ValueError):
        return default


def _term(signum, frame):
    # rclpy shutdown + serial close can take seconds; TimeoutStopSec=5 in production
    log('SIGTERM: shutting down')
    time.sleep(num('stop_s', 0.0))
    os._exit(0)


signal.signal(signal.SIGTERM, _term)
code = (SCRIPTS / 'yahboom_base.py').read_text()
rc = '# ATLAS Stage 28 RC report' in code
with open(SIM / 'starts.log', 'a') as f:
    f.write(json.dumps({'t': time.time(), 'pid': os.getpid(), 'inv': INV, 'rc': rc}) + '\n')
time.sleep(num('init_s', 2.0))                       # serial discovery + IMU init (unit is "activating")
if flag('fail_init') or (rc and flag('candidate_fails_init')):
    log('Traceback (most recent call last): simulated init failure')
    sys.exit(1)
notify('READY=1\nSTATUS=fake board ready')
log('[INFO] [yahboom_base]: Yahboom board ready on /dev/fake, firmware=3.6, car_type=5')
if rc:
    (SIM / 'rc_publisher').write_text(str(os.getpid()))
time.sleep(num('gap_s', 0.0))                        # DDS rediscovery gap before subscribers see data
n = 0
t_ready = time.monotonic()
while True:
    if flag('crash') or (rc and flag('candidate_crash_after_s') and time.monotonic() - t_ready > num('candidate_crash_after_s', 1)):
        log('simulated crash')
        os._exit(70)
    if not flag('hang'):
        notify('WATCHDOG=1')
    n += 1
    if n % 6 == 0:                                   # ~3 Hz, like yahboom_base's odom runtime file
        otmp = SIM / f'odom.{os.getpid()}.tmp'
        otmp.write_text(json.dumps({'x': -0.0035, 'y': 0.0, 'yaw': 0.0}))
        os.replace(otmp, SIM / 'odom.json')
    tmp = SIM / f'hb.{os.getpid()}.tmp'
    tmp.write_text(json.dumps({'mono': time.monotonic(), 'wall': time.time(), 'n': n, 'pid': os.getpid()}))
    os.replace(tmp, SIM / 'hb')
    time.sleep(0.05)

#!/usr/bin/env python3
"""Read-only FlySky receiver bridge: PROPOSAL / NOT DEPLOYED / NOT ENABLED.

Purpose: get receiver channel frames to the dashboard WITHOUT touching the Yahboom/STM32 board or its firmware.
It reads ONE dedicated serial adapter that is wired only to the receiver, validates frames passively, and publishes
them on /atlas/rc/frames for the FlySky Test Lab to display.

Safety rules (tests enforce each):
  * Read only: the port is only ever read. This file contains no write/send call on the port.
  * It publishes exactly ONE topic (/atlas/rc/frames, std_msgs/String JSON) and subscribes to nothing. No cmd_vel, no
    steering, no estop, no joystick topic, no service, no action.
  * It refuses ambiguous ports. ATLAS has three serial-number-less CH340 adapters whose /dev/ttyUSBn numbers can swap
    across reboots, so only a /dev/serial/by-id path with a unique serial is accepted, never a bare ttyUSBn and never the
    generic "USB_Serial" CH340 name. It also refuses a port another process already holds open.
  * Output is rate limited (20 Hz, plus an immediate frame when the failsafe/frame-lost/digital flags change) so it can
    never become a heavy ROS load.
  * Only frames that pass the protocol checks are forwarded; everything else is counted and dropped.

Electrical (owner to confirm from the receiver and adapter documentation before wiring; NOT verified here):
  * FS-iA10B SBUS is inverted-logic serial, 100000 baud, 8E2. A USB-serial adapter needs a hardware inverter (or an
    adapter that supports RX inversion) to read it.
  * FS-iA10B iBUS is normal-polarity 115200 8N1 and needs no inverter. This is the simpler read-only route.
  * Ground must be common between the receiver and the adapter. Use the adapter's RX pin only; leave its TX unconnected.
  * Check the receiver and adapter logic levels (3.3 V vs 5 V) before connecting.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_flysky_core as core   # noqa: E402

TOPIC = '/atlas/rc/frames'
MAX_HZ = 20.0
BY_ID = re.compile(r'^/dev/serial/by-id/[A-Za-z0-9_.:+-]+$')
AMBIGUOUS = ('USB_Serial', 'CH340', 'QinHeng', '1a86')     # the three serial-number-less ATLAS adapters share these
SETTINGS = {'ibus': dict(baud=115200, parity='N', stopbits=1), 'sbus': dict(baud=100000, parity='E', stopbits=2)}


class PortRefused(Exception):
    pass


def check_port(path: str, in_use: Callable[[str], bool]) -> str:
    """Return the resolved device path, or raise PortRefused with the reason."""
    if not BY_ID.match(path):
        raise PortRefused('only a /dev/serial/by-id/<unique adapter> path is accepted, not %r' % path)
    if any(tag.lower() in path.lower() for tag in AMBIGUOUS):
        raise PortRefused('that adapter name is shared by ATLAS CH340 devices and cannot be told apart; use an adapter with a unique serial')
    real = str(Path(path).resolve())
    if not Path(path).exists():
        raise PortRefused('port does not exist')
    if in_use(real):
        raise PortRefused('port is already held open by another process')
    return real


class FrameForwarder:
    """Decides which valid frames to publish: at most MAX_HZ, plus immediately on a flag change."""

    def __init__(self, proto: str, max_hz: float = MAX_HZ):
        self.parser = core.StreamParser(proto)
        self.proto = proto
        self.min_dt = 1.0 / max_hz
        self.last_pub = -1e9
        self.last_flags: Optional[tuple] = None
        self.seq = 0
        self.dropped_rate = 0

    def feed(self, data: bytes, rx: float, wall: float, publish: Callable[[Dict[str, Any]], None]) -> int:
        n = 0
        for f in self.parser.feed(data, rx, wall):
            flags = (f.frame_lost, f.failsafe, f.ch17, f.ch18)
            if rx - self.last_pub < self.min_dt and flags == self.last_flags:
                self.dropped_rate += 1
                continue
            self.seq += 1
            raw = (core.encode_sbus(f.raw, bool(f.ch17), bool(f.ch18), bool(f.frame_lost), bool(f.failsafe))
                   if f.proto == 'sbus' else core.encode_ibus(f.raw))
            publish({'proto': f.proto, 'hex': raw.hex(), 'seq': self.seq})
            self.last_pub, self.last_flags = rx, flags
            n += 1
        return n


def main(argv=None) -> int:                                    # pragma: no cover - needs ROS and hardware
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--port', required=True)
    ap.add_argument('--proto', choices=sorted(SETTINGS), default='ibus')
    a = ap.parse_args(argv)
    from atlas_usb_identity import in_use
    try:
        dev = check_port(a.port, in_use)
    except PortRefused as exc:
        print('REFUSED:', exc, file=sys.stderr)
        return 2
    import rclpy
    import serial
    from std_msgs.msg import String
    s = SETTINGS[a.proto]
    ser = serial.Serial(dev, s['baud'], parity=s['parity'], stopbits=s['stopbits'], timeout=0.02, dsrdtr=False, rtscts=False)
    rclpy.init()
    node = rclpy.create_node('atlas_rc_readonly_bridge')
    pub = node.create_publisher(String, TOPIC, 10)
    fwd = FrameForwarder(a.proto)

    def publish(msg):
        out = String()
        out.data = json.dumps(msg, separators=(',', ':'))
        pub.publish(out)
    try:
        while rclpy.ok():
            data = ser.read(64)
            if data:
                fwd.feed(data, time.monotonic(), time.time(), publish)
    finally:
        ser.close()
        node.destroy_node()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

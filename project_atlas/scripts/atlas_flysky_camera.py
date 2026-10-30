#!/usr/bin/env python3
"""ATLAS FlySky camera knobs: VrA (CH9) -> camera pan, VrB (CH10) -> camera tilt.

Separate from driving: it never touches /cmd_vel*, the mux or the E-STOP. Its only outputs are the same servo command
topics the Xbox D-pad node uses (/camera/bottom_servo_cmd_us pan, /camera/second_servo_cmd_us tilt, 700..2300 us) and
the same "manual camera action pauses tracking" message.

A knob is an ABSOLUTE control, so (all tested in KnobCamera, pure, no ROS):
  * nothing happens until the receiver has been LIVE (fresh frames, no failsafe, no frame-lost) for LINK_HEALTHY_S;
    a failsafe (every channel 1024) or a lost signal freezes the camera where it is and drops control;
  * the first good reading is only a REFERENCE: a knob follows only after it is turned more than ENGAGE_COUNTS from it
    (power-on, reconnect, or the knob simply resting somewhere never moves the camera);
  * the servo slews to the knob position at the D-pad's speed (SERVO_RATE_US_S), never jumps; it starts from the servo's
    reported position and does nothing without that feedback;
  * RELEASE_S after the knob stops moving, control is released (no more commands), so the D-pad, the dashboard and
    tracking work as before; the knob must be turned again to take control back.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

SERVO_MIN, SERVO_MAX = 700, 2300          # same limits as camera_joystick_node.py
RAW_MIN, RAW_MAX = 240, 1807              # owner-verified FS-i6S knob travel (CH9/CH10, 2026-10-29)
RAW_MARGIN = 60
ENGAGE_COUNTS = 50                        # about 3 % of the knob travel
RELEASE_S = 2.0
LINK_HEALTHY_S = 1.0
FRAME_TIMEOUT_S = 0.5
SERVO_RATE_US_S = 400.0                   # the D-pad node's default rate
AXES = {'pan': {'channel': 9, 'reversed': False}, 'tilt': {'channel': 10, 'reversed': False}}


def knob_to_us(raw: int, reversed_: bool) -> int:
    f = (min(RAW_MAX, max(RAW_MIN, raw)) - RAW_MIN) / float(RAW_MAX - RAW_MIN)
    if reversed_:
        f = 1.0 - f
    return int(round(SERVO_MIN + f * (SERVO_MAX - SERVO_MIN)))


@dataclass
class Axis:
    channel: int
    reversed: bool
    ref: Optional[int] = None             # reading the knob must move away from to take control
    engaged: bool = False
    last_move: float = -1e9
    last_raw: Optional[int] = None
    out: Optional[float] = None           # current commanded position (us)
    feedback: Optional[int] = None


@dataclass
class KnobCamera:
    axes: Dict[str, Axis] = field(default_factory=lambda: {k: Axis(v['channel'], v['reversed']) for k, v in AXES.items()})
    healthy_since: Optional[float] = None
    last_t: Optional[float] = None

    def on_feedback(self, name: str, us: int) -> None:
        if SERVO_MIN <= us <= SERVO_MAX:
            self.axes[name].feedback = us

    def _drop(self) -> None:
        for a in self.axes.values():
            a.ref = None; a.engaged = False; a.out = None; a.last_raw = None

    def step(self, frame, now: float) -> Dict[str, int]:
        """frame: RcFrame or None. Returns {axis: us} to publish now (empty = publish nothing)."""
        dt = 0.0 if self.last_t is None else max(0.0, min(0.1, now - self.last_t))
        self.last_t = now
        ok = (frame is not None and now - frame.rx <= FRAME_TIMEOUT_S and not frame.failsafe and not frame.frame_lost
              and len(frame.raw) >= max(a.channel for a in self.axes.values()))
        if not ok:
            self.healthy_since = None
            self._drop()                                    # freeze where it is; never chase failsafe values
            return {}
        if self.healthy_since is None:
            self.healthy_since = now
        if now - self.healthy_since < LINK_HEALTHY_S:
            return {}
        out = {}
        for name, a in self.axes.items():
            raw = frame.raw[a.channel - 1]
            if not (RAW_MIN - RAW_MARGIN <= raw <= RAW_MAX + RAW_MARGIN):
                a.ref = None; a.engaged = False; a.out = None
                continue
            if a.ref is None:
                a.ref, a.last_raw = raw, raw
                continue
            if a.last_raw is not None and abs(raw - a.last_raw) > 3:
                a.last_move = now
            a.last_raw = raw
            if not a.engaged:
                if abs(raw - a.ref) > ENGAGE_COUNTS and a.feedback is not None:
                    a.engaged, a.out, a.last_move = True, float(a.feedback), now
                else:
                    continue
            if now - a.last_move > RELEASE_S:
                a.engaged, a.ref, a.out = False, raw, None   # release; turn again to take control back
                continue
            target = knob_to_us(raw, a.reversed)
            step = SERVO_RATE_US_S * dt
            a.out += max(-step, min(step, target - a.out))
            us = int(round(max(SERVO_MIN, min(SERVO_MAX, a.out))))
            out[name] = us
        return out

    def status(self) -> Dict[str, object]:
        return {name: {'engaged': a.engaged, 'ref': a.ref, 'out': None if a.out is None else int(round(a.out)),
                       'feedback': a.feedback} for name, a in self.axes.items()} | {'link_ok': self.healthy_since is not None}


def main(argv=None):                                        # pragma: no cover - needs ROS
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import Bool, Int32, String
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import atlas_flysky_drive_core as dc

    rclpy.init(args=argv)
    node = Node('atlas_flysky_camera')
    logic = KnobCamera()
    for name, spec in AXES.items():
        env = os.environ.get('ATLAS_FLYSKY_CAMERA_%s_REVERSED' % name.upper())
        if env in ('0', '1'):
            logic.axes[name].reversed = env == '1'
    st = {'frame': None, 'last_pub': {}, 'engaged': False}
    pubs = {'pan': node.create_publisher(Int32, '/camera/bottom_servo_cmd_us', 1),
            'tilt': node.create_publisher(Int32, '/camera/second_servo_cmd_us', 1)}
    tracking = node.create_publisher(Bool, '/atlas/camera_tracking/enabled', 10)
    node.create_subscription(Int32, '/camera/bottom_servo_us', lambda m: logic.on_feedback('pan', m.data), 10)
    node.create_subscription(Int32, '/camera/second_servo_us', lambda m: logic.on_feedback('tilt', m.data), 10)

    def on_frame(m):
        try:
            st['frame'] = dc.parse_message(json.loads(m.data), time.monotonic())
        except (TypeError, ValueError):
            pass
    node.create_subscription(String, '/atlas/rc/frames', on_frame, 10)

    def tick():
        now = time.monotonic()
        cmds = logic.step(st['frame'], now)
        if cmds and not st['engaged']:
            tracking.publish(Bool(data=False))             # a manual camera action pauses tracking (as the D-pad does)
            node.get_logger().info('FlySky camera knob control: %s' % ', '.join(sorted(cmds)))
        if not cmds and st['engaged']:
            node.get_logger().info('FlySky camera knobs released')
        st['engaged'] = bool(cmds)
        for name, us in cmds.items():
            if st['last_pub'].get(name) != us:
                pubs[name].publish(Int32(data=us))
                st['last_pub'][name] = us
        if not cmds:
            st['last_pub'] = {}

    node.create_timer(0.04, tick)
    node.get_logger().info('FlySky camera ready: VrA (CH9) pan, VrB (CH10) tilt; turn a knob to take control '
                           '(reversed pan=%s tilt=%s)' % (logic.axes['pan'].reversed, logic.axes['tilt'].reversed))
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

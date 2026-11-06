#!/usr/bin/env python3
"""ATLAS dashboard: live Xbox controller input for the FlySky Driving page (Stage 29, additive, READ ONLY).

GET /api/controller_inputs -> {"xbox": {"state", "age_s", "rate_hz", "axes", "buttons", "layout_ok"}, "read_only": true}

Hard rules (tests enforce each):
  * READ ONLY. One subscription (/joy, sensor_msgs/Joy). It creates no ROS publisher, no service client, imports no
    motion/stop message type and answers no POST. Pressing a button can only change numbers on the page.
  * It does not touch the dashboard's own /joy subscription (the "joy" item feeds the web E-STOP observation).
    This module owns a separate lazy node, started on the first page request and torn down after IDLE_STOP_S
    without a request, the same pattern as atlas_flysky_web.
  * Values are copied, bounded and rounded; a malformed message is counted, never forwarded.
"""
from __future__ import annotations

import json
import math
import threading
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlsplit

ROUTE = '/api/controller_inputs'
JOY_TOPIC = '/joy'
IDLE_STOP_S = 60.0
LIVE_MAX_AGE_S = 0.5            # same staleness the mux RemoteStop uses to latch "joystick unavailable"
STALE_MAX_AGE_S = 3.0
XBOX_AXES, XBOX_BUTTONS = 8, 11 # Xbox 360 pad through joy_node on this rover (verified live 2026-10-29)
MAX_LEN = 32


class RosTransport:
    """Own node + executor thread; ONE /joy subscription, NO publishers."""

    def __init__(self):
        self.node = self._exec = self._thread = None

    def start(self, on_message: Callable[[list, list], None]) -> None:
        import rclpy
        import rclpy.executors
        from sensor_msgs.msg import Joy
        self.node = rclpy.create_node('atlas_controller_input_readonly')
        self.node.create_subscription(Joy, JOY_TOPIC, lambda m: on_message(list(m.axes), list(m.buttons)), 10)
        self._exec = rclpy.executors.SingleThreadedExecutor()
        self._exec.add_node(self.node)
        self._thread = threading.Thread(target=self._exec.spin, name='atlas-controller-input-ros', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        try:
            if self._exec is not None:
                self._exec.shutdown()
            if self.node is not None:
                self.node.destroy_node()
        except Exception:
            pass
        self.node = self._exec = self._thread = None


def _clean(axes, buttons):
    if not isinstance(axes, (list, tuple)) or not isinstance(buttons, (list, tuple)):
        return None
    if len(axes) > MAX_LEN or len(buttons) > MAX_LEN:
        return None
    try:
        a = [float(x) for x in axes]
        b = [int(x) for x in buttons]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in a):
        return None
    return [round(max(-1.0, min(1.0, x)), 3) for x in a], [1 if x else 0 for x in b]


class InputService:
    def __init__(self, transport_factory: Callable[[], Any] = RosTransport, clock: Callable[[], float] = time.monotonic,
                 start_threads: bool = True):
        self.factory, self.clock = transport_factory, clock
        self.lock = threading.RLock()
        self.transport = None
        self.last = None            # (rx, axes, buttons)
        self.rx_times = []
        self.bad = 0
        self.total = 0
        self.last_request = 0.0
        if start_threads:
            threading.Thread(target=self._reaper, name='atlas-controller-input-idle', daemon=True).start()

    def _on_message(self, axes, buttons) -> None:
        c = _clean(axes, buttons)
        now = self.clock()
        with self.lock:
            if c is None:
                self.bad += 1
                return
            self.total += 1
            self.last = (now, c[0], c[1])
            self.rx_times.append(now)
            if len(self.rx_times) > 64:
                del self.rx_times[:-64]

    def ensure_started(self) -> None:
        with self.lock:
            self.last_request = self.clock()
            if self.transport is None:
                t = self.factory()
                t.start(self._on_message)
                self.transport = t

    def _reaper(self) -> None:
        while True:
            time.sleep(5.0)
            self.reap()

    def reap(self) -> None:
        with self.lock:
            if self.transport is not None and self.clock() - self.last_request > IDLE_STOP_S:
                self.transport.stop()
                self.transport = None
                self.last = None
                self.rx_times = []

    def state(self) -> Dict[str, Any]:
        self.ensure_started()
        with self.lock:
            now = self.clock()
            recent = [t for t in self.rx_times if now - t <= 2.0]
            rate = round((len(recent) - 1) / (recent[-1] - recent[0]), 1) if len(recent) > 2 and recent[-1] > recent[0] else 0.0
            if self.last is None:
                xb = {'state': 'NO_DATA', 'age_s': None, 'rate_hz': 0.0, 'axes': [], 'buttons': [], 'layout_ok': None}
            else:
                rx, axes, buttons = self.last
                age = now - rx
                st = 'LIVE' if age <= LIVE_MAX_AGE_S else 'STALE' if age <= STALE_MAX_AGE_S else 'LOST'
                xb = {'state': st, 'age_s': round(age, 3), 'rate_hz': rate, 'axes': axes, 'buttons': buttons,
                      'layout_ok': len(axes) == XBOX_AXES and len(buttons) == XBOX_BUTTONS}
            xb.update({'messages': self.total, 'malformed': self.bad, 'topic': JOY_TOPIC,
                       'live_max_age_s': LIVE_MAX_AGE_S})
            return {'xbox': xb, 'read_only': True}


_SERVICE: Optional[InputService] = None
_SERVICE_LOCK = threading.Lock()


def service() -> InputService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = InputService()
        return _SERVICE


def _send(handler, code, data) -> None:
    body = json.dumps(data, allow_nan=False, separators=(',', ':')).encode()
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def serve(handler, ros=None, post=False, svc: Optional[InputService] = None) -> bool:
    """True when the request was for ROUTE (answered here). GET only; a POST is refused."""
    if urlsplit(handler.path).path != ROUTE:
        return False
    if post:
        _send(handler, 405, {'ok': False, 'message': 'read only'})
        return True
    _send(handler, 200, (svc or service()).state())
    return True

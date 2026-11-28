#!/usr/bin/env python3
"""FlySky Remote Test Lab: read-only web API + a tiny lazy ROS subscriber (additive hook for atlas_status_web).

Hard rules this module keeps (tests enforce each):
  * READ ONLY.  It creates no ROS publisher, imports no motion/steering/estop message type, opens no serial port and
    makes no network request.  Moving the transmitter sticks can only change numbers on the page.
  * It never touches the Yahboom/STM32 port.  The only input is ONE topic, /atlas/rc/frames, that a separate read-only
    receiver bridge may publish.  If nobody publishes it, the page says SIGNAL NOT VERIFIED and why.
  * Bounded and event driven: the subscription is created on the first page request and torn down after
    IDLE_STOP_S without a client (and with no recording open).  No timers run while idle.
  * POST accepts exactly ACTIONS: record start/stop and reset-ranges.  Nothing else.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

import atlas_flysky_core as core

API = '/api/flysky/'
FRAMES_TOPIC = '/atlas/rc/frames'
MAX_BODY = 256
IDLE_STOP_S = 120.0
TICK_S = 0.25
ACTIONS = {'session_start': {'action'}, 'session_stop': {'action'}, 'reset_ranges': {'action'}}
SESSION_ID = re.compile(r'^[0-9a-f]{12}$')
KEEP_FILES = 50


def default_dir() -> Path:
    return Path(os.environ.get('ATLAS_FLYSKY_DIR') or (Path.home() / 'project_atlas' / 'data' / 'diagnostics' / 'flysky'))


class RosTransport:
    """Own node + executor thread; ONE subscription, NO publishers."""

    def __init__(self):
        self.node = None
        self._exec = None
        self._thread = None

    def start(self, on_message) -> None:
        import rclpy
        import rclpy.executors
        from std_msgs.msg import String
        self.node = rclpy.create_node('atlas_flysky_readonly')
        self.node.create_subscription(String, FRAMES_TOPIC, lambda m: on_message(m.data), 10)
        self._exec = rclpy.executors.SingleThreadedExecutor()
        self._exec.add_node(self.node)
        self._thread = threading.Thread(target=self._exec.spin, name='atlas-flysky-ros', daemon=True)
        self._thread.start()

    def publisher_count(self) -> int:
        return len(self.node.get_publishers_info_by_topic(FRAMES_TOPIC)) if self.node is not None else 0

    def stop(self) -> None:
        try:
            if self._exec is not None:
                self._exec.shutdown()
            if self.node is not None:
                self.node.destroy_node()
        except Exception:
            pass
        self.node = self._exec = None


class FlyskyService:
    def __init__(self, transport_factory: Callable[[], Any] = RosTransport, state_dir: Optional[Path] = None,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time,
                 start_threads: bool = True):
        self.factory, self.clock, self.wall = transport_factory, clock, wall
        self.dir = Path(state_dir) if state_dir else default_dir()
        self.lock = threading.RLock()
        self.lab = core.FlyskyLab()
        self.transport = None
        self.touched = clock()
        self.start_threads = start_threads
        self._ticker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.last_session: Optional[core.LabSession] = None
        self.saved_files: List[str] = []

    # ---- lifecycle
    def ensure_started(self) -> None:
        with self.lock:
            self.touched = self.clock()
            if self.transport is not None:
                return
            t = self.factory()
            t.start(self._on_message)
            self.transport = t
            if self.start_threads:
                self._stop.clear()
                self._ticker = threading.Thread(target=self._loop, name='atlas-flysky-tick', daemon=True)
                self._ticker.start()

    def stop(self) -> None:
        with self.lock:
            self._close_session('service_stopping')
            self._stop.set()
            t, self.transport = self.transport, None
        if t is not None:
            t.stop()

    def _loop(self) -> None:
        while not self._stop.wait(TICK_S):
            try:
                with self.lock:
                    self.lab.tick(self.clock())
                    if self.lab.session is None and self.clock() - self.touched > IDLE_STOP_S:
                        break
            except Exception:
                pass
        if not self._stop.is_set():
            self.stop()

    def _on_message(self, data: str) -> None:
        try:
            msg = json.loads(data)
        except (TypeError, ValueError):
            with self.lock:
                self.lab.bad_messages += 1
            return
        with self.lock:
            self.lab.ingest_message(msg, self.clock(), self.wall())

    # ---- sessions
    def _close_session(self, reason: str) -> Optional[str]:
        s = self.lab.session
        if s is None:
            return None
        s.event('session_end', self.wall(), self.clock(), reason)
        s.closed = True
        self.lab.session, self.last_session = None, s
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            name = 'flysky_%s_%s.csv' % (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(s.started_wall)), s.id)
            fd = os.open(str(self.dir / name), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
            with os.fdopen(fd, 'w', newline='') as fh:
                fh.write(s.to_csv())
            for old in sorted(self.dir.glob('flysky_*.csv'))[:-KEEP_FILES]:
                old.unlink()
            self.saved_files = [p.name for p in sorted(self.dir.glob('flysky_*.csv'))][-20:]
            return name
        except OSError:
            return None

    # ---- read API
    def state(self, history: bool = True) -> Dict[str, Any]:
        self.ensure_started()
        with self.lock:
            now = self.clock()
            pubs = self.transport.publisher_count() if self.transport is not None else 0
            avail = pubs > 0 or self.lab.total_frames > 0 and now - (self.lab.last.rx if self.lab.last else -1e9) < core.STALE_MAX_AGE_S
            reason = '' if avail else core.NO_SOURCE_REASON
            snap = self.lab.snapshot(now, avail, reason, history)
            snap.update({'server_time_utc': core._iso(self.wall()), 'topic': FRAMES_TOPIC, 'publishers': pubs,
                         'saved_files': self.saved_files[-10:], 'read_only': True,
                         'last_session': None if self.last_session is None else
                         {'id': self.last_session.id, 'rows': len(self.last_session.rows)}})
            return snap

    def csv_for(self, session_id: Optional[str]) -> Optional[str]:
        with self.lock:
            for s in (self.lab.session, self.last_session):
                if s is not None and session_id in (None, '', s.id):
                    return s.to_csv()
        if session_id and SESSION_ID.match(session_id):
            for p in self.dir.glob('flysky_*_%s.csv' % session_id):
                try:
                    return p.read_text()
                except OSError:
                    return None
        return None

    # ---- actions (record / reset only)
    def act(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = payload.get('action')
        if action not in ACTIONS or set(payload) != ACTIONS[action]:
            raise ValueError('unknown action or fields')
        self.ensure_started()
        with self.lock:
            if action == 'session_start':
                if self.lab.session is not None:
                    raise ValueError('a session is already recording')
                s = core.LabSession(secrets.token_hex(6), self.wall(), self.clock())
                s.event('session_start', self.wall(), self.clock())
                self.lab.session = s
                return {'ok': True, 'id': s.id}
            if action == 'session_stop':
                if self.lab.session is None:
                    raise ValueError('no session is recording')
                return {'ok': True, 'file': self._close_session('operator_stop')}
            self.lab.tracker.reset_ranges()
            return {'ok': True}


SERVICE = FlyskyService()


# ------------------------------------------------------------------- HTTP hook
def _send(handler, code: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None) -> None:
    handler.send_response(code)
    handler.send_header('Content-Type', ctype)
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', str(len(body)))
    for k, v in (extra or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)


def _json(handler, code: int, data: Dict[str, Any]) -> None:
    _send(handler, code, json.dumps(data, allow_nan=False, separators=(',', ':')).encode(), 'application/json')


def serve(handler, ros=None, post: bool = False, service: Optional[FlyskyService] = None) -> bool:
    """True when the request was an /api/flysky/ request (answered here)."""
    svc = service or SERVICE
    parts = urlsplit(handler.path)
    if not parts.path.startswith(API):
        return False
    route = parts.path[len(API):]
    try:
        if post:
            if route != 'action':
                return _json(handler, 404, {'error': 'unknown route'}) or True
            from atlas_wifi_web import same_origin
            headers = dict(handler.headers)
            if handler.headers.get('X-Atlas-Flysky') != '1':
                raise PermissionError('missing request header')
            headers['X-Atlas-Wifi'] = '1'
            if not same_origin(headers):
                raise PermissionError('same-origin request required')
            length = int(handler.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY or handler.headers.get_content_type() != 'application/json':
                raise ValueError('bounded JSON request required')
            payload = json.loads(handler.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('JSON object required')
            _json(handler, 200, svc.act(payload))
        elif route == 'state':
            q = parse_qs(parts.query)
            _json(handler, 200, svc.state(history=q.get('history', ['1'])[0] != '0'))
        elif route == 'session.csv':
            sid = parse_qs(parts.query).get('id', [None])[0]
            text = svc.csv_for(sid)
            if text is None:
                _json(handler, 404, {'error': 'no such session'})
            else:
                _send(handler, 200, text.encode(), 'text/csv; charset=utf-8',
                      {'Content-Disposition': 'attachment; filename="atlas_flysky_%s.csv"' % (sid or 'current')})
        else:
            _json(handler, 404, {'error': 'unknown route'})
    except PermissionError as exc:
        _json(handler, 403, {'error': str(exc)})
    except (ValueError, TypeError, KeyError) as exc:
        _json(handler, 400, {'error': str(exc)})
    except Exception:
        _json(handler, 503, {'error': 'FlySky Test Lab service unavailable'})
    return True

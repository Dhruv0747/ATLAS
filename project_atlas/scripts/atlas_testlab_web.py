#!/usr/bin/env python3
"""Motor & Encoder Test Lab: web API + ROS transport (additive hook for atlas_status_web, same pattern as
atlas_location_check_web).

Architecture rules this module keeps:
  * It NEVER opens the STM32 serial port or any serial device.  The Yahboom base driver stays the sole hardware owner.
  * Read side: subscribes to existing telemetry (/atlas/encoder_update, /atlas/encoder_health and the lifted status).
  * Actuation side: the ONLY thing it can publish is a request for the EXISTING lifted-drive commissioning interface
    (/atlas/drive_pid/lifted/request), built by atlas_testlab_core.PulseRun, one bounded single-wheel raw pulse per run.
    It publishes nothing on cmd_vel / cmd_vel_web / joystick / motor topics, and exposes no general actuator API.
  * Pulse start is refused unless the owner itself reports every commissioning gate satisfied; the owner re-validates.
  * Everything runs in its own small ROS node + thread, started lazily on first use and stopped when idle.
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

import atlas_testlab_core as core

API = '/api/testlab/'
REQUEST_TOPIC = '/atlas/drive_pid/lifted/request'
STATUS_TOPIC = '/atlas/drive_pid/lifted/status'
MAX_BODY = 512
IDLE_STOP_S = 300.0
TICK_S = 0.05
GRAPH_S = 30.0
GRAPH_HZ = 8.0
ACTIONS = {
    'session_start': {'action', 'mode'}, 'session_stop': {'action'},
    'hand_begin': {'action', 'wheel', 'direction'}, 'hand_finish': {'action'}, 'hand_reset': {'action'},
    'pulse_start': {'action', 'wheel', 'direction', 'pwm', 'duration_s', 'confirm', 'checklist'},
    'pulse_cancel': {'action'}, 'pulse_recover': {'action'},
}
CHECKLIST_KEYS = ('wheels_lifted', 'support_secure', 'owner_present', 'power_cutoff_in_reach')
SESSION_ID = re.compile(r'^[0-9a-f]{12}$')


def default_dir() -> Path:
    return Path(os.environ.get('ATLAS_TESTLAB_DIR') or (Path.home() / 'project_atlas' / 'data' / 'diagnostics' / 'testlab'))


# ------------------------------------------------------------------ transports
class RosTransport:
    """Own node + executor thread.  Publisher for the lifted request topic is created only when a pulse run starts."""

    def __init__(self):
        self.node = None
        self.pub = None
        self._thread = None
        self._exec = None

    def start(self, on_update, on_health, on_status) -> None:
        import rclpy
        import rclpy.executors
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from std_msgs.msg import String
        self._String = String
        self._qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=20, reliability=ReliabilityPolicy.RELIABLE,
                               durability=DurabilityPolicy.VOLATILE)
        self.node = rclpy.create_node('atlas_testlab_readonly')
        self.node.create_subscription(String, '/atlas/encoder_update', lambda m: on_update(m.data), 10)
        self.node.create_subscription(String, '/atlas/encoder_health', lambda m: on_health(m.data), 10)
        self.node.create_subscription(String, STATUS_TOPIC, lambda m: on_status(m.data), self._qos)
        self._exec = rclpy.executors.SingleThreadedExecutor()
        self._exec.add_node(self.node)
        self._thread = threading.Thread(target=self._exec.spin, name='atlas-testlab-ros', daemon=True)
        self._thread.start()

    def publish_lifted_request(self, msg: Dict[str, Any]) -> None:
        if self.pub is None:
            self.pub = self.node.create_publisher(self._String, REQUEST_TOPIC, self._qos)
        out = self._String()
        out.data = json.dumps(msg, sort_keys=True, separators=(',', ':'))
        self.pub.publish(out)

    def subscriber_count(self) -> int:
        if self.pub is None:
            self.pub = self.node.create_publisher(self._String, REQUEST_TOPIC, self._qos)
        return self.pub.get_subscription_count()

    def stop(self) -> None:
        try:
            if self._exec is not None:
                self._exec.shutdown()
            if self.node is not None:
                self.node.destroy_node()
        except Exception:
            pass
        self.node = self.pub = self._exec = None


# --------------------------------------------------------------------- service
class TestLabService:
    __test__ = False        # not a unittest class

    def __init__(self, transport_factory: Callable[[], Any] = RosTransport, state_dir: Optional[Path] = None,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time,
                 start_threads: bool = True):
        self.factory, self.clock, self.wall = transport_factory, clock, wall
        self.dir = Path(state_dir) if state_dir else default_dir()
        self.lock = threading.RLock()
        self.buf = core.FrameBuffer()
        self.transport = None
        self.status: Optional[Dict[str, Any]] = None
        self.status_at: Optional[float] = None
        self.hand = core.HandTest()
        self.session: Optional[core.LabSession] = None
        self.last_session: Optional[core.LabSession] = None
        self.run: Optional[core.PulseRun] = None
        self.last_run_public: Optional[Dict[str, Any]] = None
        self.last_run_done_at = -1e9
        self.pulse_results: List[Dict[str, Any]] = []
        self.touched = clock()
        self.fault_cache: List[Dict[str, Any]] = []
        self.fault_cache_at = -1e9
        self.start_threads = start_threads
        self._ticker: Optional[threading.Thread] = None
        self._stop_ticker = threading.Event()
        self.saved_files: List[str] = []
        self.session_tail_until = 0.0

    # ---- lifecycle
    def ensure_started(self) -> None:
        with self.lock:
            self.touched = self.clock()
            if self.transport is not None:
                return
            t = self.factory()
            t.start(self._on_update, self._on_health, self._on_status)
            self.transport = t
            if self.start_threads:
                self._stop_ticker.clear()
                self._ticker = threading.Thread(target=self._loop, name='atlas-testlab-tick', daemon=True)
                self._ticker.start()

    def stop(self) -> None:
        with self.lock:
            if self.run and not self.run.done:
                self.run.cancel('service_stopping')
                self._tick_run()
            self._close_session('service_stopping')
            self._stop_ticker.set()
            t, self.transport = self.transport, None
        if t is not None:
            t.stop()

    def _loop(self) -> None:
        while not self._stop_ticker.wait(TICK_S):
            try:
                with self.lock:
                    self._tick_run()
                    busy = (self.run is not None and not self.run.done) or self.session is not None
                    if not busy and self.clock() - self.touched > IDLE_STOP_S:
                        break
            except Exception:
                pass
        if not self._stop_ticker.is_set():
            self.stop()

    # ---- ROS callbacks (executor thread)
    def _on_update(self, data: str) -> None:
        f = core.parse_update(data, self.clock(), self.wall())
        if f is None:
            return
        self.buf.add(f)
        with self.lock:
            s = self.session
            if s is not None:
                if self.run is not None and self.run.done and self.clock() > self.session_tail_until:
                    self._close_session('run_finished')
                else:
                    codes = ';'.join('%s:%s' % (x['code'], x['channel']) for x in self.fault_cache)
                    s.add_frame(f, self.buf.snapshot_health().get('state'), codes)
                    if s.closed:
                        self._close_session('session_limit')

    def _on_health(self, data: str) -> None:
        try:
            d = json.loads(data)
            if isinstance(d, dict):
                self.buf.set_health(d, self.clock())
        except ValueError:
            pass

    def _on_status(self, data: str) -> None:
        try:
            d = json.loads(data)
        except ValueError:
            return
        if not isinstance(d, dict):
            return
        with self.lock:
            self.status, self.status_at = d, self.clock()
            if self.run is not None and not self.run.done:
                self.run.on_status(d)

    # ---- pulse run plumbing
    def _tick_run(self) -> None:
        r = self.run
        if r is None:
            return
        was_done = r.done
        try:
            r.tick()
        except Exception as exc:      # a transport fault must end in the fail-safe path, never leave a run half-open
            r.error = r.error or 'transport_error: %s' % type(exc).__name__
            if r.entered:
                r._fail_safe('transport_error')
            elif not r.done:
                r._set('FAILED')
        if r.done and not was_done:
            self.last_run_done_at = self.clock()
            self.last_run_public = r.public()
            if r.observation:
                self.pulse_results.append({**r.observation, 'pwm': r.plan['pwm'], 'duration_s': r.plan['duration_s'],
                                           'direction': 'forward' if r.plan['pwm'] > 0 else 'reverse'})
            if self.session is not None:
                self.session.event('pulse_run_' + r.phase.lower(), self.wall(), self.clock(), r.plan['wheel'],
                                   r.error or json.dumps(r.observation or {}, sort_keys=True))
                self.session_tail_until = self.clock() + 2.0
            self._clear_token()
        elif self.session is not None and r.log:
            pass

    def _token_path(self) -> Path:
        return self.dir / 'lifted_session.json'

    def _persist_token(self, token: str, next_seq: int) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self._token_path().with_suffix('.tmp')
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as fh:
                json.dump({'token': token, 'next_seq': next_seq}, fh)
            os.replace(tmp, self._token_path())
        except OSError:
            pass

    def _clear_token(self) -> None:
        try:
            self._token_path().unlink()
        except OSError:
            pass

    def _publish(self, msg: Dict[str, Any]) -> None:
        if self.session is not None:
            self.session.event('request_' + str(msg.get('op')), self.wall(), self.clock(),
                               msg.get('wheel'), 'seq=%s' % msg.get('seq'))
        if msg.get('op') == 'enter' and hasattr(self.transport, 'subscriber_count') and self.transport.subscriber_count() == 0:
            raise RuntimeError('owner request subscriber unavailable')
        self.transport.publish_lifted_request(msg)

    # ---- sessions
    def _open_session(self, mode: str) -> core.LabSession:
        s = core.LabSession(secrets.token_hex(6), mode, self.wall(), self.clock())
        s.event('session_start', self.wall(), self.clock(), note=mode)
        self.session = s
        return s

    def _close_session(self, reason: str) -> Optional[str]:
        s = self.session
        if s is None:
            return None
        s.event('session_end', self.wall(), self.clock(), note=reason)
        s.closed = True
        self.session, self.last_session = None, s
        path = None
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            name = 'testlab_%s_%s_%s.csv' % (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(s.started_wall)), s.mode, s.id)
            path = self.dir / name
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
            with os.fdopen(fd, 'w', newline='') as fh:
                fh.write(s.to_csv())
            files = sorted(self.dir.glob('testlab_*.csv'))
            for old in files[:-100]:
                old.unlink()
            self.saved_files = [p.name for p in sorted(self.dir.glob('testlab_*.csv'))][-20:]
        except OSError:
            path = None
        return path.name if path else None

    # ---- read API
    def state(self, history: bool = True) -> Dict[str, Any]:
        self.ensure_started()
        with self.lock:
            now = self.clock()
            frames = self.buf.frames(60.0, now)
            health = self.buf.snapshot_health()
            view = core.channel_view(frames, health, now)
            expect = None
            if self.run is not None and not self.run.done:
                expect = {'channel': self.run.plan['wheel'], 'sign': 1 if self.run.plan['pwm'] > 0 else -1}
            elif self.hand.open_step is not None:
                o = self.hand.open_step
                expect = {'channel': o['wheel'], 'sign': 1 if o['direction'] == 'forward' else -1}
            faults = core.detect_faults(frames, health, now, expect=expect)
            self.fault_cache, self.fault_cache_at = faults, now
            age = None if self.status_at is None else round(now - self.status_at, 2)
            gate = core.gate_report(self.status, age)
            out: Dict[str, Any] = {
                'server_time_utc': core._iso(self.wall()), 'view': view, 'faults': faults,
                'comparison': core.direction_comparison(frames), 'gate': gate, 'status_age_s': age,
                'owner': self._owner_public(),
                'limits': {'max_pwm': core.MAX_RAW_PWM, 'min_duration_s': core.MIN_RAW_DURATION_S,
                           'max_duration_s': core.MAX_RAW_DURATION_S, 'confirmation_phrase': core.CONFIRMATION_PHRASE,
                           'checklist': list(CHECKLIST_KEYS), 'single_wheel_only': True},
                'run': self.run.public() if self.run is not None else self.last_run_public,
                'pulse_results': self.pulse_results[-12:],
                'hand': {'open': self.hand.open_step, 'results': self.hand.results[-16:],
                         'summary': {str(k): v for k, v in self.hand.summary().items()}},
                'session': self._session_public(self.session), 'last_session': self._session_public(self.last_session),
                'saved_files': self.saved_files, 'recoverable': self._token_path().exists() and self.run is None,
            }
            if history:
                out['graph'] = self._graph(frames, now)
            return out

    def _owner_public(self) -> Optional[Dict[str, Any]]:
        s = self.status
        if not s:
            return None
        keys = ('state', 'stop_latched', 'remote_b_stop', 'arm_ready', 'exit_ready', 'entry_problem', 'entry_stable_s',
                'fault_reason', 'raw_interface_enabled', 'physical_power_cut_confirmed', 'result', 'bms_ok', 'wheel', 'motor_pwm')
        return {k: s.get(k) for k in keys if k in s}

    @staticmethod
    def _session_public(s: Optional[core.LabSession]) -> Optional[Dict[str, Any]]:
        if s is None:
            return None
        return {'id': s.id, 'mode': s.mode, 'rows': len(s.rows), 'closed': s.closed, 'truncated': s.truncated,
                'events': s.events[-12:]}

    @staticmethod
    def _graph(frames: List[core.Frame], now: float) -> Dict[str, Any]:
        fr = [f for f in frames if now - f.rx <= GRAPH_S]
        if not fr:
            return {'t': [], 'turns': [[], [], [], []], 'raw': [[], [], [], []]}
        step = max(1, int(round(len(fr) / max(1.0, GRAPH_S * GRAPH_HZ))))
        pick = fr[::step]
        if pick[-1] is not fr[-1]:
            pick.append(fr[-1])
        base = fr[0].dist
        return {'t': [round(f.rx - now, 2) for f in pick],
                'turns': [[round((f.dist[i] - base[i]) / core.CIRCUMFERENCE_M, 4) for f in pick] for i in range(4)],
                'raw': [[f.raw[i] for f in pick] for i in range(4)]}

    def csv_for(self, session_id: Optional[str]) -> Optional[str]:
        with self.lock:
            for s in (self.session, self.last_session):
                if s is not None and (session_id in (None, '', s.id)):
                    return s.to_csv()
        if session_id and SESSION_ID.match(session_id):
            for p in self.dir.glob('testlab_*_%s.csv' % session_id):
                try:
                    return p.read_text()
                except OSError:
                    return None
        return None

    # ---- actions
    def act(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = payload.get('action')
        if action not in ACTIONS or set(payload) != ACTIONS[action]:
            raise ValueError('unsupported action or fields')
        self.ensure_started()
        with self.lock:
            now = self.clock()
            if action == 'session_start':
                if payload['mode'] not in ('observe', 'hand'):
                    raise ValueError('mode must be observe or hand')
                if self.session is not None:
                    raise PermissionError('a recording session is already open')
                s = self._open_session(payload['mode'])
                return {'ok': True, 'session': s.id}
            if action == 'session_stop':
                return {'ok': True, 'file': self._close_session('operator_stop')}
            if action == 'hand_begin':
                if self.run is not None and not self.run.done:
                    raise PermissionError('hand test is unavailable while a pulse run is active')
                f = self.buf.last()
                if f is None or now - f.rx > core.STALE_FRAME_S:
                    raise PermissionError('encoder data is stale; cannot start a hand-test step')
                w, d = payload['wheel'], payload['direction']
                if type(w) is not int:
                    raise ValueError('wheel must be 1-4')
                info = self.hand.begin(w, d, f)
                if self.session is None:
                    self._open_session('hand')
                if self.session is not None:
                    self.session.event('hand_begin', self.wall(), now, w, d)
                return {'ok': True, **info}
            if action == 'hand_finish':
                f = self.buf.last()
                if f is None or now - f.rx > core.STALE_FRAME_S:
                    raise PermissionError('encoder data is stale; step not scored')
                op = self.hand.open_step or {}
                res = self.hand.finish(f)
                if self.session is not None:
                    self.session.event('hand_result', self.wall(), now, op.get('wheel'),
                                       '%s ratio=%s %s' % (res['direction'], res['ratio'], res['status']))
                return {'ok': True, 'result': res}
            if action == 'hand_reset':
                self.hand = core.HandTest()
                saved = self._close_session('hand_test_cleared') if self.session is not None and self.session.mode == 'hand' else None
                return {'ok': True, 'file': saved}
            if action == 'pulse_cancel':
                if self.run is not None and not self.run.done:
                    self.run.cancel('operator_stop_button')
                    self._tick_run()
                    return {'ok': True, 'cancelled': True}
                return {'ok': True, 'cancelled': False}
            if action == 'pulse_recover':
                p = self._token_path()
                if self.run is not None and not self.run.done:
                    raise PermissionError('a run is active')
                try:
                    saved = json.loads(p.read_text())
                    token, nxt = saved['token'], int(saved['next_seq'])
                except (OSError, ValueError, KeyError, TypeError):
                    raise PermissionError('no recoverable session')
                self.run = core.PulseRun({'wheel': 1, 'pwm': 1, 'duration_s': 0.2}, self._publish, clock=self.clock,
                                         token=token, first_seq=nxt, persist=self._persist_token)
                self.run.recover()
                return {'ok': True}
            # ---- pulse_start
            return self._pulse_start(payload, now)

    def _pulse_start(self, p: Dict[str, Any], now: float) -> Dict[str, Any]:
        if self.run is not None and not self.run.done:
            raise PermissionError('a pulse run is already active')
        if now - self.last_run_done_at < 3.0:
            raise PermissionError('wait 3 seconds after the previous run')
        if p['confirm'] != core.CONFIRMATION_PHRASE:
            raise PermissionError('exact confirmation phrase required')
        cl = p['checklist']
        if not isinstance(cl, dict) or set(cl) != set(CHECKLIST_KEYS) or any(cl[k] is not True for k in CHECKLIST_KEYS):
            raise PermissionError('every safety checklist item must be explicitly confirmed')
        plan = core.validate_pulse(p['wheel'], p['direction'], p['pwm'], p['duration_s'])
        age = None if self.status_at is None else now - self.status_at
        gate = core.gate_report(self.status, age)
        if not gate['entry_ok']:
            raise PermissionError('commissioning conditions not met: %s' % (gate['owner_problem'] or 'see gate list'))
        f = self.buf.last()
        if f is None or now - f.rx > core.STALE_FRAME_S:
            raise PermissionError('encoder data is stale')
        if self.hand.open_step is not None:
            raise PermissionError('finish or reset the open hand-test step first')
        if self.session is None:
            self._open_session('pulse')
        self.session.event('pulse_requested', self.wall(), now, plan['wheel'],
                           'pwm=%d duration_s=%.2f' % (plan['pwm'], plan['duration_s']))
        self.pulse_results = [r for r in self.pulse_results][-11:]
        self.run = core.PulseRun(plan, self._publish, clock=self.clock, persist=self._persist_token)
        return {'ok': True, 'session_fingerprint': self.run.public()['session_fingerprint']}


SERVICE = TestLabService()


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


def serve(handler, ros=None, post: bool = False, service: Optional[TestLabService] = None) -> bool:
    """Return True when the request was an /api/testlab/ request (and has been answered)."""
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
            if handler.headers.get('X-Atlas-Testlab') != '1':
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
                      {'Content-Disposition': 'attachment; filename="atlas_testlab_%s.csv"' % (sid or 'current')})
        else:
            _json(handler, 404, {'error': 'unknown route'})
    except PermissionError as exc:
        _json(handler, 403, {'error': str(exc)})
    except (ValueError, TypeError, KeyError) as exc:
        _json(handler, 400, {'error': str(exc)})
    except Exception:
        _json(handler, 503, {'error': 'Test Lab service unavailable'})
    return True

#!/usr/bin/env python3
"""ATLAS Stage 28: independent, bounded, read-only safety observer for supervised maintenance windows.

Why: during a ROS 2 discovery CPU storm the dashboard's /api/status timed out (it refreshes a subprocess-based cache
synchronously inside the request). Safety evidence must not depend on that path.

Sources (all pre-existing; nothing is restarted, no serial port is opened, no new DDS participant is created):
  * foxglove_bridge (already running, C++, port 8765) over its WebSocket protocol "foxglove.websocket.v1":
      /atlas/control_policy  std_msgs/String (JSON)  -> stop_latched, manual_only, commission_armed, source
      /cmd_vel               geometry_msgs/Twist      -> all six components must be exactly 0.0
      /motor_speed           std_msgs/Float32         -> applied base output must be exactly 0.0
      /atlas/encoder_health  std_msgs/String (JSON)  -> state READY/HEALTHY/DEGRADED, packet_fresh, packet_age_s <= 1
    Subscribing adds endpoints to the bridge's EXISTING participant; the bridge never publishes on our behalf.
  * The base driver's own runtime file /run/user/<uid>/atlas_yahboom_odom_state.json (written ~3 Hz by
    yahboom_base.py): mtime proves the base loop is alive, x/y/yaw prove the rover is still.
  * /proc/<base pid>/stat: process identity (pid + kernel start time), not a zombie.

Freshness is judged by LOCAL arrival time (time.monotonic), never by a sender's clock. The bridge receive timestamp is
recorded only to measure transport latency. Missing, stale, malformed, contradictory or disconnected = FAIL.
Python standard library only (the Jetson has no websocket package).
"""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import struct
import threading
import time

TOPICS = {
    '/atlas/control_policy': 'std_msgs/msg/String',
    '/cmd_vel': 'geometry_msgs/msg/Twist',
    '/motor_speed': 'std_msgs/msg/Float32',
    '/atlas/encoder_health': 'std_msgs/msg/String',
}
MAX_AGE_S = 1.0                 # same freshness as the existing deployer/web predicates; never relaxed
ODOM_STILL_M, ODOM_STILL_RAD = 0.001, 0.002
GOOD_ENCODER_STATES = {'READY', 'HEALTHY', 'DEGRADED'}
WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
SUBPROTOCOLS = ('foxglove.sdk.v1', 'foxglove.websocket.v1')


class ObserverError(RuntimeError):
    pass


# ------------------------------------------------------------------ minimal RFC 6455 client
class WebSocket:
    def __init__(self, host, port, subprotocol, timeout=2.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f'GET / HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
               f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: {subprotocol}\r\n\r\n')
        self.sock.sendall(req.encode())
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ObserverError('handshake: connection closed')
            head += chunk
            if len(head) > 65536:
                raise ObserverError('handshake: oversized response')
        head, self.buf = head.split(b'\r\n\r\n', 1)
        lines = head.decode('latin-1').split('\r\n')
        if not lines[0].startswith('HTTP/1.1 101'):
            raise ObserverError(f'handshake refused: {lines[0]!r}')
        hdr = {k.strip().lower(): v.strip() for k, v in (l.split(':', 1) for l in lines[1:] if ':' in l)}
        want = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        if hdr.get('sec-websocket-accept') != want:
            raise ObserverError('handshake: bad accept key')
        if hdr.get('sec-websocket-protocol') != subprotocol:
            raise ObserverError('handshake: subprotocol not accepted')
        self.sock.settimeout(None)
        self.lock = threading.Lock()

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise ObserverError('connection closed')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, opcode, payload):
        mask = os.urandom(4)
        n = len(payload)
        hdr = bytes([0x80 | opcode])
        hdr += bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + struct.pack('>H', n) if n < 65536
                                                  else bytes([0x80 | 127]) + struct.pack('>Q', n))
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self.lock:
            self.sock.sendall(hdr + mask + masked)

    def recv(self):
        """Returns (opcode, payload) for complete text/binary messages; answers pings; raises on close."""
        parts, first_op = [], None
        while True:
            b0, b1 = self._read(2)
            fin, op = b0 & 0x80, b0 & 0x0F
            n = b1 & 0x7F
            if b1 & 0x80:
                raise ObserverError('protocol: masked server frame')
            if n == 126:
                n = struct.unpack('>H', self._read(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._read(8))[0]
            if n > 16 * 1024 * 1024:
                raise ObserverError('protocol: frame too large')
            data = self._read(n)
            if op == 0x9:
                self.send(0xA, data)
                continue
            if op == 0xA:
                continue
            if op == 0x8:
                raise ObserverError('server closed the connection')
            if op in (0x1, 0x2):
                first_op, parts = op, [data]
            elif op == 0x0 and first_op is not None:
                parts.append(data)
            else:
                raise ObserverError(f'protocol: unexpected opcode {op}')
            if fin:
                return first_op, b''.join(parts)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ------------------------------------------------------------------ CDR decoding (little-endian, ROS 2 default)
def _body(payload):
    if len(payload) < 4 or payload[0] != 0x00 or payload[1] != 0x01:
        raise ValueError('not CDR little-endian')
    return payload[4:]


def decode(schema, payload):
    b = _body(payload)
    if schema == 'std_msgs/msg/String':
        (n,) = struct.unpack_from('<I', b, 0)
        if n < 1 or 4 + n > len(b) or b[4 + n - 1] != 0:
            raise ValueError('bad string length/terminator')
        return b[4:4 + n - 1].decode('utf-8')
    if schema == 'std_msgs/msg/Float32':
        if len(b) < 4:
            raise ValueError('short Float32')
        return struct.unpack_from('<f', b, 0)[0]
    if schema == 'geometry_msgs/msg/Twist':
        if len(b) < 48:
            raise ValueError('short Twist')
        return struct.unpack_from('<6d', b, 0)
    raise ValueError(f'unsupported schema {schema}')


# ------------------------------------------------------------------ observer
class Obs:
    __slots__ = ('mono', 'wall', 'bridge_ns', 'value', 'error', 'count')

    def __init__(self):
        self.mono = self.wall = self.bridge_ns = self.value = self.error = None
        self.count = 0


class SafetyObserver:
    def __init__(self, host='127.0.0.1', port=8765, base_pid=None, odom_path=None, clock=time.monotonic,
                 proc_root='/proc', max_age_s=MAX_AGE_S):
        self.host, self.port, self.clock, self.max_age = host, port, clock, max_age_s
        self.proc = Path(proc_root)
        self.odom_path = Path(odom_path or f'/run/user/{os.getuid()}/atlas_yahboom_odom_state.json')
        self.base_pid = base_pid
        self.base_start = self._start_ticks(base_pid) if base_pid else None
        self.obs = {t: Obs() for t in TOPICS}
        self.lock = threading.Lock()
        self.connected = False
        self.fatal = None
        self.channels = {}
        self.ws = None
        self.odom_ref = None
        self._next_sid = 1
        self.subprotocol = None
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True, name='safety-observer')

    # ---- lifecycle
    def start(self, timeout=5.0):
        last = None
        for proto in SUBPROTOCOLS:                  # foxglove_bridge 3.x speaks foxglove.sdk.v1
            try:
                self.ws = WebSocket(self.host, self.port, proto)
                self.subprotocol = proto
                break
            except ObserverError as exc:
                last = exc
        else:
            raise ObserverError(f'bridge refused every subprotocol: {last}')
        self.connected = True
        self._t.start()
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            with self.lock:
                if len(self.channels) == len(TOPICS):
                    break
                if self.fatal:
                    raise ObserverError(self.fatal)
            time.sleep(0.05)
        with self.lock:
            missing = [t for t in TOPICS if t not in self.channels]
        if missing:
            self.stop()
            raise ObserverError(f'topics not advertised by the bridge: {missing}')
        self.odom_ref = self._odom()
        if self.odom_ref.get('error'):
            self.stop()
            raise ObserverError(f'odom state unavailable: {self.odom_ref["error"]}')
        return self

    def stop(self):
        self._stop.set()
        if self.ws:
            try:
                self.ws.send(0x1, json.dumps({'op': 'unsubscribe',
                                             'subscriptionIds': list(range(1, self._next_sid))}).encode())
            except Exception:
                pass
            self.ws.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # ---- reader thread
    def _run(self):
        subs = {}
        try:
            while not self._stop.is_set():
                op, data = self.ws.recv()
                now_m, now_w = self.clock(), time.time()
                if op == 0x1:
                    msg = json.loads(data)
                    if msg.get('op') == 'advertise':
                        new = []
                        for ch in msg.get('channels', []):
                            t = ch.get('topic')
                            if t in TOPICS and t not in self.channels:
                                if ch.get('encoding') != 'cdr' or ch.get('schemaName') != TOPICS[t]:
                                    raise ObserverError(f'{t}: unexpected encoding/schema {ch.get("encoding")}/{ch.get("schemaName")}')
                                sid = self._next_sid
                                self._next_sid += 1
                                subs[sid] = t
                                with self.lock:
                                    self.channels[t] = ch['id']
                                new.append({'id': sid, 'channelId': ch['id']})
                        if new:
                            self.ws.send(0x1, json.dumps({'op': 'subscribe', 'subscriptions': new}).encode())
                    elif msg.get('op') == 'unadvertise':
                        # e.g. the only publisher (the base) restarted: that signal FAILS (closed) until the
                        # topic is advertised again and fresh data arrives on the new subscription.
                        with self.lock:
                            for t, cid in list(self.channels.items()):
                                if cid in msg.get('channelIds', []):
                                    del self.channels[t]
                                    self.obs[t].error = 'unadvertised by bridge'
                                    for sid in [k for k, v in subs.items() if v == t]:
                                        del subs[sid]
                    continue
                if not data or data[0] != 0x01:
                    continue                                   # other binary ops are not used here
                if len(data) < 13:
                    raise ObserverError('protocol: short MessageData')
                sid, bridge_ns = struct.unpack_from('<IQ', data, 1)
                topic = subs.get(sid)
                if topic is None:
                    continue
                o = self.obs[topic]
                if self.channels.get(topic) is None:
                    continue
                try:
                    value, err = decode(TOPICS[topic], data[13:]), None
                except (ValueError, struct.error, UnicodeDecodeError) as exc:
                    value, err = None, f'malformed {type(exc).__name__}: {exc}'
                with self.lock:
                    o.mono, o.wall, o.bridge_ns, o.value, o.error = now_m, now_w, bridge_ns, value, err
                    o.count += 1
        except Exception as exc:
            with self.lock:
                self.fatal = f'{type(exc).__name__}: {exc}'
        finally:
            self.connected = False

    # ---- non-ROS channels
    @staticmethod
    def _stat_fields(path):
        raw = Path(path).read_text()
        return raw[raw.rindex(')') + 2:].split()

    def _start_ticks(self, pid):
        try:
            return int(self._stat_fields(self.proc / str(pid) / 'stat')[19])
        except (OSError, ValueError, IndexError):
            return None

    def _odom(self):
        try:
            st = os.stat(self.odom_path)
            d = json.loads(self.odom_path.read_text())
            vals = [float(d[k]) for k in ('x', 'y', 'yaw')]
            if not all(math.isfinite(v) for v in vals):
                raise ValueError('non-finite odom')
            return {'mtime_wall': st.st_mtime, 'x': vals[0], 'y': vals[1], 'yaw': vals[2]}
        except Exception as exc:
            return {'error': f'{type(exc).__name__}: {exc}'}

    # ---- evaluation
    def evaluate(self):
        """One fail-closed verdict. Every required signal must be present, fresh, well-formed and safe."""
        now_m, now_w = self.clock(), time.time()
        sig = {}

        def put(name, ok, source, age=None, value=None, why=''):
            sig[name] = {'ok': bool(ok), 'source': source, 'age_s': None if age is None else round(age, 3),
                         'value': value, 'why': why}

        with self.lock:
            snap = {t: (o.mono, o.bridge_ns, o.value, o.error, o.count) for t, o in self.obs.items()}
            fatal, connected = self.fatal, self.connected
        put('observer_connected', connected and not fatal, 'foxglove_bridge ws', why=fatal or '')

        def fresh(topic):
            mono, _, value, err, _ = snap[topic]
            if mono is None:
                return None, None, 'no message received'
            age = now_m - mono
            if err:
                return None, age, err
            if age > self.max_age:
                return None, age, f'stale {age:.2f}s > {self.max_age}s'
            return value, age, ''

        src = 'foxglove_bridge /atlas/control_policy'
        raw, age, why = fresh('/atlas/control_policy')
        pol = None
        if raw is not None:
            try:
                pol = json.loads(raw)
                if not isinstance(pol, dict):
                    raise ValueError('not an object')
            except ValueError as exc:
                pol, why = None, f'malformed policy JSON: {exc}'
        for name, test in (('estop_latched', lambda p: p.get('stop_latched') is True),
                           ('manual_only', lambda p: p.get('manual_only') is True),
                           ('commission_off', lambda p: p.get('commission_armed') is False),
                           ('source_stopped', lambda p: p.get('source') == 'STOPPED')):
            put(name, pol is not None and test(pol), src, age, None if pol is None else
                {'stop_latched': pol.get('stop_latched'), 'manual_only': pol.get('manual_only'),
                 'commission_armed': pol.get('commission_armed'), 'source': pol.get('source')}.get(
                    {'estop_latched': 'stop_latched', 'manual_only': 'manual_only',
                     'commission_off': 'commission_armed', 'source_stopped': 'source'}[name]), why)

        tw, age, why = fresh('/cmd_vel')
        put('cmd_zero', tw is not None and all(v == 0.0 for v in tw), 'foxglove_bridge /cmd_vel', age,
            None if tw is None else [round(v, 6) for v in tw], why)
        ms, age, why = fresh('/motor_speed')
        put('motor_output_zero', ms is not None and ms == 0.0, 'foxglove_bridge /motor_speed', age, ms, why)

        raw, age, why = fresh('/atlas/encoder_health')
        eh = None
        if raw is not None:
            try:
                eh = json.loads(raw)
            except ValueError as exc:
                why = f'malformed encoder_health JSON: {exc}'
        ok = (isinstance(eh, dict) and str(eh.get('state', '')).upper() in GOOD_ENCODER_STATES
              and eh.get('packet_fresh') is True and type(eh.get('packet_age_s')) in (int, float)
              and 0 <= eh['packet_age_s'] <= self.max_age)
        put('telemetry_live', ok, 'foxglove_bridge /atlas/encoder_health', age,
            None if not isinstance(eh, dict) else {k: eh.get(k) for k in ('state', 'packet_fresh', 'packet_age_s',
                                                                          'serial_encoder_packets')}, why)

        # base driver's own runtime file (no ROS, no HTTP)
        od = self._odom()
        if 'error' in od:
            put('base_loop_alive', False, 'odom_state file', why=od['error'])
            put('base_still', False, 'odom_state file', why=od['error'])
        else:
            fage = now_w - od['mtime_wall']
            put('base_loop_alive', -0.5 <= fage <= self.max_age, 'odom_state file mtime', fage, None,
                '' if fage <= self.max_age else f'not rewritten for {fage:.2f}s')
            ref = self.odom_ref or od
            still = (abs(od['x'] - ref['x']) <= ODOM_STILL_M and abs(od['y'] - ref['y']) <= ODOM_STILL_M
                     and abs(od['yaw'] - ref['yaw']) <= ODOM_STILL_RAD)
            put('base_still', still, 'odom_state file x/y/yaw', fage, [od['x'], od['y'], od['yaw']],
                '' if still else 'pose changed')
        if self.base_pid:
            try:
                fields = self._stat_fields(self.proc / str(self.base_pid) / 'stat')
                same = int(fields[19]) == self.base_start and fields[0] != 'Z'
                put('base_identity', same, f'/proc/{self.base_pid}/stat', value=fields[0],
                    why='' if same else 'base process replaced or zombie')
            except (OSError, ValueError, IndexError) as exc:
                put('base_identity', False, f'/proc/{self.base_pid}/stat', why=f'{type(exc).__name__}')
        transport = {t: (round(time.time() - s[1] / 1e9, 3) if s[1] else None) for t, s in snap.items()}
        return {'ok': all(v['ok'] for v in sig.values()), 'mono': now_m, 'wall': now_w, 'signals': sig,
                'counts': {t: s[4] for t, s in snap.items()}, 'transport_age_s': transport}


def main():
    import argparse
    p = argparse.ArgumentParser(description='Read-only safety observer (prints one JSON verdict per period).')
    p.add_argument('--seconds', type=float, default=10.0)
    p.add_argument('--period', type=float, default=0.25)
    p.add_argument('--base-pid', type=int)
    a = p.parse_args()
    with SafetyObserver(base_pid=a.base_pid) as obs:
        end = time.monotonic() + a.seconds
        while time.monotonic() < end:
            print(json.dumps(obs.evaluate(), separators=(',', ':')), flush=True)
            time.sleep(a.period)


if __name__ == '__main__':
    main()

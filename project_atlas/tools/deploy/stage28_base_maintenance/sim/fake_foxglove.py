#!/usr/bin/env python3
"""SIMULATION ONLY: minimal foxglove_bridge stand-in (foxglove.sdk.v1 / foxglove.websocket.v1 framing).

Publishes the four observed topics at the Jetson's measured rates (policy 10 Hz, cmd_vel 4.7 Hz, motor_speed 1.8 Hz,
encoder_health 10 Hz) as CDR. Behaviour is controlled by a JSON control file (re-read every cycle) so tests can inject
faults from another process: stall a topic, malformed payload, E-STOP release, non-zero command, crash, unadvertise.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import sys
import threading
import time

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
CHANNELS = [
    (11, '/atlas/control_policy', 'std_msgs/msg/String', 0.100),
    (12, '/cmd_vel', 'geometry_msgs/msg/Twist', 0.213),
    (13, '/motor_speed', 'std_msgs/msg/Float32', 0.592),
    (14, '/atlas/encoder_health', 'std_msgs/msg/String', 0.100),
    (15, '/rosout', 'rcl_interfaces/msg/Log', 1.0),            # unrelated channel, never subscribed by the observer
]


def cdr_string(s):
    b = s.encode() + b'\0'
    return b'\x00\x01\x00\x00' + struct.pack('<I', len(b)) + b


def payload(topic, ctl, n):
    if ctl.get('malformed') == topic:
        return b'\x00\x01\x00\x00\xff\xff'
    if ctl.get('bad_json') == topic:
        return cdr_string('{not json')
    if topic == '/atlas/control_policy':
        pol = {'manual_only': True, 'commission_armed': False, 'commission_remaining_s': 0.0,
               'stop_latched': ctl.get('stop_latched', True), 'stop_reason': 'REMOTE STOP: sim', 'source': ctl.get('source', 'STOPPED')}
        return cdr_string(json.dumps(pol))
    if topic == '/cmd_vel':
        return b'\x00\x01\x00\x00' + struct.pack('<6d', ctl.get('cmd_lin', 0.0), 0, 0, 0, 0, ctl.get('cmd_ang', 0.0))
    if topic == '/motor_speed':
        return b'\x00\x01\x00\x00' + struct.pack('<f', ctl.get('motor', 0.0))
    if topic == '/atlas/encoder_health':
        return cdr_string(json.dumps({'state': ctl.get('encoder_state', 'READY'), 'packet_fresh': True,
                                      'packet_age_s': 0.03, 'serial_encoder_packets': n}))
    return b'\x00\x01\x00\x00'


def frame(op, data):
    n = len(data)
    hdr = bytes([0x80 | op]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack('>H', n) if n < 65536
                                else bytes([127]) + struct.pack('>Q', n))
    return hdr + data


class Client(threading.Thread):
    def __init__(self, conn, ctl_path, proto_pref):
        super().__init__(daemon=True)
        self.c, self.ctl_path, self.pref = conn, ctl_path, proto_pref
        self.subs = {}
        self.lock = threading.Lock()

    def ctl(self):
        try:
            return json.loads(Path(self.ctl_path).read_text())
        except (OSError, ValueError):
            return {}

    def send(self, op, data):
        with self.lock:
            self.c.sendall(frame(op, data))

    def handshake(self):
        req = b''
        while b'\r\n\r\n' not in req:
            req += self.c.recv(4096)
        hdr = {k.strip().lower(): v.strip() for k, v in
               (l.split(':', 1) for l in req.decode().split('\r\n')[1:] if ':' in l)}
        offered = [p.strip() for p in hdr.get('sec-websocket-protocol', '').split(',')]
        if self.pref not in offered:
            self.c.sendall(b'HTTP/1.1 400 Bad Request\r\n\r\nMissing expected sec-websocket-protocol header')
            return False
        acc = base64.b64encode(hashlib.sha1((hdr['sec-websocket-key'] + GUID).encode()).digest()).decode()
        self.c.sendall(f'HTTP/1.1 101 Switching Protocols\r\nconnection: Upgrade\r\nupgrade: websocket\r\n'
                       f'sec-websocket-accept: {acc}\r\nsec-websocket-protocol: {self.pref}\r\n\r\n'.encode())
        return True

    def reader(self):
        buf = b''
        while True:
            while len(buf) < 2:
                d = self.c.recv(4096)
                if not d:
                    return
                buf += d
            n = buf[1] & 0x7F
            off = 2
            if n == 126:
                n, off = struct.unpack('>H', buf[2:4])[0], 4
            mask_end = off + 4
            while len(buf) < mask_end + n:
                buf += self.c.recv(4096)
            mask = buf[off:mask_end]
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(buf[mask_end:mask_end + n]))
            op = buf[0] & 0x0F
            buf = buf[mask_end + n:]
            if op == 0x1:
                m = json.loads(data)
                with self.lock:
                    if m['op'] == 'subscribe':
                        for s in m['subscriptions']:
                            self.subs[s['channelId']] = s['id']
                    elif m['op'] == 'unsubscribe':
                        self.subs = {k: v for k, v in self.subs.items() if v not in m['subscriptionIds']}

    def run(self):
        try:
            if not self.handshake():
                return
            self.send(0x1, json.dumps({'op': 'serverInfo', 'name': 'sim', 'capabilities': [],
                                       'supportedEncodings': ['cdr']}).encode())
            ctl = self.ctl()
            chans = [{'id': i, 'topic': t, 'encoding': ctl.get('encoding', 'cdr'), 'schemaName': s, 'schema': ''}
                     for i, t, s, _ in CHANNELS if t not in ctl.get('not_advertised', [])]
            self.send(0x1, json.dumps({'op': 'advertise', 'channels': chans}).encode())
            threading.Thread(target=self.reader, daemon=True).start()
            nxt = {i: time.monotonic() for i, *_ in CHANNELS}
            n = 0
            while True:
                ctl = self.ctl()
                if ctl.get('crash'):
                    os._exit(3)
                if ctl.get('close'):
                    self.send(0x8, b'')
                    return
                if ctl.get('unadvertise') and not getattr(self, 'unadv_done', False):
                    self.unadv_done = True
                    self.send(0x1, json.dumps({'op': 'unadvertise', 'channelIds': [ctl.get('unadvertise_id', 11)]}).encode())
                    self.gone = ctl.get('unadvertise_id', 11)
                if ctl.get('readvertise') and getattr(self, 'gone', None) and not getattr(self, 'readv_done', False):
                    self.readv_done = True
                    i, t, sch, _ = next(c for c in CHANNELS if c[0] == self.gone)
                    new_id = i + 100
                    CHANNELS.append((new_id, t, sch, next(c for c in CHANNELS if c[0] == self.gone)[3]))
                    CHANNELS[:] = [c for c in CHANNELS if c[0] != self.gone]
                    nxt[new_id] = time.monotonic()
                    self.send(0x1, json.dumps({'op': 'advertise', 'channels': [
                        {'id': new_id, 'topic': t, 'encoding': 'cdr', 'schemaName': sch, 'schema': ''}]}).encode())
                now = time.monotonic()
                for i, t, s, period in CHANNELS:
                    if now >= nxt[i]:
                        nxt[i] = now + period * ctl.get('slow', 1.0)
                        with self.lock:
                            sid = self.subs.get(i)
                        if sid is None or t in ctl.get('stall', []):
                            continue
                        n += 1
                        self.send(0x2, b'\x01' + struct.pack('<IQ', sid, time.time_ns()) + payload(t, ctl, n))
                time.sleep(0.005)
        except (OSError, BrokenPipeError):
            return


def serve(port, ctl_path, proto='foxglove.sdk.v1'):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('127.0.0.1', port))
    s.listen(8)
    while True:
        c, _ = s.accept()
        Client(c, ctl_path, proto).start()


if __name__ == '__main__':
    serve(int(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'foxglove.sdk.v1')

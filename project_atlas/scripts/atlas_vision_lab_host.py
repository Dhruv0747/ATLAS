"""Optional feature API over a private Unix socket; access via existing SSH auth.

No TCP listener, new credentials, ROS imports, camera controls or general proxy.
The owner can forward localhost:8099 to this socket using authenticated SSH.
"""
from collections import deque
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import resource
import signal
import socket
import socketserver
import stat
import struct
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
HOST = 'localhost:8099'
INDEX = b'''<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>ATLAS Vision Lab</title><link rel="stylesheet" href="/v2/vision_features.css">
<h1>ATLAS Vision Lab</h1><p>Independent read-only inference. Camera must be separately approved.
No camera, motor, servo, navigation or recording controls.</p>
<p id="featureNotice">Execution disabled until separately approved.</p><section id="featureCards"></section>
<img id="rgbImage" hidden alt=""><canvas id="featureOverlay" hidden></canvas>
<p id="featureOverlayStatus">Frame overlay unavailable.</p>
<script src="/v2/vision_features.js" defer></script></html>'''


def peer_allowed(peer_uid, owner_uid):
    return type(peer_uid) is int and peer_uid == owner_uid


class Host(socketserver.UnixStreamServer):
    request_queue_size = 4
    allow_reuse_address = False

    def __init__(self, path, lab, frame_factory):
        self.lab, self.frame_factory = lab, frame_factory
        self.requests = deque(maxlen=8)
        path = Path(path); parent = path.parent.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
                or stat.S_IMODE(parent.st_mode) != 0o700):
            raise ValueError('socket directory must be owner-only mode 0700')
        # Never unlink an existing listener or stale socket automatically.
        if path.exists() or path.is_symlink(): raise ValueError('socket path already exists')
        super().__init__(str(path), Handler)
        os.chmod(path, 0o600)

    def verify_request(self, request, client_address):
        try:
            _, uid, _ = struct.unpack('3i', request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            return peer_allowed(uid, os.getuid())
        except OSError:
            return False

    def finish_request(self, request, client_address):
        # Bound slow headers/body too, not only socket inactivity.
        def expire():
            try: request.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        timer = threading.Timer(.75, expire); timer.daemon = True; timer.start()
        try: super().finish_request(request, client_address)
        finally: timer.cancel()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def setup(self):
        self.request.settimeout(.5)
        super().setup()

    def log_message(self, *args):
        pass  # no credentials/request bodies in logs

    def reply(self, code, value, content='application/json'):
        body = value if isinstance(value, bytes) else json.dumps(value, allow_nan=False).encode()
        if len(body) > 1048576: raise ValueError('response too large')
        self.send_response(code)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'; object-src 'none'")
        self.end_headers(); self.wfile.write(body)

    def admitted(self):
        if self.headers.get_all('Host') != [HOST]:
            self.reply(403, {'error': 'unexpected host'}); return False
        now = time.monotonic(); q = self.server.requests
        while q and now-q[0] >= 1: q.popleft()
        if len(q) >= 8:
            self.reply(429, {'error': 'request rate limit'}); return False
        q.append(now)
        return True

    def do_GET(self):
        if not self.admitted(): return
        try:
            if self.path == '/': self.reply(200, INDEX, 'text/html; charset=utf-8')
            elif self.path == '/api/vision3d/features': self.reply(200, self.server.lab.status())
            elif self.path.startswith('/api/vision3d/feature-report?feature='):
                feature = self.path.split('=', 1)[1]
                if feature not in ('object', 'target'): raise ValueError('unsupported feature')
                raw, _ = self.server.lab.download(feature); self.reply(200, raw)
            elif self.path in ('/v2/vision_features.js', '/v2/vision_features.css'):
                path = ROOT/'web'/self.path.lstrip('/')
                self.reply(200, path.read_bytes(), 'text/javascript' if path.suffix == '.js' else 'text/css')
            else: self.reply(404, {'error': 'route unavailable'})
        except (ValueError, KeyError, TypeError, OSError) as error:
            self.reply(409, {'error': str(error)[:200]})

    def do_POST(self):
        if not self.admitted(): return
        if (self.headers.get('Origin') != 'http://'+HOST
                or self.headers.get('X-Atlas-Vision3D') != '1'):
            self.reply(403, {'error': 'same-origin request required'}); return
        if self.path != '/api/vision3d/features':
            self.reply(404, {'error': 'route unavailable'}); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if (not 0 < length <= 512 or self.headers.get('Transfer-Encoding')
                    or len(self.headers.get_all('Content-Length', [])) != 1):
                self.reply(413, {'error': 'bounded body required'}); return
            if self.headers.get_content_type() != 'application/json': raise ValueError('JSON required')
            raw = self.rfile.read(length)
            if len(raw) != length: raise ValueError('incomplete body')
            data = json.loads(raw); lab = self.server.lab
            if data == {'action': 'stop'}: lab.stop()
            elif isinstance(data, dict) and set(data) == {'action', 'feature'} and data['action'] == 'start':
                if data['feature'] not in ('object', 'target'): raise ValueError('feature unavailable')
                lab.start(data['feature'], None)
            elif isinstance(data, dict) and set(data) == {'action', 'feature', 'verdict'} and data['action'] == 'verdict':
                lab.verdict(data['feature'], data['verdict'])
            else: raise ValueError('operation unavailable')
            self.reply(200, lab.status())
        except (ValueError, KeyError, TypeError, OSError) as error:
            self.reply(409, {'error': str(error)[:200]})


def main():
    import argparse
    from atlas_vision_feature_lab import Lab
    from atlas_vision_cache_only import HTTPFrames
    parser = argparse.ArgumentParser()
    parser.add_argument('--socket', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    lab = Lab(config=args.config, frame_factory=HTTPFrames)
    host = Host(args.socket, lab, HTTPFrames)
    def stop(*_):
        lab.stop()
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    try:
        host.serve_forever(poll_interval=.1)
    except KeyboardInterrupt:
        pass
    finally:
        lab.stop()
        if lab.thread: lab.thread.join(timeout=3)
        host.server_close()
        args.socket.unlink()  # only our socket, after listener closes


if __name__ == '__main__': main()

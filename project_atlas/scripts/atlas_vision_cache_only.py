"""Passive RGB cache boundary and local client; no ROS or camera controls."""
import base64
import io
import json
import math
import socket
import threading
import time


def identity(runtime, now):
    pid = runtime.get('driver_pid')
    start = runtime.get('startup_guard_baseline_monotonic_s')
    if (runtime.get('state') != 'ACTIVE' or type(pid) is not int or pid <= 0
            or type(start) not in (int, float) or not math.isfinite(start)
            or not 0 <= now-start < 60):
        raise ValueError('camera identity inactive, invalid or expired')
    return pid, start


def cached_rgb(service, runtime):
    """Never calls touch/frame, creates transport, or alters camera/cache state."""
    with service.lock:
        now = service.clock(); pid, start = identity(runtime, now)
        if service.transport is None or service.error or getattr(service.transport, 'error', ''):
            raise ValueError('camera transport disconnected')
        try:
            png = service.cache['rgb']; msg = service.cache['rgb_message']
            received = service.cache['rgb_received']
            stamp = msg.header.stamp.sec*1_000_000_000 + msg.header.stamp.nanosec
        except (KeyError, AttributeError):
            raise ValueError('RGB cache unavailable') from None
        if (type(stamp) is not int or not 0 <= service.wall()-stamp/1e9 <= 1.0
                or type(received) not in (float, int) or not 0 <= now-received <= 1.0):
            raise ValueError('RGB cache stale or future')
        if not isinstance(png, bytes) or not 0 < len(png) <= 262144:
            raise ValueError('invalid bounded PNG cache')
        return dict(png=base64.b64encode(png).decode(), stamp_ns=str(stamp),
                    received_mono=received, state='ACTIVE', driver_pid=pid,
                    startup_guard_baseline_monotonic_s=start)


def decode_frame(data, now_ns, now_mono):
    identity(data, now_mono)
    try:
        value = data['stamp_ns']
        if not isinstance(value, str) or not value.isascii() or not value.isdigit():
            raise ValueError('invalid original timestamp')
        stamp = int(value); received = data['received_mono']
        if (not 0 <= now_ns-stamp <= 1_000_000_000 or type(received) not in (float, int)
                or not 0 <= now_mono-received <= 1.0):
            raise ValueError('RGB source or reception stale/future')
        raw = base64.b64decode(data['png'], validate=True)
        if not 0 < len(raw) <= 262144: raise ValueError('PNG size limit')
        from PIL import Image
        import numpy as np
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != 'PNG' or not 0 < image.width <= 240 or not 0 < image.height <= 240:
                raise ValueError('unexpected preview dimensions')
            rgb = np.asarray(image.convert('RGB')).copy()
        return rgb, stamp
    except (KeyError, TypeError, OSError) as error:
        raise ValueError('invalid cache payload') from error


class HTTPFrames:
    """No I/O until read; only used by a bounded, explicitly started Lab session."""
    def __init__(self):
        self.deadline = time.monotonic()+30
        self.identity = None; self.data = None; self.fetched = -float('inf')
        self.closed = False; self.lock = threading.Lock()
        self.socket = None

    def close(self):
        self.closed = True
        sock = self.socket
        if sock:
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            sock.close()

    def _fetch(self):
        # Absolute deadline covers connect, headers AND body (not an idle timeout).
        end = min(self.deadline, time.monotonic()+.5)
        sock = socket.socket(); self.socket = sock
        try:
            sock.settimeout(max(.001, end-time.monotonic()))
            sock.connect(('127.0.0.1', 8088))
            sock.sendall(b'GET /api/vision3d/cached-rgb HTTP/1.0\r\nHost: 127.0.0.1:8088\r\nConnection: close\r\n\r\n')
            data = bytearray(); size = None; header_end = None
            while True:
                remaining = end-time.monotonic()
                if self.closed or remaining <= 0: raise ValueError('cache request deadline/cancellation')
                sock.settimeout(remaining)
                chunk = sock.recv(8192)
                if not chunk: break
                data.extend(chunk)
                if len(data) > 408192: raise ValueError('cache response too large')
                if header_end is None:
                    index = data.find(b'\r\n\r\n')
                    if index < 0:
                        if len(data) > 8192: raise ValueError('cache headers too large')
                        continue
                    header_end = index+4
                    if header_end > 8192: raise ValueError('cache headers too large')
                    lines = bytes(data[:index]).split(b'\r\n')
                    if lines[0].split()[1:2] != [b'200']: raise ValueError('cache unavailable; redirects forbidden')
                    headers = {}
                    for line in lines[1:]:
                        key, value = line.split(b':', 1); key = key.lower()
                        if key in headers: raise ValueError('duplicate cache header')
                        headers[key] = value.strip()
                    size = int(headers[b'content-length'])
                    if (not 0 < size <= 400000 or b'transfer-encoding' in headers
                            or headers.get(b'content-type', b'').split(b';')[0] != b'application/json'):
                        raise ValueError('invalid cache response framing')
                if size is not None and len(data)-header_end >= size: break
            if self.closed or time.monotonic() >= end: raise ValueError('cache request expired')
            if size is None or len(data)-header_end != size: raise ValueError('incomplete cache response')
            return json.loads(data[header_end:])
        finally:
            sock.close(); self.socket = None

    def read(self):
        if not self.lock.acquire(timeout=.5): raise ValueError('cache reader busy')
        try:
            now = time.monotonic()
            if self.closed or now >= self.deadline: raise ValueError('feature frame session closed/expired')
            # Reuse only genuinely fresh source data, not a receipt-based TTL.
            age = max((time.time_ns()-int(self.data['stamp_ns']))/1e9,
                      now-self.data['received_mono']) if self.data else float('inf')
            if self.data is None or age >= .8:
                if now-self.fetched < .25: raise ValueError('fresh cache unavailable within 4 Hz request budget')
                self.fetched = now
                self.data = self._fetch()
            current = identity(self.data, time.monotonic())
            if self.identity is not None and self.identity != current: raise ValueError('camera session changed')
            self.identity = current
            result = decode_frame(self.data, time.time_ns(), time.monotonic())
            if self.closed or time.monotonic() >= self.deadline: raise ValueError('frame deadline expired')
            if not 0 <= time.time_ns()-result[1] <= 1_000_000_000: raise ValueError('frame expired during decode')
            return result
        finally:
            self.lock.release()

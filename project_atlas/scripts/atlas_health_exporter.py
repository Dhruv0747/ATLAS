#!/usr/bin/env python3
"""Opt-in read-only metrics endpoint. No ROS, camera or motor interaction."""
import argparse
import ipaddress
import shutil
import subprocess
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
LATEST = None
LAST = 0.0
UNITS = ('rover-status-web', 'rover-base-telemetry', 'atlas-remote', 'atlas-cmd-vel-mux', 'atlas-uno-r4-sensor-hub', 'atlas-lidar', 'atlas-camera', 'atlas-nav2', 'rover-daly-bms')

def read(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return None

def collect():
    lines = []
    def emit(name, value, labels=''):
        try:
            n = float(value)
            if n == n and abs(n) != float('inf'):
                lines.append(f'{name}{labels} {n:g}')
        except (TypeError, ValueError, OverflowError):
            pass
    mem = {}
    for line in (read('/proc/meminfo') or '').splitlines():
        try:
            key, val = line.split(':', 1)
            mem[key] = int(val.split()[0]) * 1024
        except (ValueError, IndexError):
            pass
    for key, metric in [('MemTotal', 'atlas_memory_total_bytes'), ('MemAvailable', 'atlas_memory_available_bytes'), ('SwapTotal', 'atlas_swap_total_bytes'), ('SwapFree', 'atlas_swap_free_bytes')]:
        emit(metric, mem.get(key))
    try:
        disk = shutil.disk_usage('/')
        emit('atlas_disk_total_bytes', disk.total)
        emit('atlas_disk_free_bytes', disk.free)
    except OSError:
        pass
    for index, path in enumerate(sorted(Path('/sys/class/thermal').glob('thermal_zone*/temp'))[:32]):
        sensor = (read(path.parent / 'type') or 'unknown').replace('\\', '_').replace('"', '_').replace('\n', '_')[:48]
        try:
            emit('atlas_thermal_celsius', float(read(path)) / 1000, f'{{zone="{index}",sensor="{sensor}"}}')
        except (ValueError, TypeError):
            pass
    try:
        proc = subprocess.run(['systemctl', '--user', 'show', '--property=Id,ActiveState,NRestarts', *[u + '.service' for u in UNITS]], capture_output=True, text=True, timeout=3, check=False)
        if proc.returncode == 0:
            for block in proc.stdout.strip().split('\n\n'):
                fields = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
                name = fields.get('Id', '').removesuffix('.service')
                if name not in UNITS:
                    continue
                label = f'{{service="{name}"}}'
                if fields.get('ActiveState') in ('active', 'inactive', 'failed', 'activating', 'deactivating'):
                    emit('atlas_service_active', int(fields['ActiveState'] == 'active'), label)
                emit('atlas_service_restarts_total', fields.get('NRestarts'), label)
    except (OSError, subprocess.TimeoutExpired):
        pass
    emit('atlas_exporter_observed_timestamp_seconds', time.time())
    return '\n'.join(lines) + '\n'

def worker():
    global LATEST, LAST
    while True:
        try:
            output = collect()
            with LOCK:
                LATEST, LAST = output, time.time()
        except Exception:
            pass
        time.sleep(15)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/metrics':
            self.send_error(404)
            return
        with LOCK:
            value, stamp = LATEST, LAST
        if value is None or time.time() - stamp > 45:
            self.send_error(503, 'Stale metrics')
            return
        body = value.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', required=True, help='Explicit Jetson LAN IPv4')
    parser.add_argument('--port', type=int, default=9118)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.bind)
    if address.version != 4 or not address.is_private or address.is_loopback or address.is_unspecified:
        parser.error('Bind explicit non-loopback private IPv4 only')
    threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()

if __name__ == '__main__':
    main()

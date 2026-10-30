#!/usr/bin/env python3
"""Opt-in READ-ONLY Prometheus exporter for ATLAS. No ROS node, no ROS subscriber, no camera access, no commands.

Every 15 s it reads:
  * /proc and /sys (CPU, RAM, swap, disk, thermal zones, GPU load/frequency);
  * `systemctl --user show` for a fixed list of units (active state, restart counter);
  * the EXISTING dashboard API on 127.0.0.1:8088 (rover-status-web), which already caches every ROS topic with its
    age and rate: /api/status and /api/manual_controller. Nothing new subscribes to ROS for monitoring.
Missing data is never reported as zero or healthy: a metric whose source is absent is simply not emitted (Grafana
shows it as UNAVAILABLE) and atlas_source_available{source=...} says which source is missing. A cached topic older
than its freshness limit is emitted with atlas_topic_stale=1 and its real age.
/metrics answers 503 if no collection succeeded in 45 s. It binds to an explicit private LAN IPv4 only.
"""
import argparse
import ipaddress
import json
import math
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
LATEST = None
LAST = 0.0
INTERVAL_S = 15.0
API = 'http://127.0.0.1:8088'
UNITS = ('rover-status-web', 'rover-base-telemetry', 'atlas-remote', 'atlas-cmd-vel-mux', 'atlas-uno-r4-sensor-hub',
         'atlas-lidar', 'atlas-camera', 'atlas-nav2', 'rover-daly-bms',
         # added 2026-10-30
         'atlas-flysky-teleop', 'atlas-flysky-camera', 'atlas-camera-joystick', 'atlas-ekf', 'atlas-foxglove',
         'atlas-im10a', 'atlas-gnss', 'atlas-feature-on-demand')
# Cached dashboard items -> freshness limit (s), from the observed rates on 2026-10-30 (about 2-3x the period).
# cmd_vel is deliberately absent: the mux publishes it only while something drives, so its age is not staleness.
TOPICS = {'lidar': 2.0, 'motor_speed': 2.0, 'encoder_health': 1.0, 'odom': 1.0, 'control_policy': 1.0, 'joy': 1.0,
          'camera_info': 5.0, 'bat_voltage': 5.0, 'bms_voltage': 15.0, 'imu_heading': 2.0, 'board_imu_heading': 1.0,
          'us_validity': 3.0, 'radar_link': 2.0, 'jetson_power': 5.0, 'drive_pid': 1.0, 'thermal_status': 5.0}
VALUES = {'bms_voltage': 'atlas_battery_voltage_volts{source="bms"}', 'bat_voltage': 'atlas_battery_voltage_volts{source="base"}',
          'bms_percent': 'atlas_battery_percent{source="bms"}', 'bms_current': 'atlas_battery_current_amps{source="bms"}',
          'jetson_power': 'atlas_jetson_power_watts', 'bms_power': 'atlas_battery_power_watts{source="bms"}'}
for wheel in range(1, 5):
    TOPICS[f'enc_m{wheel}'] = 1.0
    VALUES[f'enc_m{wheel}'] = f'atlas_encoder_count{{wheel="M{wheel}"}}'


def valid_age(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def fresh(item, limit):
    return isinstance(item, dict) and valid_age(item.get('age')) and item['age'] <= limit


GPU_LOAD = ('/sys/devices/platform/bus@0/17000000.gpu/load', '/sys/devices/platform/17000000.gpu/load', '/sys/devices/platform/gpu.0/load')
GPU_FREQ = '/sys/class/devfreq/17000000.gpu/cur_freq'
STATE = {'cpu': None}


def read(path):
    try:
        return Path(path).read_text().strip()
    except Exception:                 # some Jetson thermal zones raise TypeError on read (found 2026-10-29)
        return None


def get_json(path, timeout=3.0):
    with urllib.request.urlopen(API + path, timeout=timeout) as r:
        return json.loads(r.read())


def cpu_sample(stat_text):
    v = [int(x) for x in stat_text.splitlines()[0].split()[1:8]]
    return sum(v), v[3] + v[4]


class Out:
    def __init__(self):
        self.lines = []

    def emit(self, name, value, labels=None):
        try:
            n = float(value)
        except (TypeError, ValueError, OverflowError):
            return
        if n != n or abs(n) == float('inf'):
            return
        lab = ''
        if labels:
            esc = lambda s: str(s).replace('\\', '_').replace('"', '_').replace('\n', '_')[:64]
            lab = '{' + ','.join(f'{k}="{esc(v)}"' for k, v in labels.items()) + '}'
        self.lines.append(f'{name}{lab} {n:g}')

    def raw(self, metric_with_labels, value):
        name, _, rest = metric_with_labels.partition('{')
        labels = dict(kv.split('=', 1) for kv in rest.rstrip('}').split(',')) if rest else {}
        self.emit(name, value, {k: v.strip('"') for k, v in labels.items()})

    def text(self):
        return '\n'.join(self.lines) + '\n'


def collect_system(o, sysroot=''):
    mem = {}
    for line in (read(sysroot + '/proc/meminfo') or '').splitlines():
        try:
            key, val = line.split(':', 1)
            mem[key] = int(val.split()[0]) * 1024
        except (ValueError, IndexError):
            pass
    for key, metric in [('MemTotal', 'atlas_memory_total_bytes'), ('MemAvailable', 'atlas_memory_available_bytes'),
                        ('SwapTotal', 'atlas_swap_total_bytes'), ('SwapFree', 'atlas_swap_free_bytes')]:
        o.emit(metric, mem.get(key))
    try:
        disk = shutil.disk_usage(sysroot or '/')
        o.emit('atlas_disk_total_bytes', disk.total)
        o.emit('atlas_disk_free_bytes', disk.free)
    except OSError:
        pass
    temps = []
    for index, path in enumerate(sorted(Path(sysroot + '/sys/class/thermal').glob('thermal_zone*/temp'))[:32]):
        raw = read(path)
        try:
            c = float(raw) / 1000
        except (TypeError, ValueError):
            continue                                   # unreadable zone: skipped, never reported as 0
        if not math.isfinite(c) or c <= -200 or c > 200:
            continue
        temps.append(c)
        o.emit('atlas_thermal_celsius', c, {'zone': index, 'sensor': read(path.parent / 'type') or 'unknown'})
    if temps:
        o.emit('atlas_thermal_max_celsius', max(temps))
    stat = read(sysroot + '/proc/stat')
    if stat:
        cur = cpu_sample(stat)
        prev, STATE['cpu'] = STATE['cpu'], cur
        if prev and cur[0] > prev[0]:
            o.emit('atlas_cpu_utilization_percent', 100.0 * (1 - (cur[1] - prev[1]) / (cur[0] - prev[0])))
    load = read(sysroot + '/proc/loadavg')
    if load:
        o.emit('atlas_load1', load.split()[0])
    gpu = next((read(sysroot + p) for p in GPU_LOAD if read(sysroot + p) is not None), None)
    if gpu is not None:
        o.emit('atlas_gpu_load_percent', float(gpu) / 10.0)          # sysfs reports 0..1000
    o.emit('atlas_gpu_frequency_hz', read(sysroot + GPU_FREQ))
    o.emit('atlas_source_available', int(gpu is not None), {'source': 'gpu_load'})


def collect_units(o, run=subprocess.run):
    try:
        proc = run(['systemctl', '--user', 'show', '--property=Id,LoadState,ActiveState,NRestarts',
                    *[u + '.service' for u in UNITS]], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        o.emit('atlas_source_available', 0, {'source': 'systemd'})
        return
    ok = proc.returncode == 0
    o.emit('atlas_source_available', int(ok), {'source': 'systemd'})
    if not ok:
        return
    for block in proc.stdout.strip().split('\n\n'):
        fields = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
        name = fields.get('Id', '').removesuffix('.service')
        if name not in UNITS:
            continue
        label = {'service': name}
        loaded = fields.get('LoadState') == 'loaded'
        o.emit('atlas_service_loaded', int(loaded), label)
        if not loaded:
            continue                                   # not installed: UNAVAILABLE, not "down"
        if fields.get('ActiveState') in ('active', 'inactive', 'failed', 'activating', 'deactivating'):
            o.emit('atlas_service_active', int(fields['ActiveState'] == 'active'), label)
            o.emit('atlas_service_failed', int(fields['ActiveState'] == 'failed'), label)
        o.emit('atlas_service_restarts_total', fields.get('NRestarts'), label)


def collect_rover(o, get=get_json):
    try:
        st = get('/api/status')
        ros = st['ros']
        if not isinstance(ros, dict):
            raise ValueError('invalid ROS cache')
    except Exception:
        o.emit('atlas_source_available', 0, {'source': 'dashboard_api'})
        return
    o.emit('atlas_source_available', 1, {'source': 'dashboard_api'})
    for topic, limit in TOPICS.items():
        item = ros.get(topic)
        age = item.get('age') if isinstance(item, dict) else None
        if not valid_age(age):
            o.emit('atlas_topic_available', 0, {'topic': topic})
            continue
        o.emit('atlas_topic_available', 1, {'topic': topic})
        o.emit('atlas_topic_age_seconds', age, {'topic': topic})
        o.emit('atlas_topic_stale', int(age > limit), {'topic': topic})
        o.emit('atlas_topic_freshness_limit_seconds', limit, {'topic': topic})
        if item.get('observed_hz') is not None:
            o.emit('atlas_topic_rate_hz', item['observed_hz'], {'topic': topic})
    for topic, metric in VALUES.items():
        item = ros.get(topic)
        if fresh(item, TOPICS.get(topic, 15.0)):
            o.raw(metric, item.get('value'))
    cmd = ros.get('cmd_vel')
    if isinstance(cmd, dict) and valid_age(cmd.get('age')):
        o.emit('atlas_command_age_seconds', cmd['age'])            # idle mux publishes rarely: an age, not a fault
    enc = ros.get('encoder_health')
    try:
        h = json.loads(enc['value']) if isinstance(enc.get('value'), str) else enc.get('value')
    except Exception:
        h = None
    if isinstance(h, dict) and fresh(enc, TOPICS['encoder_health']):
        if isinstance(h.get('state'), str) and h['state']:
            o.emit('atlas_encoder_ready', int(h['state'] == 'READY'))
        if isinstance(h.get('faults'), list):
            o.emit('atlas_encoder_faults', len(h['faults']))
        for k in ('serial_checksum_errors', 'serial_write_errors', 'link_stale_events', 'link_recoveries'):
            o.emit(f'atlas_encoder_{k}_total', h.get(k))
    # No verified Astra frame-health source in this API. Key names are not proof of frames.
    astra = False
    o.emit('atlas_source_available', int(astra), {'source': 'astra'})
    try:
        mc = get('/api/manual_controller')
        if not isinstance(mc, dict):
            raise ValueError('invalid control API')
    except Exception:
        o.emit('atlas_source_available', 0, {'source': 'control_api'})
        return
    o.emit('atlas_source_available', 1, {'source': 'control_api'})
    p = mc.get('policy')
    policy_ok = (isinstance(p, dict) and p.get('fresh') is True
                 and valid_age(p.get('age_s')) and p['age_s'] <= 1.0)
    o.emit('atlas_source_available', int(policy_ok), {'source': 'control_policy'})
    if policy_ok:
        for field, metric in [('stop_latched', 'atlas_estop_latched'), ('flysky_drive_enabled', 'atlas_flysky_drive_enabled')]:
            if type(p.get(field)) is bool:
                o.emit(metric, int(p[field]))
        if p.get('manual_controller') in ('XBOX', 'FLYSKY'):
            for c in ('XBOX', 'FLYSKY'):
                o.emit('atlas_control_selected', int(p['manual_controller'] == c), {'controller': c})
    d = mc.get('drive')
    if not isinstance(d, dict):
        return
    if type(d.get('running')) is bool:
        o.emit('atlas_flysky_teleop_running', int(d['running']))
    s = d.get('status')
    status_ok = (d.get('running') is True and isinstance(s, dict)
                 and valid_age(d.get('age_s')) and d['age_s'] <= 1.0)
    o.emit('atlas_source_available', int(status_ok), {'source': 'flysky_status'})
    if status_ok:
        if valid_age(s.get('frame_age_s')):
            o.emit('atlas_flysky_frame_age_seconds', s['frame_age_s'])
        i = s.get('inputs')
        if isinstance(i, dict):
            for field in ('failsafe', 'frame_lost'):
                if type(i.get(field)) is bool:
                    o.emit('atlas_flysky_' + field, int(i[field]))
        if isinstance(s.get('state'), str) and s['state']:
            o.emit('atlas_flysky_drive_state', 1, {'state': s['state']})


def collect(get=get_json, run=subprocess.run, sysroot=''):
    t0 = time.monotonic()
    o = Out()
    collect_system(o, sysroot)
    collect_units(o, run)
    collect_rover(o, get)
    o.emit('atlas_exporter_collect_seconds', time.monotonic() - t0)
    o.emit('atlas_exporter_observed_timestamp_seconds', time.time())
    return o.text()


def worker():
    global LATEST, LAST
    while True:
        try:
            output = collect()
            with LOCK:
                LATEST, LAST = output, time.time()
        except Exception:
            pass
        time.sleep(INTERVAL_S)


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

    def do_POST(self):                      # read-only: nothing can be sent to the rover through this port
        self.send_error(405)

    do_PUT = do_DELETE = do_PATCH = do_POST

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

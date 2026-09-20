#!/usr/bin/env python3
"""Bounded, read-only diagnostics for the existing ATLAS web server.

No ROS publishers, service restart operations, network probes or serial opens.
Slow OS queries run in one cached worker, never in a camera/control handler.
"""
import glob
import hashlib
import os
import re
import subprocess
import threading
import time


UNITS = {
    'rover-status-web': 'Web dashboard',
    'rover-base-telemetry': 'Yahboom encoders / IMU',
    'atlas-remote': 'Xbox remote',
    'atlas-cmd-vel-mux': 'Command mux / watchdog',
    'atlas-uno-r4-sensor-hub': 'UNO R4 I2C / UART hub',
    'rover-radar': 'RD-03D decoder',
    'atlas-lidar': 'LiDAR',
    'atlas-scan-filter': 'LiDAR self-filter',
    'atlas-gnss': 'Hiwonder USB GNSS',
    'atlas-im10a': 'Hiwonder IM10A monitoring',
    'rover-cellular': 'Cellular telemetry',
    'rover-daly-bms': 'Main battery BMS',
    'atlas-ina3221-power': 'Jetson power',
    'atlas-carrier-health': 'Orin carrier board',
    'atlas-camera': 'Camera publisher',
    'atlas-ai-annotator': 'AI camera annotations',
    'atlas-camera-tracker': 'Camera tracking',
    'atlas-ekf': 'EKF odometry',
    'atlas-localization': 'Saved-map localization / Nav2',
    'atlas-nav2': 'Mapping Nav2 stack',
    'atlas-slam-fast': 'SLAM mapping',
    'atlas-explore': 'Frontier exploration',
    'atlas-safety-status': 'Navigation safety',
    'atlas-tight-recovery': 'Guarded recovery',
    'atlas-mission-control': 'Mission controls',
    'atlas-agent-supervisor': 'Mission supervisor',
    'atlas-experience-store': 'Mission / recovery history',
    'atlas-foxglove': 'Foxglove bridge',
    'atlas-visual-cloud-agent': 'Visual Cloud agent',
    'atlas-visual-cloud-server': 'Visual Cloud preview',
    'atlas-voice-companion': 'Voice assistant',
    'atlas-intercom': 'Intercom',
}
ON_DEMAND = {'atlas-localization', 'atlas-nav2', 'atlas-slam-fast', 'atlas-explore'}


def command(args, timeout=3):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip(), '' if result.returncode == 0 else result.stderr.strip()[:500]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return '', str(exc)


def parse_units(text):
    result = []
    for block in text.strip().split('\n\n'):
        fields = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
        name = fields.get('Id', '').removesuffix('.service')
        if name not in UNITS:
            continue
        result.append({
            'unit': name, 'label': UNITS[name], 'mode': 'on demand' if name in ON_DEMAND else 'background',
            'load': fields.get('LoadState', 'unknown'), 'active': fields.get('ActiveState', 'unknown'),
            'sub': fields.get('SubState', 'unknown'), 'result': fields.get('Result', 'unknown'),
            'restarts': fields.get('NRestarts', 'unknown'),
            'exit_code': fields.get('ExecMainStatus', 'unknown'),
            'since': fields.get('ActiveEnterTimestamp', ''),
        })
    present = {u['unit'] for u in result}
    for name in UNITS.keys() - present:
        result.append({'unit': name, 'label': UNITS[name], 'active': 'unknown', 'load': 'unknown',
                       'mode': 'on demand' if name in ON_DEMAND else 'background'})
    return sorted(result, key=lambda x: x['label'])


def redact(text):
    text = re.sub(r'sk-[A-Za-z0-9_-]{12,}', '[REDACTED]', text)
    return re.sub(r'(?i)((?:password|token|api[_-]?key|authorization)\s*[:=]\s*)\S+', r'\1[REDACTED]', text)


def service_logs(unit):
    if unit not in UNITS:
        raise ValueError('Unknown diagnostic unit')
    out, error = command(['journalctl', '--user', '-b', '-r', '-u', unit + '.service', '-n', '60',
                          '--no-pager', '-o', 'short-iso'], timeout=3)
    return {'unit': unit, 'log': redact(out[-24000:]), 'error': redact(error),
            'note': 'Read-only: current boot only, newest first, maximum 60 entries. Refresh to fetch newer logs; old receiver errors from earlier boots are excluded.'}


class DiagnosticCache:
    def __init__(self):
        self.lock = threading.Lock()
        self.updated = 0.0
        self.pending = False
        self.value = {'state': 'collecting', 'services': [], 'serial_devices': []}

    def snapshot(self):
        with self.lock:
            if not self.pending and time.monotonic() - self.updated > 10:
                self.pending = True
                threading.Thread(target=self._collect, daemon=True).start()
            return {**self.value, 'cache_age_s': round(time.monotonic() - self.updated, 1) if self.updated else None}

    def _collect(self):
        try:
            props = 'Id,LoadState,ActiveState,SubState,Result,NRestarts,ExecMainStatus,ActiveEnterTimestamp'
            out, error = command(['systemctl', '--user', 'show', '--property=' + props,
                                  *[name + '.service' for name in UNITS]], timeout=4)
            ports = [{'path': path, 'device': os.path.realpath(path), 'present': os.path.exists(path)}
                     for path in sorted(glob.glob('/dev/serial/by-id/*'))]
            versions = {}
            for name in ('atlas_status_web.py', 'atlas_web_diagnostics.py'):
                try:
                    with open(os.path.join(os.path.dirname(__file__), name), 'rb') as stream:
                        versions[name] = hashlib.sha256(stream.read()).hexdigest()
                except OSError:
                    versions[name] = 'unavailable'
            value = {'state': 'ready' if not error else 'partial', 'error': error,
                     'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                     'services': parse_units(out), 'serial_devices': ports, 'deployed_sha256': versions,
                     'note': 'Service active means process running, not sensor validated. Inactive on-demand mapping services can be normal. No movement or recovery is triggered by this page.'}
        except Exception as exc:
            value = {'state': 'error', 'error': str(exc), 'services': [], 'serial_devices': []}
        with self.lock:
            self.value = value
            self.updated = time.monotonic()
            self.pending = False

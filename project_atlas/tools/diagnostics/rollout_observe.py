#!/usr/bin/env python3
"""Finite read-only rollout observation. Stores private evidence only in --out."""
import argparse
import os
import json
from pathlib import Path
import re
import statistics
import subprocess
import time
import urllib.request


def command(*args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=12)
    return result.stdout.strip()


def summary(values):
    values = sorted(values)
    return {'n': len(values), 'median_ms': statistics.median(values) if values else None,
            'max_ms': max(values) if values else None,
            'p95_ms': values[min(len(values)-1, int(len(values)*.95))] if values else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=120)
    args = parser.parse_args()
    if args.out.exists() or not 10 <= args.seconds <= 600:
        parser.error('new output path and 10..600 seconds required')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    start_wall, start_mono = time.time(), time.monotonic()
    samples = []
    bms_pid = command('systemctl', '--user', 'show', 'rover-daly-bms', '-p', 'MainPID', '--value')
    routes = command('ip', '-j', 'route', 'show', 'default')
    route_list = json.loads(routes)
    gateway = next((r['gateway'] for r in route_list if r.get('dev') == 'wlP1p1s0' and r.get('gateway')), None)
    while time.monotonic()-start_mono < args.seconds:
        row = {'elapsed_s': time.monotonic()-start_mono}
        try:
            stat = Path('/proc/'+bms_pid+'/stat').read_text().split(') ',1)[1].split()
            row['bms_start_ticks'] = int(stat[19])
            row['bms_cpu_s'] = (int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK')
            mem = Path('/proc/'+bms_pid+'/status').read_text().splitlines()
            row['bms_rss_kib'] = next(int(s.split()[1]) for s in mem if s.startswith('VmRSS:'))
        except (OSError, StopIteration):
            row['bms_process_changed'] = True
        tick = time.monotonic()
        try:
            with urllib.request.urlopen('http://127.0.0.1:8088/api/status', timeout=4) as response:
                data = json.load(response)
            row['dashboard_ms'] = (time.monotonic()-tick)*1000
            ros = data.get('ros', {})
            row['system'] = data.get('system', {})
            row['safety'] = ros.get('control_policy', {})
            row['bms'] = ros.get('bms_status', {})
            row['cmd'] = ros.get('cmd_vel', {})
            row['services'] = {k:v for k,v in data.get('services', {}).items()
                               if k in ('atlas-nav2','atlas-explore','rover-daly-bms','rover-status-web')}
        except Exception as exc:
            row['error'] = type(exc).__name__
        if gateway:
            ping = command('ping', '-n', '-c', '1', '-W', '1', '-I', 'wlP1p1s0', gateway)
            match = re.search(r'time[=<]([\d.]+)', ping)
            row['gateway_ms'] = float(match.group(1)) if match else None
        samples.append(row)
        time.sleep(max(0, 5-(time.monotonic()-tick)))
    bms = command('journalctl', '--user', '-u', 'rover-daly-bms.service', '--since', '@'+str(int(start_wall)), '--no-pager', '-o', 'cat')
    bt = command('journalctl', '-u', 'bluetooth', '--since', '@'+str(int(start_wall)), '--no-pager', '-o', 'cat')
    net = command('journalctl', '-u', 'NetworkManager', '-u', 'wpa_supplicant', '-u', 'tailscaled', '--since', '@'+str(int(start_wall)), '--no-pager', '-o', 'cat')
    result = {'duration_s': time.monotonic()-start_mono,
              'dashboard': summary([s['dashboard_ms'] for s in samples if 'dashboard_ms' in s]),
              'dashboard_errors': sum('error' in s for s in samples),
              'gateway': summary([s['gateway_ms'] for s in samples if s.get('gateway_ms') is not None]),
              'gateway_loss_samples': sum(s.get('gateway_ms') is None for s in samples),
              'bms_ok': bms.count('Daly OK'), 'bms_read_failed': bms.count('Daly read failed'),
              'bond_failures': sum('bond' in line.lower() and ('fail' in line.lower() or 'status' in line.lower()) for line in bt.splitlines()),
              'dhcp_failures': net.count('ip-config-unavailable'),
              'wifi_disconnects': net.count('CTRL-EVENT-DISCONNECTED'),
              'route_cell_events': net.count('(usb0) as default'),
              'tailscale_major_changes': net.count('LinkChange: major'),
              'bms_healthy_samples': sum(json.loads(s.get('bms',{}).get('value','{}')).get('ok') is True for s in samples)}
    cpu_rows = [s for s in samples if 'bms_cpu_s' in s]
    result['bms_cpu_measurement_valid'] = (len(cpu_rows) == len(samples)
        and len(cpu_rows) > 1
        and len({s['bms_start_ticks'] for s in cpu_rows}) == 1)
    result['bms_process_missing_samples'] = len(samples)-len(cpu_rows)
    if result['bms_cpu_measurement_valid']:
        result['bms_cpu_one_core_percent'] = 100*(cpu_rows[-1]['bms_cpu_s']-cpu_rows[0]['bms_cpu_s'])/(cpu_rows[-1]['elapsed_s']-cpu_rows[0]['elapsed_s'])
        result['bms_peak_rss_mib'] = max(s['bms_rss_kib'] for s in cpu_rows)/1024
    args.out.write_text(json.dumps({'summary':result, 'samples': samples, 'routes': route_list,
                                   'bms_log':bms, 'bluetooth_log':bt, 'network_log':net}, indent=2)+'\n')
    args.out.chmod(0o600)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()

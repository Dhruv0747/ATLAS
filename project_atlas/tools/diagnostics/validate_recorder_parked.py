#!/usr/bin/env python3
"""Finite opt-in recorder validation; only reads status and stops its own child."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request


def status():
    with urllib.request.urlopen('http://127.0.0.1:8088/api/status', timeout=3) as response:
        data = json.load(response)
    policy, cmd = data['ros']['control_policy'], data['ros']['cmd_vel']
    assert policy['age'] <= 2 and cmd['age'] <= 2, 'stale stop evidence'
    assert json.loads(policy['value'])['stop_latched'], 'stop not latched'
    assert cmd['value']['lin'] == 0 and cmd['value']['ang'] == 0, 'nonzero command'
    assert all(data['services'].get(k) == 'inactive' for k in ('atlas-nav2','atlas-explore')), 'navigation active'
    return {'system': data['system'], 'topic_age': {k:v.get('age') for k,v in data['ros'].items()
            if k in ('scan','odom','imu','control_policy','cmd_vel','encoder_health')},
            'stop_latched': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recorder', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    if not args.root.is_absolute() or args.root.exists():
        parser.error('use a NEW absolute test root')
    baseline = status()
    args.root.mkdir(parents=True)
    env = dict(os.environ, FASTDDS_BUILTIN_TRANSPORTS='UDPv4')
    free_before = shutil.disk_usage(args.root).free
    writes_before = int(Path('/sys/block/nvme0n1/stat').read_text().split()[6])
    started = time.monotonic()
    peak_rss = cpu_seconds = 0
    rows = []
    with (args.root/'console.log').open('w') as log:
        child = subprocess.Popen([sys.executable, str(args.recorder), '--record', '--root',
                                  str(args.root/'bags'), '--duration', '60', '--stationary-probe'],
                                 env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            while child.poll() is None:
                if time.monotonic()-started > 85:
                    raise TimeoutError('recorder exceeded finite test window')
                values = status()
                try:
                    stat = Path(f'/proc/{child.pid}/stat').read_text().split(') ', 1)[1].split()
                    cpu_seconds = (int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK')
                    mem = Path(f'/proc/{child.pid}/status').read_text().splitlines()
                    rss = next(int(s.split()[1]) for s in mem if s.startswith('VmRSS:'))
                    peak_rss = max(peak_rss, rss)
                except FileNotFoundError:
                    pass
                rows.append(values)
                time.sleep(2)
        finally:
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
                try:
                    child.wait(20)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    wall = time.monotonic()-started
    health_file = args.root/'bags/recorder_health.json'
    health = json.loads(health_file.read_text()) if health_file.exists() else {}
    bags = []
    for db in (args.root/'bags').glob('capture_*/*.db3'):
        with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as connection:
            count, low, high = connection.execute('select count(*),min(timestamp),max(timestamp) from messages').fetchone()
            integrity = connection.execute('pragma integrity_check').fetchone()[0]
            topics = connection.execute('select name,count(messages.id) from topics left join messages on topics.id=messages.topic_id group by topics.id').fetchall()
        bags.append(dict(path=str(db), messages=count, duration_s=(high-low)/1e9,
                         integrity=integrity, topics=topics))
    result = dict(returncode=child.returncode, wall_s=wall, cpu_one_core_percent=100*cpu_seconds/wall,
                  peak_rss_mib=peak_rss/1024, baseline=baseline, final=status(),
                  samples=rows, health=health, bags=bags,
                  free_before_bytes=free_before, free_after_bytes=shutil.disk_usage(args.root).free,
                  recorder_file_bytes=sum(p.stat().st_size for p in (args.root/'bags').rglob('*') if p.is_file()),
                  whole_nvme_write_bytes=512*(int(Path('/sys/block/nvme0n1/stat').read_text().split()[6])-writes_before))
    (args.root/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('samples','baseline','final')}, indent=2))
    assert child.returncode == 0 and health.get('disabled') is None, 'recorder failed'
    assert len(bags) == 1 and bags[0]['integrity'] == 'ok', 'missing or broken bag'
    assert not health.get('dropped'), 'recorder application drops'


if __name__ == '__main__':
    main()

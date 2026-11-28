#!/usr/bin/env python3
"""Record a taught route while the owner drives (2026-11-22). Read-only and light.

Polls the dashboard /api/status (127.0.0.1:8088) a few times per second and appends the authoritative map pose
(map -> base_link TF), the AMCL std and the stop latch to a JSON-lines file. It never commands motion and never
touches ROS. Stop it by creating <out>.stop (or Ctrl-C); it also stops after --max-s seconds.

  teach_route_record.py ~/atlas_bags/route_teach_YYYYmmdd_HHMMSS.jsonl
"""
import argparse
import json
import os
import time
import urllib.request


def sample(url):
    d = json.load(urllib.request.urlopen(url, timeout=2))['ros']
    p = (d.get('map_pose') or {}).get('value') or {}
    q = (d.get('amcl_quality') or {}).get('value') or {}
    pol = (d.get('control_policy') or {}).get('value')
    try:
        pol = json.loads(pol) if isinstance(pol, str) else (pol or {})
    except ValueError:
        pol = {}
    return {'t': time.time(), 'x': p.get('x'), 'y': p.get('y'), 'yaw': p.get('yaw'),
            'pose_age_s': (d.get('map_pose') or {}).get('age'), 'xy_std_m': q.get('xy_std_m'),
            'stop_latched': pol.get('stop_latched'), 'source': pol.get('source')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--url', default='http://127.0.0.1:8088/api/status')
    ap.add_argument('--period-s', type=float, default=0.3)
    ap.add_argument('--max-s', type=float, default=1200.0)
    a = ap.parse_args()
    stop = a.out + '.stop'
    end = time.time() + a.max_s
    with open(a.out, 'a', encoding='utf-8') as f:
        while time.time() < end and not os.path.exists(stop):
            try:
                f.write(json.dumps(sample(a.url)) + '\n'); f.flush()
            except Exception as exc:          # keep recording through dashboard hiccups
                f.write(json.dumps({'t': time.time(), 'error': str(exc)[:120]}) + '\n'); f.flush()
            time.sleep(a.period_s)


if __name__ == '__main__':
    main()

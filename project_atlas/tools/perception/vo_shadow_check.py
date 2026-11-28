#!/usr/bin/env python3
"""ATLAS master-plan step 7: camera visual odometry in SHADOW MODE (read-only, no motion, no ROS). 2026-11-23.

Plan text: "Evaluate camera VO/VIO in shadow mode with rate, age, confidence and GOOD/DEGRADED/LOST states."
The shadow VO (scripts/atlas_vo_shadow.py, unit atlas-vo-shadow) runs on the Astra depth camera in the private ROS
domain 77 and writes ~/.local/state/project_atlas/vo_shadow_status.json at 2 Hz. This tool, with ATLAS PARKED:

  1. reads that file every 0.5 s for 20 s and the wheel speed from the dashboard (/api/status, light endpoint):
     VO running, rate, p95 age, share of GOOD, parked drift, the node's own CPU, and that ATLAS stood still;
  2. checks isolation: no EKF config, the live Nav2 params or the domain-77 -> 0 bridge names a VO topic, and the
     node reports shadow=true in domain 77;
  3. takes the VO-vs-LiDAR comparison from the newest Stage-2 / step-4B turn check (turn_check_*.json,
     imu_workload_check_*.json, last 7 days): those bounded, owner-PIN arcs record the VO and LiDAR-ICP heading
     change and distance of each arc. This tool itself never moves ATLAS.

Verdicts (scripts/atlas_vo_core.evaluate_step7): PASS / NOT USABLE (evaluation done, VO disagrees in motion and stays
shadow-only) / NEEDS MOTION (run the Stage-2 turn check once, then this again) / FAIL.
Writes ~/.local/state/project_atlas/vo_shadow_check_<time>.json and records step 7 on the master plan.
Usage (on the Jetson):  python3 vo_shadow_check.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path('/home/jetson/project_atlas')
HERE = Path(__file__).resolve()
for p in (ROOT / 'scripts', HERE.parents[2] / 'scripts', ROOT / 'tools/nav', HERE.parents[1] / 'nav'):
    sys.path.insert(0, str(p))
import atlas_vo_core as core  # noqa: E402

STATE = Path.home() / '.local/state/project_atlas'
STATUS_FILE = STATE / 'vo_shadow_status.json'
SAMPLE_S, PERIOD_S, FRESH_S = 20.0, 0.5, 2.0


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8')
    except OSError:
        return ''


def read_status(now):
    try:
        s = json.loads(STATUS_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return s if abs(now - float(s.get('wall_time') or 0)) <= FRESH_S else None


def wheel_speed():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8088/api/status', timeout=2) as r:
            v = ((json.load(r).get('ros') or {}).get('odom') or {}).get('value')
        v = json.loads(v) if isinstance(v, str) else v
        return float((v or {}).get('vx') or 0.0)
    except Exception:
        return None


def newest_vo_arcs(now, state=STATE):
    """(arcs, file name, age in days) from the newest turn check whose arcs carry VO data, or ([], None, None)."""
    files = sorted(list(state.glob('turn_check_*.json')) + list(state.glob('imu_workload_check_*.json')),
                   key=lambda f: f.stat().st_mtime)
    for f in reversed(files):
        try:
            arcs = [a.get('vo') for a in json.loads(f.read_text(encoding='utf-8')).get('arcs') or []]
        except (OSError, ValueError, AttributeError):
            continue
        arcs = [a for a in arcs if isinstance(a, dict)]
        if arcs:
            return arcs, f.name, (now - f.stat().st_mtime) / 86400.0
    return [], None, None


def main():
    print('Step 7: shadow visual odometry check. ATLAS does not move; keep it parked for 20 s.', flush=True)
    samples, wheels, t_end = [], [], time.time() + SAMPLE_S
    while time.time() < t_end:
        s = read_status(time.time())
        if s:
            samples.append(s)
        w = wheel_speed()
        if w is not None:
            wheels.append(w)
        if len(samples) % 4 == 1 and s:
            print('VO %s rate %.1f Hz age %s s conf %.2f cpu %s %%' % (s.get('state'), s.get('rate_hz') or 0,
                  s.get('age_s'), s.get('confidence') or 0, s.get('cpu_pct')), flush=True)
        time.sleep(PERIOD_S)
    if not samples:
        print('no fresh VO status: is atlas-vo-shadow running (and atlas-astra-obstacles)?', flush=True)
    try:
        import nav2_recovery_audit
        nav2_text = _read(nav2_recovery_audit.live_nav2_params())
    except Exception:
        nav2_text = _read(ROOT / 'config/nav2_params.yaml')
    ekf_texts = [_read(f) for f in sorted((ROOT / 'config').glob('atlas_ekf*.yaml'))]
    iso = core.isolation_texts_ok(ekf_texts, nav2_text, _read(ROOT / 'config/astra_obstacles_bridge.yaml'))
    arcs, arcs_file, age_days = newest_vo_arcs(time.time())
    res = core.evaluate_step7(samples, wheels, iso, arcs, arcs_file, age_days)
    res['when'] = time.strftime('%Y-%m-%d %H:%M')
    out = STATE / f'vo_shadow_check_{time.strftime("%Y%m%d_%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    try:
        import atlas_master_plan
        atlas_master_plan.record_later(7, res, out.name)
    except Exception as exc:
        print(f'note: master plan not updated ({exc})')
    print(json.dumps(res, indent=1))
    print(f'STEP 7: {res["verdict"]}')
    print(f'saved {out}')


if __name__ == '__main__':
    main()

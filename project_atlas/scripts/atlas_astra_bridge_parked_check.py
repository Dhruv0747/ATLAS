#!/usr/bin/env python3
"""Track A bridge interlock (systemd ExecCondition): exit 0 only if the rover is verifiably parked.

Any new participant joining production ROS domain 0 makes every existing node re-run DDS discovery. Measured
2026-11-06 with the rover parked: a minimal rclpy node pushed the whole Jetson to ~100 % CPU for ~3.5 s, the
domain_bridge for ~4.5 s (LiDAR observed rate dipped 1.86 -> 1.58 Hz). So the bridge may only START while parked.
Exit 1 (systemd: skip the unit, no failure, no retry) when moving, unknown, stale, or the dashboard is unreachable.
"""
import json
import sys
import urllib.request

URL = 'http://127.0.0.1:8088/api/status'
MAX_AGE_S = 2.0


def parked(status):
    """[] when parked, else the reasons. Commanded zero (cmd_vel), measured zero (motor_speed) and still (odom).
    ('motion_state' on the dashboard is the IMX708 scene-motion detector, not rover motion: not used.)"""
    ros = status['ros']
    why = []
    for key in ('cmd_vel', 'motor_speed', 'odom'):
        age = ros.get(key, {}).get('age')
        if age is None or not 0 <= float(age) <= MAX_AGE_S:
            why.append(f'{key} telemetry stale/missing (age {age})')
    v = ros.get('cmd_vel', {}).get('value') or {}
    if abs(float(v.get('lin', 1))) > 1e-3 or abs(float(v.get('ang', 1))) > 1e-3:
        why.append(f'cmd_vel not zero {v}')
    if abs(float(ros.get('motor_speed', {}).get('value', 1) or 0)) > 1e-3:
        why.append('motor_speed not zero')
    o = ros.get('odom', {}).get('value') or {}
    if abs(float(o.get('vx', 1))) > 0.01 or abs(float(o.get('wz', 1))) > 0.02:
        why.append(f"odom not still (vx {o.get('vx')}, wz {o.get('wz')})")
    return why


def main():
    try:
        with urllib.request.urlopen(URL, timeout=4) as r:
            why = parked(json.load(r))
    except Exception as e:  # unreachable / malformed -> fail closed
        why = [f'status unavailable: {e}']
    if why:
        print('atlas-astra-bridge NOT started (rover not verifiably parked): ' + '; '.join(why), file=sys.stderr)
        sys.exit(1)
    print('atlas-astra-bridge: rover parked, bridge may start')


if __name__ == '__main__':
    main()

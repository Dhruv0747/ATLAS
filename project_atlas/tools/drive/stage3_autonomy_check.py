#!/usr/bin/env python3
"""ATLAS Stage-3 gate check (read-only, offline; publishes nothing, never commands motion). 2026-11-16.

Master plan (docs/AI_ROBOTICS_ADAPTATION_PHASE0_2026-09-30.md) entry gate, stage 3:
  "One supervised autonomous Dhruv Room -> Hall -> Dhruv Room round trip, including safe stop and return-home evidence."

Reads a recorded bag of that drive and gives one verdict per criterion:
  legs        an outbound named goal (not HOME) and then the HOME goal both FINISHED status=4 (SUCCEEDED)
  return_home final AMCL pose within 0.30 m / 20 deg of the AMCL pose at the first goal dispatch
  safe_stop   at least one owner stop (B / E-STOP / remote stop) while Nav2 was driving the rover, with the rover
              still (|v| < 0.02 m/s) within 1.5 s; stopping distance is reported
  turn_sign   AUTONOMOUS commanded yaw-rate vs IM10A gyro sign opposite in <= 5 % of turning samples (needs >= 20);
              owner remote samples (/cmd_vel_joy) and the 1 s after a yaw-sign flip are excluded (2026-11-19)
  encoders    no CRITICAL / INVALID / MISSING encoder health while the rover was moving
Information only: localization blocks/jumps while driving, mean speed, duration.

Usage (on the rover, parked):  python3 stage3_autonomy_check.py BAG --home "dhruv room"
Record the drive with at least: /atlas/mission_status /atlas/motion_safety /atlas/encoder_health /amcl_pose
/cmd_vel /cmd_vel_joy /yahboom/odom /im10a/imu/bias_corrected_candidate
"""
import argparse, bisect, json, math, re, sys

RETURN_XY_M, RETURN_YAW_DEG = 0.30, 20.0
STOP_STILL_MPS, STOP_WITHIN_S = 0.02, 1.5
TURN_OPPOSITE_MAX, TURN_MIN_SAMPLES = 0.05, 20
TURN_REMOTE_WINDOW_S, TURN_FLIP_SKIP_S = 0.5, 1.0
STOP_PATTERNS = ('REMOTE STOP', 'E-STOP', 'ESTOP', 'LATCHED')
BAD_ENCODER = ('CRITICAL', 'INVALID', 'MISSING')
FINISHED = re.compile(r'NAMED GOAL FINISHED name=(.+?) status=(\d+)')
DISPATCHED = re.compile(r'NAMED GOAL (?:DISPATCHED|ACCEPTED) name=(.+)$')


def _wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def evaluate(home, mission, safety, encoder, amcl, odom, cmd, imu, joy=None):
    """Pure. Each input is a time-sorted list:
    mission/safety: (t, text); encoder: (t, state); amcl: (t, x, y, yaw_deg); odom: (t, vx); cmd: (t, vx, wz);
    imu: (t, gz). Returns {'verdict', 'checks': {name: {'ok', 'detail'}}, 'info': {...}}."""
    home_key = home.strip().lower()
    checks, info = {}, {}

    # legs ------------------------------------------------------------------------------------------------------
    finished, last = [], None          # mission_status repeats its latest line ~1 Hz: count a goal result once
    for t, s in mission:
        m = FINISHED.search(s)
        # 2026-11-22: taught-route goals report 'name=<place> taught-route'; the place is what counts
        key = (re.sub(r'\s+taught-route$', '', m.group(1).strip().lower()), int(m.group(2))) if m else None
        if key and key != last:
            finished.append((t,) + key)
        if m or DISPATCHED.search(s):
            last = key
    ok_legs = [(t, n) for t, n, st in finished if st == 4]
    out_t = next((t for t, n in ok_legs if n != home_key), None)
    home_t = next((t for t, n in ok_legs if n == home_key and out_t is not None and t > out_t), None)
    checks['legs'] = {'ok': out_t is not None and home_t is not None,
                      'detail': 'finished: ' + (', '.join(f'{n}={st}' for _, n, st in finished) or 'none')}

    # return home -----------------------------------------------------------------------------------------------
    t_first = next((t for t, s in mission if DISPATCHED.search(s)), None)
    start = next((a for a in amcl if t_first is not None and a[0] >= t_first), None)
    end_t = home_t if home_t is not None else (amcl[-1][0] if amcl else None)
    end = None
    if end_t is not None:
        before = [a for a in amcl if a[0] <= end_t + 3.0]
        end = before[-1] if before else None
    if start and end and home_t is not None:
        dxy = math.hypot(end[1] - start[1], end[2] - start[2]); dyaw = abs(_wrap_deg(end[3] - start[3]))
        checks['return_home'] = {'ok': dxy <= RETURN_XY_M and dyaw <= RETURN_YAW_DEG,
                                 'detail': f'{dxy:.2f} m / {dyaw:.0f} deg from the start pose'}
    else:
        checks['return_home'] = {'ok': False, 'detail': 'no HOME goal success or no AMCL pose'}

    # safe stop ---------------------------------------------------------------------------------------------------
    ot = [o[0] for o in odom]
    def speed_at(t):
        i = bisect.bisect_right(ot, t) - 1
        return abs(odom[i][1]) if i >= 0 else None
    nav_moving = [c for c in cmd if abs(c[1]) > 0.02]
    ct = [c[0] for c in nav_moving]
    stops, last_stop = [], -1e9
    for t, s in safety:
        if not any(p in s.upper() for p in STOP_PATTERNS) or t - last_stop < 3.0:
            continue
        i = bisect.bisect_right(ct, t) - 1
        v0 = speed_at(t)
        if i < 0 or t - ct[i] > 0.6 or v0 is None or v0 < 0.05:
            continue                              # not a stop of an autonomously moving rover
        last_stop = t
        still_t, dist, prev = None, 0.0, t
        for j in range(bisect.bisect_left(ot, t), len(odom)):
            tj, vj = odom[j]
            if tj > t + STOP_WITHIN_S + 2.0: break
            dist += abs(vj) * max(0.0, tj - prev); prev = tj
            if abs(vj) < STOP_STILL_MPS:
                still_t = tj; break
        stops.append({'t': t, 'v0': round(v0, 3), 'still_after_s': None if still_t is None else round(still_t - t, 2),
                      'distance_m': round(dist, 3), 'text': s[:60]})
    good = [s for s in stops if s['still_after_s'] is not None and s['still_after_s'] <= STOP_WITHIN_S]
    checks['safe_stop'] = {'ok': bool(good) and len(good) == len(stops),
                           'detail': (f'{len(good)}/{len(stops)} stops within {STOP_WITHIN_S} s; ' +
                                      '; '.join(f"v {s['v0']} -> still {s['still_after_s']} s, {s['distance_m']} m"
                                                for s in stops)) if stops else 'no owner stop while Nav2 was driving'}

    # turn sign ---------------------------------------------------------------------------------------------------
    # 2026-11-19: count AUTONOMOUS turning only. The owner's remote steers like a car (stick-left in reverse yaws the
    # rover right), so remote reverse turns were 99-100 % "opposite" (dhruvroom_test3: 240/243) and inflated attempt 7
    # to 5.8 %. Samples within TURN_FLIP_SKIP_S of a commanded yaw-sign change are also skipped: the steering servos
    # need that long to swing lock-to-lock (4-10 % "opposite" there, 0-3 % otherwise).
    it = [g[0] for g in imu]
    jt = [j[0] for j in joy] if joy is not None else []
    same = opp = skipped_remote = skipped_flip = 0
    last_flip, prev = -1e18, 0
    for t, vx, wz in cmd:
        sg = 1 if wz > 0.1 else (-1 if wz < -0.1 else 0)
        if sg and prev and sg != prev:
            last_flip = t
        if sg:
            prev = sg
        if abs(wz) > 0.1 and abs(vx) > 0.05:
            if joy is not None:
                k = bisect.bisect_right(jt, t) - 1
                if k >= 0 and t - joy[k][0] <= TURN_REMOTE_WINDOW_S and joy[k][1]:
                    skipped_remote += 1
                    continue
            if t - last_flip < TURN_FLIP_SKIP_S:
                skipped_flip += 1
                continue
            i = bisect.bisect_right(it, t + 0.3) - 1
            if i >= 0 and abs(imu[i][1]) > 0.03:
                if (wz > 0) == (imu[i][1] > 0): same += 1
                else: opp += 1
    n = same + opp
    note = (f'; excluded {skipped_remote} remote, {skipped_flip} steering-flip samples' if joy is not None
            else f'; excluded {skipped_flip} steering-flip samples; /cmd_vel_joy not recorded, owner remote driving '
                 'cannot be separated')
    checks['turn_sign'] = {'ok': n >= TURN_MIN_SAMPLES and opp <= TURN_OPPOSITE_MAX * n,
                           'detail': f'autonomous: same {same}, opposite {opp}' + note}

    # encoders ----------------------------------------------------------------------------------------------------
    bad = [(t, st) for t, st in encoder if st in BAD_ENCODER and (speed_at(t) or 0.0) > 0.02]
    checks['encoders'] = {'ok': not bad, 'detail': f'{len(bad)} bad samples while moving' +
                          (f' (first {bad[0][1]})' if bad else '')}

    # info --------------------------------------------------------------------------------------------------------
    info['localization_blocks_while_moving'] = sum(1 for t, s in safety if 'LOCALIZATION' in s and (speed_at(t) or 0) > 0.02)
    moving = [abs(v) for _, v in odom if abs(v) > 0.02]
    info['mean_moving_speed_mps'] = round(sum(moving) / len(moving), 3) if moving else None
    if t_first is not None and home_t is not None:
        info['duration_s'] = round(home_t - t_first, 1)
    verdict = 'PASS' if all(c['ok'] for c in checks.values()) else 'FAIL'
    return {'verdict': verdict, 'checks': checks, 'info': info, 'stops': stops}


def read_bag(path):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from std_msgs.msg import String
    from geometry_msgs.msg import Twist, PoseWithCovarianceStamped
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import Imu
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=path, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
    want = ['/atlas/mission_status', '/atlas/motion_safety', '/atlas/encoder_health', '/amcl_pose', '/cmd_vel',
            '/yahboom/odom', '/im10a/imu/bias_corrected_candidate', '/cmd_vel_joy']
    present = {t.name for t in r.get_all_topics_and_types()}
    r.set_filter(rosbag2_py.StorageFilter(topics=[t for t in want if t in present]))
    d = {k: [] for k in ('mission', 'safety', 'encoder', 'amcl', 'odom', 'cmd', 'imu')}
    d['joy'] = [] if '/cmd_vel_joy' in present else None
    while r.has_next():
        topic, data, ts = r.read_next(); t = ts / 1e9
        if topic == '/atlas/mission_status': d['mission'].append((t, deserialize_message(data, String).data))
        elif topic == '/atlas/motion_safety': d['safety'].append((t, deserialize_message(data, String).data))
        elif topic == '/atlas/encoder_health':
            try: d['encoder'].append((t, json.loads(deserialize_message(data, String).data).get('state')))
            except ValueError: pass
        elif topic == '/amcl_pose':
            p = deserialize_message(data, PoseWithCovarianceStamped).pose.pose
            d['amcl'].append((t, p.position.x, p.position.y, math.degrees(2 * math.atan2(p.orientation.z, p.orientation.w))))
        elif topic == '/cmd_vel':
            m = deserialize_message(data, Twist); d['cmd'].append((t, m.linear.x, m.angular.z))
        elif topic == '/cmd_vel_joy':
            m = deserialize_message(data, Twist); d['joy'].append((t, abs(m.linear.x) > 0.01 or abs(m.angular.z) > 0.01))
        elif topic == '/yahboom/odom':
            d['odom'].append((t, deserialize_message(data, Odometry).twist.twist.linear.x))
        else:
            d['imu'].append((t, deserialize_message(data, Imu).angular_velocity.z))
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('bag'); ap.add_argument('--home', required=True, help='named place the round trip returns to')
    ap.add_argument('--json', help='also write the result here')
    a = ap.parse_args()
    res = evaluate(a.home, **read_bag(a.bag))
    for k, c in res['checks'].items():
        print(f"{'PASS' if c['ok'] else 'FAIL'}  {k:12s} {c['detail']}")
    print('info:', json.dumps(res['info']))
    print('STAGE 3:', res['verdict'])
    if a.json:
        json.dump(res, open(a.json, 'w'), indent=1)
    sys.exit(0 if res['verdict'] == 'PASS' else 1)


if __name__ == '__main__':
    main()

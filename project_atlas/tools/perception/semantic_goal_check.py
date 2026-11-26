#!/usr/bin/env python3
"""ATLAS master-plan step 9 PART B: semantic goal resolution THROUGH NAV2 (owner-triggered, bounded). 2026-11-26.

Plan text: "Add advisory semantic perception, then semantic goal resolution through Nav2 only after recorded
validation." Part A (semantic_advisory_check.py) is the advisory half and the recorded validation: it writes
semantic_advisory.json (object label, map position, stop point 0.70 m in front of it). This part B sends ATLAS to that
stop point once and checks that it really arrived in front of the same object.

Authority does NOT change (same rule as the Stage-3 runner):
  * the goal goes through the dashboard map-point path (POST /api/places go_at -> /atlas/navigate_to_point), which is
    refused unless AUTONOMOUS mode is ON (operator PIN) and the E-STOP is released; mission control then runs every
    check it runs for a map tap (free spot with 0.35 m clearance, localisation, map identity, scan/map agreement,
    camera obstacles) and Nav2 plus the cmd_vel mux, LiDAR/ultrasonic guards and the remote decide HOW ATLAS moves;
  * this tool never arms autonomy, never releases the E-STOP and never sends a velocity.
Bounds (refused before anything is sent): advisory result <= 30 min old, ATLAS has not moved since it (<= 0.30 m,
<= 20 deg), stop point 0.15-2.5 m away. While driving it sends Abort (Manual + cancel goal) if the drive takes
> 60 s, ATLAS leaves the straight start->stop-point corridor by > 1.0 m, or CPU >= 75 % x3 / RAM >= 80 % / 70 C.
At the end ATLAS is always switched back to Manual.
After arrival (ATLAS still), 5 YOLO+LiDAR rounds must see the same label within 0.40 m of its recorded map position
in >= 3 rounds. Verdicts (evaluate): PASS / REFUSED (nothing was sent) / FAIL. Writes semantic_goal_<time>.json and
records step 9 part B on the master-plan board.
"""
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path('/home/jetson/project_atlas')
HERE = Path(__file__).resolve()
for p in (ROOT / 'scripts', HERE.parents[2] / 'scripts', HERE.parent):
    sys.path.insert(0, str(p))

STATE = Path.home() / '.local/state/project_atlas'
ADVISORY_FILE = STATE / 'semantic_advisory.json'
LOCAL_DASH = 'http://localhost:8088'          # same-origin POSTs (atlas_wifi_web.same_origin allows localhost)
MAX_ADVISORY_AGE_S = 1800.0
MAX_MOVED_M, MAX_MOVED_DEG = 0.30, 20.0
MIN_GOAL_M, MAX_GOAL_M = 0.15, 2.5
DISPATCH_WAIT_S, DRIVE_TIMEOUT_S, OFF_COURSE_M = 15.0, 60.0, 1.0
ARRIVE_M, ARRIVE_DEG = 0.25, 25.0
CONFIRM_ROUNDS, CONFIRM_MIN, CONFIRM_MATCH_M = 5, 3, 0.40
POLL_S = 0.25
STAGE3_IDLE = ('IDLE', 'DONE', 'CANCELLED', 'ERROR')    # Stage-3 runner states in which it sends no goal


def _dyaw_deg(a_rad, b_rad):
    return abs((math.degrees(a_rad - b_rad) + 180.0) % 360.0 - 180.0)


# 2026-11-26: people and animals move and are the later human-aware step; never a part-B goal (advisory may list them)
NOT_GOALS = {'person', 'cat', 'dog'}


# 2026-11-26 owner "auto step back": when the 0.70 m stop point is not clear on the accepted map (mission control's own
# check_point: free, 0.35 m clearance), step back along the same line of sight in 0.10 m steps up to 1.30 m.
STANDOFFS_M = (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3)


def pick_target(adv, robot, now_unix, clear_fn=None):
    """(target, reasons). target: label, map_x/y, goal_x/y, goal_yaw_deg, goal_dist_m, standoff_m. reasons non-empty =
    refuse. clear_fn(x, y) -> None when the map point is clear, else the reason (None = no map: keep 0.70 m)."""
    if not isinstance(adv, dict):
        return None, ['no advisory result: run step 9 part A (START CHECK) first']
    if not isinstance(robot, dict):
        return None, ['no live map pose: ATLAS must be localised on the map']
    if adv.get('written_unix') is None or not isinstance(adv.get('robot'), dict):
        return None, ['advisory result has no time/pose (made before part B existed): run step 9 part A again']
    if not adv.get('camera_home_us'):      # 2026-11-26: results before the camera-forward fix used a turned camera
        return None, ['advisory result was taken before the camera-forward fix (camera turned): run step 9 part A again']
    if now_unix - float(adv['written_unix']) > MAX_ADVISORY_AGE_S:
        return None, ['advisory result is older than %d min: run step 9 part A again' % (MAX_ADVISORY_AGE_S // 60)]
    then = adv['robot']
    moved = math.hypot(robot['x'] - then['x'], robot['y'] - then['y'])
    turned = _dyaw_deg(robot['yaw'], then['yaw'])
    if moved > MAX_MOVED_M or turned > MAX_MOVED_DEG:
        return None, ['ATLAS moved since step 9 part A (%.2f m, %.0f deg): run part A again here' % (moved, turned)]
    listed = [o for o in adv.get('objects') or [] if isinstance(o.get('advisory_goal'), dict)]
    objs = [o for o in listed if o.get('label') not in NOT_GOALS]
    if listed and not objs:
        return None, ['only people or animals were found (never a goal here): face ATLAS to a chair, table, bag... '
                      'and run part A again']
    if not objs:
        return None, ['no object in the advisory result: run step 9 part A facing an object']
    o = max(objs, key=lambda o: (float(o.get('seen', 0)), float(o.get('confidence', 0))))
    g = o['advisory_goal']
    t = {'label': o['label'], 'map_x': float(o['map_x']), 'map_y': float(o['map_y']),
         'goal_x': round(float(g['x']), 2), 'goal_y': round(float(g['y']), 2),
         'goal_yaw_deg': float(g.get('yaw_deg', 0.0)), 'standoff_m': STANDOFFS_M[0]}
    if clear_fn is not None:
        dx, dy = t['goal_x'] - t['map_x'], t['goal_y'] - t['map_y']
        n = math.hypot(dx, dy)
        if n < 1e-6:
            return t, ['stop point equals the object position: run part A again']
        ux, uy, why = dx / n, dy / n, None
        for d in STANDOFFS_M:
            x, y = round(t['map_x'] + ux * d, 2), round(t['map_y'] + uy * d, 2)
            why = clear_fn(x, y)
            if not why:
                t.update(goal_x=x, goal_y=y, standoff_m=d)
                break
        else:
            return t, ['no map-clear stop point 0.7-1.3 m in front of the %s (%s): park ATLAS facing it from a more '
                       'open side and run part A again' % (t['label'], why)]
    t['goal_dist_m'] = round(math.hypot(t['goal_x'] - robot['x'], t['goal_y'] - robot['y']), 3)
    if t['goal_dist_m'] > MAX_GOAL_M:
        return t, ['stop point is too far (%.2f m > %.1f m): bring ATLAS closer and run part A again'
                   % (t['goal_dist_m'], MAX_GOAL_M)]
    if t['goal_dist_m'] < MIN_GOAL_M:
        return t, ['ATLAS is already at the stop point: park it 1-2 m from the object and run part A again']
    return t, []


_FINISHED = re.compile(r'^NAMED GOAL FINISHED name=(.+?) status=(\d+)')


def mission_event(text, x, y):
    """Classify one /atlas/mission_status line for OUR map-point goal: queued/dispatched/accepted/succeeded/failed."""
    text = str(text or '')
    label = 'map point %.2f,%.2f' % (x, y)
    if text == 'QUEUED navigate to ' + label:
        return 'queued'
    if text == 'NAMED GOAL DISPATCHED name=' + label:
        return 'dispatched'
    if text == 'NAMED GOAL ACCEPTED name=' + label:
        return 'accepted'
    m = _FINISHED.match(text)
    if m:
        return None if m.group(1) != label else ('succeeded' if m.group(2) == '4' else 'failed')
    if text in ('NAMED GOAL REJECTED name=' + label, 'BUSY: ignored navigate to ' + label):
        return 'failed'
    if text.startswith('ERROR navigate to ' + label) or text.startswith(('NAVIGATION STOPPED', 'NAVIGATION CANCELED')):
        return 'failed'
    return None


def accept_event(ev, seen, status, status_before):
    """Does this mission event count? QUEUED/DISPATCHED/ACCEPTED always. A success only after our goal was seen (a
    stale success must never make a PASS). A refusal naming OUR goal also counts when its text is new since the send
    (2026-11-26 11:52: mission control refused before the 1 Hz status ever showed QUEUED)."""
    if ev in ('queued', 'dispatched', 'accepted'):
        return True
    if ev == 'succeeded':
        return bool(seen)
    if ev == 'failed':
        if seen:
            return True
        generic = str(status).startswith(('NAVIGATION STOPPED', 'NAVIGATION CANCELED'))
        return not generic and status != status_before
    return False


def off_course(start, goal, p):
    """Distance of p from the straight segment start -> goal (metres)."""
    sx, sy = start
    dx, dy = goal[0] - sx, goal[1] - sy
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 <= 1e-9 else max(0.0, min(1.0, ((p[0] - sx) * dx + (p[1] - sy) * dy) / L2))
    return math.hypot(p[0] - (sx + u * dx), p[1] - (sy + u * dy))


# 2026-11-26 owner "show reason": why the safety chain kept ATLAS still. The mux logs every veto; the dashboard API does
# not carry /atlas/motion_safety, so the tool reads the mux journal for the run window afterwards (read-only).
_LOG_PREFIX = re.compile(r'^\[(ERROR|WARN)\]\s+\[[^\]]*\]\s+\[[^\]]*\]:\s*')
_OUR_ABORT = ('autonomy switched OFF', 'AUTONOMY OFF', 'NAV2 released')
HINTS = [
    (re.compile(r'LIDAR AVAILABILITY'), 'The LiDAR could not see part of the path (no reflection), so the safety mux did '
     'not let ATLAS move. Face ATLAS straight at the object, 1-1.5 m away, and cover or move dark, shiny or open areas '
     'next to the path.'),
    (re.compile(r'ULTRASONIC'), 'An ultrasonic sensor gave no data, so the safety mux stopped ATLAS. Check the sensor.'),
    (re.compile(r'AUTONOMY BLOCKED'), 'Something was too close to ATLAS, so the safety mux stopped it. Clear the path.'),
    (re.compile(r'too close to a wall'), 'The stop point is too close to a wall on the map. Park ATLAS facing the object '
     'from another side and run Part A again.'),
    (re.compile(r'(unknown|occupied) on the map'), 'The stop point is not free on the map. Run Part A from another spot.'),
    (re.compile(r'[Ll]ocali[sz]ation'), 'ATLAS was not sure where it is on the map. Re-localise it, then run Part A again.'),
    (re.compile(r'camera obstacles'), 'The obstacle camera was off or stale. Start it, then try again.'),
]


def mux_summary(lines):
    """[{reason, count}] of the mux ERROR/WARN lines, most frequent first, numbers and our own Abort dropped."""
    counts = {}
    for line in lines or []:
        m = _LOG_PREFIX.match(str(line))
        if not m:
            continue
        text = str(line)[m.end():].strip()
        if any(k in text for k in _OUR_ABORT):
            continue
        text = re.sub(r'\s*\([^)]*\)', '', text)
        text = re.sub(r'\s+-?\d[\d.]*\b.*$', '', text).strip()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return [{'reason': k, 'count': v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


def block_hint(reason):
    for rx, hint in HINTS:
        if reason and rx.search(reason):
            return hint
    return None


def evaluate(refused, seen, end_reason, final_pose, target, confirm_rounds, max_off_course_m, elapsed_s, limit_stop,
             blocked=None, mission_text=None):
    if refused:
        return {'verdict': 'REFUSED', 'checks': {}, 'failed': [], 'notes': list(refused),
                'detail': 'nothing was sent: ' + '; '.join(refused), 'measured': {'target': target}}
    c, m = {}, {'target': target, 'end_reason': end_reason, 'elapsed_s': round(elapsed_s, 1),
                'max_off_course_m': round(max_off_course_m, 3), 'limit_stop': limit_stop}
    c['dispatched'] = bool(seen & {'queued', 'dispatched', 'accepted'})
    c['nav2_succeeded'] = 'succeeded' in seen and end_reason == 'ARRIVED'
    c['no_owner_stop'] = end_reason != 'OWNER_STOP'
    c['within_time'] = end_reason != 'TIMEOUT' and elapsed_s <= DRIVE_TIMEOUT_S
    c['stayed_on_course'] = end_reason != 'OFF_COURSE' and max_off_course_m <= OFF_COURSE_M
    c['limits_held'] = limit_stop is None and end_reason != 'LIMIT'
    if final_pose and target:
        m['stop_error_m'] = round(math.hypot(final_pose['x'] - target['goal_x'], final_pose['y'] - target['goal_y']), 3)
        m['heading_error_deg'] = round(_dyaw_deg(final_pose['yaw'], math.radians(target['goal_yaw_deg'])), 1)
    c['arrived_at_stop_point'] = c['nav2_succeeded'] and m.get('stop_error_m', 99.0) <= ARRIVE_M
    c['facing_object'] = c['nav2_succeeded'] and m.get('heading_error_deg', 999.0) <= ARRIVE_DEG
    hits = 0
    for objs in confirm_rounds or []:
        if any(o[0] == target['label'] and math.hypot(o[2] - target['map_x'], o[3] - target['map_y']) <= CONFIRM_MATCH_M
               for o in objs):
            hits += 1
    m['confirm_hits'] = '%d/%d' % (hits, len(confirm_rounds or []))
    c['object_confirmed'] = hits >= CONFIRM_MIN
    failed = [k for k, v in c.items() if not v]
    verdict = 'PASS' if not failed else 'FAIL'
    if verdict == 'PASS':
        detail = ('went to the %s through Nav2 and stopped %.2f m from the stop point (heading off %.0f deg) in %.0f s; '
                  'object seen again %s' % (target['label'], m['stop_error_m'], m['heading_error_deg'], elapsed_s,
                                            m['confirm_hits']))
    else:
        detail = 'go to the %s: %s (end: %s)' % ((target or {}).get('label', 'object'), ', '.join(failed), end_reason)
        why = (blocked or [{}])[0].get('reason') or (mission_text if mission_text and not mission_text.startswith(
            'NAVIGATION CANCELED') else None)
        if why:
            m['blocked_by'], m['hint'] = why, block_hint(why)
            m['mux_stops'] = (blocked or [])[:5]
            detail += '; blocked by the safety chain: %s%s' % (why, (' (%dx)' % blocked[0]['count']) if blocked else '')
        elif blocked:
            m['mux_stops'] = blocked[:5]
    return {'verdict': verdict, 'checks': c, 'failed': failed, 'notes': [], 'detail': detail, 'measured': m}


# ------------------------------------------------------------------ IO (Jetson only)
def post(path, payload, timeout=4):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(LOCAL_DASH + path, data=body, method='POST', headers={
        'Content-Type': 'application/json', 'Origin': LOCAL_DASH, 'X-Atlas-Wifi': '1'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b'{}')
        except ValueError:
            return e.code, {}
    except Exception as exc:
        return 0, {'message': str(exc)}


def main():
    import yolo_benchmark as yb
    import semantic_advisory_check as sa
    print('Step 9 part B: go to the object through Nav2 (ATLAS MOVES; remote in hand, B stops it).', flush=True)

    def ros_val(r, k):
        v = (r.get(k) or {}).get('value')
        try:
            return json.loads(v) if isinstance(v, str) and v[:1] in '{[' else v
        except ValueError:
            return v

    def snapshot():
        try:
            r = yb.dash_json('/api/status').get('ros') or {}
        except Exception:
            r = {}
        pose = ros_val(r, 'map_pose')
        pol = ros_val(r, 'control_policy') or {}
        return ({k: float(pose[k]) for k in ('x', 'y', 'yaw')} if isinstance(pose, dict) else None,
                str(ros_val(r, 'mission_status') or ''), pol if isinstance(pol, dict) else {})

    try:
        adv = json.loads(ADVISORY_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        adv = None
    robot, _, pol = snapshot()
    try:                                   # the accepted map, read-only, same check as mission control's map tap
        from atlas_map_acceptance_core import _map_yaml_values, _read_pgm
        from atlas_map_waypoint import check_point
        yaml_path = ROOT / 'maps/atlas_latest.yaml'
        meta = _map_yaml_values(yaml_path)
        image = Path(str(meta.get('image', 'atlas_latest.pgm')))
        pgm = _read_pgm(image if image.is_absolute() else yaml_path.parent / image)
        clear_fn = lambda x, y: check_point(x, y, pgm, meta)
    except Exception as exc:
        clear_fn = None
        print(f'note: map not read ({exc}); keeping the 0.70 m stop point', flush=True)
    target, refused = pick_target(adv, robot, time.time(), clear_fn=clear_fn)
    if target and target.get('standoff_m', 0.7) > 0.7:
        print(f"0.70 m stop point not clear on the map: stepped back to {target['standoff_m']:.1f} m", flush=True)
    if not refused and not (pol.get('autonomy') or {}).get('armed'):
        refused = ['AUTONOMOUS mode is OFF: switch to Autonomous (operator PIN) first']
    if not refused and pol.get('stop_latched'):
        refused = ['E-STOP is latched: release it with the remote first']
    if not refused and not yb.wheel_still():
        refused = ['ATLAS is moving: wait until it is still']
    if not refused:
        try:
            s3 = yb.dash_json('/api/stage3').get('state')
        except Exception:
            s3 = None
        if s3 not in STAGE3_IDLE:
            refused = ['the Stage-3 round trip is running (%s): finish or cancel it first' % s3]
    seen, end, final, rounds, worst, elapsed, stop = set(), None, None, [], 0.0, 0.0, None
    mission_text, t0_wall = None, None
    if refused:
        print('REFUSED: ' + '; '.join(refused), flush=True)
    else:
        gx, gy = target['goal_x'], target['goal_y']
        print(f"target: {target['label']} at map ({target['map_x']:.2f}, {target['map_y']:.2f}); stop point "
              f"({gx:.2f}, {gy:.2f}) {target['goal_dist_m']:.2f} m away", flush=True)
        status_before = snapshot()[1]
        code, resp = post('/api/places', {'action': 'go_at', 'x': gx, 'y': gy})
        print(f'go_at -> HTTP {code}: {resp.get("message")}', flush=True)
        start, t0, sampler, strikes = (robot['x'], robot['y']), time.time(), yb.SystemSampler(), 0
        t0_wall = time.strftime('%Y-%m-%d %H:%M:%S')
        if code != 202:
            refused = ['dashboard refused the goal: %s' % resp.get('message')]
        while not refused:
            time.sleep(POLL_S)
            elapsed = time.time() - t0
            pose, status, pol = snapshot()
            ev = mission_event(status, gx, gy)
            if ev and ev not in seen:
                print(f'{elapsed:5.1f} s  mission: {status}', flush=True)
            if accept_event(ev, seen, status, status_before):
                seen.add(ev)
                if ev == 'failed':
                    mission_text = status
            if pose:
                final = pose
                worst = max(worst, off_course(start, (gx, gy), (pose['x'], pose['y'])))
            stop, strikes = yb.over_limit(sampler.sample(), strikes)
            if pol.get('stop_latched') or not (pol.get('autonomy') or {}).get('armed'):
                end = 'OWNER_STOP'
            elif 'failed' in seen:
                end = 'NAV2_FAILED'
            elif 'succeeded' in seen:
                end = 'ARRIVED'
            elif stop:
                end = 'LIMIT'
            elif worst > OFF_COURSE_M:
                end = 'OFF_COURSE'
            elif elapsed > DRIVE_TIMEOUT_S:
                end = 'TIMEOUT'
            elif not seen and elapsed > DISPATCH_WAIT_S:
                end = 'NOT_DISPATCHED'
            if end:
                break
        if end and end not in ('ARRIVED', 'NAV2_FAILED'):
            code, resp = post('/api/autonomy', {'action': 'abort'})
            print(f'{end}: Abort sent (Manual + cancel goal) -> HTTP {code}: {resp.get("message")}', flush=True)
        if end == 'ARRIVED':
            print(f'arrived after {elapsed:.1f} s; waiting until ATLAS is still', flush=True)
            for _ in range(12):
                if yb.wheel_still():
                    break
                time.sleep(0.25)
            final = snapshot()[0] or final
            try:
                pan, tilt = sa.parse_servo(ros_val(yb.dash_json('/api/status').get('ros') or {}, 'camera_servo_status'))
            except Exception:
                pan, tilt = None, None
            cam_ok = sa.camera_is_forward(pan, tilt, sa.camera_home())
            print(f'camera pan {pan} tilt {tilt} forward {cam_ok}', flush=True)
            det = None                      # bearings assume a straight camera: no confirmation with a turned one
            try:
                if cam_ok:
                    from trt_yolo_detector import TensorRTYOLO
                    det = TensorRTYOLO(str(yb.ENGINE), confidence=sa.MIN_CONF)
            except Exception as exc:
                print(f'engine did not load: {exc}', flush=True)
            for r in range(CONFIRM_ROUNDS if det else 0):
                rgb = yb.camera_rgb()
                try:
                    lv = yb.dash_json('/api/lidar-view')
                except Exception:
                    lv = {}
                pose = snapshot()[0]
                if rgb is None or lv.get('state') != 'LIVE' or not pose:
                    rounds.append([])
                    continue
                dets = [(sa.COCO[c] if c < len(sa.COCO) else str(c), conf, x1, x2)
                        for x1, _, x2, _, c, conf in det.infer(rgb)]
                objs = sa.round_objects(dets, rgb.shape[1], [tuple(p) for p in lv.get('points') or []], pose)
                rounds.append(objs)
                print(f'confirm {r}: {objs}', flush=True)
                time.sleep(0.5)
            if det:
                det.close()
        if end in ('ARRIVED', 'NAV2_FAILED'):
            code, resp = post('/api/autonomy', {'action': 'off'})
            print(f'switched back to Manual -> HTTP {code}: {resp.get("message")}', flush=True)
    blocked = []
    if not refused and end != 'ARRIVED':
        try:
            import subprocess
            out = subprocess.run(['journalctl', '--user', '-u', 'atlas-cmd-vel-mux.service', '--since', t0_wall,
                                  '--no-pager', '-o', 'cat'], capture_output=True, text=True, timeout=10).stdout
            blocked = mux_summary(out.splitlines())
            for b in blocked[:3]:
                print(f"safety mux: {b['reason']} ({b['count']}x)", flush=True)
        except Exception as exc:
            print(f'note: mux log not read ({exc})', flush=True)
    res = evaluate(refused, seen, end, final, target, rounds, worst, elapsed, stop, blocked=blocked,
                   mission_text=mission_text)
    res['when'] = time.strftime('%Y-%m-%d %H:%M')
    out = STATE / f'semantic_goal_{time.strftime("%Y%m%d_%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    try:
        import atlas_master_plan
        atlas_master_plan.record_later(9, res, out.name, part='b')
    except Exception as exc:
        print(f'note: master plan not updated ({exc})')
    print(json.dumps(res, indent=1))
    print(f'STEP 9 PART B: {res["verdict"]}')
    print(f'saved {out}')


if __name__ == '__main__':
    main()

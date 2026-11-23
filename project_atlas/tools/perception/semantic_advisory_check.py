#!/usr/bin/env python3
"""ATLAS master-plan step 9: ADVISORY semantic perception + semantic goal resolution DRY-RUN (read-only, no motion,
no ROS, no Nav2 goal). 2026-11-23.

Plan text: "Add advisory semantic perception, then semantic goal resolution through Nav2 only after recorded
validation." This step is the advisory half and the recorded validation. Sending a semantic goal to Nav2 is NOT part
of it (that would be a later, owner-approved motion step).

With ATLAS PARKED, the camera centred forward and the robot localised, for 10 rounds (~1 per second):
  * the existing TensorRT YOLO (scripts/trt_yolo_detector) runs on a live IMX708 frame (/camera.jpg);
  * each detection of a navigation-relevant class (>= 0.45) gets a bearing from its box (66 deg HFOV, the geometry
    of scripts/atlas_vision_lidar_core) and is CONFIRMED only by LiDAR points in that bearing within 3 m
    (/api/lidar-view, base_link); the point goes to the map frame with the authoritative map pose (map_pose);
  * per label, positions are grouped (0.40 m). An object counts when it is seen in >= 60 % of the rounds and its
    positions stay within 0.25 m (stable).
  * Goal resolution DRY-RUN: for each object a standoff goal 0.70 m short of it on the line of sight (already
    LiDAR-clear), facing it. Goals are written to a file only; nothing is sent to Nav2 or any motion interface.
Stops at once if CPU >= 75 % x3, RAM >= 80 % or 70 C (same limits as step 8).
Verdicts (evaluate): PASS (advisory) / NEEDS SCENE (all OK but no stable object: face ATLAS to a chair, table,
bottle, ... 0.5-3 m away) / FAIL. Writes semantic_check_<time>.json and semantic_advisory.json (the advisory map).
"""
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path('/home/jetson/project_atlas')
HERE = Path(__file__).resolve()
for p in (ROOT / 'scripts', HERE.parents[2] / 'scripts', HERE.parent):
    sys.path.insert(0, str(p))

# geometry and class list of the existing camera/LiDAR fusion (scripts/atlas_vision_lidar_fusion.py)
FORWARD_PAN_US, FORWARD_TILT_US, PAN_TOL_US, TILT_TOL_US = 2300, 1500, 90, 180
HFOV_RAD = math.radians(66.0)
MIN_CONF, MAX_RANGE_M = 0.45, 3.0
NAV_CLASSES = {'person', 'bicycle', 'car', 'motorcycle', 'bus', 'truck', 'bench', 'cat', 'dog', 'backpack',
               'handbag', 'suitcase', 'sports ball', 'skateboard', 'bottle', 'chair', 'couch', 'potted plant', 'bed',
               'dining table', 'toilet', 'tv', 'laptop', 'refrigerator'}
COCO = ['person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat', 'traffic light',
        'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
        'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
        'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
        'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
        'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
        'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone',
        'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear',
        'hair drier', 'toothbrush']
ROUNDS, GROUP_M, MIN_SEEN, MAX_SPREAD_M, STANDOFF_M = 10, 0.40, 0.6, 0.25, 0.70
MAX_POSE_STD_M = 0.10


def pixel_to_bearing(px, width):
    return (0.5 - float(px) / float(width)) * HFOV_RAD


def confirm_with_lidar(points, left, right, max_range=MAX_RANGE_M):
    """Foreground LiDAR point (base_link) inside the bearing sector [right, left]: the 20th-percentile range, as in
    atlas_vision_lidar_core.associate_detection. points: [(x, y)]. None when the sector holds no point."""
    lo, hi = min(left, right), max(left, right)
    cand = [(math.hypot(x, y), x, y) for x, y in points
            if 0.05 < math.hypot(x, y) <= max_range and lo <= math.atan2(y, x) <= hi]
    if not cand:
        return None
    cand.sort()
    target = cand[max(0, min(len(cand) - 1, int(round((len(cand) - 1) * 0.2))))][0]
    _, x, y = min(cand, key=lambda c: abs(c[0] - target))
    return x, y


def to_map(pose, x, y):
    c, s = math.cos(pose['yaw']), math.sin(pose['yaw'])
    return pose['x'] + c * x - s * y, pose['y'] + s * x + c * y


def round_objects(dets, width, points, pose):
    """One round: [(label, conf, map_x, map_y)] for LiDAR-confirmed navigation-class detections. Pure."""
    out = []
    for label, conf, x1, x2 in dets:
        if label not in NAV_CLASSES or conf < MIN_CONF or width <= 0:
            continue
        left, right = pixel_to_bearing(x1, width), pixel_to_bearing(x2, width)
        mid, half = (left + right) / 2, max(abs(left - right) / 2, math.radians(2.0))
        hit = confirm_with_lidar(points, mid + half, mid - half)
        if hit:
            out.append((label, round(conf, 2)) + tuple(round(v, 3) for v in to_map(pose, *hit)))
    return out


def group_objects(rounds, n_rounds):
    """Group per label across rounds (greedy, GROUP_M). Returns objects with seen ratio, mean and spread."""
    groups = []
    for r, objs in enumerate(rounds):
        for label, conf, x, y in objs:
            g = next((g for g in groups if g['label'] == label and math.hypot(g['x'] - x, g['y'] - y) <= GROUP_M), None)
            if g is None:
                g = {'label': label, 'pts': [], 'rounds': set(), 'conf': []}
                groups.append(g)
            g['pts'].append((x, y)); g['rounds'].add(r); g['conf'].append(conf)
            g['x'] = sum(p[0] for p in g['pts']) / len(g['pts'])
            g['y'] = sum(p[1] for p in g['pts']) / len(g['pts'])
    out = []
    for g in groups:
        spread = max(math.hypot(px - g['x'], py - g['y']) for px, py in g['pts'])
        out.append({'label': g['label'], 'map_x': round(g['x'], 2), 'map_y': round(g['y'], 2),
                    'seen': round(len(g['rounds']) / float(max(1, n_rounds)), 2), 'spread_m': round(spread, 3),
                    'confidence': round(sum(g['conf']) / len(g['conf']), 2)})
    return sorted(out, key=lambda o: -o['seen'])


def resolve_goal(robot, obj):
    """Advisory standoff goal STANDOFF_M short of the object on the robot->object line, facing it (map frame).
    The line of sight is LiDAR-clear up to the object (it was confirmed as the foreground return)."""
    dx, dy = obj['map_x'] - robot['x'], obj['map_y'] - robot['y']
    d = math.hypot(dx, dy)
    yaw = math.atan2(dy, dx)
    if d <= STANDOFF_M + 0.15:
        return {'x': round(robot['x'], 2), 'y': round(robot['y'], 2), 'yaw_deg': round(math.degrees(yaw), 1),
                'note': 'already within the standoff: stay and face it'}
    k = (d - STANDOFF_M) / d
    return {'x': round(robot['x'] + k * dx, 2), 'y': round(robot['y'] + k * dy, 2),
            'yaw_deg': round(math.degrees(yaw), 1), 'note': 'standoff %.2f m, facing the object' % STANDOFF_M}


def evaluate(parked, camera_forward, localised, lidar_live, frames, rounds, robot, stop_reason):
    """Pure; unit-tested."""
    objs = group_objects(rounds, frames)
    stable = [o for o in objs if o['seen'] >= MIN_SEEN]
    for o in stable:
        o['advisory_goal'] = resolve_goal(robot, o)
    c = {'parked': bool(parked), 'camera_forward': bool(camera_forward), 'localised': bool(localised),
         'lidar_live': bool(lidar_live), 'yolo_ran': frames >= int(0.8 * ROUNDS),
         'limits_held': stop_reason is None,
         'objects_found': bool(stable),
         'positions_stable': bool(stable) and all(o['spread_m'] <= MAX_SPREAD_M for o in stable),
         'goals_resolved_not_sent': bool(stable) and all('advisory_goal' in o for o in stable)}
    base_ok = all(c[k] for k in ('parked', 'camera_forward', 'localised', 'lidar_live', 'yolo_ran', 'limits_held'))
    if not base_ok:
        verdict = 'FAIL'
    elif not stable:
        verdict = 'NEEDS SCENE'
    elif c['positions_stable']:
        verdict = 'PASS'
    else:
        verdict = 'FAIL'
    failed = [k for k, v in c.items() if not v] if verdict == 'FAIL' else []
    names = ', '.join('%s %.1f m' % (o['label'], math.hypot(o['map_x'] - robot['x'], o['map_y'] - robot['y']))
                      for o in stable) if robot else ''
    detail = {'PASS': 'advisory only: %d stable object(s) (%s); goals resolved and written, none sent' % (
                  len(stable), names),
              'NEEDS SCENE': 'checks OK but no stable object: face ATLAS to a chair, table, bottle, bag... 0.5-3 m '
                             'away, camera centred, then run this again',
              'FAIL': 'semantic check failed: ' + ', '.join(failed)}[verdict]
    return {'verdict': verdict, 'checks': c, 'failed': failed, 'detail': detail,
            'measured': {'frames': frames, 'objects': objs, 'stable_objects': stable, 'robot_map_pose': robot,
                         'stopped_early': stop_reason},
            'notes': ['No goal is sent: this tool has no Nav2, ROS or motion interface.']}


def parse_servo(text):
    """'online via=... cam1_us=1801 cam2_us=1501' -> (pan_us, tilt_us) or (None, None)."""
    vals = {}
    for part in str(text or '').split():
        if '=' in part:
            k, v = part.split('=', 1)
            try:
                vals[k] = int(v)
            except ValueError:
                pass
    return vals.get('cam1_us'), vals.get('cam2_us')


def main():
    import yolo_benchmark as yb
    print('Step 9: advisory semantic perception (no goal is sent). ATLAS does not move; ~15 s.', flush=True)

    def ros_val(r, k):
        v = (r.get(k) or {}).get('value')
        try:
            return json.loads(v) if isinstance(v, str) and v[:1] in '{[' else v
        except ValueError:
            return v
    try:
        ros = yb.dash_json('/api/status').get('ros') or {}
    except Exception:
        ros = {}
    pan, tilt = parse_servo(ros_val(ros, 'camera_servo_status'))
    camera_forward = (pan is not None and tilt is not None and abs(pan - FORWARD_PAN_US) <= PAN_TOL_US
                      and abs(tilt - FORWARD_TILT_US) <= TILT_TOL_US)
    q = ros_val(ros, 'amcl_quality') or {}
    localised = (isinstance(q, dict) and not q.get('uncertain') and q.get('xy_std_m') is not None
                 and float(q['xy_std_m']) <= MAX_POSE_STD_M)
    parked = yb.wheel_still()
    print(f'camera pan {pan} us tilt {tilt} us (forward {FORWARD_PAN_US}/{FORWARD_TILT_US}), localised {localised}, '
          f'parked {parked}', flush=True)
    rounds, frames, stop, lidar_live, robot = [], 0, None, False, None
    if parked and camera_forward and localised:
        try:
            from trt_yolo_detector import TensorRTYOLO
            det = TensorRTYOLO(str(yb.ENGINE), confidence=MIN_CONF)
        except Exception as exc:
            det = None
            print(f'engine did not load: {exc}', flush=True)
        sampler, strikes = yb.SystemSampler(), 0
        for r in range(ROUNDS if det else 0):
            t0 = time.time()
            rgb = yb.camera_rgb()
            try:
                lv = yb.dash_json('/api/lidar-view')
                status = yb.dash_json('/api/status').get('ros') or {}
            except Exception:
                lv, status = {}, {}
            pose = ros_val(status, 'map_pose')
            lidar_live = lv.get('state') == 'LIVE' and lv.get('display_frame') == 'base_link'
            if rgb is None or not lidar_live or not isinstance(pose, dict):
                print(f'round {r}: missing camera / LiDAR / pose', flush=True)
                continue
            robot = {k: float(pose[k]) for k in ('x', 'y', 'yaw')}
            dets = [(COCO[c] if c < len(COCO) else str(c), conf, x1, x2) for x1, _, x2, _, c, conf in det.infer(rgb)]
            frames += 1
            objs = round_objects(dets, rgb.shape[1], [tuple(p) for p in lv.get('points') or []], robot)
            rounds.append(objs)
            print(f'round {r}: YOLO {[(d[0], round(d[1], 2)) for d in dets]} -> confirmed {objs}', flush=True)
            stop, strikes = yb.over_limit(sampler.sample(), strikes)
            if stop:
                print(f'STOP: {stop} limit reached', flush=True)
                break
            time.sleep(max(0.0, 1.0 - (time.time() - t0)))
        if det:
            det.close()
    res = evaluate(parked, camera_forward, localised, lidar_live, frames, rounds, robot, stop)
    res['measured'].update({'pan_us': pan, 'tilt_us': tilt})
    res['when'] = time.strftime('%Y-%m-%d %H:%M')
    state = Path.home() / '.local/state/project_atlas'
    out = state / f'semantic_check_{time.strftime("%Y%m%d_%H%M%S")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    if res['verdict'] == 'PASS':                       # the advisory semantic map (labels + goals), never sent
        (state / 'semantic_advisory.json').write_text(json.dumps(
            {'when': res['when'], 'frame': 'map', 'advisory_only': True, 'objects': res['measured']['stable_objects']},
            indent=1))
    try:
        import atlas_master_plan
        atlas_master_plan.record_later(9, res, out.name)
    except Exception as exc:
        print(f'note: master plan not updated ({exc})')
    print(json.dumps(res, indent=1))
    print(f'STEP 9: {res["verdict"]}')
    print(f'saved {out}')


if __name__ == '__main__':
    main()

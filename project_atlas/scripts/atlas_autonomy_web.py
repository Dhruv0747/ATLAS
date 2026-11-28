"""Dashboard AUTONOMY ON/OFF and waypoints (2026-11-15, owner request). Thin HTTP layer only.

All authority stays where it was: the cmd_vel mux decides ON (atlas_autonomy_arm gates: E-STOP latched, still,
encoder autonomy-ready, speed gate) and mission control runs every navigation check before a waypoint goal.
  GET  /api/autonomy          -> {autonomy, stop_latched, places[], map_id}
  POST /api/autonomy          {action: on|off|abort, pin}   ON needs the operator PIN (same store/lockout as E-STOP reset)
                              abort (2026-11-16): switch to Manual (mux disarm) AND cancel the Nav2 goal; never refused
  POST /api/places            {action: save|save_at|go|go_at|delete, name[, x, y]}  *_at = map tap (map frame)
"Go" is refused here unless autonomy is ON and the E-STOP is released, so a queued goal can never start by itself
when someone later releases the stop.
"""
import json
import time
from pathlib import Path

import atlas_wifi_web

PLACES_FILE = Path.home() / '.config/project_atlas/named_places.json'
POLICY_MAX_AGE_S = 1.5


def clean_name(value):
    name = ' '.join(str(value or '').strip().lower().split())
    if not name or len(name) > 24 or not all(c.isalnum() or c in ' _-' for c in name):
        raise ValueError('name: 1-24 letters, digits, space, _ or -')
    return name


def policy(ros):
    item = ros._item('control_policy')
    if not item or time.time() - float(item.get('ts', 0.0)) > POLICY_MAX_AGE_S:
        return None
    try:
        return json.loads(item['value'])
    except (TypeError, ValueError, KeyError):
        return None


MAP_YAML = Path('/home/jetson/project_atlas/maps/atlas_latest.yaml')
_MAP_CACHE = {'key': None, 'id': None}


def accepted_map_id():
    """Same identity mission control checks (map_pair_id of the accepted YAML + image); cached by mtime."""
    try:
        image = MAP_YAML.with_suffix('.pgm')
        for line in MAP_YAML.read_text(encoding='utf-8').splitlines():
            if line.strip().startswith('image:'):
                name = line.split(':', 1)[1].strip().strip('\'"')
                image = Path(name) if Path(name).is_absolute() else MAP_YAML.parent / name
                break
        key = (MAP_YAML.stat().st_mtime_ns, image.stat().st_mtime_ns)
        if key != _MAP_CACHE['key']:
            from atlas_map_acceptance_core import map_pair_id
            _MAP_CACHE.update(key=key, id=map_pair_id(MAP_YAML, image))
        return _MAP_CACHE['id']
    except (OSError, ImportError, ValueError):
        return None


def places():
    try:
        data = json.loads(PLACES_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return [], None
    map_id = accepted_map_id()
    out = []
    for name, p in (data.items() if isinstance(data, dict) else []):
        if isinstance(p, dict) and p.get('frame_id') == 'map':
            out.append({'name': name, 'x': round(float(p.get('x', 0.0)), 2), 'y': round(float(p.get('y', 0.0)), 2),
                        'current_map': map_id is None or p.get('map_id') == map_id})
    return sorted(out, key=lambda p: p['name']), map_id


def go_refusal(ros):
    """None when a goal may be sent: fresh mux state, autonomy ON, E-STOP released."""
    pol = policy(ros)
    if pol is None:
        return 'no fresh mux state'
    if not ((pol.get('autonomy') or {}).get('armed')):
        return 'AUTONOMOUS mode is OFF (switch to Autonomous first)'
    if pol.get('stop_latched'):
        return 'E-STOP is latched; release it with the remote first'
    return None


def state(ros):
    pol = policy(ros)
    plist, map_id = places()
    return {'autonomy': (pol or {}).get('autonomy'), 'stop_latched': None if pol is None else pol.get('stop_latched'),
            'source': (pol or {}).get('source'), 'policy_fresh': pol is not None, 'places': plist, 'map_id': map_id}


def call_trigger(client, timeout_s=2.0):
    if client is None or not client.service_is_ready():
        return False, 'mux service unavailable'
    from std_srvs.srv import Trigger
    future = client.call_async(Trigger.Request())
    end = time.monotonic() + timeout_s
    while not future.done() and time.monotonic() < end:
        time.sleep(0.02)
    if not future.done():
        future.cancel()
        return False, 'mux did not answer'
    r = future.result()
    return bool(r.success), str(r.message)


def publish(pub, text):
    if pub is None:
        return False
    from std_msgs.msg import String
    pub.publish(String(data=text))
    return True


def read_json(handler):
    length = int(handler.headers.get('Content-Length', '0'))
    if not 0 < length <= 1024 or handler.headers.get_content_type() != 'application/json':
        raise ValueError('invalid request')
    payload = json.loads(handler.rfile.read(length))
    if not isinstance(payload, dict):
        raise ValueError('invalid request')
    return payload


def json_response(handler, code, payload):
    body = json.dumps(payload, allow_nan=False).encode()
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


# 2026-11-28 home "Next step" + "Why isn't ATLAS moving?" (read-only; atlas_why_core decides nothing).
_NEXT = {'t': 0.0, 'v': None}


def _age_value(ros, key):
    item = ros._item(key)
    if not item:
        return None, None
    return item.get('value'), max(0.0, time.time() - float(item.get('ts', 0.0)))


def why_payload(ros, clock=time.time):
    import atlas_why_core
    pol, pol_age = _age_value(ros, 'control_policy')
    try:
        pol = json.loads(pol) if isinstance(pol, str) else pol
    except ValueError:
        pol = None
    safety, safety_age = _age_value(ros, 'motion_safety')
    mission, mission_age = _age_value(ros, 'mission_status')
    out = {'why': atlas_why_core.explain(pol, pol_age, safety, safety_age, mission, mission_age)}
    if clock() - _NEXT['t'] > 5.0:                      # the board reads files: refresh at most every 5 s
        try:
            import atlas_master_plan
            _NEXT['v'] = atlas_master_plan.evaluate().get('next_step')
        except Exception:
            _NEXT['v'] = None
        _NEXT['t'] = clock()
    out['next'] = _NEXT['v']
    return out


def serve(handler, ros, post=False):
    if serve_readiness(handler, ros, post):
        return True
    path = handler.path.split('?')[0]
    if path == '/api/why' and not post:
        json_response(handler, 200, why_payload(ros))
        return True
    if path not in ('/api/autonomy', '/api/places'):
        return False
    if not post:
        if path == '/api/autonomy':
            json_response(handler, 200, state(ros))
        else:
            json_response(handler, 200, {'places': places()[0]})
        return True
    if not atlas_wifi_web.same_origin(handler.headers):
        handler.send_error(403)
        return True
    try:
        payload = read_json(handler)
    except (ValueError, TypeError):
        json_response(handler, 400, {'ok': False, 'message': 'invalid request'})
        return True
    action = payload.get('action')
    clients = getattr(ros, 'autonomy_clients', {}) or {}
    pubs = getattr(ros, 'place_pubs', {}) or {}
    if path == '/api/autonomy':
        if action == 'abort':                                  # Abort mission: never refused, needs no PIN
            ok, msg = call_trigger(clients.get('disarm'))      # Manual first: the mux blocks every Nav2 command at once
            cancelled = False
            pub = getattr(ros, 'cancel_nav_pub', None)
            if pub is not None:
                from std_msgs.msg import Empty
                pub.publish(Empty()); cancelled = True        # mission control: zero Twist + cancel all Nav2 goals
            ros.estop_log.write('mission_abort', client=handler.client_address[0], disarm_ok=ok, cancel_sent=cancelled)
            text = ('MISSION ABORTED: Manual mode' if ok else 'Manual switch FAILED (' + str(msg) + ')') + \
                   ('; Nav2 goal cancel sent' if cancelled else '; goal cancel unavailable')
            json_response(handler, 200 if ok else 503, {'ok': ok, 'message': text})
            return True
        if action == 'off':                                    # OFF is never refused
            ok, msg = call_trigger(clients.get('disarm'))
            ros.estop_log.write('autonomy_off', client=handler.client_address[0], ok=ok, message=msg)
            json_response(handler, 200 if ok else 503, {'ok': ok, 'message': msg})
            return True
        if action != 'on':
            json_response(handler, 400, {'ok': False, 'message': 'unknown action'})
            return True
        if ros.reset_lockout.remaining() > 0:
            json_response(handler, 429, {'ok': False, 'message': f'too many wrong PINs; wait {int(ros.reset_lockout.remaining())} s'})
            return True
        if not ros.reset_pins.verify(str(payload.get('pin', ''))):
            ros.reset_lockout.fail()
            ros.estop_log.write('autonomy_on_denied_pin', client=handler.client_address[0])
            json_response(handler, 403, {'ok': False, 'message': 'AUTONOMY ON refused: wrong operator PIN'})
            return True
        ros.reset_lockout.success()
        ok, msg = call_trigger(clients.get('arm'))
        ros.estop_log.write('autonomy_on', client=handler.client_address[0], ok=ok, message=msg)
        json_response(handler, 200 if ok else 409, {'ok': ok, 'message': msg})
        return True
    # /api/places
    if action == 'go_at':                                   # map tap "Move here" (no saved place)
        why = go_refusal(ros)
        if why:
            json_response(handler, 409, {'ok': False, 'message': 'MOVE refused: ' + why})
            return True
        try:
            x, y = float(payload.get('x')), float(payload.get('y'))
            if not (abs(x) < 1000 and abs(y) < 1000):
                raise ValueError
        except (TypeError, ValueError):
            json_response(handler, 400, {'ok': False, 'message': 'invalid map point'})
            return True
        ok = publish(pubs.get('go_at'), json.dumps({'x': x, 'y': y}))
        ros.estop_log.write('map_point_go', client=handler.client_address[0], x=x, y=y, ok=ok)
        json_response(handler, 202 if ok else 503, {'ok': ok, 'message': (
            f'moving to {x:.2f}, {y:.2f} (mission control checks the spot, localization, camera and safety first)'
            if ok else 'ROS link not ready')})
        return True
    try:
        name = clean_name(payload.get('name'))
    except ValueError as exc:
        json_response(handler, 400, {'ok': False, 'message': str(exc)})
        return True
    if action == 'save_at':
        try:
            x, y = float(payload.get('x')), float(payload.get('y'))
            if not (abs(x) < 1000 and abs(y) < 1000):
                raise ValueError
        except (TypeError, ValueError):
            json_response(handler, 400, {'ok': False, 'message': 'invalid map point'})
            return True
        ok = publish(pubs.get('save_at'), json.dumps({'name': name, 'x': x, 'y': y}))
        json_response(handler, 202 if ok else 503, {'ok': ok, 'message': (
            f'saving waypoint "{name}" at {x:.2f}, {y:.2f} (refused by mission control if not free or too close to a wall)'
            if ok else 'ROS link not ready')})
        return True
    if action == 'save':
        ok = publish(pubs.get('save'), name)
        json_response(handler, 202 if ok else 503, {'ok': ok, 'message': f'saving waypoint "{name}" at the current position' if ok else 'ROS link not ready'})
    elif action == 'delete':
        ok = publish(pubs.get('delete'), name)
        json_response(handler, 202 if ok else 503, {'ok': ok, 'message': f'deleting waypoint "{name}"' if ok else 'ROS link not ready'})
    elif action == 'go':
        why = go_refusal(ros)
        if why:
            json_response(handler, 409, {'ok': False, 'message': 'GO refused: ' + why})
            return True
        ok = publish(pubs.get('go'), name)
        ros.estop_log.write('waypoint_go', client=handler.client_address[0], name=name, ok=ok)
        json_response(handler, 202 if ok else 503, {'ok': ok, 'message': f'going to "{name}" (mission control checks localization, camera and safety first)' if ok else 'ROS link not ready'})
    else:
        json_response(handler, 400, {'ok': False, 'message': 'unknown action'})
    return True


# ---------------------------------------------------------------------------------------------------------------
# 2026-11-15 Autonomy readiness (owner: self-service — show why, how to fix, open the test, unlock on PASS).
# GET  /api/readiness              -> atlas_readiness.checklist(...) + speed evidence
# POST /api/readiness/bridge       -> start atlas-astra-bridge-starter (it re-checks parked + CPU itself)
# POST /api/readiness/speedcheck   {speed: 0.10|0.15, pin} -> run tools/drive/speed_loop_ground_check.py (one at a time)
# GET  /api/readiness/speedcheck   -> {running, log, result}
# ---------------------------------------------------------------------------------------------------------------
import os
import subprocess
import threading

STATE_DIR = Path.home() / '.local/state/project_atlas'
LOC_FILE = STATE_DIR / 'localization_check.json'
GROUND_CHECK = Path('/home/jetson/project_atlas/tools/drive/speed_loop_ground_check.py')
SPEEDCHECK_LOG = STATE_DIR / 'speedcheck_dashboard.log'
SPEEDS = (0.10, 0.15)
_RUN = {'proc': None, 'speed': None, 'started': None, 'lock': threading.Lock()}
_LAST_VERIFIED = {'unix': None}       # last LiDAR VERIFIED seen (written_unix), for the AMCL-estimate path


def _item_age(ros, key):
    item = ros._item(key)
    return (item, None) if not item else (item, max(0.0, time.time() - float(item.get('ts', 0.0))))


def speedcheck_running():
    p = _RUN['proc']
    return p is not None and p.poll() is None


# 2026-11-23 Stage-2 gentle turn check (master-plan entry gate stage 2), same owner gates as the Speed check.
TURN_CHECK = Path('/home/jetson/project_atlas/tools/drive/turn_ground_check.py')
TURNCHECK_LOG = STATE_DIR / 'turncheck_dashboard.log'
_TURN = {'proc': None, 'started': None}


def turncheck_running():
    p = _TURN['proc']
    return p is not None and p.poll() is None


def _latest_turn_results(n=4, prefix='turn_check_'):
    out = []
    for f in sorted(STATE_DIR.glob(prefix + '*.json'))[-n:]:
        try:
            r = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        out.append({'file': f.name, 'when': r.get('when'), 'verdict': r.get('verdict'), 'detail': r.get('detail'),
                    'failed': r.get('failed', []), 'checks': r.get('checks', {}),
                    'arcs': [{k: a.get(k) for k in ('direction', 'end_reason', 'imu_yaw_deg', 'icp_yaw_deg',
                                                     'wheel_distance_m', 'peak_mps', 'settle_s', 'checks', 'verdict')}
                             for a in r.get('arcs', [])],
                    'workload': (r.get('workload') or {}).get('measured')})
    return out


# 2026-11-23 Stage-4 part A: parked IM10A/EKF/TF check. Read-only (publishes nothing), so no PIN; locked until the
# entry gate (stages 1-3) has passed.
IMU_CHECK = Path('/home/jetson/project_atlas/tools/localization/imu_ekf_tf_parked_check.py')
IMUCHECK_LOG = STATE_DIR / 'imucheck_dashboard.log'
_IMU = {'proc': None, 'started': None}


def imucheck_running():
    p = _IMU['proc']
    return p is not None and p.poll() is None


def imucheck_status():
    try:
        log = IMUCHECK_LOG.read_text(encoding='utf-8', errors='replace')[-4000:]
    except OSError:
        log = ''
    results = []
    for f in sorted(STATE_DIR.glob('imu_check_*.json'))[-4:]:
        try:
            r = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        results.append({'file': f.name, 'when': r.get('when'), 'verdict': r.get('verdict'), 'detail': r.get('detail'),
                        'checks': r.get('checks', {}), 'measured': r.get('measured', {}), 'failed': r.get('failed', [])})
    return {'running': imucheck_running(), 'started': _IMU['started'], 'log': log,
            'tool_installed': IMU_CHECK.is_file(), 'results': results}


def start_imucheck(ros):
    if not IMU_CHECK.is_file():
        return 409, 'IMU check tool is not installed on the rover yet'
    import atlas_master_plan
    if not atlas_master_plan.evaluate().get('gate_open'):
        return 409, 'Stage 4 is locked: pass stages 1, 2 and 3 first'
    pol = policy(ros)
    if pol is None:
        return 409, 'no fresh mux state'
    if ((pol.get('autonomy') or {}).get('armed')):
        return 409, 'switch to Manual mode first (ATLAS must stay parked)'
    with _RUN['lock']:
        if speedcheck_running() or turncheck_running() or imucheck_running() or stepcheck_running() or semgo_running():
            return 409, 'another check is already running'
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        log = open(IMUCHECK_LOG, 'w', encoding='utf-8')
        cmd = ('source /opt/ros/humble/setup.bash; source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null; '
               f'cd {IMU_CHECK.parent}; exec python3 -u {IMU_CHECK.name} --duration 60')
        _IMU['proc'] = subprocess.Popen(['bash', '-lc', cmd], stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, start_new_session=True,
                                        env=dict(os.environ, PYTHONUNBUFFERED='1'))
        _IMU['started'] = time.time()
    ros.estop_log.write('imucheck_start')
    return 202, 'parked IMU/EKF/TF check started: 60 s. Do not touch ATLAS or the remote.'


# 2026-11-23 later master-plan steps with read-only owner tests (no motion, no PIN). Locked until the board unlocks them.
STEP_CHECKS = {
    5: (Path('/home/jetson/project_atlas/tools/nav/nav2_recovery_audit.py'), 'nav2_audit_'),
    6: (Path('/home/jetson/project_atlas/tools/drive/wheel_pid_evaluation.py'), 'pid_eval_'),
    7: (Path('/home/jetson/project_atlas/tools/perception/vo_shadow_check.py'), 'vo_shadow_check_'),
    8: (Path('/home/jetson/project_atlas/tools/perception/yolo_benchmark.py'), 'yolo_bench_'),
    9: (Path('/home/jetson/project_atlas/tools/perception/semantic_advisory_check.py'), 'semantic_check_'),
}
_STEP = {'proc': None, 'n': None, 'started': None}


def stepcheck_running():
    p = _STEP['proc']
    return p is not None and p.poll() is None


def stepcheck_status(n):
    log_file = STATE_DIR / ('stepcheck_%s_dashboard.log' % n)
    try:
        log = log_file.read_text(encoding='utf-8', errors='replace')[-4000:]
    except OSError:
        log = ''
    tool, prefix = STEP_CHECKS.get(n, (None, None))
    results = []
    if prefix:
        for f in sorted(STATE_DIR.glob(prefix + '*.json'))[-4:]:
            try:
                r = json.loads(f.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            results.append({'file': f.name, 'when': r.get('when'), 'verdict': r.get('verdict'), 'detail': r.get('detail'),
                            'checks': r.get('checks', {}), 'measured': r.get('measured', {}),
                            'failed': r.get('failed', []), 'notes': r.get('notes', []) or r.get('blockers', [])})
    return {'n': n, 'running': stepcheck_running() and _STEP['n'] == n, 'busy': stepcheck_running(),
            'log': log if _STEP['n'] == n else '', 'tool_installed': bool(tool and tool.is_file()), 'results': results}


def start_stepcheck(ros, n):
    if n not in STEP_CHECKS:
        return 400, 'no owner test for this step'
    tool, _ = STEP_CHECKS[n]
    if not tool.is_file():
        return 409, 'step %d tool is not installed on the rover yet' % n
    import atlas_master_plan
    step = next((l for l in atlas_master_plan.evaluate().get('later', []) if l.get('n') == n), None)
    if not step or step.get('status') == 'LOCKED':
        return 409, 'Step %d is locked: finish %s first' % (n, (step or {}).get('unlock_after', 'the step before'))
    with _RUN['lock']:
        if speedcheck_running() or turncheck_running() or imucheck_running() or stepcheck_running() or semgo_running():
            return 409, 'another check is already running'
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        log = open(STATE_DIR / ('stepcheck_%s_dashboard.log' % n), 'w', encoding='utf-8')
        cmd = (f'cd {tool.parent}; exec /usr/bin/python3 -u {tool.name}')
        _STEP['proc'] = subprocess.Popen(['bash', '-lc', cmd], stdout=log, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, start_new_session=True,
                                         env=dict(os.environ, PYTHONUNBUFFERED='1'))
        _STEP['n'], _STEP['started'] = n, time.time()
    ros.estop_log.write('stepcheck_start', step=n)
    return 202, 'step %d check started (read-only; ATLAS does not move)' % n


# 2026-11-26 step 9 PART B: go to the object through Nav2 (owner-triggered, bounded; ATLAS MOVES). Same authority as
# the Stage-3 runner and the map-tap "Move here": the tool sends ONE go_at through /api/places (refused unless
# AUTONOMOUS is ON and the E-STOP is released), never arms autonomy, never releases the E-STOP, never sends velocity.
SEMANTIC_GO = Path('/home/jetson/project_atlas/tools/perception/semantic_goal_check.py')
SEMGO_LOG = STATE_DIR / 'semantic_goal_dashboard.log'
_SGO = {'proc': None, 'started': None}


def semgo_running():
    p = _SGO['proc']
    return p is not None and p.poll() is None


def semgo_status():
    try:
        log = SEMGO_LOG.read_text(encoding='utf-8', errors='replace')[-4000:]
    except OSError:
        log = ''
    results = []
    for f in sorted(STATE_DIR.glob('semantic_goal_*.json'))[-4:]:
        try:
            r = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        results.append({'file': f.name, 'when': r.get('when'), 'verdict': r.get('verdict'), 'detail': r.get('detail'),
                        'checks': r.get('checks', {}), 'measured': r.get('measured', {}),
                        'failed': r.get('failed', []), 'notes': r.get('notes', [])})
    return {'running': semgo_running(), 'started': _SGO['started'], 'log': log,
            'tool_installed': SEMANTIC_GO.is_file(), 'results': results}


def start_semanticgo(ros):
    if not SEMANTIC_GO.is_file():
        return 409, 'step 9 part B tool is not installed on the rover yet'
    import atlas_master_plan
    step = next((l for l in atlas_master_plan.evaluate().get('later', []) if l.get('n') == 9), None)
    if not step or not step.get('part_a_done'):
        return 409, 'Part B is locked: pass step 9 part A (START CHECK above) first'
    why = go_refusal(ros)
    if why:
        return 409, 'GO TO OBJECT refused: ' + why
    with _RUN['lock']:
        if speedcheck_running() or turncheck_running() or imucheck_running() or stepcheck_running() or semgo_running():
            return 409, 'another check is already running'
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        log = open(SEMGO_LOG, 'w', encoding='utf-8')
        cmd = f'cd {SEMANTIC_GO.parent}; exec /usr/bin/python3 -u {SEMANTIC_GO.name}'
        _SGO['proc'] = subprocess.Popen(['bash', '-lc', cmd], stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, start_new_session=True,
                                        env=dict(os.environ, PYTHONUNBUFFERED='1'))
        _SGO['started'] = time.time()
    ros.estop_log.write('semantic_go_start')
    return 202, ('go to object started: ATLAS drives through Nav2 to the stop point in front of the object and stops. '
                 'B on the remote stops it; Abort mission cancels it.')


def turncheck_status():
    try:
        log = TURNCHECK_LOG.read_text(encoding='utf-8', errors='replace')[-4000:]
    except OSError:
        log = ''
    return {'running': turncheck_running(), 'started': _TURN['started'], 'log': log,
            'tool_installed': TURN_CHECK.is_file(), 'results': _latest_turn_results(),
            'workload_results': _latest_turn_results(prefix='imu_workload_check_'), 'workload': _TURN.get('workload')}


def _latest_speed_results(n=4):
    out = []
    for f in sorted(STATE_DIR.glob('speed_loop_check_*.json'))[-n:]:
        try:
            r = json.loads(f.read_text(encoding='utf-8'))
            out.append({'file': f.name, 'target_mps': r.get('target_mps'), 'requested_mps': r.get('requested_mps'),
                        'verdict': r.get('verdict'),
                        'steady_mean_mps': r.get('steady_mean_mps'), 'peak_mps': r.get('peak_mps'),
                        'end_reason': r.get('end_reason'),
                        'failed_checks': [k for k, v in (r.get('checks') or {}).items() if not v]})
        except (OSError, ValueError):
            continue
    return out


def readiness(ros):
    import atlas_autonomy_arm as arm
    import atlas_readiness
    pol = policy(ros)
    enc_item, enc_age = _item_age(ros, 'encoder_health')
    try:
        enc = json.loads(enc_item['value']) if enc_item else {}
    except (TypeError, ValueError):
        enc = {}
    _, astra_age = _item_age(ros, 'astra_nav2')
    try:
        loc = json.loads(LOC_FILE.read_text(encoding='utf-8'))
        loc_age = time.time() - float(loc.get('written_unix', 0))
        if loc.get('state') == 'VERIFIED':
            _LAST_VERIFIED['unix'] = max(_LAST_VERIFIED['unix'] or 0.0, float(loc.get('written_unix', 0)))
    except (OSError, ValueError, TypeError):
        loc, loc_age = None, None
    amcl_item, amcl_age = _item_age(ros, 'amcl_quality')
    last_ver_age = None if _LAST_VERIFIED['unix'] is None else time.time() - _LAST_VERIFIED['unix']
    try:
        bridge = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'atlas-astra-bridge.service'],
                                timeout=3).returncode == 0
    except Exception:
        bridge = False
    ev = arm.speed_evidence()
    gate = arm.read_gate(evidence=ev)
    plist = [p for p in places()[0] if p['current_map']]
    out = atlas_readiness.checklist(pol, enc, enc_age, loc, loc_age, astra_age, bridge, ev, gate, len(plist),
                                    speedcheck_running(), amcl=(amcl_item or {}).get('value'), amcl_age_s=amcl_age,
                                    last_verified_age_s=last_ver_age)
    out['speed'] = {'enabled': ev.get('enabled'), 'passed': ev.get('passed'), 'missing': ev.get('missing'),
                    'passes_needed': ev.get('passes_needed'),
                    'tool_installed': GROUND_CHECK.is_file(), 'results': _latest_speed_results()}
    out['mode'] = 'AUTONOMOUS' if ((pol or {}).get('autonomy') or {}).get('armed') else 'MANUAL'
    return out


def speedcheck_status():
    try:
        log = SPEEDCHECK_LOG.read_text(encoding='utf-8', errors='replace')[-4000:]
    except OSError:
        log = ''
    return {'running': speedcheck_running(), 'speed': _RUN['speed'], 'started': _RUN['started'], 'log': log,
            'results': _latest_speed_results()}


def start_speedcheck(ros, speed, pin):
    """Owner-triggered from the dashboard. Refused unless every precondition holds; the tool itself enforces its
    own bounds (<= 1 m, <= 15 s, LiDAR clearance, runaway cut) and the remote/E-STOP pre-empt it at any time."""
    if speed not in SPEEDS:
        return 400, 'speed must be 0.10 or 0.15'
    if not GROUND_CHECK.is_file():
        return 409, 'speed check tool is not installed on the rover yet'
    if ros.reset_lockout.remaining() > 0:
        return 429, f'too many wrong PINs; wait {int(ros.reset_lockout.remaining())} s'
    if not ros.reset_pins.verify(str(pin or '')):
        ros.reset_lockout.fail()
        return 403, 'wrong operator PIN'
    ros.reset_lockout.success()
    pol = policy(ros)
    if pol is None:
        return 409, 'no fresh mux state'
    if ((pol.get('autonomy') or {}).get('armed')):
        return 409, 'switch to Manual mode first'
    if pol.get('stop_latched'):
        return 409, 'release the E-STOP with the remote first (sticks centred); keep the remote in hand'
    import atlas_autonomy_arm as arm
    if not arm.speed_evidence().get('enabled'):
        return 409, 'speed loop is not enabled on this rover'
    with _RUN['lock']:
        if speedcheck_running() or turncheck_running() or imucheck_running() or stepcheck_running() or semgo_running():
            return 409, 'another check is already running'
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        log = open(SPEEDCHECK_LOG, 'w', encoding='utf-8')
        cmd = ('source /opt/ros/humble/setup.bash; source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null; '
               f'cd {GROUND_CHECK.parent}; exec python3 -u {GROUND_CHECK.name} --speed {speed:.2f} --distance 0.6 --timeout 12')
        _RUN['proc'] = subprocess.Popen(['bash', '-lc', cmd], stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, start_new_session=True,
                                        env=dict(os.environ, PYTHONUNBUFFERED='1'))
        _RUN['speed'], _RUN['started'] = speed, time.time()
    ros.estop_log.write('speedcheck_start', speed=speed)
    return 202, (f'speed check started (requested {speed:.2f} m/s; the rover gets the mux-scaled speed): it moves '
                 '~0.6 m forward slowly and stops. B on the remote stops it.')


def start_turncheck(ros, pin, workload=False):
    """Owner-triggered from the Stage-2 page. Same refusals as the Speed check, plus: Stage 1 (bounded straight
    run) must have passed first. The tool bounds itself (two ~25 deg arcs, <= 0.6 m, <= 12 s each, swept-path LiDAR
    stop) and the mux clamps COMMISSION to 0.12 m/s / 0.15 rad/s; the remote and E-STOP pre-empt it at any time."""
    if not TURN_CHECK.is_file():
        return 409, 'turn check tool is not installed on the rover yet'
    import atlas_master_plan
    if not atlas_master_plan.stage1_evidence():
        return 409, 'Stage 2 is locked: pass Stage 1 (Speed check straight run) first'
    if workload and not atlas_master_plan.evaluate().get('gate_open'):
        return 409, 'Stage 4 is locked: pass stages 1, 2 and 3 first'
    if ros.reset_lockout.remaining() > 0:
        return 429, f'too many wrong PINs; wait {int(ros.reset_lockout.remaining())} s'
    if not ros.reset_pins.verify(str(pin or '')):
        ros.reset_lockout.fail()
        return 403, 'wrong operator PIN'
    ros.reset_lockout.success()
    pol = policy(ros)
    if pol is None:
        return 409, 'no fresh mux state'
    if ((pol.get('autonomy') or {}).get('armed')):
        return 409, 'switch to Manual mode first'
    if pol.get('stop_latched'):
        return 409, 'release the E-STOP with the remote first (sticks centred); keep the remote in hand'
    import atlas_autonomy_arm as arm
    if not arm.speed_evidence().get('enabled'):
        return 409, 'speed loop is not enabled on this rover'
    with _RUN['lock']:
        if speedcheck_running() or turncheck_running() or imucheck_running() or stepcheck_running() or semgo_running():
            return 409, 'another check is already running'
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        log = open(TURNCHECK_LOG, 'w', encoding='utf-8')
        cmd = ('source /opt/ros/humble/setup.bash; source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null; '
               f'cd {TURN_CHECK.parent}; exec python3 -u {TURN_CHECK.name} --yaw 25' + (' --workload' if workload else ''))
        _TURN['proc'] = subprocess.Popen(['bash', '-lc', cmd], stdout=log, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, start_new_session=True,
                                         env=dict(os.environ, PYTHONUNBUFFERED='1'))
        _TURN['started'], _TURN['workload'] = time.time(), bool(workload)
    ros.estop_log.write('turncheck_start', workload=bool(workload))
    return 202, ('turn check started: ATLAS curves gently LEFT ~25 deg, stops, then RIGHT ~25 deg, and stops. '
                 'B on the remote stops it.')


def serve_readiness(handler, ros, post=False):
    path = handler.path.split('?')[0]
    if path not in ('/api/readiness', '/api/readiness/bridge', '/api/readiness/speedcheck',
                    '/api/readiness/turncheck', '/api/readiness/imucheck', '/api/readiness/stepcheck',
                    '/api/readiness/semanticgo'):
        return False
    if not post:
        if path == '/api/readiness':
            json_response(handler, 200, readiness(ros))
        elif path == '/api/readiness/speedcheck':
            json_response(handler, 200, speedcheck_status())
        elif path == '/api/readiness/turncheck':
            json_response(handler, 200, turncheck_status())
        elif path == '/api/readiness/imucheck':
            json_response(handler, 200, imucheck_status())
        elif path == '/api/readiness/semanticgo':
            json_response(handler, 200, semgo_status())
        elif path == '/api/readiness/stepcheck':
            from urllib.parse import parse_qs, urlsplit
            try:
                n = int((parse_qs(urlsplit(handler.path).query).get('n') or ['0'])[0])
            except ValueError:
                n = 0
            json_response(handler, 200, stepcheck_status(n))
        else:
            handler.send_error(405)
        return True
    if not atlas_wifi_web.same_origin(handler.headers):
        handler.send_error(403)
        return True
    try:
        payload = read_json(handler)
    except (ValueError, TypeError):
        json_response(handler, 400, {'ok': False, 'message': 'invalid request'})
        return True
    if path == '/api/readiness/bridge':
        try:
            r = subprocess.run(['systemctl', '--user', 'start', '--no-block', 'atlas-astra-bridge-starter.service'],
                               timeout=5, capture_output=True, text=True)
            ok = r.returncode == 0
        except Exception:
            ok = False
        json_response(handler, 202 if ok else 503, {'ok': ok, 'message': (
            'camera bridge starter launched: it starts the bridge only while the rover is parked; wait ~20 s'
            if ok else 'could not launch the camera bridge starter')})
        return True
    if path == '/api/readiness/speedcheck':
        try:
            speed = round(float(payload.get('speed')), 2)
        except (TypeError, ValueError):
            speed = None
        code, msg = start_speedcheck(ros, speed, payload.get('pin'))
        json_response(handler, code, {'ok': code == 202, 'message': msg})
        return True
    if path == '/api/readiness/stepcheck':
        try:
            n = int(payload.get('n'))
        except (TypeError, ValueError):
            n = 0
        code, msg = start_stepcheck(ros, n)
        json_response(handler, code, {'ok': code == 202, 'message': msg})
        return True
    if path == '/api/readiness/semanticgo':
        code, msg = start_semanticgo(ros)
        json_response(handler, code, {'ok': code == 202, 'message': msg})
        return True
    if path == '/api/readiness/imucheck':
        code, msg = start_imucheck(ros)
        json_response(handler, code, {'ok': code == 202, 'message': msg})
        return True
    if path == '/api/readiness/turncheck':
        code, msg = start_turncheck(ros, payload.get('pin'), workload=payload.get('workload') is True)
        json_response(handler, code, {'ok': code == 202, 'message': msg})
        return True
    return False

"""Dashboard AUTONOMY ON/OFF and waypoints (2026-11-15, owner request). Thin HTTP layer only.

All authority stays where it was: the cmd_vel mux decides ON (atlas_autonomy_arm gates: E-STOP latched, still,
encoder autonomy-ready, speed gate) and mission control runs every navigation check before a waypoint goal.
  GET  /api/autonomy          -> {autonomy, stop_latched, places[], map_id}
  POST /api/autonomy          {action: on|off, pin}   ON needs the operator PIN (same store/lockout as E-STOP reset)
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


def serve(handler, ros, post=False):
    if serve_readiness(handler, ros, post):
        return True
    path = handler.path.split('?')[0]
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


def _item_age(ros, key):
    item = ros._item(key)
    return (item, None) if not item else (item, max(0.0, time.time() - float(item.get('ts', 0.0))))


def speedcheck_running():
    p = _RUN['proc']
    return p is not None and p.poll() is None


def _latest_speed_results(n=4):
    out = []
    for f in sorted(STATE_DIR.glob('speed_loop_check_*.json'))[-n:]:
        try:
            r = json.loads(f.read_text(encoding='utf-8'))
            out.append({'file': f.name, 'target_mps': r.get('target_mps'), 'verdict': r.get('verdict'),
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
    except (OSError, ValueError, TypeError):
        loc, loc_age = None, None
    try:
        bridge = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'atlas-astra-bridge.service'],
                                timeout=3).returncode == 0
    except Exception:
        bridge = False
    ev = arm.speed_evidence()
    gate = arm.read_gate(evidence=ev)
    plist = [p for p in places()[0] if p['current_map']]
    out = atlas_readiness.checklist(pol, enc, enc_age, loc, loc_age, astra_age, bridge, ev, gate, len(plist),
                                    speedcheck_running())
    out['speed'] = {'enabled': ev.get('enabled'), 'passed': ev.get('passed'), 'missing': ev.get('missing'),
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
        if speedcheck_running():
            return 409, 'a speed check is already running'
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        log = open(SPEEDCHECK_LOG, 'w', encoding='utf-8')
        cmd = ('source /opt/ros/humble/setup.bash; source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null; '
               f'cd {GROUND_CHECK.parent}; exec python3 -u {GROUND_CHECK.name} --speed {speed:.2f} --distance 0.6 --timeout 12')
        _RUN['proc'] = subprocess.Popen(['bash', '-lc', cmd], stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, start_new_session=True,
                                        env=dict(os.environ, PYTHONUNBUFFERED='1'))
        _RUN['speed'], _RUN['started'] = speed, time.time()
    ros.estop_log.write('speedcheck_start', speed=speed)
    return 202, f'speed check {speed:.2f} m/s started: rover moves ~0.6 m forward slowly. B on the remote stops it.'


def serve_readiness(handler, ros, post=False):
    path = handler.path.split('?')[0]
    if path not in ('/api/readiness', '/api/readiness/bridge', '/api/readiness/speedcheck'):
        return False
    if not post:
        if path == '/api/readiness':
            json_response(handler, 200, readiness(ros))
        elif path == '/api/readiness/speedcheck':
            json_response(handler, 200, speedcheck_status())
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
    return False

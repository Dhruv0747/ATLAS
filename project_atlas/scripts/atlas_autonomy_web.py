"""Dashboard AUTONOMY ON/OFF and waypoints (2026-11-15, owner request). Thin HTTP layer only.

All authority stays where it was: the cmd_vel mux decides ON (atlas_autonomy_arm gates: E-STOP latched, still,
encoder autonomy-ready, speed gate) and mission control runs every navigation check before a waypoint goal.
  GET  /api/autonomy          -> {autonomy, stop_latched, places[], map_id}
  POST /api/autonomy          {action: on|off, pin}   ON needs the operator PIN (same store/lockout as E-STOP reset)
  POST /api/places            {action: save|save_at|go|delete, name[, x, y]}  save_at = map tap (map frame)
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
        pol = policy(ros)
        auto = (pol or {}).get('autonomy') or {}
        if pol is None:
            why = 'no fresh mux state'
        elif not auto.get('armed'):
            why = 'AUTONOMY is OFF'
        elif pol.get('stop_latched'):
            why = 'E-STOP is latched; release it with the remote first'
        else:
            why = None
        if why:
            json_response(handler, 409, {'ok': False, 'message': 'GO refused: ' + why})
            return True
        ok = publish(pubs.get('go'), name)
        ros.estop_log.write('waypoint_go', client=handler.client_address[0], name=name, ok=ok)
        json_response(handler, 202 if ok else 503, {'ok': ok, 'message': f'going to "{name}" (mission control checks localization, camera and safety first)' if ok else 'ROS link not ready'})
    else:
        json_response(handler, 400, {'ok': False, 'message': 'unknown action'})
    return True

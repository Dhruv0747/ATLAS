"""Dashboard routes for camera settings (issue #11, 25 Oct 2026). Additive plug-in for rover-status-web.

GET  /api/cameras/summary              both cameras: connection, streaming, current/saved, measured FPS, recommendation
GET  /api/cameras/<astra|picam>/capabilities
POST /api/cameras/<astra|picam>        {"action": "validate"|"apply"|"reset", "settings": {...}}
     same-origin + X-Atlas-Camera: 1 required. Astra: saved for the next Vision Lab Start (no restart).
     Pi Camera: saved and atlas-camera restarted, only while parked (E-STOP latched, manual-only, commissioning
     disarmed, mission READY) and the Vision Lab idle; a failed start reverts to the previous settings.
Nothing here starts a camera on page load or on a capability query.
"""
import json
import subprocess
import threading
import time
from urllib.parse import urlsplit

import atlas_camera_settings as S

API = '/api/cameras/'
MAX_BODY = 4096
APPLY_LOCK = threading.Lock()
_last_apply = {'t': 0.0}
MIN_APPLY_INTERVAL_S = 20.0


def _json(handler, code, data):
    body = json.dumps(data, allow_nan=False, separators=(',', ':'), default=str).encode()
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return True


_cache = {}


def cached(key, ttl, fn):
    now = time.monotonic(); hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = fn(); _cache[key] = (now, value)
    return value


def _systemctl(*args, timeout=10):
    return subprocess.run(['systemctl', '--user', *args], capture_output=True, text=True, timeout=timeout)


def _vision():
    try:
        import atlas_vision3d_web
        return atlas_vision3d_web.SERVICE.summary()
    except Exception as exc:
        return {'state': 'UNKNOWN', 'reason': str(exc)[:100]}


def _ros_value(snap, key):
    item = (snap or {}).get(key) or {}
    value = item.get('value')
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            pass
    return value, item.get('age'), item.get('observed_hz')


def parked_gate(snap, vision):
    """Reasons applying Pi Camera settings is refused now ([] = allowed)."""
    why = []
    policy, age, _ = _ros_value(snap, 'control_policy')
    if not isinstance(policy, dict) or age is None or age > 3:
        why.append('control policy unknown or stale')
    else:
        if policy.get('stop_latched') is not True:
            why.append('E-STOP is not latched')
        if policy.get('manual_only') is not True:
            why.append('ATLAS is not in manual-only mode')
        if policy.get('commission_armed') is not False:
            why.append('commissioning is armed')
    mission, mage, _ = _ros_value(snap, 'mission_status')
    if mission != 'READY' or mage is None or mage > 5:
        why.append('mission is not READY')
    if str(vision.get('state')) in ('ACTIVE', 'CHECKING'):
        why.append('the Vision Lab camera session is running')
    return why


def summary(ros):
    snap = ros.snapshot() if ros is not None else {}
    vision = _vision()
    a_saved, a_has = S.stored('astra')
    usb = vision.get('usb') or {}
    astra = {'name': 'Orbbec Astra Pro', 'device': usb.get('port') and 'USB %s' % usb['port'],
             'connection': usb.get('state', 'UNKNOWN'), 'connection_detail': usb.get('detail'),
             'streaming': vision.get('state') == 'ACTIVE', 'session_state': vision.get('state'),
             'session_mode': vision.get('mode'), 'saved': a_saved, 'customised': a_has,
             'measured_fps': {k: vision.get(k + '_fps') for k in ('depth', 'rgb', 'ir')},
             'recommended': S.recommendation('astra'), 'applies': 'at the next Vision Lab Start'}
    p_saved, p_has = S.stored('picam')
    det = cached('picam_detected', 30.0, S.picam_detected)

    def is_active():
        try:
            return _systemctl('is-active', 'atlas-camera.service', timeout=5).stdout.strip()
        except Exception:
            return 'unknown'
    active = cached('picam_active', 5.0, is_active)
    info, info_age, hz = _ros_value(snap, 'camera_info')
    picam = {'name': 'Raspberry Pi Camera Module 3 (IMX708)', 'device': 'CSI sensor 0',
             'connection': 'CONNECTED' if active == 'active' and det['modes'] else ('SERVICE_' + active.upper()),
             'service': active, 'streaming': info_age is not None and info_age < 4,
             'running': det['current'], 'saved': p_saved, 'customised': p_has,
             'measured_fps': hz if info_age is not None and info_age < 4 else None,
             'measured_note': 'Measured only while a camera view is open on the dashboard.',
             'recommended': S.recommendation('picam'), 'apply_blocked': parked_gate(snap, vision),
             'applies': 'restarts the Pi camera (about 5 s)'}
    return {'astra': astra, 'picam': picam, 'unix': round(time.time(), 1)}


def _wait_camera_started(since_unix, timeout_s=25):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(1.0)
        try:
            out = subprocess.run(['journalctl', '--user', '-u', 'atlas-camera', '--since', '@%d' % int(since_unix),
                                  '-o', 'cat', '--no-pager'], capture_output=True, text=True, timeout=5).stdout
        except Exception:
            out = ''
        if 'Camera node started' in out and 'Failed' not in out.split('Camera node started')[-1][:200]:
            if _systemctl('is-active', 'atlas-camera.service', timeout=5).stdout.strip() == 'active':
                return True, out[-600:]
        if 'Traceback' in out or 'failed to open' in out.lower():
            return False, out[-600:]
    return False, 'no "Camera node started" within %d s' % timeout_s


def apply_picam(settings, ros, action):
    with APPLY_LOCK:
        if time.monotonic() - _last_apply['t'] < MIN_APPLY_INTERVAL_S:
            raise PermissionError('please wait a few seconds between camera restarts')
        snap = ros.snapshot() if ros is not None else {}
        blocked = parked_gate(snap, _vision())
        if blocked:
            raise PermissionError('Pi Camera settings can only be applied while parked: ' + '; '.join(blocked))
        previous, had = S.stored('picam')
        new = S.validate_picam(settings if action == 'apply' else dict(S.PICAM_DEFAULTS))
        S.save_camera('picam', new)
        _last_apply['t'] = time.monotonic()
        t0 = time.time() - 1
        S.log('picam_apply', action=action, settings=new)
        _systemctl('restart', 'atlas-camera.service', timeout=30)
        ok, evidence = _wait_camera_started(t0)
        _cache.clear()
        if ok:
            S.log('picam_apply_ok', settings=new)
            return {'ok': True, 'saved': new, 'message': 'Pi Camera restarted with the new settings.'}
        S.log('picam_apply_failed', settings=new, evidence=evidence)
        S.save_camera('picam', previous if had else dict(S.PICAM_DEFAULTS))
        t1 = time.time() - 1
        _systemctl('restart', 'atlas-camera.service', timeout=30)
        back, _ = _wait_camera_started(t1)
        S.log('picam_revert', restored=previous, ok=back)
        raise RuntimeError('the camera did not start with those settings; previous settings restored%s'
                           % ('' if back else ' (camera restart still failing - check the camera service)'))


def act(cam, payload, ros):
    action = payload.get('action')
    settings = payload.get('settings') or {}
    if action not in ('validate', 'apply', 'reset') or not isinstance(settings, dict):
        raise ValueError('action must be validate, apply or reset')
    if cam == 'astra':
        clean = S.validate_astra(settings if action != 'reset' else dict(S.ASTRA_DEFAULTS))
        if action == 'validate':
            return {'ok': True, 'valid': clean}
        S.save_camera('astra', clean)
        S.log('astra_apply', action=action, settings=clean)
        return {'ok': True, 'saved': clean, 'message': 'Saved. Used at the next Vision Lab Start.'}
    if cam == 'picam':
        if action == 'validate':
            return {'ok': True, 'valid': S.validate_picam(settings)}
        return apply_picam(settings, ros, action)
    raise ValueError('unknown camera')


def serve(handler, ros=None, post=False):
    parts = urlsplit(handler.path)
    if not parts.path.startswith(API):
        return False
    route = parts.path[len(API):].strip('/')
    try:
        if post:
            from atlas_wifi_web import same_origin
            headers = dict(handler.headers)
            if handler.headers.get('X-Atlas-Camera') != '1':
                raise PermissionError('missing request header')
            headers['X-Atlas-Wifi'] = '1'
            if not same_origin(headers):
                raise PermissionError('same-origin request required')
            length = int(handler.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY or handler.headers.get_content_type() != 'application/json':
                raise ValueError('bounded JSON request required')
            payload = json.loads(handler.rfile.read(length))
            if route not in ('astra', 'picam') or not isinstance(payload, dict):
                return _json(handler, 404, {'error': 'unknown route'})
            return _json(handler, 200, act(route, payload, ros))
        if route == 'summary':
            return _json(handler, 200, summary(ros))
        if route in ('astra/capabilities', 'picam/capabilities'):
            return _json(handler, 200, S.capabilities(route.split('/')[0]))
        return _json(handler, 404, {'error': 'unknown route'})
    except PermissionError as exc:
        return _json(handler, 403, {'error': str(exc)})
    except (S.SettingsError, ValueError, TypeError, KeyError) as exc:
        S.log('settings_rejected', route=route, error=str(exc))
        return _json(handler, 400, {'error': str(exc)})
    except RuntimeError as exc:
        return _json(handler, 409, {'error': str(exc)})
    except Exception as exc:
        S.log('settings_route_error', route=route, error=repr(exc)[:200])
        return _json(handler, 503, {'error': 'camera settings service unavailable'})

#!/usr/bin/env python3
"""ATLAS dashboard: manual controller selection (Xbox / FlySky) and FlySky drive status. Stage 29, additive.

GET  /api/manual_controller          -> mux policy view, FlySky drive-node status, which selections are possible now.
POST /api/manual_controller {"target": "XBOX"|"FLYSKY"}
     -> asks the mux (/atlas/manual_controller/select_<target>) to change the manual controller. The mux only agrees
        while its E-STOP is latched and the rover is stopped, and it flushes every command; this module also refuses
        first unless fresh policy shows the latch. It can NOT reset or release the E-STOP, send a velocity, or change
        any driving parameter: the only POST field is the target name.
Hooked into atlas_status_web, which owns the ROS node, the /atlas/control_policy and /atlas/flysky/drive_status
subscriptions and the two Trigger clients (see tools/deploy/stage29_flysky_drive/insert_status_web_hooks.py).
"""
import json
import time
from urllib.parse import urlsplit

ROUTE = '/api/manual_controller'
TARGETS = ('XBOX', 'FLYSKY')
MAX_BODY = 128
POLICY_MAX_AGE_S = 1.0
DRIVE_MAX_AGE_S = 2.0
CALL_TIMEOUT_S = 2.0


def _age(item, now):
    return None if not item else max(0.0, now - float(item.get('ts', 0.0)))


def _parse(item):
    try:
        v = json.loads(item['value']) if item else None
        return v if isinstance(v, dict) else None
    except (TypeError, ValueError, KeyError):
        return None


def view(ros, now=None):
    now = time.time() if now is None else now
    pol_item, drv_item = ros._item('control_policy'), ros._item('flysky_drive')
    pol, drv = _parse(pol_item), _parse(drv_item)
    pol_age, drv_age = _age(pol_item, now), _age(drv_item, now)
    pol_fresh = pol is not None and pol_age is not None and pol_age <= POLICY_MAX_AGE_S
    supported = pol_fresh and 'manual_controller' in pol           # mux has the Stage 29 patch
    latched = pol_fresh and pol.get('stop_latched') is True
    enabled = supported and pol.get('flysky_drive_enabled') is True
    current = pol.get('manual_controller') if supported else None
    why = ('mux policy is missing or stale' if not pol_fresh else
           'this mux does not support controller selection yet' if not supported else
           'latch the E-STOP first' if not latched else '')
    can = {'XBOX': bool(supported and latched and current != 'XBOX'),
           'FLYSKY': bool(supported and latched and enabled and current != 'FLYSKY')}
    return {
        'policy': {'fresh': pol_fresh, 'age_s': None if pol_age is None else round(pol_age, 2),
                   'stop_latched': latched if pol_fresh else None,
                   'stop_reason': pol.get('stop_reason') if pol_fresh else None,
                   'source': pol.get('source') if pol_fresh else None,
                   'manual_controller': current, 'flysky_drive_enabled': enabled, 'selection_supported': supported},
        'drive': {'running': drv is not None and drv_age is not None and drv_age <= DRIVE_MAX_AGE_S,
                  'age_s': None if drv_age is None else round(drv_age, 2), 'status': drv},
        'can_select': can,
        'blocked_reason': why or ('FlySky driving is disabled on this rover' if not enabled else ''),
    }


def _send(handler, code, data):
    body = json.dumps(data, allow_nan=False, separators=(',', ':')).encode()
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def request_select(ros, target, timeout_s=CALL_TIMEOUT_S):
    clients = getattr(ros, 'manual_controller_clients', None) or {}
    client = clients.get(target)
    if not getattr(ros, 'ready', False) or client is None or not client.service_is_ready():
        return False, 'controller selection service unavailable (mux not updated or not running)'
    future = client.call_async(client.srv_type.Request())      # std_srvs/Trigger, from the client itself
    end = time.monotonic() + timeout_s
    while not future.done() and time.monotonic() < end:
        time.sleep(0.02)                     # the status web's executor thread completes the future
    if not future.done():
        future.cancel()
        return False, 'mux did not answer'
    result = future.result()
    return bool(result.success), str(result.message)


def serve(handler, ros, post=False):
    """True when the request was for ROUTE (answered here)."""
    if urlsplit(handler.path).path != ROUTE:
        return False
    if not post:
        _send(handler, 200, view(ros))
        return True
    from atlas_wifi_web import same_origin
    client = handler.client_address[0] if getattr(handler, 'client_address', None) else '?'
    log = getattr(getattr(ros, 'estop_log', None), 'write', None)

    def deny(code, why):
        if log:
            log('controller_select_denied', result='denied', reason=why, client=client)
        _send(handler, code, {'ok': False, 'message': why})
        return True

    headers = dict(handler.headers)
    if handler.headers.get('X-Atlas-Controller') != '1':
        return deny(403, 'missing request header')
    headers['X-Atlas-Wifi'] = '1'
    if not same_origin(headers):
        return deny(403, 'request did not come from the ATLAS dashboard page')
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= MAX_BODY or handler.headers.get_content_type() != 'application/json':
            raise ValueError
        payload = json.loads(handler.rfile.read(length))
        if not isinstance(payload, dict) or set(payload) != {'target'} or payload['target'] not in TARGETS:
            raise ValueError
    except (ValueError, TypeError):
        return deny(400, 'send exactly {"target": "XBOX"} or {"target": "FLYSKY"}')
    target = payload['target']
    v = view(ros)
    if not v['can_select'][target]:
        return deny(409, v['blocked_reason'] or ('%s is already selected' % target))
    ok, message = request_select(ros, target)
    if log:
        log('controller_select', result='granted' if ok else 'refused', target=target, reason=message, client=client)
    _send(handler, 200 if ok else 409, {'ok': ok, 'message': message, 'target': target})
    return True

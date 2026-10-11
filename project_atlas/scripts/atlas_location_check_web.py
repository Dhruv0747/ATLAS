"""Read-only diagnostic HTTP adapter. No initial-pose or actuator interface."""
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

STATE_FILE=Path.home()/'.local/state/project_atlas/manual_location_check.json'


def status(path=STATE_FILE,now=None,boot_path=Path('/proc/sys/kernel/random/boot_id')):
    now=time.time() if now is None else now
    try:
        data=json.loads(path.read_text())
        if not 0<=now-data['written_unix']<3 or data['boot_id']!=boot_path.read_text().strip():
            raise ValueError('monitor status stale or from another boot')
        if 'ended_unix' in data:data['result_age_s']=max(0.,now-data['ended_unix'])
        data.update(navigation_authorized=False,correction_enabled=False)
        return data
    except (OSError,ValueError,KeyError,TypeError):
        return dict(state='STALE',reason='Location-check monitor unavailable or stale',navigation_authorized=False,correction_enabled=False)


def serve(handler,ros,post=False):
    if urlsplit(handler.path).path!='/api/location-check':return False
    code=200
    try:
        if post:
            from atlas_wifi_web import same_origin
            headers=dict(handler.headers)
            if handler.headers.get('X-Atlas-Location')!='1':raise PermissionError('missing request header')
            headers['X-Atlas-Wifi']='1'
            if not same_origin(headers):raise PermissionError('same-origin request required')
            length=int(handler.headers.get('Content-Length','0'))
            if not 0<length<=128 or handler.headers.get_content_type()!='application/json':raise ValueError('bounded JSON request required')
            payload=json.loads(handler.rfile.read(length))
            if not isinstance(payload,dict) or set(payload)!={'action'} or payload['action'] not in ('start','cancel'):
                raise ValueError('Only start or cancel diagnostic is supported')
            data=ros.request_location_check(payload['action'])
            code=202 if data.get('accepted') else 409
        else:data=status()
    except PermissionError as exc:code=403;data=dict(error=str(exc))
    except (ValueError,TypeError) as exc:code=400;data=dict(error=str(exc))
    except Exception:code=503;data=dict(error='Location-check service unavailable')
    body=json.dumps(data,allow_nan=False).encode()
    handler.send_response(code);handler.send_header('Content-Type','application/json')
    handler.send_header('Cache-Control','no-store');handler.send_header('Content-Length',str(len(body)))
    handler.end_headers();handler.wfile.write(body)
    return True

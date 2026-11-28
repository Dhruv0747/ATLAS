"""Dashboard "FIX MY LOCATION" (2026-11-21 owner request).

When the start verdict is LOCALIZATION UNKNOWN (for example the boot check ran while something blocked the
LiDAR), the owner presses one button and ATLAS re-runs exactly the boot-time LiDAR search:
`seed_atlas_localization.py --mode verify`. It never moves the rover. It seeds AMCL only for a unique,
well-fitting match (same thresholds as boot) and otherwise reports UNKNOWN with the reason.

Gates (server side): same-origin dashboard request with confirm=FIND_LOCATION, autonomy NOT armed,
one run at a time. The seeder itself refuses while the rover is moving.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

SCRIPT = Path(__file__).resolve().parent / 'seed_atlas_localization.py'
VERDICT_FILE = Path.home() / '.local/state/project_atlas/localization_verdict.json'
TIMEOUT_S = 150.0          # verify mode: up to 3 parked checks, ~90 s worst case
CONFIRM = 'FIND_LOCATION'


class Relocalizer:
    def __init__(self, script=SCRIPT, verdict_file=VERDICT_FILE, runner=subprocess.run, clock=time.time):
        self.script, self.verdict_file, self.runner, self.clock = Path(script), Path(verdict_file), runner, clock
        self.lock = threading.Lock()
        self.running = False
        self.started_unix = self.finished_unix = None
        self.last = None            # {'state', 'reason', 'pose', 'seeded', ...}

    def _verdict(self):
        try:
            return json.loads(self.verdict_file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def status(self):
        with self.lock:
            return {'running': self.running, 'started_unix': self.started_unix,
                    'finished_unix': self.finished_unix, 'last': self.last,
                    'elapsed_s': round(self.clock() - self.started_unix, 1) if self.running and self.started_unix else None,
                    'navigation_authorized': False}

    def start(self, armed):
        """(http_status, payload). `armed` is True/False/None (None = autonomy state unknown -> refuse)."""
        if armed is not False:
            return 409, {'ok': False, 'message': 'Turn AUTONOMY OFF first (finding the location never runs while '
                                                  'autonomy is armed or its state is unknown).'}
        with self.lock:
            if self.running:
                return 409, {'ok': False, 'message': 'A location search is already running.'}
            self.running, self.started_unix, self.finished_unix = True, self.clock(), None
        threading.Thread(target=self._run, name='find-my-location', daemon=True).start()
        return 202, {'ok': True, 'message': 'Searching the map with the LiDAR. Keep ATLAS still (up to about 90 s).'}

    def _run(self):
        before = (self._verdict() or {}).get('written_unix')
        result = {'state': 'ERROR', 'reason': 'search did not finish'}
        try:
            proc = self.runner([sys.executable, str(self.script), '--mode', 'verify'],
                               capture_output=True, text=True, timeout=TIMEOUT_S, env=dict(os.environ))
            v = self._verdict() or {}
            if v.get('written_unix') and v.get('written_unix') != before:
                attempts = v.get('attempts') or []
                best = (attempts[-1] if attempts else {}).get('best') or {}
                result = {'state': 'VERIFIED' if v.get('seeded') else (v.get('state') or 'UNKNOWN'),
                          'seeded': bool(v.get('seeded')), 'reason': v.get('reason') or (attempts[-1].get('reason') if attempts else ''),
                          'pose': {k: best.get(k) for k in ('x', 'y', 'yaw_deg')} if best else None,
                          'fit': (attempts[-1] if attempts else {}).get('best_fit')}
            else:
                tail = ((proc.stderr or '') + (proc.stdout or '')).strip().splitlines()[-1:] or ['no verdict written']
                result = {'state': 'ERROR', 'seeded': False, 'reason': ('exit %s: ' % proc.returncode) + tail[0][:200]}
        except subprocess.TimeoutExpired:
            result = {'state': 'ERROR', 'seeded': False, 'reason': 'search timed out after %d s' % TIMEOUT_S}
        except Exception as exc:   # never let the dashboard thread die silently
            result = {'state': 'ERROR', 'seeded': False, 'reason': str(exc)[:200]}
        with self.lock:
            self.running, self.finished_unix, self.last = False, self.clock(), result


RELOCALIZER = Relocalizer()


def serve(handler, armed_fn, json_response, post=False):
    """Route /api/relocalize. Returns False when the path is not ours."""
    if urlsplit(handler.path).path != '/api/relocalize':
        return False
    if not post:
        json_response(handler, 200, RELOCALIZER.status())
        return True
    try:
        from atlas_wifi_web import same_origin
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 128 or handler.headers.get_content_type() != 'application/json':
            raise ValueError('bounded JSON request required')
        payload = json.loads(handler.rfile.read(length))
        if not isinstance(payload, dict) or payload.get('confirm') != CONFIRM:
            raise ValueError('dashboard confirmation required')
        if not same_origin(handler.headers):
            raise PermissionError('request did not come from the ATLAS dashboard page')
    except PermissionError as exc:
        json_response(handler, 403, {'ok': False, 'message': str(exc)})
        return True
    except (ValueError, TypeError) as exc:
        json_response(handler, 400, {'ok': False, 'message': str(exc)})
        return True
    try:
        armed = armed_fn()
    except Exception:
        armed = None
    code, body = RELOCALIZER.start(armed)
    json_response(handler, code, body)
    return True

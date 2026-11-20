"""2026-11-16 dashboard Abort mission: disarm (Manual) + cancel the Nav2 goal; never refused, needs no PIN."""
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import types
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
if 'std_msgs.msg' not in sys.modules:
    std_msgs = types.ModuleType('std_msgs'); std_msgs.msg = types.ModuleType('std_msgs.msg')
    std_msgs.msg.Empty = lambda: 'EMPTY'; std_msgs.msg.String = lambda data='': NS(data=data)
    sys.modules['std_msgs'] = std_msgs; sys.modules['std_msgs.msg'] = std_msgs.msg
# 2026-11-19: stub atlas_wifi_web only for this import; never leave it in sys.modules (it made later
# tests' origin checks always pass: test_flysky_web / test_testlab_web failed when run in one process).
_saved_wifi = sys.modules.get('atlas_wifi_web')
sys.modules['atlas_wifi_web'] = types.SimpleNamespace(same_origin=lambda headers: True)
import atlas_autonomy_web as aw  # noqa: E402
if _saved_wifi is None:
    del sys.modules['atlas_wifi_web']
else:
    sys.modules['atlas_wifi_web'] = _saved_wifi


class Handler:
    def __init__(self, body):
        raw = json.dumps(body).encode()
        self.headers = {'Content-Length': str(len(raw)), 'X-Atlas-Wifi': '1', 'Content-Type': 'application/json'}
        self.rfile = io.BytesIO(raw); self.client_address = ('192.168.1.7', 1)
        self.path = '/api/autonomy'


class AbortTests(unittest.TestCase):
    def run_abort(self, disarm_ok):
        published, logs, responses = [], [], []
        ros = NS(autonomy_clients={'disarm': object()}, place_pubs={},
                 cancel_nav_pub=NS(publish=lambda m: published.append(m)),
                 estop_log=NS(write=lambda ev, **kw: logs.append((ev, kw))),
                 reset_lockout=NS(remaining=lambda: 0))
        with mock.patch.object(aw, 'json_response', lambda h, code, payload: responses.append((code, payload))), \
                mock.patch.object(aw, 'call_trigger', lambda c: (disarm_ok, 'ok' if disarm_ok else 'mux unavailable')), \
                mock.patch.object(aw, 'read_json', lambda h: {'action': 'abort'}), \
                mock.patch.object(aw, 'serve_readiness', lambda *a, **k: False), \
                mock.patch.object(aw.atlas_wifi_web, 'same_origin', lambda headers: True):
            aw.serve(Handler({'action': 'abort'}), ros, post=True)
        return published, logs, responses

    def test_abort_disarms_and_cancels_without_pin(self):
        published, logs, responses = self.run_abort(True)
        self.assertEqual(len(published), 1)
        code, payload = responses[-1]
        self.assertEqual(code, 200)
        self.assertIn('MISSION ABORTED', payload['message'])
        self.assertEqual(logs[-1][0], 'mission_abort')

    def test_abort_still_cancels_if_disarm_fails(self):
        published, _, responses = self.run_abort(False)
        self.assertEqual(len(published), 1)
        self.assertEqual(responses[-1][0], 503)


if __name__ == '__main__':
    unittest.main()

"""V2 as the default dashboard: / serves V2, old V1 page paths redirect, APIs and assets unchanged.

Runs the real rover-status-web GET handler (ROS stubbed). ATLAS_CLASSIC_UI=1 must restore the
classic routing exactly.
"""
import email.message
import io
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_status_web_estop_safety import Recorder, web  # noqa: E402  (installs ROS stubs)

V2 = web.atlas_web_v2
REPO_V2 = Path(__file__).resolve().parents[1] / 'web' / 'v2'


def get(path, client='127.0.0.1'):
    h = web.Handler.__new__(web.Handler)
    h.headers, h.rfile, h.wfile = email.message.Message(), io.BytesIO(), io.BytesIO()
    h.path, h.command, h.request_version, h.requestline = path, 'GET', 'HTTP/1.1', f'GET {path} HTTP/1.1'
    h.client_address, h.close_connection = (client, 5555), True
    h.do_GET()
    raw = h.wfile.getvalue()
    head, _, body = raw.partition(b'\r\n\r\n')
    lines = head.decode('latin-1').split('\r\n')
    headers = dict(l.split(': ', 1) for l in lines[1:] if ': ' in l)
    return int(lines[0].split(' ', 2)[1]), headers, body


class Base(unittest.TestCase):
    def setUp(self):
        self._ros, self._classic, self._dir = web.ROS, V2.CLASSIC_UI, V2.V2_DIR
        self.r = Recorder(policy={'stop_latched': True, 'stop_reason': 'REMOTE STOP: voice stop requested'})
        now = time.time()
        self.r.data['control_policy'] = {'value': '{"stop_latched": true}', 'ts': now}
        web.ROS = self.r
        V2.V2_DIR = REPO_V2.resolve()
        V2.CLASSIC_UI = False

    def tearDown(self):
        web.ROS, V2.CLASSIC_UI, V2.V2_DIR = self._ros, self._classic, self._dir


class V2IsDefault(Base):
    def test_root_serves_v2_index(self):
        index = (REPO_V2 / 'index.html').read_bytes()
        for path in ('/', '/?from=bookmark', '/index.html'):
            code, headers, body = get(path)
            self.assertEqual(code, 200, path)
            self.assertEqual(body, index, path)
            self.assertTrue(headers['Content-Type'].startswith('text/html'))

    def test_v2_paths_unchanged(self):
        self.assertEqual(get('/v2/')[2], (REPO_V2 / 'index.html').read_bytes())
        self.assertEqual(get('/v2')[0], 301)
        self.assertEqual(get('/v2/mapping')[2], (REPO_V2 / 'mapping.html').read_bytes())

    def test_old_page_paths_redirect_to_v2(self):
        for old, new in (('/mapping', '/v2/mapping'), ('/commissioning', '/v2/commissioning'), ('/wifi', '/v2/wifi')):
            code, headers, body = get(old)
            self.assertEqual((code, headers.get('Location'), body), (302, new, b''), old)

    def test_unknown_paths_no_longer_render_the_classic_page(self):
        for path in ('/favicon.ico', '/old-bookmark', '/api'):
            code, _, body = get(path)
            self.assertEqual(code, 404, path)
            self.assertNotIn(b'Project ATLAS Command', body)

    def test_assets_and_apis_keep_their_routes(self):
        for path in ('/commissioning.js', '/steering-commissioning.js', '/commissioning-evidence.js', '/diagnostics.js',
                     '/manifest.webmanifest'):
            self.assertEqual(get(path)[0], 200, path)
        code, _, body = get('/api/estop/state')
        self.assertEqual(code, 200)
        self.assertIn(b'"latched"', body)

    def test_access_control_still_applies_first(self):
        self.assertEqual(get('/', client='8.8.8.8')[0], 403)
        self.assertEqual(get('/mapping', client='8.8.8.8')[0], 403)

    def test_no_v2_page_links_back_to_disabled_v1_pages(self):
        import re
        for f in list(REPO_V2.glob('*.html')) + list(REPO_V2.glob('*.js')):
            hits = re.findall(r'''(?:href|location(?:\.href)?)\s*=\s*['"]/(?:mapping|commissioning|wifi)?['"]''', f.read_text())
            self.assertEqual(hits, [], f.name)


class ClassicFallback(Base):
    def test_classic_switch_restores_v1_routing(self):
        V2.CLASSIC_UI = True
        code, _, body = get('/')
        self.assertEqual(code, 200)
        self.assertNotEqual(body, (REPO_V2 / 'index.html').read_bytes())
        self.assertEqual(body, web.render_control_page().encode())
        self.assertEqual(get('/mapping')[0], 200)
        self.assertEqual(get('/wifi')[0], 200)
        self.assertEqual(get('/old-bookmark')[0], 200)   # classic catch-all behaviour


if __name__ == '__main__':
    unittest.main()

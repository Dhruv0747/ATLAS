"""Offline Playwright harness for V1/V2 dashboards: recorded ATLAS data, POSTs captured, never sent."""
import json, copy, time
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
WEB = REPO / 'web'
TYPES = {'.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png',
         '.webp': 'image/webp', '.woff2': 'font/woff2', '.json': 'application/json', '.jpg': 'image/jpeg', '.txt': 'text/plain'}

class Harness:
    def __init__(self, snap_dir, state=None):
        self.snap = Path(snap_dir); self.posts = []; self.counts = {}; self.state = state or {}
        self.data = {k: json.loads((self.snap / f).read_text()) for k, f in
                     (('status', 'status.json'), ('radar', 'radar.json'), ('diag', 'diagnostics.json'), ('map', 'map.json'),
                      ('comm', 'commissioning.json'), ('evidence', 'evidence.json'), ('wifi', 'wifi.json'))}
        self.offline = False; self.delay_s = 0.0

    def mutate(self, fn):
        fn(self.data)

    def _json(self, route, obj):
        return route.fulfill(status=200, body=json.dumps(obj), content_type='application/json')

    def handle(self, route):
        req = route.request
        url = req.url.split('://', 1)[1]; path = '/' + url.split('/', 1)[1] if '/' in url else '/'
        path = path.split('?')[0].split('#')[0]
        if req.method != 'GET':
            self.posts.append({'t': time.time(), 'path': path, 'body': req.post_data, 'headers': {k: v for k, v in req.headers.items() if k.lower() in ('content-type', 'x-atlas-wifi')}})
            return self._json(route, {'ok': True, 'message': 'captured by test harness (not sent)'})
        self.counts[path] = self.counts.get(path, 0) + 1
        if self.offline and (path.startswith('/api/') or path.startswith('/camera')):
            return route.abort()
        if self.delay_s and path.startswith('/api/'):
            time.sleep(self.delay_s)
        if path.startswith('/v2/'):
            rel = path[4:] or 'index.html'
            alias = {'': 'index.html', 'mapping': 'mapping.html', 'commissioning': 'commissioning.html', 'wifi': 'wifi.html'}
            rel = alias.get(rel.strip('/'), rel.lstrip('/'))
            f = WEB / 'v2' / rel
            if f.is_file():
                return route.fulfill(status=200, body=f.read_bytes(), content_type=TYPES.get(f.suffix, 'application/octet-stream'))
            return route.fulfill(status=404, body='')
        static = {'/': 'index.html', '/mapping': 'mapping.html', '/commissioning': 'commissioning.html', '/wifi': 'wifi.html',
                  '/diagnostics.js': 'diagnostics.js', '/commissioning.js': 'commissioning.js', '/steering-commissioning.js': 'steering.js',
                  '/commissioning-evidence.js': 'evidence.js', '/camera.jpg': 'camera.jpg', '/map.png': 'map.png', '/manifest.webmanifest': 'manifest.json'}
        api = {'/api/status': 'status', '/api/radar': 'radar', '/api/diagnostics': 'diag', '/api/map': 'map', '/api/commissioning': 'comm',
               '/api/commissioning/evidence': 'evidence', '/api/wifi': 'wifi'}
        if path in api:
            return self._json(route, self.data[api[path]])
        if path == '/logo.png':
            return route.fulfill(status=200, body=(self.snap / 'logo.png').read_bytes() if (self.snap / 'logo.png').exists() else b'', content_type='image/png')
        if path in static:
            f = self.snap / static[path]
            return route.fulfill(status=200, body=f.read_bytes(), content_type=TYPES.get(f.suffix, 'application/octet-stream'))
        return route.fulfill(status=404, body='')

def open_page(browser, h, path, vw, scale=1):
    ctx = browser.new_context(viewport={'width': vw[0], 'height': vw[1]}, device_scale_factor=scale, has_touch=vw[0] < 1200)
    pg = ctx.new_page(); pg.errors = []
    pg.on('pageerror', lambda e: pg.errors.append(str(e)[:200]))
    pg.route('**/*', h.handle)
    pg.goto('http://atlas.local:8088' + path, wait_until='load')
    return ctx, pg

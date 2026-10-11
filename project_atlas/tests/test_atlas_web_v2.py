"""Glass UI V2 static route: allow-list, traversal and V1 independence (no ROS needed)."""
import io
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import atlas_web_v2  # noqa: E402


class FakeHandler:
    def __init__(self, path):
        self.path, self.status, self.headers, self.wfile = path, None, {}, io.BytesIO()

    def send_response(self, code): self.status = code
    def send_header(self, k, v): self.headers[k] = v
    def end_headers(self): pass
    def send_error(self, code): self.status = code


class WebV2Route(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        (root / 'assets').mkdir()
        for name in ('index.html', 'mapping.html', 'glass.css', 'shell.js', '.secret.html'):
            (root / name).write_text(name)
        (root / 'assets' / 'icons.svg').write_text('<svg/>')
        (root / 'notes.md').write_text('not served')
        (root.parent / 'outside.html').write_text('outside')
        self.old, atlas_web_v2.V2_DIR = atlas_web_v2.V2_DIR, root

    def tearDown(self):
        atlas_web_v2.V2_DIR = self.old
        self.tmp.cleanup()

    def get(self, path):
        h = FakeHandler(path); atlas_web_v2.serve(h); return h

    def test_pages_and_aliases(self):
        for path, body in (('/v2/', b'index.html'), ('/v2/mapping', b'mapping.html'), ('/v2/glass.css', b'glass.css'),
                           ('/v2/shell.js?x=1', b'shell.js'), ('/v2/assets/icons.svg', b'<svg/>')):
            h = self.get(path)
            self.assertEqual(h.status, 200, path)
            self.assertEqual(h.wfile.getvalue(), body)
            self.assertEqual(h.headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn('max-age', self.get('/v2/assets/icons.svg').headers['Cache-Control'])
        self.assertEqual(self.get('/v2/index.html').headers['Cache-Control'], 'no-cache')

    def test_bare_v2_redirects(self):
        h = self.get('/v2')
        self.assertEqual((h.status, h.headers['Location']), (301, '/v2/'))

    def test_rejects_traversal_hidden_unknown_types_and_listing(self):
        for path in ('/v2/../outside.html', '/v2/%2e%2e/outside.html', '/v2/assets/../../outside.html', '/v2/.secret.html',
                     '/v2/notes.md', '/v2/assets/', '/v2/missing.js', '/v2/a/b/c.js', '/v2/other/x.css', '/v2/glass.css%00.js',
                     '/v2//etc/passwd', '/v2/..%5c..%5coutside.html'):
            self.assertEqual(self.get(path).status, 404, path)

    def test_only_v2_paths_are_claimed(self):
        for path in ('/', '/mapping', '/commissioning', '/wifi', '/api/status', '/v2x', '/v20/'):
            self.assertFalse(atlas_web_v2.handles(path), path)
        self.assertTrue(atlas_web_v2.handles('/v2/?a=1'))

    def test_status_web_hook_follows_client_allowed(self):
        src = (SCRIPTS / 'atlas_status_web.py').read_text(encoding='utf-8')
        get = src[src.index('    def do_GET(self):'):]
        self.assertLess(get.index('self.client_allowed()'), get.index('atlas_web_v2.handles(self.path)'))
        self.assertEqual(src.count('atlas_web_v2.serve('), 1)

    def test_repo_v2_files_are_all_servable(self):
        real = Path(__file__).parents[1] / 'web' / 'v2'
        atlas_web_v2.V2_DIR = real.resolve()
        for name in ('index.html', 'mapping.html', 'commissioning.html', 'wifi.html', 'base.css', 'glass.css', 'pages.css',
                     'command.js', 'shell.js', 'estop.js', 'assets/icons.svg', 'assets/atlas-logo-96.webp',
                     'assets/michroma-latin-400.woff2'):
            self.assertEqual(self.get('/v2/' + name).status, 200, name)


if __name__ == '__main__':
    unittest.main()

"""Extend-map preview on the dashboard (2026-11-26): read-only status-web helpers + the Mapping page card (static)."""
import ast
import json
from pathlib import Path
import re
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'scripts' / 'atlas_status_web.py'
TEXT = SRC.read_text(encoding='utf-8')
tree = ast.parse(TEXT)
ns = {'json': json, 'Path': Path, 'time': time}
body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('read_map_extend', 'map_extend_preview_path')
        or (isinstance(n, ast.Assign) and any(getattr(t, 'id', '') in ('MAP_EXTEND_DIR', 'MAP_EXTEND_MAX_AGE_S')
                                              for t in n.targets))]
exec(compile(ast.Module(body=body, type_ignores=[]), str(SRC), 'exec'), ns)
JS = (ROOT / 'web' / 'v2' / 'map-extend.js').read_text(encoding='utf-8')
PAGE = (ROOT / 'web' / 'v2' / 'mapping.html').read_text(encoding='utf-8')


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def latest(self, **kw):
        (self.d / 's1').mkdir(exist_ok=True)
        (self.d / 's1' / 'preview.png').write_bytes(b'\x89PNGfake')
        r = dict({'schema': 1, 'session_id': 's1', 'created_unix': 1000.0, 'ok': True, 'failures': [],
                  'match': 0.97, 'stats': {'added_free_m2': 6.4, 'saved_cells_changed': 0, 'conflict_fraction': 0.02,
                                           'unreachable_m2': 0.1, 'contact_cells': 30},
                  'preview': str(self.d / 's1' / 'preview.png'), 'candidate_yaml': str(self.d / 's1' / 'candidate.yaml')},
                 **kw)
        (self.d / 'latest.json').write_text(json.dumps(r))
        return r

    def test_latest_result_for_the_page(self):
        self.latest()
        v = ns['read_map_extend'](now=1060.0, state_dir=self.d)
        self.assertEqual(v['session_id'], 's1')
        self.assertTrue(v['ok'])
        self.assertTrue(v['has_preview'])
        self.assertTrue(v['has_candidate'])
        self.assertEqual(v['age_s'], 60.0)
        self.assertEqual(v['stats']['saved_cells_changed'], 0)
        self.assertNotIn('candidate_yaml', v)                     # no file paths to the browser
        self.assertNotIn('preview', v)

    def test_missing_old_or_bad_is_none(self):
        self.assertIsNone(ns['read_map_extend'](now=1.0, state_dir=self.d))
        self.latest()
        self.assertIsNone(ns['read_map_extend'](now=1000.0 + 8 * 86400, state_dir=self.d))
        (self.d / 'latest.json').write_text('{broken')
        self.assertIsNone(ns['read_map_extend'](now=1000.0, state_dir=self.d))

    def test_preview_path_stays_inside_the_state_dir(self):
        self.latest()
        self.assertEqual(ns['map_extend_preview_path'](state_dir=self.d), (self.d / 's1' / 'preview.png').resolve())
        self.latest(preview='/etc/passwd')
        self.assertIsNone(ns['map_extend_preview_path'](state_dir=self.d))
        self.latest(preview=str(self.d / '..' / 'x.png'))
        self.assertIsNone(ns['map_extend_preview_path'](state_dir=self.d))

    def test_routes_registered_before_the_api_map_prefix_route(self):
        i_ext = TEXT.index('"/api/map_extend"')
        i_png = TEXT.index('"/map_extend_preview.png"')
        i_map = TEXT.index('if self.path.startswith("/api/map"):')
        self.assertLess(i_ext, i_map)
        self.assertLess(i_png, i_map)


class CardTests(unittest.TestCase):
    def test_page_loads_card(self):
        self.assertRegex(PAGE, r'<script src="/v2/map-extend\.js\?v=\d{8}[a-z]*" defer></script>')

    def test_card_is_read_only(self):
        self.assertNotRegex(JS, r"method:\s*'POST'|method:\s*\"POST\"")
        self.assertNotRegex(JS, r'/api/places|/api/autonomy|cmd_vel')
        self.assertIn("fetch('/api/map_extend'", JS)

    def test_card_text_english_and_escaped(self):
        self.assertFalse(any('ऀ' <= ch <= 'ॿ' for ch in JS))
        for word in ('kya', 'kaise', 'karo', 'hai'):
            self.assertNotRegex(JS, r'\b' + word + r'\b')
        self.assertRegex(JS, r'function esc\(')
        self.assertIn('MAP EXTENSION PREVIEW', JS)
        self.assertIn('saved map unchanged', JS.lower())
        self.assertIn('promote extension', JS)


if __name__ == '__main__':
    unittest.main()

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_web_v2  # noqa: E402


class Static(unittest.TestCase):
    def test_page_is_registered_and_assets_served(self):
        self.assertEqual(atlas_web_v2.PAGES['flysky-testlab'], 'flysky-testlab.html')
        self.assertEqual(atlas_web_v2.PAGES['testlab'], 'testlab.html')       # existing Test Lab untouched
        for p in ('/v2/flysky-testlab', '/v2/flysky-testlab/', '/v2/flysky-testlab.js', '/v2/flysky.css'):
            self.assertTrue(atlas_web_v2.handles(p), p)

    def test_home_has_one_flysky_shortcut_and_existing_ones_remain(self):
        idx = (ROOT / 'web/v2/index.html').read_text()
        self.assertEqual(idx.count('href="/v2/flysky-testlab"'), 1)
        self.assertEqual(idx.count('href="/v2/testlab"'), 1)
        for keep in ('href="/v2/mapping"', 'href="/v2/commissioning"', 'id="stop"', 'estopReset'):
            self.assertIn(keep, idx)
        self.assertIn('FlySky Remote Test Lab', idx)

    def test_index_diff_only_adds_the_flysky_link(self):
        try:
            old = subprocess.run(['git', 'show', 'HEAD:project_atlas/web/v2/index.html'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        except Exception:
            self.skipTest('git history unavailable')
        new = (ROOT / 'web/v2/index.html').read_text()
        if 'hm-labs' in new:
            self.skipTest('Stage31 Home layout: link visibility is covered by test_stage31_ui; the old Home is web/v2/classic.html')
        if old == new:
            self.skipTest('already committed')
        self.assertEqual([l for l in old.splitlines() if l not in new.splitlines()], [])
        added = [l for l in new.splitlines() if l not in old.splitlines()]
        self.assertEqual(len([l for l in added if 'href="/v2/flysky-testlab"' in l]), 1)
        self.assertTrue(all('flysky' in l.lower() or 'lblShort' in l or 'lblFull' in l for l in added), added)   # the link and its CSS only
        self.assertLessEqual(len(added), 4)

    def test_testlab_files_are_not_modified_by_this_stage(self):
        try:
            out = subprocess.run(['git', 'status', '--porcelain', '--', 'project_atlas/web/v2/testlab.html', 'project_atlas/web/v2/testlab.js',
                                  'project_atlas/web/v2/testlab.css', 'project_atlas/scripts/atlas_testlab_core.py', 'project_atlas/scripts/atlas_testlab_web.py'],
                                 cwd=ROOT.parent, capture_output=True, text=True, check=True).stdout
        except Exception:
            self.skipTest('git unavailable')
        self.assertEqual(out.strip(), '')

    def test_html_has_no_external_assets_or_inline_handlers(self):
        html = (ROOT / 'web/v2/flysky-testlab.html').read_text()
        self.assertEqual(re.findall(r'(?:src|href)="(https?:)?//', html), [])
        self.assertIsNone(re.search(r'\son[a-z]+=', html))
        for needed in ('id="banner"', 'id="chans"', 'id="graph"', 'id="recStart"', 'id="v2Estop"', 'id="sticks"'):
            self.assertIn(needed, html)
        self.assertIn('FlySky Remote Test Lab', html)

    def test_js_talks_only_to_flysky_api_and_posts_only_record_actions(self):
        js = (ROOT / 'web/v2/flysky-testlab.js').read_text()
        self.assertEqual(sorted(set(re.findall(r"fetch\('([^']+)'", js))), ['/api/flysky/action', '/api/flysky/state'])
        self.assertEqual(sorted(set(re.findall(r"action: '([a-z_]+)'", js))), ['reset_ranges', 'session_start', 'session_stop'])
        code = re.sub(r'/\*[\s\S]*?\*/', '', js)
        for bad in ('cmd_vel', 'e_stop', 'estop', '/api/drive', 'linear', 'angular', 'throttle', 'steer', 'innerHTML', 'eval(', 'document.write', 'WebSocket', 'XMLHttpRequest'):
            self.assertNotIn(bad, code, bad)
        self.assertEqual(js.count("method: 'POST'"), 1)

    def test_states_never_say_connected_without_verified(self):
        js = (ROOT / 'web/v2/flysky-testlab.js').read_text(); core = (ROOT / 'scripts/atlas_flysky_core.py').read_text()
        self.assertEqual(len(re.findall(r"'CONNECTED'", core)), 1)
        self.assertIn("'LIVE': 'CONNECTED'", core)
        self.assertNotIn('CONNECTED', js.replace("st.link.label", ''))

    def test_no_signal_strength_is_invented(self):
        js = (ROOT / 'web/v2/flysky-testlab.js').read_text()
        self.assertNotRegex(js.lower(), r'rssi\s*[:=]\s*\d')
        self.assertIn('not available', js)

    def test_hooks_in_repo_status_web_are_additive(self):
        s = (ROOT / 'scripts/atlas_status_web.py').read_text()
        self.assertEqual(s.count('atlas_flysky_web.serve(self, ROS)'), 1)
        self.assertEqual(s.count('atlas_flysky_web.serve(self, ROS, post=True)'), 1)
        self.assertEqual(s.count('atlas_testlab_web.serve(self, ROS)'), 1)


if __name__ == '__main__':
    unittest.main()

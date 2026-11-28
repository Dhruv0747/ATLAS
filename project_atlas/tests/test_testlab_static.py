import re
import subprocess
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_web_v2  # noqa: E402


class StaticIntegration(unittest.TestCase):
    def test_page_registered_and_served_by_allow_list(self):
        self.assertEqual(atlas_web_v2.PAGES['testlab'], 'testlab.html')
        for p in ('/v2/testlab', '/v2/testlab.js', '/v2/testlab.css'):
            self.assertIsNotNone(atlas_web_v2.resolve(p), p)

    def test_title_and_home_link(self):
        html = (ROOT / 'web/v2/testlab.html').read_text()
        self.assertIn('Motor &amp; Encoder Test Lab', html)
        idx = (ROOT / 'web/v2/index.html').read_text()
        self.assertEqual(idx.count('href="/v2/testlab"'), 1)
        for keep in ('/v2/mapping', '/v2/commissioning', 'shutdownAtlas()', 'id="v2Estop"', '#diagnosticsPanel'):
            self.assertIn(keep, idx)

    def test_index_only_gained_one_link(self):
        try:
            old = subprocess.run(['git', 'show', 'HEAD:project_atlas/web/v2/index.html'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        except Exception:
            self.skipTest('git history unavailable')
        new = (ROOT / 'web/v2/index.html').read_text()
        if 'hm-labs' in new:
            self.skipTest('Stage31 Home layout: link visibility is covered by test_stage31_ui; the old Home is web/v2/classic.html')
        if old == new:
            self.skipTest('already committed')
        removed = [l for l in old.splitlines() if l not in new.splitlines()]
        added = [l for l in new.splitlines() if l not in old.splitlines() and 'flysky' not in l.lower()
                 and 'lblFull' not in l and 'lblShort' not in l]   # Stage 27 FlySky link is covered by test_flysky_static
        self.assertEqual(removed, [])
        self.assertLessEqual(len(added), 1)

    def test_no_external_assets_and_safe_dom(self):
        html = (ROOT / 'web/v2/testlab.html').read_text()
        self.assertEqual(re.findall(r'(?:src|href)="(https?:[^"]+)"', html), [])
        js = (ROOT / 'web/v2/testlab.js').read_text()
        self.assertNotIn('innerHTML', js)
        self.assertNotIn('eval(', js)

    def test_js_only_talks_to_testlab_api_and_dock_estop(self):
        js = (ROOT / 'web/v2/testlab.js').read_text()
        urls = set(re.findall(r"fetch\(\s*'([^']+)'", js))
        self.assertEqual({u.split('?')[0] for u in urls}, {'/api/testlab/action', '/api/testlab/state', '/', })
        self.assertNotIn('cmd_vel', js)
        self.assertNotIn('/api/drive', js)
        actions = set(re.findall(r"action: '([a-z_]+)'", js))
        from atlas_testlab_web import ACTIONS
        self.assertTrue(actions <= set(ACTIONS) | {'e_stop'}, actions - set(ACTIONS))

    def test_protected_safety_files_untouched(self):
        try:
            out = subprocess.run(['git', 'status', '--porcelain', '--', 'scripts/yahboom_base.py', 'scripts/atlas_cmd_vel_mux.py',
                                  'scripts/atlas_drive_pid_lifted.py', 'config'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        except Exception:
            self.skipTest('git unavailable')
        self.assertEqual(out.strip(), '')

    def test_deploy_scripts_refuse_without_approval_and_keep_dropin_disabled(self):
        d = ROOT / 'tools/deploy/stage26_testlab'
        r = subprocess.run(['bash', str(d / 'apply.sh')], capture_output=True, text=True, env={'PATH': '/usr/bin:/bin'})
        self.assertEqual(r.returncode, 2)
        self.assertIn('OWNER_APPROVED', r.stderr)
        self.assertTrue((d / 'base_dropin/99-testlab-lifted.conf.disabled').exists())
        self.assertFalse(list((d / 'base_dropin').glob('*.conf')))
        self.assertNotIn('yahboom', (d / 'apply.sh').read_text().replace('DOES NOT touch the base driver', ''))


if __name__ == '__main__':
    unittest.main()

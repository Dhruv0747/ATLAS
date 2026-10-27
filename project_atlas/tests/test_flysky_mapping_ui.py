"""FlySky Test Lab channel-mapping card: static safety rules + real-browser behaviour against the offline simulator."""
import re
import socket
import subprocess
import sys
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'web/v2/flysky-mapping.js'
try:
    from playwright.sync_api import sync_playwright
    HAVE = True
except Exception:       # pragma: no cover
    HAVE = False


class MappingStatic(unittest.TestCase):
    def test_mapping_js_makes_no_requests_and_names_no_drive_path(self):
        js = JS.read_text()
        code = re.sub(r'/\*[\s\S]*?\*/', '', js)
        for bad in ('fetch(', 'XMLHttpRequest', 'WebSocket', 'sendBeacon', 'innerHTML', 'eval(', 'document.write',
                    'cmd_vel', 'estop', 'e_stop', '/api/', 'linear', 'angular', 'throttle', 'steer', 'motor', 'drive('):
            self.assertNotIn(bad, code, bad)

    def test_page_loads_mapping_before_main_script_and_keeps_existing_ids(self):
        html = (ROOT / 'web/v2/flysky-testlab.html').read_text()
        self.assertLess(html.index('/v2/flysky-mapping.js'), html.index('/v2/flysky-testlab.js'))
        for needed in ('id="mapCard"', 'id="mapRows"', 'id="mapApply"', 'id="mapCancel"', 'id="mapDefaults"', 'id="rawToggle"',
                       'id="banner"', 'id="chans"', 'id="graph"', 'id="recStart"', 'id="v2Estop"', 'id="sticks"'):
            self.assertIn(needed, html)
        self.assertEqual(re.findall(r'(?:src|href)="(https?:)?//', html), [])
        self.assertIsNone(re.search(r'\son[a-z]+=', html))

    def test_main_script_change_is_the_event_and_graph_filter_only(self):
        js = (ROOT / 'web/v2/flysky-testlab.js').read_text()
        self.assertEqual(js.count("new CustomEvent('atlas-flysky-state'"), 1)
        self.assertEqual(js.count("method: 'POST'"), 1)          # still only the existing record/reset actions


def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p


@unittest.skipUnless(HAVE, 'playwright not installed')
class MappingRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.proc = subprocess.Popen([sys.executable, str(ROOT / 'tools/flysky/sim_server.py'), '--port', str(cls.port), '--scenario', 'live'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/v2/flysky-testlab' % cls.port, timeout=1).read(); break
            except Exception:
                time.sleep(0.2)
        try:
            cls.pw = sync_playwright().start(); cls.browser = cls.pw.chromium.launch()
        except Exception as exc:
            cls.proc.terminate(); raise unittest.SkipTest('chromium unavailable: %s' % exc)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close(); cls.pw.stop()
        finally:
            cls.proc.terminate()

    def setUp(self):
        urllib.request.urlopen('http://127.0.0.1:%d/sim?reset=1&scenario=live' % self.port).read()
        self.ctx = self.browser.new_context(viewport={'width': 1440, 'height': 1000})
        self.pg = self.ctx.new_page(); self.errs = []; self.reqs = []
        self.pg.on('console', lambda m: self.errs.append(m.text) if m.type == 'error' else None)
        self.pg.on('pageerror', lambda e: self.errs.append(str(e)))
        self.pg.on('request', lambda r: self.reqs.append((r.method, r.url.split('?')[0].replace('http://127.0.0.1:%d' % self.port, ''))))
        self.pg.goto('http://127.0.0.1:%d/v2/flysky-testlab' % self.port)

    def tearDown(self):
        self.assertEqual(self.errs, [])
        self.ctx.close()

    def badge(self, ch):
        return self.pg.inner_text('#mapRows .fm-row:nth-child(%d) .fm-badge' % ch)

    def test_defaults_apply_verify_switches_and_sticks(self):
        pg = self.pg
        self.assertTrue(pg.is_disabled('#mapApply'))
        pg.click('#mapDefaults'); self.assertFalse(pg.is_disabled('#mapApply'))
        self.assertEqual(pg.input_value('#mapSel5'), 'swa'); self.assertEqual(pg.input_value('#mapSel10'), 'vrb')
        pg.click('#mapApply'); pg.wait_for_timeout(13000)          # sim: CH5 flips every 4 s, CH6 steps every 3 s
        for ch in (1, 2, 3, 4, 5, 6):
            self.assertTrue(self.badge(ch).startswith('Verified'), (ch, self.badge(ch)))
        for ch in (7, 8, 9, 10):
            self.assertTrue(self.badge(ch).startswith('Assigned'), (ch, self.badge(ch)))
        self.assertIn('10 of 10 assigned', pg.inner_text('#mapSummary'))
        self.assertIn('6 verified', pg.inner_text('#mapSummary'))
        # the existing stick pads follow the mapping
        self.assertEqual(pg.input_value('select[aria-label="Left stick Up–down channel"]'), '3')
        self.assertEqual(pg.input_value('select[aria-label="Right stick Left–right channel"]'), '1')

    def test_unassigned_changing_and_kind_mismatch_are_flagged(self):
        pg = self.pg
        pg.select_option('#mapSel5', 'rv'); pg.select_option('#mapSel1', 'swa'); pg.click('#mapApply')
        pg.wait_for_timeout(9000)
        self.assertIn('reads as', self.badge(5))        # a switch-like channel mapped to a stick axis
        self.assertIn('reads as', self.badge(1))        # an analog channel mapped to a switch
        self.assertTrue(self.badge(6).startswith('Unassigned, but it changed'), self.badge(6))
        self.assertEqual(self.badge(8), 'Unassigned')

    def test_duplicate_blocks_apply_cancel_reverts(self):
        pg = self.pg
        pg.select_option('#mapSel2', 'swa'); pg.select_option('#mapSel3', 'swa')
        self.assertTrue(pg.is_disabled('#mapApply'))
        self.assertIn('both CH2 and CH3', pg.inner_text('#mapState'))
        pg.click('#mapCancel')
        self.assertEqual(pg.input_value('#mapSel2'), ''); self.assertEqual(pg.inner_text('#mapState'), 'Not saved yet')

    def test_saved_mapping_reloads_and_cancel_keeps_saved(self):
        pg = self.pg
        pg.click('#mapDefaults'); pg.click('#mapApply'); pg.wait_for_timeout(300)
        self.assertTrue(pg.inner_text('#mapState').startswith('Saved'))
        pg.reload(); pg.wait_for_timeout(800)
        self.assertEqual(pg.input_value('#mapSel7'), 'swc')
        pg.select_option('#mapSel7', ''); self.assertEqual(pg.inner_text('#mapState'), 'Unsaved changes')
        pg.click('#mapCancel'); self.assertEqual(pg.input_value('#mapSel7'), 'swc')
        pg.reload(); pg.wait_for_timeout(500); self.assertEqual(pg.input_value('#mapSel7'), 'swc')

    def test_export_import_round_trip(self):
        pg = self.pg
        pg.select_option('#mapSel5', 'swd'); pg.click('#mapApply')
        with pg.expect_download() as dl:
            pg.click('#mapExport')
        path = dl.value.path(); text = Path(path).read_text()
        self.assertIn('"5": "swd"', text)
        pg.click('#mapDefaults'); pg.click('#mapApply'); self.assertEqual(pg.input_value('#mapSel5'), 'swa')
        pg.set_input_files('#mapImport', path); pg.wait_for_timeout(300)
        self.assertEqual(pg.input_value('#mapSel5'), 'swd'); self.assertEqual(pg.inner_text('#mapState'), 'Unsaved changes')

    def test_ten_channels_by_default_raw_toggle_shows_sixteen_and_no_new_requests(self):
        pg = self.pg; pg.wait_for_timeout(2500)
        visible = pg.evaluate("[...document.querySelectorAll('#chans .fs-row')].filter(r => r.offsetParent !== null).length")
        self.assertEqual(visible, 10)
        pg.check('#rawToggle'); pg.wait_for_timeout(500)
        visible = pg.evaluate("[...document.querySelectorAll('#chans .fs-row')].filter(r => r.offsetParent !== null).length")
        self.assertEqual(visible, 16)
        api = {(m, u) for m, u in self.reqs if u.startswith('/api')}
        self.assertEqual(api, {('GET', '/api/flysky/state')})

    def test_phone_width_has_no_horizontal_scroll(self):
        pg = self.ctx.new_page(); pg.set_viewport_size({'width': 390, 'height': 844})
        pg.goto('http://127.0.0.1:%d/v2/flysky-testlab' % self.port); pg.wait_for_timeout(1500)
        self.assertFalse(pg.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth'))
        pg.close()


if __name__ == '__main__':
    unittest.main()

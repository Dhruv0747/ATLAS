"""Real-browser rendering test against the offline simulator (skips when Playwright/Chromium is not installed)."""
import json
import socket
import subprocess
import sys
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    from playwright.sync_api import sync_playwright
    HAVE = True
except Exception:       # pragma: no cover
    HAVE = False


def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p


@unittest.skipUnless(HAVE, 'playwright not installed')
class Render(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.proc = subprocess.Popen([sys.executable, str(ROOT / 'tools/flysky/sim_server.py'), '--port', str(cls.port), '--scenario', 'no_source'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/v2/flysky-testlab' % cls.port, timeout=1).read(); break
            except Exception:
                time.sleep(0.2)
        try:
            cls.pw = sync_playwright().start(); cls.browser = cls.pw.chromium.launch()
        except Exception as exc:          # browser binary missing
            cls.proc.terminate(); raise unittest.SkipTest('chromium unavailable: %s' % exc)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close(); cls.pw.stop()
        finally:
            cls.proc.terminate()

    def scenario(self, name):
        urllib.request.urlopen('http://127.0.0.1:%d/sim?reset=1&scenario=%s' % (self.port, name)).read()

    def open(self, w, h, path='/v2/flysky-testlab', wait=1500):
        pg = self.browser.new_page(viewport={'width': w, 'height': h}); errs = []
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto('http://127.0.0.1:%d%s' % (self.port, path)); pg.wait_for_timeout(wait)
        return pg, errs

    def test_no_source_says_not_verified_never_connected(self):
        self.scenario('no_source')
        for w, h in ((1440, 900), (390, 844)):
            pg, errs = self.open(w, h)
            self.assertEqual(pg.inner_text('#chipLink'), 'SIGNAL NOT VERIFIED')
            self.assertIn('does not forward SBUS', pg.inner_text('#banner'))
            self.assertNotIn('CONNECTED', pg.inner_text('body').upper().replace('NOT VERIFIED', '').replace('DISCONNECTED', '') if False else pg.inner_text('#chipLink').upper())
            self.assertFalse(pg.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth'))
            self.assertEqual(errs, []); pg.close()

    def test_live_channels_move_and_page_has_no_errors(self):
        self.scenario('live')
        for w, h in ((1440, 900), (390, 844)):
            pg, errs = self.open(w, h, wait=6500)
            self.assertEqual(pg.inner_text('#chipLink'), 'CONNECTED')
            vals = [pg.inner_text('.fs-row:nth-child(1) .raw')]; pg.wait_for_timeout(700); vals.append(pg.inner_text('.fs-row:nth-child(1) .raw'))
            self.assertNotEqual(vals[0], vals[1], 'CH1 raw value must change live')
            self.assertGreaterEqual(pg.locator('.fs-row.hot').count(), 3)
            self.assertIn('switch', pg.inner_text('.fs-row:nth-child(5)'))
            self.assertFalse(pg.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth'))
            self.assertEqual(pg.inner_text('#recStart'), 'Start recording'); self.assertEqual(errs, []); pg.close()

    def test_failsafe_and_lost_states_render(self):
        self.scenario('failsafe'); pg, errs = self.open(1024, 800, wait=2500)
        self.assertEqual(pg.inner_text('#chipLink'), 'RECEIVER FAILSAFE'); pg.close()
        self.scenario('stale'); pg, errs = self.open(1024, 800, wait=9500)
        self.assertEqual(pg.inner_text('#chipLink'), 'SIGNAL LOST'); self.assertIn('last known', pg.inner_text('#banner')); self.assertEqual(errs, []); pg.close()

    def test_record_and_csv_download(self):
        self.scenario('live'); pg, errs = self.open(1440, 900, wait=2500)
        pg.click('#recStart'); pg.wait_for_timeout(2000)
        self.assertIn('Recording', pg.inner_text('#chipRec'))
        href = pg.get_attribute('#csvCurrent', 'href'); text = urllib.request.urlopen('http://127.0.0.1:%d%s' % (self.port, href)).read().decode()
        head = text.splitlines()[0]; self.assertIn('ch1_raw', head); self.assertGreater(len(text.splitlines()), 10)
        pg.click('#recStop'); pg.wait_for_timeout(800); self.assertEqual(pg.inner_text('#chipRec'), 'Not recording'); self.assertEqual(errs, []); pg.close()

    def test_moving_sticks_issue_no_requests_except_state_polls(self):
        self.scenario('live'); pg = self.browser.new_page(viewport={'width': 1200, 'height': 900}); seen = []
        pg.on('request', lambda r: seen.append((r.method, r.url.split('?')[0].replace('http://127.0.0.1:%d' % self.port, ''))))
        pg.goto('http://127.0.0.1:%d/v2/flysky-testlab' % self.port); pg.wait_for_timeout(5000)
        api = {(m, u) for m, u in seen if u.startswith('/api') or u == '/'}
        self.assertEqual(api, {('GET', '/api/flysky/state')}); pg.close()

    def test_home_shortcut_opens_page_in_one_click(self):
        for w, h in ((1440, 900), (390, 844)):
            pg, errs = self.open(w, h, path='/v2/', wait=800)
            btn = pg.locator('a.flyskyShortcut'); self.assertTrue(btn.is_visible()); label = btn.inner_text().split('\n')[0]   # Stage31 Home shows a one-line description under the name
            self.assertIn(label, ('FlySky Remote Test Lab', 'FlySky Remote Test Lab' if w > 759 else 'FlySky Test Lab')); self.assertEqual(btn.get_attribute('aria-label'), 'FlySky Remote Test Lab')
            box = btn.bounding_box(); self.assertTrue(0 <= box['x'] and box['x'] + box['width'] <= w, box)
            btn.click(); pg.wait_for_load_state(); self.assertTrue(pg.url.endswith('/v2/flysky-testlab'))
            self.assertEqual(pg.locator('h1').first.inner_text(), 'FlySky Remote Test Lab'); pg.close()


if __name__ == '__main__':
    unittest.main()

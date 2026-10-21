"""Stage31 Home / Vision Lab UI gates. Offline: no browser, ROS, camera or service."""
import hashlib
import io
import json
import re
import sys
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_vision3d_runtime as R   # noqa: E402
import atlas_vision3d_web as W       # noqa: E402

V2 = ROOT / 'web/v2'
NEW = (V2 / 'index.html').read_text()
OLD = (V2 / 'classic.html').read_text()
CARDS = (V2 / 'home-cards.js').read_text()
VJS = (V2 / 'vision3d.js').read_text()
VHTML = (V2 / 'vision3d.html').read_text()
CLASSIC_LIVE_SHA = 'f53d68120ecdb82efa0d942ec5519712e283ee511dc02e3b2cbdc88cc12a53c0'   # live index.html, 21 Oct 2026


def ids(html):
    return re.findall(r'\sid="([^"]+)"', html)


def attrs(html, name):
    return sorted(re.findall(r'<button[^>]*\s' + name + r'="([^"]*)"[^>]*>', html))


class HomePreservesEverything(unittest.TestCase):
    def test_classic_is_the_verbatim_live_home(self):
        self.assertEqual(hashlib.sha256((V2 / 'classic.html').read_bytes()).hexdigest(), CLASSIC_LIVE_SHA)

    def test_every_previous_element_id_exists_once(self):
        new = ids(NEW)
        self.assertEqual([i for i in ids(OLD) if i not in new], [])
        self.assertEqual(len(new), len(set(new)), 'duplicate ids')

    def test_every_id_command_and_shell_scripts_use_exists(self):
        used = set()
        for f in ('command.js', 'shell.js', 'estop.js'):
            used |= set(re.findall(r"(?:\$|getElementById)\('([A-Za-z0-9_]+)'\)", (V2 / f).read_text()))
        generated = {'mainBatteryBadge', 'modalCamera'}   # created at runtime by diagnostics.js / detail modal
        self.assertEqual(sorted(used - set(ids(NEW)) - generated - {'v2EstopMsg'}), [])

    def test_control_markup_is_identical(self):
        for a in ('data-l', 'data-a', 'data-cam', 'data-dir', 'data-track', 'data-ai'):
            self.assertEqual(attrs(NEW, a), attrs(OLD, a), a)
        for handler in ('onclick="voiceMute(true)"', 'onclick="voiceMute(false)"', 'onclick="shutdownAtlas()"', "setRadarView('2d')",
                        'ontoggle="if(this.open){renderDiagnostics();refreshDiagnostics(true)}"', 'downloadDiagnostics()'):
            self.assertIn(handler, NEW, handler)

    def test_same_scripts_load_plus_cards_last(self):
        old = re.findall(r'<script src="([^"]+)"', OLD)
        new = re.findall(r'<script src="([^"]+)"', NEW)
        self.assertEqual(new[:len(old)], old)
        self.assertEqual(new[len(old):], ['/v2/home-cards.js'])

    def test_estop_is_never_inside_a_menu_or_drawer(self):
        for estop in ('id="v2Estop"', 'id="stop"'):
            i = NEW.index(estop)
            before = NEW[:i]
            self.assertEqual(before.count('<details'), before.count('</details>'), estop + ' is inside a collapsible')
        self.assertIn('class="dock"', NEW)

    def test_lab_shortcuts_stay_visible(self):
        nav = NEW[NEW.index('<nav class="hm-labs"'):NEW.index('</nav>', NEW.index('<nav class="hm-labs"'))]
        for href in ('/v2/testlab', '/v2/flysky-testlab', '/v2/vision3d'):
            self.assertIn('href="%s"' % href, nav)
        self.assertNotIn('<details', NEW[NEW.index('<nav class="hm-labs"') - 200:NEW.index('<nav class="hm-labs"')].split('</details>')[-1])

    def test_home_cards_are_read_only(self):
        self.assertNotRegex(CARDS, r"method\s*:")
        self.assertEqual(sorted(set(re.findall(r"fetch\('([^'?]+)", CARDS))), ['/api/lidar-view', '/api/vision3d/summary'])
        self.assertNotIn("'/api/vision3d/status'", CARDS)        # status GET would extend the camera viewer lease
        self.assertNotIn('innerHTML', CARDS)
        for token in ("'e_stop'", 'action:', "'drive'", "action=", '/api/estop'):
            self.assertNotIn(token, CARDS)

    def test_no_external_assets(self):
        for f in ('index.html', 'home.css', 'home-cards.js', 'vision3d.html', 'vision3d.css', 'vision3d.js'):
            text = (V2 / f).read_text()
            self.assertEqual(re.findall(r'(?:src|href)="(https?://(?!project-atlas-jetson)[^"]+)"', text), [], f)
            self.assertNotIn('@import', text)


class VisionLabUi(unittest.TestCase):
    def test_every_element_the_script_uses_exists(self):
        used = set(re.findall(r"\$\('([A-Za-z0-9_]+)'\)", VJS)) | {k + s for k in ('rgb', 'depth', 'ir') for s in ('Image', 'State', 'Meta')}
        present = set(ids(VHTML))
        self.assertEqual(sorted(used - present), [])

    def test_only_existing_vision_routes(self):
        routes = set(re.findall(r"get\('([a-z]+)", VJS)) | set(re.findall(r"get\(`([a-z]+)", VJS))
        self.assertTrue(routes <= {'status', 'frame', 'pixel', 'cloud'}, routes)
        self.assertEqual(re.findall(r"viewer\(\{\s*action:\s*'([a-z]+)'", VJS), ['start', 'stop', 'stop', 'stop'])
        self.assertNotIn('innerHTML', VJS)

    def test_blocked_explanation_uses_measured_values_and_limits(self):
        for text in ('failed.cpu', 'lim.cpu_percent', 'driver_stopped', 'Nothing else on ATLAS was changed'):
            self.assertIn(text, VJS)

    def test_cloud_and_calibration_stay_disabled(self):
        self.assertIn('id="showCloud" disabled', VHTML)
        self.assertIn('Disabled until calibration', VHTML)

    def test_page_has_the_standard_estop_dock(self):
        self.assertIn('id="v2Estop"', VHTML); self.assertIn('/v2/estop.js', VHTML)


class SummaryRoute(unittest.TestCase):
    def handler(self, route):
        class H:
            path = '/api/vision3d/' + route
            wfile = io.BytesIO(); headers = Message()
            def send_response(self, c): self.code = c
            def send_header(*a): pass
            def end_headers(*a): pass
        return H()

    def test_summary_reports_block_without_touching_lease_or_transport(self):
        blocked = {'state': 'RESOURCE BLOCKED', 'reason': 'RESOURCE BLOCKED: CPU', 'limits': {'cpu_percent': 75, 'ram_percent': 80, 'temperature_c': 70},
                   'failed_resources': {'cpu': 80.7785888}, 'driver_stopped': True, 'mode': 'depth'}
        svc = W.VisionService({'viewer_runtime': True, 'topics': {'depth': '/astra/depth/image_raw'}})
        h = self.handler('summary')
        with patch.object(R.SESSION, 'status', return_value=blocked), patch.object(R.SESSION, 'touch') as touch, \
             patch.object(W.VisionService, 'touch') as svc_touch:
            self.assertTrue(W.serve(h, svc))
        touch.assert_not_called(); svc_touch.assert_not_called(); self.assertIsNone(svc.transport)
        data = json.loads(h.wfile.getvalue().split(b'\r\n\r\n')[-1] or h.wfile.getvalue())
        self.assertEqual(h.code, 200)
        self.assertEqual((data['state'], data['cpu_limit_percent'], data['driver_stopped']), ('RESOURCE BLOCKED', 75, True))
        self.assertAlmostEqual(data['blocked_cpu_percent'], 80.7785888)
        self.assertIsNone(data['depth_fps'])

    def test_summary_without_runtime_is_off(self):
        svc = W.VisionService({'topics': {}})
        self.assertEqual(svc.summary()['state'], 'OFF')

    def test_status_route_still_touches_lease(self):
        svc = W.VisionService({'viewer_runtime': True, 'topics': {}})
        with patch.object(R.SESSION, 'status', return_value={'state': 'OFF'}), patch.object(R.SESSION, 'touch') as touch:
            W.serve(self.handler('status'), svc)
        touch.assert_called()


if __name__ == '__main__':
    unittest.main()

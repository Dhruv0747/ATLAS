"""Stage 29 dual-controller dashboard: read-only Xbox input endpoint, its status-web hook, the controller mapping
(checked against the code that runs on the rover) and the FlySky Driving page in a browser for every safety state."""
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'tools/deploy/stage29_flysky_drive'
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(PKG))
import atlas_controller_input_web as IW     # noqa: E402
import insert_controller_input_hooks as HK  # noqa: E402
try:
    from playwright.sync_api import sync_playwright
    HAVE_PW = True
except Exception:       # pragma: no cover
    HAVE_PW = False
V2 = ROOT / 'web/v2'
SRC = lambda p: re.sub(r'/\*[\s\S]*?\*/', '', (V2 / p).read_text())


def node_map():
    code = "const m=require(%r);process.stdout.write(JSON.stringify({XBOX:m.XBOX,FLYSKY:m.FLYSKY,KEYS:m.FLYSKY_KEYS}))" % str(V2 / 'controller-map.js')
    return json.loads(subprocess.run(['node', '-e', code], capture_output=True, text=True, check=True).stdout)


def node_eval(expr):
    code = "const m=require(%r);process.stdout.write(JSON.stringify(%s))" % (str(V2 / 'controller-map.js'), expr)
    return json.loads(subprocess.run(['node', '-e', code], capture_output=True, text=True, check=True).stdout)


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


class InputEndpoint(unittest.TestCase):
    def svc(self):
        self.clock = Clock(); self.started = []
        return IW.InputService(lambda: NS(start=lambda cb: self.started.append(cb), stop=lambda: self.started.append('stop')),
                               clock=self.clock, start_threads=False)

    def test_states_layout_and_bounds(self):
        s = self.svc()
        self.assertEqual(s.state()['xbox']['state'], 'NO_DATA'); self.assertEqual(len(self.started), 1)
        s._on_message([0.0, 0.5, 1.0, -2.0, 0.0, 1.0, 0.0, 0.0], [0, 1] + [0] * 9)
        x = s.state()['xbox']
        self.assertEqual((x['state'], x['layout_ok'], x['axes'][3], x['buttons'][1]), ('LIVE', True, -1.0, 1))
        self.clock.t += 0.6; self.assertEqual(s.state()['xbox']['state'], 'STALE')
        self.clock.t += 3.0; self.assertEqual(s.state()['xbox']['state'], 'LOST')
        s._on_message([0.0] * 6, [0] * 11); self.assertFalse(s.state()['xbox']['layout_ok'])
        for bad in ([float('nan')] * 8, 'x', [0.0] * 40):
            s._on_message(bad, [0] * 11)
        self.assertEqual(s.state()['xbox']['malformed'], 3)
        self.assertTrue(s.state()['read_only'])

    def test_idle_teardown_and_restart(self):
        s = self.svc(); s.state()
        self.clock.t += IW.IDLE_STOP_S + 1; s.reap()
        self.assertIn('stop', self.started); self.assertIsNone(s.transport)
        s.state(); self.assertEqual(sum(1 for x in self.started if x != 'stop'), 2)

    def test_post_refused_and_other_routes_ignored(self):
        sent = {}
        h = NS(path=IW.ROUTE, wfile=NS(write=lambda b: sent.setdefault('body', b)),
               send_response=lambda c: sent.setdefault('code', c), send_header=lambda *a: None, end_headers=lambda: None)
        self.assertTrue(IW.serve(h, post=True, svc=self.svc())); self.assertEqual(sent['code'], 405)
        self.assertFalse(IW.serve(NS(path='/api/other'), svc=self.svc()))

    def test_module_is_read_only(self):
        code = re.sub(r'"""[\s\S]*?"""', '', (ROOT / 'scripts/atlas_controller_input_web.py').read_text())
        for bad in ('create_publisher', 'create_client', 'create_service', 'Twist', 'std_msgs', 'Bool', 'serial', 'socket',
                    'urlopen', 'cmd_vel', 'estop', 'subprocess'):
            self.assertNotIn(bad, code, bad)
        self.assertEqual(code.count('create_subscription('), 1)
        self.assertIn("JOY_TOPIC = '/joy'", code)


class Hook(unittest.TestCase):
    BASE = PKG / 'baseline/atlas_status_web.py.live-983024c3'

    def test_additive_on_live_a3_file_only(self):
        import hashlib
        src = self.BASE.read_text()
        self.assertEqual(hashlib.sha256(src.encode()).hexdigest()[:8], '983024c3')
        out = HK.apply(src); compile(out, 'x', 'exec')
        a, b = src.splitlines(), out.splitlines()
        added = [l for l in b if l not in a]
        self.assertEqual(len(b) - len(a), 3); self.assertEqual(len(added), 2)   # + one 'return'
        it = iter(b); self.assertTrue(all(any(l == m for m in it) for l in a), 'an original line was removed or reordered')
        self.assertTrue(all('atlas_controller_input_web' in l or l.strip() == 'return' for l in added))
        self.assertNotIn('post=True', '\n'.join(added))
        with self.assertRaises(SystemExit):
            HK.apply(out)
        with self.assertRaises(SystemExit):
            HK.apply(src.replace('import atlas_manual_controller_web', 'import something_else'))


class MappingMatchesRover(unittest.TestCase):
    """Every Xbox label must match the code and config that run on the rover; FlySky roles must match the drive config."""

    @classmethod
    def setUpClass(cls):
        cls.m = node_map()
        cls.x = {c['id']: c for c in cls.m['XBOX']}

    def fn(self, cid, group):
        return [f for f in self.x[cid]['functions'] if f['group'] == group]

    def test_teleop_and_stop_bindings(self):
        y = (ROOT / 'config/teleop_twist_joy.yaml').read_text()
        val = lambda k: int(re.search(r'\n\s*' + re.escape(k) + r':\s*(\d+)', y).group(1))
        self.assertEqual(self.x['lb']['button'], val('enable_button')); self.assertEqual(self.x['rb']['button'], val('enable_turbo_button'))
        axis_lin = int(re.search(r'axis_linear:\s*\n\s*x:\s*(\d+)', y).group(1)); axis_yaw = int(re.search(r'axis_angular:\s*\n\s*yaw:\s*(\d+)', y).group(1))
        self.assertEqual(self.fn('ls', 'drive')[0]['axis'], axis_lin); self.assertEqual(self.fn('rs', 'drive')[0]['axis'], axis_yaw)
        self.assertIn('0.52', self.fn('ls', 'drive')[0]['detail']); self.assertIn('0.65', self.fn('ls', 'drive')[0]['detail'])
        self.assertIn('1.20', self.fn('rs', 'drive')[0]['detail']); self.assertIn('1.60', self.fn('rs', 'drive')[0]['detail'])
        rs = (ROOT / 'scripts/atlas_remote_stop.py').read_text(); mux = (ROOT / 'scripts/atlas_cmd_vel_mux.py').read_text()
        self.assertIn('if buttons[1]:', rs); self.assertEqual(self.x['b']['button'], 1); self.assertEqual(self.fn('b', 'stop')[0]['button'], 1)
        self.assertIn("declare_parameter('remote_reset_button', 4)", mux); self.assertEqual(self.fn('lb', 'stop')[0]['button'], 4)
        self.assertIn("reset_hold_s=2.0", rs); self.assertIn('2 s', self.fn('lb', 'stop')[0]['text'])

    def test_camera_bindings(self):
        cam = (ROOT / 'scripts/camera_joystick_node.py').read_text()
        self.assertIn('axes[6]', cam); self.assertIn('axes[7]', cam); self.assertIn('bool(buttons[3])', cam)
        self.assertEqual(sorted(f['axis'] for f in self.fn('dpad', 'camera')), [6, 7]); self.assertEqual(self.fn('y', 'camera')[0]['button'], 3)

    def test_every_xbox_input_is_listed_once_and_unused_ones_say_so(self):
        buttons = sorted(f['button'] for c in self.m['XBOX'] for f in c['functions'] if 'button' in f and f['group'] != 'drive' or ('button' in f and c['id'] == 'rb'))
        self.assertEqual(sorted(set(buttons)), list(range(11)))
        axes = sorted({f['axis'] for c in self.m['XBOX'] for f in c['functions'] if 'axis' in f})
        self.assertEqual(axes, list(range(8)))
        for c in self.m['XBOX']:
            for f in c['functions']:
                if f['group'] == 'none':
                    self.assertTrue(f['text'].lower().endswith('not used'), f)

    def test_flysky_channels_are_the_verified_mapping_and_match_the_drive_config(self):
        f = {c['ch']: c for c in self.m['FLYSKY']}
        self.assertEqual(sorted(f), list(range(1, 11)))
        want = {1: ('right', 'steering'), 2: ('right', 'throttle'), 3: ('left', None), 4: ('left', None), 5: ('SwA', 'arm'),
                6: ('SwB', 'stop'), 7: ('SwC', 'speed'), 8: ('SwD', None), 9: ('VrA', None), 10: ('VrB', None)}
        for ch, (where, role) in want.items():
            self.assertEqual(f[ch]['role'], role, ch)
            self.assertTrue(where in (f[ch].get('stick') or f[ch]['name']), ch)
        self.assertIn('Camera pan', f[9]['camera']); self.assertIn('Camera tilt', f[10]['camera'])      # atlas-flysky-camera
        self.assertNotIn('planned', f[9]); self.assertNotIn('planned', f[10])
        cfg = json.loads((ROOT / 'config/atlas_flysky_drive.json').read_text())
        live_cfg = {'throttle': {'channel': cfg['throttle']['channel']}, 'steering': {'channel': cfg['steering']['channel']},
                    'arm_channel': cfg['arm']['channel'], 'stop_channel': cfg['stop']['channel'], 'speed_mode_channel': cfg['speed_mode']['channel']}
        self.assertEqual(node_eval('m.configMismatches(%s)' % json.dumps(live_cfg)), [])
        bad = dict(live_cfg, steering={'channel': 4})
        self.assertTrue(any('CH4' in x for x in node_eval('m.configMismatches(%s)' % json.dumps(bad))))
        self.assertEqual([k['id'] for k in self.m['KEYS']], ['key1', 'key2'])

    def test_flysky_never_active_unless_enabled_selected_live_and_released(self):
        cfg = {'throttle': {'channel': 2}, 'steering': {'channel': 1}, 'arm_channel': 5, 'stop_channel': 6, 'speed_mode_channel': 7}
        base = dict(config=cfg, enabled=True, controller='FLYSKY', flyskyLive=True, latched=False)
        cases = [({}, 'active'), ({'enabled': False}, 'proposed'), ({'config': None}, 'proposed'), ({'controller': 'XBOX'}, 'inactive'),
                 ({'flyskyLive': False}, 'blocked'), ({'latched': True}, 'blocked'), ({'latched': None}, 'blocked')]
        for over, want in cases:
            ctx = dict(base, **over)
            for i in range(5):
                self.assertEqual(node_eval('m.flyskyFunctionState(m.FLYSKY[%d], %s).state' % (i if i < 2 else i + 2, json.dumps(ctx))), want, (over, i))
        self.assertEqual(node_eval('m.flyskyFunctionState(m.FLYSKY[8], %s).state' % json.dumps(base)), 'active')     # VrA camera
        self.assertEqual(node_eval('m.flyskyFunctionState(m.FLYSKY[8], %s).state' % json.dumps(dict(base, flyskyLive=False))), 'blocked')
        self.assertEqual(node_eval('m.flyskyFunctionState(m.FLYSKY[9], %s).state' % json.dumps(dict(base, controller='XBOX', latched=True))), 'active')
        self.assertEqual(node_eval('m.flyskyFunctionState(m.FLYSKY[2], %s).state' % json.dumps(base)), 'unassigned')

    def test_xbox_drive_only_active_when_xbox_selected_live_and_released(self):
        f = 'm.XBOX[0].functions[0]'
        ok = dict(controller='XBOX', latched=False, xboxLive=True)
        for over, want in [({}, 'active'), ({'latched': True}, 'blocked'), ({'controller': 'FLYSKY'}, 'inactive'), ({'xboxLive': False}, 'blocked')]:
            self.assertEqual(node_eval('m.xboxFunctionState(%s, %s).state' % (f, json.dumps(dict(ok, **over)))), want, over)
        stop = 'm.XBOX[6].functions[0]'   # B
        self.assertEqual(node_eval('m.xboxFunctionState(%s, %s).state' % (stop, json.dumps(dict(ok, controller='FLYSKY', latched=True)))), 'active')


class PageStatic(unittest.TestCase):
    def test_visualisation_is_read_only(self):
        code = SRC('controller-viz.js')
        self.assertEqual(sorted(set(re.findall(r"fetch\('([^']+)'", code))), ['/api/controller_inputs', '/api/flysky/state?history=0'])
        for bad in ('POST', 'method:', '/api/estop', '/api/manual_controller', 'cmd_vel', 'innerHTML', 'outerHTML', 'eval(',
                    'WebSocket', 'XMLHttpRequest', 'localStorage', 'sendBeacon', 'insertAdjacentHTML'):
            self.assertNotIn(bad, code, bad)
        m = SRC('controller-map.js')
        for bad in ('fetch(', 'XMLHttpRequest', 'WebSocket', 'document.', 'innerHTML'):
            self.assertNotIn(bad, m, bad)

    def test_images_are_local_licensed_and_sized(self):
        from PIL import Image
        code = SRC('controller-viz.js')
        self.assertEqual(sorted(set(re.findall(r"'(/v2/assets/[^']+)'", code))), ['/v2/assets/flysky-fs-i6s-front.webp', '/v2/assets/xbox360-controller-black.webp'])
        self.assertIsNone(re.search(r"https?://", code.replace("'http://www.w3.org/2000/svg'", '')))   # only the SVG namespace
        self.assertEqual(Image.open(V2 / 'assets/xbox360-controller-black.webp').size, (1680, 1230))
        self.assertEqual(Image.open(V2 / 'assets/flysky-fs-i6s-front.webp').size, (1416, 1252))
        lic = (V2 / 'assets/CONTROLLER-IMAGES.txt').read_text()
        for needed in ('Evan-Amos', 'Public domain', 'owner', 'xbox360-controller-black.webp', 'flysky-fs-i6s-front.webp'):
            self.assertIn(needed, lic)
        self.assertIn('Evan-Amos', code); self.assertIn('public domain', code)

    def test_page_wiring(self):
        html = (V2 / 'flysky-drive.html').read_text()
        for needed in ('SELECT XBOX', 'SELECT FLYSKY', 'id="useXbox"', 'id="useFlysky"', 'id="cvStage"', 'id="cvLegendBody"', 'id="v2Estop"'):
            self.assertIn(needed, html)
        order = [html.index(s) for s in ('controller-map.js', 'controller-viz.js', 'flysky-drive.js')]
        self.assertEqual(order, sorted(order))
        self.assertIsNone(re.search(r'\son[a-z]+=', html)); self.assertEqual(re.findall(r'(?:src|href)="(https?:)?//', html), [])
        js = SRC('flysky-drive.js')
        self.assertEqual(js.count("dispatchEvent(new CustomEvent('atlas:controller'"), 2)


def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p


@unittest.skipUnless(HAVE_PW, 'playwright not installed')
class PageRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.srv = subprocess.Popen([sys.executable, str(ROOT / 'tools/flysky/drive_sim_server.py'), '--port', str(cls.port)])
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', cls.port), 0.2).close(); break
            except OSError:
                time.sleep(0.05)
        try:
            cls.pw = sync_playwright().start(); cls.browser = cls.pw.chromium.launch()
        except Exception as exc:
            cls.srv.terminate(); raise unittest.SkipTest('chromium unavailable: %s' % exc)
        cls.shots = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.srv.terminate(); cls.srv.wait(5)

    def url(self, p): return 'http://127.0.0.1:%d%s' % (self.port, p)

    def open(self, scenario, w=1440, h=1000):
        urllib.request.urlopen(self.url('/sim?scenario=' + scenario)).read()
        pg = self.browser.new_page(viewport={'width': w, 'height': h}); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        reqs = []
        pg.on('request', lambda r: reqs.append((r.method, r.url)))
        pg.goto(self.url('/v2/flysky-drive')); pg.wait_for_timeout(1400)
        return pg, errs, reqs

    def txt(self, pg, sel): return pg.inner_text(sel)

    def test_xbox_mode_default_live_highlights_and_no_commands(self):
        pg, errs, reqs = self.open('xbox_demo')
        self.assertIn('Selected remote: Xbox', self.txt(pg, '#cvSel')); self.assertEqual(pg.get_attribute('#cvTabX', 'aria-selected'), 'true')
        self.assertEqual(pg.get_attribute('#useXbox', 'aria-pressed'), 'true'); self.assertIn('Selected', self.txt(pg, '#useXbox'))
        self.assertIn('Xbox connected', self.txt(pg, '#cvSignal')); self.assertIn('E-STOP latched', self.txt(pg, '#cvEstop'))
        self.assertGreater(pg.locator('#cvStage .cv-hit.hot, #cvStage .cv-hidden.hot').count(), 3)
        self.assertEqual(pg.locator('#cvStage image[href="/v2/assets/xbox360-controller-black.webp"]').count(), 1)
        for cid in ('y', 'dLeft', 'dpad', 'ls', 'rs'):     # pressed or moved in this scene
            self.assertIn('hot', pg.get_attribute('#cvStage [data-id="%s"]' % cid, 'class'), cid)
        self.assertNotIn('hot', pg.get_attribute('#cvStage [data-id="b"]', 'class'))
        legend = self.txt(pg, '#cvLegendBody').lower()
        for s in ('remote stop', 'hold to drive', 'camera pan', 'camera tilt', 'camera home', 'not used', 'turbo', 'e-stop reset'):
            self.assertIn(s, legend)
        self.assertGreater(pg.locator('#cvLegendBody tr.hot').count(), 2)
        self.assertIn('Blocked', pg.inner_text('#cvLegendBody tr:first-child'))   # drive while latched
        posts = [u for m, u in reqs if m != 'GET']
        self.assertEqual(posts, []); pg.screenshot(path=str(self.shots / 'xbox.png')); self.assertEqual(errs, []); pg.close()

    def test_flysky_blocked_shows_exact_reason_and_preview_never_claims_selection(self):
        pg, errs, reqs = self.open('live')
        self.assertTrue(pg.is_disabled('#useFlysky')); self.assertIn('Blocked', self.txt(pg, '#useFlysky'))
        self.assertIn('FlySky driving is disabled on this rover', self.txt(pg, '#selNote'))
        pg.click('#cvTabF'); pg.wait_for_timeout(900)
        self.assertIn('Preview only', self.txt(pg, '#cvViewNote')); self.assertIn('Selected remote: Xbox', self.txt(pg, '#cvSel'))
        self.assertEqual(pg.get_attribute('#useFlysky', 'aria-pressed'), 'false')
        legend = self.txt(pg, '#cvLegendBody')
        drive_rows = [r for r in legend.split('\n') if any(k in r for k in ('CH1', 'CH2', 'SwA', 'SwB', 'SwC'))]
        self.assertTrue(drive_rows); self.assertFalse(any('Active' in r for r in drive_rows), drive_rows)   # driving never shown active
        self.assertIn('Proposed', legend); self.assertIn('Camera pan', legend)
        self.assertIn('CH5', legend); self.assertIn('240', legend)
        # the backend refuses too, with the same reason, and nothing changes
        req = urllib.request.Request(self.url('/api/manual_controller'), data=b'{"target": "FLYSKY"}', method='POST',
                                     headers={'Content-Type': 'application/json', 'X-Atlas-Controller': '1', 'Origin': self.url(''), 'Host': '127.0.0.1:%d' % self.port})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 409)
        self.assertEqual(json.loads(urllib.request.urlopen(self.url('/api/manual_controller')).read())['policy']['manual_controller'], 'XBOX')
        self.assertEqual([u for m, u in reqs if m != 'GET'], []); self.assertEqual(errs, []); pg.close()

    def test_flysky_selected_follows_view_and_functions_blocked_until_released(self):
        pg, errs, _ = self.open('flysky_selected')
        self.assertEqual(pg.get_attribute('#cvTabF', 'aria-selected'), 'true'); self.assertIn('Selected remote: FlySky', self.txt(pg, '#cvSel'))
        self.assertEqual(pg.get_attribute('#useFlysky', 'aria-pressed'), 'true')
        rows = self.txt(pg, '#cvLegendBody'); self.assertIn('Blocked', rows)
        drive = rows.split('Switch SwD')[0]                     # CH1..SwC: the drive rows (the camera knobs follow SwD)
        self.assertIn('CH1', drive); self.assertNotIn('Active', drive)
        pg.close()
        pg, errs, _ = self.open('flysky_armed')
        self.assertIn('Active', self.txt(pg, '#cvLegendBody').split('Switch SwD')[0]); self.assertIn('Command source: FlySky', self.txt(pg, '#cvSrc'))
        self.assertIn('FlySky driving enabled', self.txt(pg, '#cvGate'))
        pg.screenshot(path=str(self.shots / 'flysky_armed.png')); self.assertEqual(errs, []); pg.close()

    def test_signal_loss_states(self):
        for scen, view, pill, alert in (('rc_lost', 'F', 'FlySky: signal', 'receiver frame'),
                                        ('rc_failsafe', 'F', 'receiver failsafe', None),
                                        ('xbox_lost', 'X', 'Xbox', 'No live Xbox input'),
                                        ('no_input_api', 'X', 'not installed', 'not installed')):
            pg, errs, _ = self.open(scen)
            if view == 'F':
                pg.click('#cvTabF'); pg.wait_for_timeout(4200 if scen == 'rc_lost' else 900)
            self.assertIn(pill.lower(), self.txt(pg, '#cvSignal').lower(), scen)
            self.assertIn('fail' if scen != 'no_input_api' else 'warn', pg.get_attribute('#cvSignal', 'class'), scen)
            if alert:
                self.assertTrue(pg.is_visible('#cvLost'), scen); self.assertIn(alert, self.txt(pg, '#cvLost'), scen)
            if scen in ('rc_lost', 'rc_failsafe'):
                self.assertNotIn('Active', self.txt(pg, '#cvLegendBody'))
            if scen == 'xbox_lost':
                self.assertIn('Blocked', pg.inner_text('#cvLegendBody'))
            self.assertEqual(errs, [], scen); pg.close()

    def geometry(self, pg, sel):
        return pg.evaluate('''(sel) => { const img = document.querySelector('#cvStage image').getBoundingClientRect();
            const el = document.querySelector(sel).getBoundingClientRect();
            return {fx: (el.x + el.width / 2 - img.x) / img.width, fy: (el.y + el.height / 2 - img.y) / img.height,
                    aspect: img.width / img.height}; }''', sel)

    def test_photo_overlays_stay_aligned_and_photos_are_not_stretched(self):
        # B button centre in the original photo: (2910, 710) -> crop (0, 40, 3360, 2460); right stick (2113, 793)
        expect = {'XBOX': (1680 / 1230, {'#cvStage [data-id="b"]': (2910 / 3360, (710 - 40) / 2460), '#cvStage [data-id="rs"]': (2113 / 3360, (793 - 40) / 2460)}),
                  'FLYSKY': (1416 / 1252, {'#cvStage [data-id="swb"]': (488 / 1416, 140 / 1252), '#cvStage [data-id="swd"]': (1115 / 1416, 170 / 1252)})}
        seen = {}
        for w, h in ((1440, 1000), (1024, 768), (390, 844)):
            for scen, tab, kind in (('xbox_demo', 'X', 'XBOX'), ('flysky_demo', 'F', 'FLYSKY')):
                pg, errs, _ = self.open(scen, w, h)
                pg.click('#cvTab' + tab); pg.wait_for_timeout(500)
                g = self.geometry(pg, '#cvStage .cv-ov ellipse, #cvStage .cv-ov circle')
                self.assertAlmostEqual(g['aspect'], expect[kind][0], delta=0.01, msg=(w, kind))     # never stretched
                for sel, (fx, fy) in expect[kind][1].items():
                    gg = self.geometry(pg, sel)
                    self.assertAlmostEqual(gg['fx'], fx, delta=0.01, msg=(w, sel)); self.assertAlmostEqual(gg['fy'], fy, delta=0.01, msg=(w, sel))
                seen.setdefault(kind, []).append((round(g['fx'], 3), round(g['fy'], 3)))
                self.assertEqual(errs, []); pg.close()
        for kind, pts in seen.items():                       # the same overlay sits at the same place on the photo at every size
            self.assertLess(max(p[0] for p in pts) - min(p[0] for p in pts), 0.005, kind)
            self.assertLess(max(p[1] for p in pts) - min(p[1] for p in pts), 0.005, kind)

    def test_missing_photo_falls_back_honestly(self):
        urllib.request.urlopen(self.url('/sim?scenario=flysky_demo')).read()
        pg = self.browser.new_page(viewport={'width': 1280, 'height': 900})
        pg.route('**/assets/*.webp', lambda r: r.abort())
        pg.goto(self.url('/v2/flysky-drive')); pg.wait_for_timeout(1200)
        self.assertEqual(pg.locator('#cvStage svg.cv-schematic').count(), 1)    # Xbox: accurate schematic fallback
        self.assertEqual(pg.locator('#cvStage image').count(), 0)
        pg.click('#cvTabF'); pg.wait_for_timeout(1200)
        self.assertIn('could not be loaded', pg.inner_text('#cvStage'))
        self.assertIn('Proposed', pg.inner_text('#cvLegendBody')); pg.close()

    def test_switch_indicator_shows_live_position(self):
        pg, errs, _ = self.open('flysky_demo')
        pg.click('#cvTabF'); pg.wait_for_timeout(900)
        on = pg.evaluate("[...document.querySelectorAll('#cvStage .cv-swdot.on')].map(d => d.getAttribute('data-pos'))")
        self.assertEqual(sorted(on), sorted(['down', 'up', 'middle', 'up']))          # SwA down, SwB up, SwC middle, SwD up
        pg.close()

    def test_config_mismatch_is_shown(self):
        pg, errs, _ = self.open('mismatch')
        self.assertTrue(pg.is_visible('#cvMismatch')); self.assertIn('CH4', self.txt(pg, '#cvMismatch')); pg.close()

    def test_responsive_no_horizontal_scroll(self):
        for w, h in ((390, 844), (820, 1180), (1280, 800)):
            for scen, tab in (('xbox_demo', 'X'), ('flysky_demo', 'F')):
                pg, errs, _ = self.open(scen, w, h)
                pg.click('#cvTab' + tab); pg.wait_for_timeout(500)
                self.assertFalse(pg.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth'), (w, scen))
                self.assertTrue(pg.is_visible('#cvStage svg'))
                narrow = w <= 760
                self.assertEqual(pg.evaluate("document.querySelector('#cvStage svg').classList.contains('narrow')"), narrow)
                self.assertEqual(errs, []); pg.close()


if __name__ == '__main__':
    unittest.main()

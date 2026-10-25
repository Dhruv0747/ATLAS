"""Offline tests for issue #11 camera settings (no hardware, no ROS, no systemd)."""
import io, json, os, sys, tempfile, types, unittest, importlib.util
from pathlib import Path
from unittest import mock
NEW = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(NEW))
TMP = Path(tempfile.mkdtemp())
os.environ['ATLAS_CAMERA_SETTINGS'] = str(TMP / 'camera_settings.json')
os.environ['ATLAS_CAMERA_SETTINGS_LOG'] = str(TMP / 'log.jsonl')
import atlas_camera_settings as S
import uvc_descriptors as U

JOURNAL = """GST_ARGUS: Creating output stream
GST_ARGUS: Available Sensor modes :
GST_ARGUS: 4608 x 2592 FR = 14.000001 fps Duration = 71428568 ; Analog Gain range min 1.000000, max 16.000000; Exposure Range min 500000, max 65487000;
GST_ARGUS: 2304 x 1296 FR = 55.000001 fps Duration = 18181818 ; Analog Gain range min 1.000000, max 16.000000; Exposure Range min 500000, max 65487000;
GST_ARGUS: 1536 x 864 FR = 90.000001 fps Duration = 11111111 ; Analog Gain range min 1.000000, max 16.000000; Exposure Range min 500000, max 65487000;
GST_ARGUS: Running with following settings:
   Camera index = 0
   Camera mode  = 2
   Output Stream W = 1536 H = 864
   seconds to Run    = 0
   Frame Rate = 90.000001
[INFO] [1792904489.6] [atlas_camera_node]: Camera node started, pipeline: nvarguscamerasrc sensor-id=0 ee-mode=2 ee-strength=0.6 tnr-mode=2 tnr-strength=0.35 exposurecompensation=0.25 saturation=1.2 wbmode=1 ! video/x-raw(memory:NVMM),width=1280,height=720,framerate=10/1 ! nvvidconv ! appsink drop=1 max-buffers=1
"""
DET = S.picam_detected(JOURNAL)
ADET = {'depth': ['160x120@30', '320x240@30', '640x480@30', '1280x1024@7'], 'ir': ['640x480@30', '640x400@30'],
        'color': ['320x240@15', '320x240@30', '640x480@30', '1280x720@30'], 'controls': {}, 'not_served': {'ir': ['320x240@30']}}


def uvc_frame(sub, w, h, fps):
    iv = [int(1e7 / f) for f in fps]
    body = bytes([sub, 1, 0]) + w.to_bytes(2, 'little') + h.to_bytes(2, 'little') + bytes(12) + iv[0].to_bytes(4, 'little') + bytes([len(iv)])
    body += b''.join(i.to_bytes(4, 'little') for i in iv)
    return bytes([len(body) + 2, 0x24]) + body


class Capabilities(unittest.TestCase):
    def test_argus_modes_and_current(self):
        self.assertEqual([(m['width'], m['height'], m['max_fps']) for m in DET['modes']], [(4608, 2592, 14.0), (2304, 1296, 55.0), (1536, 864, 90.0)])
        c = DET['current']
        self.assertEqual((c['width'], c['height'], c['framerate'], c['sensor_mode'], c['stream_w'], c['stream_h']), (1280, 720, 10, 2, 1536, 864))

    def test_uvc_descriptor_parser(self):
        fmt = bytes([11, 0x24, 0x06, 1, 2]) + bytes(6)
        raw = fmt + uvc_frame(0x07, 640, 480, [30, 15]) + uvc_frame(0x07, 320, 240, [30, 15])
        self.assertEqual(U.parse(raw), [{'format': 'MJPEG', 'sizes': [{'w': 640, 'h': 480, 'fps': [30.0, 15.0]}, {'w': 320, 'h': 240, 'fps': [30.0, 15.0]}]}])

    def test_astra_detected_from_real_enumeration(self):
        d = S.astra_detected(NEW.parent / 'config/astra_detected_capabilities.json', usb_find=lambda: {'rgb': 'x'},
                             uvc_read=lambda p: [{'format': 'MJPEG', 'sizes': [{'w': 320, 'h': 240, 'fps': [30.0, 15.0]}]}])
        self.assertEqual(d['depth'], ['160x120@30', '320x240@30', '640x480@30', '1280x1024@7'])
        self.assertNotIn('320x240@30', d['ir']); self.assertIn('640x480@30', d['ir'])
        self.assertEqual(d['color'], ['320x240@30', '320x240@15'])
        self.assertFalse(d['controls']['ir_gain']); self.assertEqual(d['serial'], '17122120830')

    def test_astra_rgb_missing_does_not_crash(self):
        d = S.astra_detected(NEW.parent / 'config/astra_detected_capabilities.json', usb_find=lambda: (_ for _ in ()).throw(RuntimeError('unplugged')))
        self.assertEqual(d['color'], []); self.assertIn('unavailable', d['source']['color'])


class Validation(unittest.TestCase):
    def test_astra_rejects_unsupported(self):
        for bad in ({'depth': '800x600@30'}, {'ir': '320x240@30'}, {'color': '1920x1080@30'}, {'depth': 'abc'}, {'laser': True}):
            with self.assertRaises(S.SettingsError, msg=bad): S.validate_astra(bad, ADET)
        self.assertEqual(S.validate_astra({'depth': '640x480@30'}, ADET)['depth'], '640x480@30')

    def test_picam_rejects_unsupported(self):
        for bad in ({'framerate': 91}, {'framerate': 0}, {'framerate': 10.5}, {'width': 1000, 'height': 700}, {'sensor_mode': 7},
                    {'sensor_mode': 0, 'framerate': 20}, {'saturation': 3}, {'white_balance_mode': 12}, {'ae_lock': 'yes'},
                    {'jpeg_quality': 99}, {'hdr': True}, {'framerate': True}):
            with self.assertRaises(S.SettingsError, msg=bad): S.validate_picam(bad, DET)
        ok = S.validate_picam({'sensor_mode': 1, 'width': 1920, 'height': 1080, 'framerate': 30}, DET)
        self.assertEqual((ok['width'], ok['framerate']), (1920, 30))
        self.assertEqual(S.validate_picam({'framerate': 90, 'width': 1280, 'height': 720}, DET)['framerate'], 90)

    def test_picam_no_modes_refuses(self):
        with self.assertRaises(S.SettingsError): S.validate_picam({}, {'modes': [], 'current': {}})


class Persistence(unittest.TestCase):
    def setUp(self):
        Path(os.environ['ATLAS_CAMERA_SETTINGS']).unlink(missing_ok=True)

    def test_defaults_give_exact_previous_launch(self):
        unit = "-p width:=1280 -p height:=720 -p framerate:=10 -p jpeg_quality:=75 -p edge_enhancement:=0.60 -p noise_reduction:=0.35 -p exposure_compensation:=0.25 -p saturation:=1.20 -p white_balance_mode:=1"
        self.assertEqual(' '.join(S.picam_ros_args(detected=DET)), unit)
        self.assertEqual(S.astra_driver_values(detected=ADET), {'depth_width': '160', 'depth_height': '120', 'depth_fps': '30', 'color_width': '320',
                         'color_height': '240', 'color_fps': '15', 'ir_width': '640', 'ir_height': '480', 'ir_fps': '30'})

    def test_save_roundtrip_previous_and_args(self):
        S.save_camera('picam', S.validate_picam({'sensor_mode': 1, 'width': 1920, 'height': 1080, 'framerate': 30, 'rotate_180': False, 'ae_antibanding': 2}, DET))
        a = ' '.join(S.picam_ros_args(detected=DET))
        self.assertIn('width:=1920', a); self.assertIn('sensor_mode:=1', a); self.assertIn('rotate_180:=false', a); self.assertIn('ae_antibanding:=2', a)
        S.save_camera('picam', dict(S.PICAM_DEFAULTS))
        self.assertEqual(S.load_all()['previous']['picam']['width'], 1920)

    def test_corrupt_or_invalid_saved_falls_back(self):
        Path(os.environ['ATLAS_CAMERA_SETTINGS']).write_text('{not json')
        self.assertIn('width:=1280', ' '.join(S.picam_ros_args(detected=DET)))
        Path(os.environ['ATLAS_CAMERA_SETTINGS']).write_text(json.dumps({'schema': 1, 'picam': {'framerate': 500}, 'astra': {'depth': '999x999@30'}}))
        self.assertIn('framerate:=10', ' '.join(S.picam_ros_args(detected=DET)))
        self.assertEqual(S.astra_driver_values(detected=ADET)['depth_width'], '160')


class Runtime(unittest.TestCase):
    def load(self, name):
        sys.modules.pop('atlas_vision3d_runtime', None)
        path = NEW / 'atlas_vision3d_runtime.py'
        if name == 'orig':   # baseline = the file before issue #11 (git), written to a temp copy
            import subprocess
            path = TMP / 'atlas_vision3d_runtime_orig.py'
            path.write_bytes(subprocess.check_output(['git', 'show', 'HEAD~0:project_atlas/scripts/atlas_vision3d_runtime.py'], cwd=NEW.parents[1]) if os.environ.get('CAMSET_BASELINE') is None else Path(os.environ['CAMSET_BASELINE']).read_bytes())
        spec = importlib.util.spec_from_file_location('rt_' + name, path)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

    def test_driver_args_identical_with_defaults_and_changed_with_settings(self):
        Path(os.environ['ATLAS_CAMERA_SETTINGS']).unlink(missing_ok=True)
        old, new = self.load('orig'), self.load('new')
        with mock.patch.object(S, 'astra_detected', return_value=ADET):
            for mode in old.VIEW_MODES:
                self.assertEqual(old.driver_args(mode), new.driver_args(mode), mode)
            S.save_camera('astra', {'depth': '640x480@30', 'color': '640x480@30', 'ir': '640x400@30'})
            a = new.driver_args('ir_depth'); s = ' '.join(a)
            self.assertIn('depth_width:=640', s); self.assertIn('ir_height:=400', s)
            self.assertNotIn('ir_width', ' '.join(new.driver_args('depth')))   # IR params still only when IR is requested
        Path(os.environ['ATLAS_CAMERA_SETTINGS']).unlink(missing_ok=True)


class FakeHandler:
    def __init__(self, path, body=None, headers=None):
        self.path = path; self.status = None; self.sent = {}; self.wfile = io.BytesIO()
        raw = json.dumps(body).encode() if body is not None else b''
        self.rfile = io.BytesIO(raw)
        from email.message import Message
        h = Message()
        for k, v in {'Content-Type': 'application/json', 'Content-Length': str(len(raw)), 'Host': '192.168.1.16:8088',
                     'Origin': 'http://192.168.1.16:8088', 'X-Atlas-Camera': '1', **(headers or {})}.items():
            if v is not None: h[k] = v
        self.headers = h
    def send_response(self, code): self.status = code
    def send_header(self, k, v): self.sent[k] = v
    def end_headers(self): pass
    def json(self): return json.loads(self.wfile.getvalue())


class FakeRos:
    def __init__(self, latched=True, manual=True, mission='READY', age=0.2):
        self.v = {'control_policy': {'value': json.dumps({'stop_latched': latched, 'manual_only': manual, 'commission_armed': False}), 'age': age},
                  'mission_status': {'value': mission, 'age': 0.3}, 'camera_info': {'value': {}, 'age': 0.5, 'observed_hz': 9.8}}
    def snapshot(self): return self.v


wifi = types.ModuleType('atlas_wifi_web'); wifi.same_origin = lambda h: h.get('Origin', '').endswith(h.get('Host', '?')); sys.modules['atlas_wifi_web'] = wifi
v3d = types.ModuleType('atlas_vision3d_web'); v3d.SERVICE = types.SimpleNamespace(summary=lambda: {'state': 'OFF', 'usb': {'state': 'CONNECTED', 'port': '2.3.4'}, 'depth_fps': None}); sys.modules['atlas_vision3d_web'] = v3d
import atlas_camera_settings_web as WEB


class Web(unittest.TestCase):
    def setUp(self):
        Path(os.environ['ATLAS_CAMERA_SETTINGS']).unlink(missing_ok=True); WEB._cache.clear(); WEB._last_apply['t'] = 0.0
        self.p1 = mock.patch.object(S, 'picam_detected', return_value=DET); self.p1.start()
        self.p2 = mock.patch.object(S, 'astra_detected', return_value=ADET); self.p2.start()
        self.calls = []
        def fake_systemctl(*a, timeout=10):
            self.calls.append(a); return types.SimpleNamespace(stdout='active\n', returncode=0)
        self.p3 = mock.patch.object(WEB, '_systemctl', side_effect=fake_systemctl); self.p3.start()
    def tearDown(self): mock.patch.stopall()

    def req(self, path, body=None, post=False, ros=None, **h):
        hd = FakeHandler(path, body, h); self.assertTrue(WEB.serve(hd, ros or FakeRos(), post=post)); return hd

    def test_summary(self):
        j = self.req('/api/cameras/summary').json()
        self.assertEqual(j['astra']['connection'], 'CONNECTED'); self.assertEqual(j['picam']['running']['framerate'], 10)
        self.assertEqual(j['picam']['measured_fps'], 9.8); self.assertEqual(j['picam']['apply_blocked'], [])
        self.assertFalse(any(c[0] == 'restart' for c in self.calls))   # page load never restarts anything

    def test_capabilities_and_unknown(self):
        self.assertEqual(self.req('/api/cameras/picam/capabilities').json()['options']['1']['max_fps']['1920x1080'], 55)
        self.assertEqual(self.req('/api/cameras/nope').status, 404)

    def test_post_requires_header_and_origin(self):
        self.assertEqual(self.req('/api/cameras/astra', {'action': 'validate', 'settings': {}}, post=True, **{'X-Atlas-Camera': None}).status, 403)
        self.assertEqual(self.req('/api/cameras/astra', {'action': 'validate', 'settings': {}}, post=True, Origin='http://evil.example').status, 403)

    def test_validate_rejects_with_400_and_logs(self):
        h = self.req('/api/cameras/picam', {'action': 'validate', 'settings': {'framerate': 200}}, post=True)
        self.assertEqual(h.status, 400); self.assertIn('frame rate', h.json()['error'])
        self.assertIn('settings_rejected', Path(os.environ['ATLAS_CAMERA_SETTINGS_LOG']).read_text())

    def test_astra_apply_saves_without_restart(self):
        h = self.req('/api/cameras/astra', {'action': 'apply', 'settings': {'depth': '320x240@30', 'color': '320x240@15', 'ir': '640x480@30'}}, post=True)
        self.assertEqual(h.status, 200); self.assertEqual(S.stored('astra')[0]['depth'], '320x240@30')
        self.assertFalse(any(c[0] == 'restart' for c in self.calls))

    def test_picam_apply_refused_unless_parked(self):
        for ros in (FakeRos(latched=False), FakeRos(manual=False), FakeRos(mission='RUNNING'), FakeRos(age=9)):
            WEB._last_apply['t'] = 0.0
            h = self.req('/api/cameras/picam', {'action': 'apply', 'settings': {'framerate': 15}}, post=True, ros=ros)
            self.assertEqual(h.status, 403, ros.v); self.assertFalse(any(c[0] == 'restart' for c in self.calls))
        self.assertFalse(Path(os.environ['ATLAS_CAMERA_SETTINGS']).exists())

    def test_picam_apply_refused_during_vision_session(self):
        with mock.patch.object(WEB, '_vision', return_value={'state': 'ACTIVE'}):
            self.assertEqual(self.req('/api/cameras/picam', {'action': 'apply', 'settings': {'framerate': 15}}, post=True).status, 403)

    def test_picam_apply_success(self):
        with mock.patch.object(WEB, '_wait_camera_started', return_value=(True, 'Camera node started')):
            h = self.req('/api/cameras/picam', {'action': 'apply', 'settings': {'framerate': 15}}, post=True)
        self.assertEqual(h.status, 200); self.assertEqual(S.stored('picam')[0]['framerate'], 15)
        self.assertEqual([c for c in self.calls if c[0] == 'restart'], [('restart', 'atlas-camera.service')])

    def test_picam_apply_failure_reverts(self):
        S.save_camera('picam', S.validate_picam({'framerate': 12}, DET))
        with mock.patch.object(WEB, '_wait_camera_started', side_effect=[(False, 'Traceback'), (True, 'ok')]):
            h = self.req('/api/cameras/picam', {'action': 'apply', 'settings': {'framerate': 15}}, post=True)
        self.assertEqual(h.status, 409); self.assertEqual(S.stored('picam')[0]['framerate'], 12)
        self.assertEqual(len([c for c in self.calls if c[0] == 'restart']), 2)
        log = Path(os.environ['ATLAS_CAMERA_SETTINGS_LOG']).read_text(); self.assertIn('picam_apply_failed', log); self.assertIn('picam_revert', log)

    def test_rate_limit(self):
        with mock.patch.object(WEB, '_wait_camera_started', return_value=(True, 'ok')):
            self.assertEqual(self.req('/api/cameras/picam', {'action': 'apply', 'settings': {'framerate': 15}}, post=True).status, 200)
            self.assertEqual(self.req('/api/cameras/picam', {'action': 'apply', 'settings': {'framerate': 12}}, post=True).status, 403)


if __name__ == '__main__':
    unittest.main()

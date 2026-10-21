"""Stage32 infrared viewer: offline gates. Synthetic IR messages only; no camera, ROS or service."""
import hashlib
import io
import json
import os
import struct
import subprocess
import sys
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_vision3d_runtime as R   # noqa: E402
import atlas_vision3d_web as W       # noqa: E402

MANIFEST = ROOT / 'config/vision3d_live.json'


def ir_msg(w=8, h=6, encoding='mono8', t=100.0, big=False):
    if encoding == 'mono8':
        data = bytes((x * 30 + y * 7) % 256 for y in range(h) for x in range(w)); step = w
    else:
        data = b''.join(struct.pack(('>' if big else '<') + 'H', (x * 900 + y * 50) % 65536) for y in range(h) for x in range(w)); step = 2 * w
    return N(width=w, height=h, encoding=encoding, step=step, is_bigendian=big, data=data,
             header=N(frame_id='astra_ir_optical_frame', stamp=N(sec=int(t), nanosec=int((t % 1) * 1e9))))


def service(t=100.0):
    return W.VisionService({'topics': {'ir': '/astra/ir/image_raw'}}, clock=lambda: t, wall=lambda: t)


class Driver(unittest.TestCase):
    def old_runtime(self):
        try:
            src = subprocess.run(['git', 'show', 'abf375b:project_atlas/scripts/atlas_vision3d_runtime.py'], cwd=ROOT, capture_output=True, check=True).stdout
        except Exception:
            self.skipTest('git history unavailable')
        ns = {'__name__': 'old_runtime', '__file__': str(ROOT / 'scripts/atlas_vision3d_runtime.py')}
        exec(compile(src, 'old_runtime', 'exec'), ns); return ns

    def test_depth_and_rgb_depth_launch_arguments_are_byte_identical_to_deployed(self):
        old = self.old_runtime()
        for mode in ('depth', 'concurrent'):
            self.assertEqual(R.driver_args(mode), old['driver_args'](mode), mode)

    def test_ir_modes_request_exactly_the_intended_streams(self):
        def params(mode):
            a = R.driver_args(mode); return dict(a[i + 1].split(':=') for i in range(len(a)) if a[i] == '-p')
        p = params('ir')
        self.assertEqual((p['enable_ir'], p['enable_depth'], p['enable_color'], p['use_uvc_camera']), ('true', 'false', 'false', 'false'))
        self.assertEqual((p['ir_width'], p['ir_height'], p['ir_fps']), ('320', '240', '30'))
        p = params('ir_depth'); self.assertEqual((p['enable_ir'], p['enable_depth'], p['enable_color']), ('true', 'true', 'false'))
        p = params('rgb_ir'); self.assertEqual((p['enable_ir'], p['enable_depth'], p['enable_color'], p['use_uvc_camera']), ('true', 'false', 'true', 'true'))
        for mode in R.VIEW_MODES:
            p = params(mode)
            for k in ('enable_point_cloud', 'enable_colored_point_cloud', 'depth_registration', 'publish_tf'):
                self.assertEqual(p[k], 'false', (mode, k))
        for bad in ('ir_rgb_depth', 'cloud', ''):
            with self.assertRaises(ValueError): R.driver_args(bad)

    def test_negotiation_lines_keep_only_mode_information(self):
        log = ('[INFO] [astra]: set ir video mode resolution: 320x240@30Hz format: GRAY8\n'
               '[INFO] [astra]: ir is started\n[INFO] [astra]: frame 1 published\n'
               '[WARN] [astra]: Video mode resolution: 320x240@30Hz format: GRAY8 is not supported. \n'
               '[INFO] [astra]: Supported video modes: \n')
        lines = R.negotiation_lines(log)
        self.assertEqual(len(lines), 4); self.assertNotIn('frame 1 published', ' '.join(lines))

    def test_driver_log_is_on_tmpfs_beside_state_and_bounded(self):
        self.assertEqual(R.driver_log().parent, R.STATE.parent)
        self.assertLessEqual(R.DRIVER_LOG_MAX, 2 * 1024 * 1024)
        src = (ROOT / 'scripts/atlas_vision3d_runtime.py').read_text()
        self.assertIn('os.truncate(driver_log(),0)', src); self.assertIn('f.read(65536)', src)


class Manifest(unittest.TestCase):
    def test_live_manifest_lists_ir_topics_and_mode_support(self):
        with patch.dict(os.environ, {'ATLAS_VISION3D_MANIFEST': str(MANIFEST)}):
            m = W.read_manifest()
        self.assertEqual(m['topics']['ir'], '/astra/ir/image_raw'); self.assertEqual(m['topics']['ir_info'], '/astra/ir/camera_info')
        self.assertEqual(m['mode_support']['depth']['state'], 'verified')
        for k in ('ir', 'ir_depth', 'rgb_ir', 'concurrent'):
            self.assertEqual(m['mode_support'][k]['state'], 'untested', k)   # never claimed before a live test

    def test_invalid_mode_support_rejected(self):
        base = json.loads(MANIFEST.read_text())
        for bad in ({'ir': {'state': 'works'}}, {'xray': {'state': 'verified'}}, {'ir': 'yes'}):
            m = dict(base, mode_support=bad); p = ROOT / 'tests' / '_tmp_manifest.json'; p.write_text(json.dumps(m))
            try:
                with patch.dict(os.environ, {'ATLAS_VISION3D_MANIFEST': str(p)}), self.assertRaises(ValueError): W.read_manifest()
            finally: p.unlink()


class Ingest(unittest.TestCase):
    def test_native_ir_is_accepted_and_served_byte_exact(self):
        for enc in ('mono8', 'mono16'):
            s = service(); msg = ir_msg(encoding=enc); s.ingest('ir', msg)
            self.assertEqual(s.status()['streams']['ir']['state'], 'ACTIVE')
            body, headers = s.raw('ir')
            self.assertEqual(body, msg.data)                     # no conversion, scaling or fabrication on the Jetson
            self.assertEqual((headers['X-Width'], headers['X-Height'], headers['X-Encoding'], headers['X-Step']), ('8', '6', enc, str(msg.step)))

    def test_non_ir_encodings_are_rejected_not_converted(self):
        for enc in ('rgb8', 'bgr8', '32FC1'):
            s = service(); m = ir_msg(); m.encoding = enc; s.ingest('ir', m)
            st = s.status()['streams']['ir']
            self.assertNotEqual(st['state'], 'ACTIVE', enc); self.assertEqual(st['rejected'], 1)
            with self.assertRaises(ValueError): s.raw('ir')

    def test_stale_ir_is_not_served(self):
        s = W.VisionService({'topics': {'ir': '/x'}}, clock=lambda: 100.0, wall=lambda: 103.5)
        s.ingest('ir', ir_msg(t=100.0))
        with self.assertRaisesRegex(ValueError, 'stale'): s.raw('ir')

    def test_raw_route_only_for_ir_and_no_lease_side_effects_beyond_status(self):
        s = service(); s.ingest('depth', N(width=2, height=1, encoding='16UC1', step=4, is_bigendian=False, data=b'\0\0\0\0',
                                         header=N(frame_id='d', stamp=N(sec=100, nanosec=0))))
        with self.assertRaises(ValueError): s.raw('depth')

    def test_http_raw_route(self):
        s = service(); s.ingest('ir', ir_msg())
        class H:
            path = '/api/vision3d/raw?kind=ir'; wfile = io.BytesIO(); headers = Message(); sent = {}
            def send_response(self, c): self.code = c
            def send_header(self, k, v): self.sent[k] = v
            def end_headers(self): pass
        h = H()
        with patch.object(s, 'touch'):
            W.serve(h, s)
        self.assertEqual(h.code, 200); self.assertEqual(h.sent['Content-Type'], 'application/octet-stream')
        self.assertEqual(h.sent['X-Encoding'], 'mono8'); self.assertTrue(h.wfile.getvalue().endswith(ir_msg().data))

    def test_ir_camera_info_is_metadata_only(self):
        self.assertEqual(W.TYPES['ir_info'], 'sensor_msgs/msg/CameraInfo')
        s = service(); s.ingest('ir_info', N(width=320, height=240, header=N(frame_id='astra_ir_optical_frame', stamp=N(sec=100, nanosec=0))))
        self.assertIn('NOT admitted', s.status()['camera_info']['ir_info']['note'])

    def test_point_cloud_still_blocked_for_viewer_runtime(self):
        s = W.VisionService({'viewer_runtime': True}, clock=lambda: 100, wall=lambda: 100)
        with self.assertRaises(ValueError): s.cloud()


class Static(unittest.TestCase):
    def test_page_offers_ir_panel_and_mode_matrix(self):
        html = (ROOT / 'web/v2/vision3d.html').read_text(); js = (ROOT / 'web/v2/vision3d.js').read_text()
        for mode in ('depth', 'concurrent', 'ir', 'ir_depth', 'rgb_ir'): self.assertIn('value="%s"' % mode, html)
        for i in ('irCanvas', 'irState', 'irFps', 'irProbe', 'freeze', 'pause', 'startViewer'): self.assertIn('id="%s"' % i, html)
        self.assertEqual(html.count('id="irState"'), 1)
        self.assertIn("get('raw?kind=ir')", js); self.assertNotIn('innerHTML', js)
        self.assertIn('id="showCloud" disabled', html)


if __name__ == '__main__':
    unittest.main()

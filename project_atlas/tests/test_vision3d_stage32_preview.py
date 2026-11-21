"""Stage32 UNCALIBRATED 3D preview: browser-only, labelled, bounded, and the calibrated gate is untouched (offline)."""
import json, math, shutil, subprocess, sys, unittest
from pathlib import Path
from types import SimpleNamespace as N
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_vision3d_web as W


@unittest.skipUnless(shutil.which('node'), 'node not installed')
class PreviewGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = json.loads(subprocess.check_output(['node', str(ROOT / 'tests/vision3d_preview_cases.js')], text=True))

    def test_flat_wall_and_nominal_field_of_view(self):
        w = self.r['wall']
        self.assertEqual((w['stride'], w['n'], w['invalid']), (2, 4740, 60))          # 80x60 samples, u=0 column invalid
        self.assertEqual((w['zmin'], w['zmax']), (2.0, 2.0))                         # Z is the sensor's own axial reading
        half = 2.0 * math.tan(1.0225999355316162 / 2)                                 # nominal half-width at 2 m
        self.assertAlmostEqual(w['xmax'], (158 - 79.5) / 80 * half, 3); self.assertLess(w['xmin'], 0)
        self.assertAlmostEqual(w['k']['fx'], 142.5856, 3)
        self.assertFalse(w['calibrated']); self.assertEqual(w['label'], 'UNCALIBRATED — DIAGNOSTIC ONLY')

    def test_formats_invalid_and_bounds(self):
        self.assertEqual(self.r['float_be'], {'n': 4800, 'z': 1.5})
        self.assertEqual(self.r['allinvalid'], {'n': 0, 'invalid': 8})
        self.assertIn('native depth', self.r['errors'][0]); self.assertIn('size mismatch', self.r['errors'][1])
        self.assertLessEqual(self.r['cap']['n'], 6000)


class PreviewGating(unittest.TestCase):
    def test_receiver_serves_labelled_native_depth_but_calibrated_outputs_stay_gated(self):
        s = W.VisionService({}, clock=lambda: 100.0, wall=lambda: 100.0)
        h = N(frame_id='astra_depth_optical_frame', stamp=N(sec=100, nanosec=0))
        s.ingest('depth', N(width=2, height=2, encoding='16UC1', step=4, is_bigendian=False, data=b'\xe8\x03' * 4, header=h))
        body, hdr = s.raw('depth'); self.assertEqual(hdr['X-Calibration'], 'UNCALIBRATED-DIAGNOSTIC-ONLY')
        with self.assertRaisesRegex(ValueError, 'CALIBRATION BLOCKED'): s.cloud()               # metric cloud still gated
        s.frame('depth'); self.assertIsNone(s.pixel(0, 0)['xyz_m'])                             # no metric XYZ on click
        src = (ROOT / 'scripts/atlas_vision3d_web.py').read_text()
        self.assertNotIn('create_publisher(', src)                                              # nothing reaches ROS / navigation

    def test_page_labels_and_isolates_the_preview(self):
        js = (ROOT / 'web/v2/vision3d.js').read_text(); html = (ROOT / 'web/v2/vision3d.html').read_text()
        self.assertIn('id="showPreview" disabled', html); self.assertIn('UNCALIBRATED — DIAGNOSTIC ONLY', html)
        self.assertIn("ctx.fillText(VS.PREVIEW_LABEL", js)                                     # label drawn on the canvas itself
        self.assertIn("get('raw?kind=depth')", js); self.assertIn("UNCALIBRATED preview point", js)
        self.assertIn("$('showPreview').disabled = !depthLive || $('showCloud').checked", js)   # off by default, never both
        self.assertNotIn("showCloud').checked = true", js)


if __name__ == '__main__':
    unittest.main()

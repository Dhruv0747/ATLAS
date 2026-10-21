"""Stage32 calibration and point-cloud foundation: synthetic tests only (no camera, ROS or capture)."""
import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(ROOT / 'tools/vision3d'))
import atlas_vision3d_geometry as G      # noqa: E402
import calibration_validation as CV       # noqa: E402

K160 = [140.0, 0, 79.5, 0, 140.0, 59.5, 0, 0, 1]   # synthetic test camera, NOT an Astra calibration


def validated_doc(serial='TESTSERIAL', k=K160, d=(0, 0, 0, 0, 0)):
    return {'source': 'measured_target', 'device_serial': serial, 'width': 160, 'height': 120, 'frame_id': G.DEPTH_FRAME,
            'distortion_model': 'plumb_bob', 'k': list(k), 'd': list(d), 'independently_validated': True,
            'validation_evidence': 'synthetic fixture', 'status': 'VALIDATED'}


def depth_msg(fn, w=160, h=120, frame=G.DEPTH_FRAME):
    data = b''.join(struct.pack('<H', fn(u, v)) for v in range(h) for u in range(w))
    return N(width=w, height=h, encoding='16UC1', step=2 * w, is_bigendian=False, data=data,
             header=N(frame_id=frame, stamp=N(sec=5, nanosec=0)))


class Gate(unittest.TestCase):
    def test_no_file_means_not_validated(self):
        st = G.calibration_state({'device_serial': 'X'}, path='/nonexistent/cal.json')
        self.assertEqual(st['state'], 'NOT VALIDATED'); self.assertIn('NaN', st['reason'])

    def test_rejects_candidates_fov_and_foreign_documents(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'c.json'
            for bad in (dict(validated_doc(), independently_validated=False), dict(validated_doc(), source='fov_estimate'),
                        dict(validated_doc(), device_serial='OTHER'), dict(validated_doc(), width=320),
                        dict(validated_doc(), k=[float('nan')] + K160[1:])):
                p.write_text(json.dumps(bad))
                self.assertEqual(G.calibration_state({'device_serial': 'TESTSERIAL'}, p)['state'], 'NOT VALIDATED', bad)
            p.write_text(json.dumps(validated_doc()))
            self.assertEqual(G.calibration_state({'device_serial': 'TESTSERIAL'}, p)['state'], 'VALIDATED')

    def test_live_repository_has_no_calibration_file(self):
        self.assertFalse(G.DEPTH_CALIBRATION.exists(), 'a calibration file must only appear after owner-approved validation')


class Backprojection(unittest.TestCase):
    def test_flat_wall_at_2m_is_a_plane_at_2m_with_correct_axes(self):
        cal = validated_doc(); pts, stats = G.backproject(depth_msg(lambda u, v: 2000), cal)
        self.assertLessEqual(len(pts), G.MAX_POINTS)
        self.assertTrue(all(abs(p[2] - 2.0) < 1e-9 for p in pts))
        # optical frame: pixel right of centre -> +X, below centre -> +Y
        right = [p for p in pts if p[0] > 0.5]; low = [p for p in pts if p[1] > 0.3]
        self.assertTrue(right and low)
        fit = G.plane_fit(pts)
        self.assertAlmostEqual(fit['distance_m'], 2.0, places=6); self.assertLess(fit['rms_m'], 1e-9); self.assertLess(fit['tilt_from_optical_axis_deg'], 1e-3)

    def test_pixel_to_point_association(self):
        cal = validated_doc(); m = depth_msg(lambda u, v: 1500 if (u, v) == (130, 10) else 0)
        pts, stats = G.backproject(m, cal, limit=160 * 120)
        self.assertEqual(len(pts), 1)
        x, y, z = pts[0]
        self.assertAlmostEqual(x, (130 - 79.5) * 1.5 / 140.0); self.assertAlmostEqual(y, (10 - 59.5) * 1.5 / 140.0); self.assertAlmostEqual(z, 1.5)

    def test_invalid_depth_filtered(self):
        cal = validated_doc(); m = depth_msg(lambda u, v: (0, 65535, 9000, 1000)[(u + v) % 4])
        pts, stats = G.backproject(m, cal, limit=160 * 120)
        self.assertTrue(all(abs(p[2] - 1.0) < 1e-9 for p in pts)); self.assertGreater(stats['invalid_samples'], 0)

    def test_tilted_plane_recovered(self):
        cal = validated_doc()
        # plane z = 2 + 0.25*x  =>  z = 2 / (1 - 0.25*xn) for normalized xn
        pts, _ = G.backproject(depth_msg(lambda u, v: int(round(1000 * 2.0 / (1 - 0.25 * (u - 79.5) / 140.0)))), cal)
        fit = G.plane_fit(pts)
        self.assertAlmostEqual(fit['tilt_from_optical_axis_deg'], math.degrees(math.atan(0.25)), delta=0.3)
        self.assertLess(fit['rms_m'], 0.002)   # millimetre quantisation only

    def test_distortion_inverse_round_trip(self):
        k, d = K160, [0.08, -0.12, 0.001, -0.0015, 0.02]
        for (x, y) in ((0.1, -0.2), (-0.35, 0.25), (0.0, 0.0)):
            r2 = x * x + y * y; rad = 1 + d[0] * r2 + d[1] * r2 * r2 + d[4] * r2 ** 3
            xd = x * rad + 2 * d[2] * x * y + d[3] * (r2 + 2 * x * x); yd = y * rad + d[2] * (r2 + 2 * y * y) + 2 * d[3] * x * y
            u, v = xd * k[0] + k[2], yd * k[4] + k[5]
            xu, yu = G.undistort(u, v, k, d)
            self.assertAlmostEqual(xu, x, places=6); self.assertAlmostEqual(yu, y, places=6)

    def test_ray_cache_matches_direct_undistortion_and_follows_calibration(self):
        d = (0.08, -0.12, 0.002, -0.001, 0.03); m = depth_msg(lambda u, v: 1500)
        for doc in (validated_doc(d=d), validated_doc(d=(0, 0, 0, 0, 0))):
            pts, st = G.backproject(m, doc)
            u, v = 3 * st['stride'], 5 * st['stride']; i = 5 * len(range(0, 160, st['stride'])) + 3
            x, y = G.undistort(u, v, doc['k'], doc['d'])
            self.assertAlmostEqual(pts[i][0], x * 1.5, 9); self.assertAlmostEqual(pts[i][1], y * 1.5, 9)
        self.assertEqual(len(G._RAYS), 1)

    def test_resolution_and_frame_must_match(self):
        with self.assertRaisesRegex(ValueError, 'no implicit scaling'): G.backproject(depth_msg(lambda u, v: 1000, w=80, h=60), validated_doc())
        with self.assertRaisesRegex(ValueError, 'frame'): G.backproject(depth_msg(lambda u, v: 1000, frame='camera_link'), validated_doc())

    def test_pointcloud2_layout(self):
        f = G.pointcloud2_fields([[1.0, 2.0, 3.0], [-1.0, 0.5, 2.5]])
        self.assertEqual((f['height'], f['width'], f['point_step'], f['row_step'], f['is_dense']), (1, 2, 12, 24, True))
        self.assertEqual(struct.unpack('<6f', f['data']), (1.0, 2.0, 3.0, -1.0, 0.5, 2.5))


class Checkerboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import cv2, numpy  # noqa: F401
        except ImportError:
            raise unittest.SkipTest('OpenCV not installed')
        import checkerboard_calibration as CB
        cls.CB = CB

    def render_views(self, k_true, n=18, pattern=(9, 6), square=0.03):
        import cv2, numpy as np
        cols, rows = pattern[0] + 1, pattern[1] + 1; ppm = 2000          # texture pixels per metre
        tex = np.full(((rows + 2) * int(square * ppm), (cols + 2) * int(square * ppm)), 255, np.uint8)
        s = int(square * ppm)
        for r in range(rows):
            for c in range(cols):
                if (r + c) % 2 == 0: tex[(r + 1) * s:(r + 2) * s, (c + 1) * s:(c + 2) * s] = 0
        K = np.array(k_true, float).reshape(3, 3); views = []; rng = np.random.default_rng(7)
        for i in range(n):
            rv = np.array([rng.uniform(-0.45, 0.45), rng.uniform(-0.45, 0.45), rng.uniform(-0.3, 0.3)])
            R, _ = cv2.Rodrigues(rv)
            t = np.array([rng.uniform(-0.18, 0.05), rng.uniform(-0.12, 0.03), rng.uniform(0.45, 0.8)])
            # board point (X, Y) metres on the texture whose inner-corner origin is offset by (2s, 2s) texture pixels
            A = np.array([[1 / ppm, 0, -2 * s / ppm + 0], [0, 1 / ppm, -2 * s / ppm], [0, 0, 1]])
            H = K @ np.column_stack([R[:, 0], R[:, 1], t]) @ A
            img = cv2.warpPerspective(tex, H, (640, 480), flags=cv2.INTER_LINEAR, borderValue=128)
            views.append(img)
        return views

    def test_recovers_known_intrinsics_and_flags_quality(self):
        CB = self.CB; k_true = [520.0, 0, 316.0, 0, 518.0, 243.0, 0, 0, 1]
        cs = CB.CornerSet((9, 6), 640, 480)
        accepted = sum(cs.add(v) for v in self.render_views(k_true, n=24))
        self.assertGreaterEqual(accepted, 15)
        doc = CB.calibrate(cs, 0.03, 'TESTSERIAL', 'astra_ir_optical_frame')
        k = doc['k']
        self.assertLess(abs(k[0] - 520) / 520, 0.01); self.assertLess(abs(k[4] - 518) / 518, 0.01)
        self.assertLess(abs(k[2] - 316), 3.0); self.assertLess(abs(k[5] - 243), 3.0)
        self.assertFalse(doc['independently_validated'])
        with self.assertRaises(ValueError):   # a candidate is never accepted as validated geometry
            CV.validate_calibration(doc, 'TESTSERIAL', 640, 480, 'astra_ir_optical_frame')

    def test_too_few_views_refused(self):
        cs = self.CB.CornerSet((9, 6), 640, 480)
        with self.assertRaisesRegex(ValueError, 'at least'): self.CB.calibrate(cs, 0.03, 'S', 'f')

    def test_derive_resolution_pixel_centre_scaling(self):
        doc = {'status': 'CANDIDATE', 'width': 640, 'height': 480, 'frame_id': 'astra_ir_optical_frame', 'k': [520.0, 0, 319.5, 0, 520.0, 239.5, 0, 0, 1]}
        out = self.CB.derive_resolution(doc, 160, 120, G.DEPTH_FRAME)
        self.assertEqual(out['k'][0], 130.0); self.assertAlmostEqual(out['k'][2], 79.5); self.assertAlmostEqual(out['k'][5], 59.5)
        self.assertFalse(out['independently_validated']); self.assertIn('derived_from', out)

    def test_validation_needs_two_passing_distances_and_a_plane(self):
        CB = self.CB; base = dict(validated_doc(), status='CANDIDATE', independently_validated=False, validation_evidence=None)
        good = [{'reference_m': 1.0, 'median_m': 1.006, 'invalid_percent': 2}, {'reference_m': 2.0, 'median_m': 2.015, 'invalid_percent': 4}]
        plane = [{'rms_m': 0.004, 'distance_m': 1.004, 'reference_m': 1.0}]
        out = CB.attach_validation(base, good, plane)
        self.assertEqual(out['status'], 'VALIDATED'); CV.validate_calibration(out, 'TESTSERIAL', 160, 120, G.DEPTH_FRAME)
        self.assertEqual(CB.attach_validation(base, good[:1], plane)['status'], 'CANDIDATE')                      # one distance
        self.assertEqual(CB.attach_validation(base, good, [])['status'], 'CANDIDATE')                              # no plane
        bad = [dict(good[0]), {'reference_m': 2.0, 'median_m': 2.06, 'invalid_percent': 4}]
        self.assertEqual(CB.attach_validation(base, bad, plane)['status'], 'CANDIDATE')                            # 3 % error


if __name__ == '__main__':
    unittest.main()

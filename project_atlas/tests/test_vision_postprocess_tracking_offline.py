"""Offline YOLO post-processing and read-only tracking checks (2026-11-03).

Runs the real TensorRTYOLO.infer() letterbox/decoding/NMS code with only the CUDA calls stubbed, on
still-frame sizes the Astra viewer produces, then the real detections() and Tracker. No GPU, camera,
ROS, servo, motor or navigation interface. No real camera still images exist in the repository, so
model outputs are synthetic tensors in YOLOv8 [1, 84, 8400] layout.
"""
import ast
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from atlas_vision_features import Tracker, detections   # noqa: E402

try:
    import cv2  # noqa: F401
    import types
    # TensorRT exists only on the Jetson. infer()'s post-processing does not use it; a placeholder
    # module lets the real class load here. Nothing from it is called by these tests.
    sys.modules.setdefault('tensorrt', types.ModuleType('tensorrt'))
    from trt_yolo_detector import TensorRTYOLO
except Exception as exc:  # pragma: no cover - environment without OpenCV
    TensorRTYOLO = None
    SKIP = str(exc)


class _Cuda:
    def cudaMemcpy(self, *args):
        return 0


class _Context:
    def execute_async_v3(self, stream):
        return True


def detector(output):
    d = object.__new__(TensorRTYOLO)          # no engine, no GPU
    d.confidence, d.iou = 0.45, 0.45
    d.input_shape, d.input_dtype = (1, 3, 640, 640), np.float32
    d.host_input = np.zeros((1, 3, 640, 640), np.float32)
    d.host_output = output
    d.cudart, d.context = _Cuda(), _Context()
    d.device_input = d.device_output = None
    return d


def tensor(*boxes):
    """boxes: (cx, cy, w, h, class_id, score) in 640x640 letterboxed model space."""
    out = np.zeros((1, 84, 8400), np.float32)
    for i, (cx, cy, w, h, cls, score) in enumerate(boxes):
        out[0, :4, i] = (cx, cy, w, h)
        out[0, 4 + cls, i] = score
    return out


@unittest.skipIf(TensorRTYOLO is None, 'OpenCV/numpy unavailable')
class PostProcessTests(unittest.TestCase):
    def run_frame(self, width, height, *boxes):
        rows = detector(tensor(*boxes)).infer(np.zeros((height, width, 3), np.uint8))
        return rows, detections(rows, width, height)

    def test_letterbox_inverse_640x480(self):
        # 640x480 -> ratio 1, pad_y 80. Original box (100,50)-(300,250) is centred at (200,230) in model space.
        rows, dets = self.run_frame(640, 480, (200, 230, 200, 200, 0, 0.9))
        self.assertEqual(len(dets), 1)
        self.assertEqual(dets[0]['box'], [100.0, 50.0, 300.0, 250.0])
        self.assertEqual((dets[0]['class_id'], dets[0]['label']), (0, 'person'))
        self.assertIsNone(dets[0]['distance_m'])

    def test_letterbox_inverse_1280x720(self):
        # ratio 0.5, pad_y 140. Original (400,200)-(800,600) -> model centre (300, 340), size 200x200.
        _, dets = self.run_frame(1280, 720, (300, 340, 200, 200, 56, 0.8))
        self.assertEqual(dets[0]['box'], [400.0, 200.0, 800.0, 600.0])
        self.assertEqual(dets[0]['class_id'], 56)

    def test_threshold_nms_per_class_and_edge_clamp(self):
        _, dets = self.run_frame(640, 480,
                                 (200, 230, 200, 200, 0, 0.90),   # kept
                                 (205, 232, 200, 200, 0, 0.70),   # same class, heavy overlap -> suppressed
                                 (200, 230, 200, 200, 58, 0.60),  # other class, same place -> kept (per-class NMS)
                                 (400, 300, 50, 50, 2, 0.44),     # below 0.45 confidence -> dropped
                                 (630, 300, 60, 60, 1, 0.80))     # crosses right edge -> clamped
        by_class = sorted((d['class_id'], d['confidence']) for d in dets)
        self.assertEqual([c for c, _ in by_class], [0, 1, 58])
        self.assertAlmostEqual(dict(by_class)[0], 0.90, places=5)
        edge = next(d for d in dets if d['class_id'] == 1)
        self.assertLessEqual(edge['box'][2], 640)
        self.assertGreater(edge['box'][2], edge['box'][0])

    def test_empty_and_degenerate_outputs(self):
        self.assertEqual(self.run_frame(640, 480)[1], [])
        # zero-area box after clamping is discarded by the adapter, never reported
        _, dets = self.run_frame(640, 480, (0, 79, 4, 2, 0, 0.9))
        self.assertEqual(dets, [])


class TrackingTests(unittest.TestCase):
    S = 1_000_000_000

    def box(self, x, cls=0):
        return dict(box=[x, 10.0, x + 20.0, 30.0], class_id=cls, label='person' if cls == 0 else 'class 2',
                    confidence=0.9, distance_m=None)

    def test_association_keeps_id_across_moving_frames(self):
        t = Tracker()
        first = t.update([self.box(0)], 1 * self.S)[0]['track_id']
        for i, x in enumerate((3, 6, 9), start=2):          # IoU >= 0.3 between steps
            self.assertEqual(t.update([self.box(x)], i * self.S // 2 + self.S)[0]['track_id'], first)

    def test_low_overlap_class_change_and_no_shared_ids(self):
        t = Tracker()
        a = t.update([self.box(0)], self.S)[0]['track_id']
        jumped = t.update([self.box(100)], self.S + self.S // 2)[0]['track_id']
        self.assertNotEqual(jumped, a)                        # IoU < 0.3 -> new image-space track
        other = t.update([self.box(100, cls=2)], 2 * self.S)[0]['track_id']
        self.assertNotEqual(other, jumped)                    # class change never inherits an ID
        two = t.update([self.box(100), self.box(101)], 2 * self.S + 1)
        self.assertNotEqual(two[0]['track_id'], two[1]['track_id'])

    def test_expiry_boundary_and_disconnect(self):
        t = Tracker()
        a = t.update([self.box(0)], self.S)[0]['track_id']
        self.assertEqual(t.update([self.box(0)], 2 * self.S)[0]['track_id'], a)           # exactly 1.0 s: kept
        self.assertNotEqual(t.update([self.box(0)], 3 * self.S + 1)[0]['track_id'], a)    # >1.0 s gap: expired
        with self.assertRaisesRegex(ValueError, 'repeated/regressed'):
            t.update([self.box(0)], 3 * self.S + 1)                                         # frozen source frame
        with self.assertRaisesRegex(ValueError, 'repeated/regressed'):
            t.update([self.box(0)], 2 * self.S)                                             # clock regression
        fresh = Tracker()                                     # a new session never resumes earlier IDs
        self.assertEqual(fresh.update([self.box(0)], 10 * self.S)[0]['track_id'], 1)

    def test_track_table_is_bounded(self):
        t = Tracker()
        for i in range(150):
            t.update([self.box(1000 + 40 * i)], self.S + i)
        self.assertLessEqual(len(t.tracks), 100)


class CommandBoundaryTests(unittest.TestCase):
    FILES = ('scripts/atlas_vision_features.py', 'scripts/atlas_vision_feature_worker.py',
             'scripts/atlas_vision_feature_lab.py', 'scripts/atlas_vision_feature_guard.py', 'scripts/trt_yolo_detector.py')
    FORBIDDEN = ('cmd_vel', 'Twist', 'create_publisher', 'servo', 'pan_tilt', 'PanTilt', 'motor', 'nav2',
                 'NavigateTo', 'action_client', 'set_speed', 'Rosmaster')   # serial ports: covered by the import check
    # The guard READS the cached cmd_vel age from /api/status to require fresh zero commands; it publishes nothing.
    READ_ONLY_SAFETY_KEYS = {('scripts/atlas_vision_feature_guard.py', 'cmd_vel')}

    def test_no_servo_motor_or_navigation_interfaces(self):
        """Checks code (imports, names, attributes, string literals), not docstrings or comments."""
        for name in self.FILES:
            tree = ast.parse((ROOT / name).read_text())
            docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                          if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
                          and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
            imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
            self.assertFalse({m for m in imported if m.split('.')[0] in ('rclpy', 'geometry_msgs', 'serial', 'Rosmaster_Lib')}, name)
            words = [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]
            words += [n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)]
            words += [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                      and id(n) not in docstrings]
            for word in self.FORBIDDEN:
                if (name, word) in self.READ_ONLY_SAFETY_KEYS:
                    continue
                self.assertFalse([w for w in words if word.lower() in w.lower()], name + ': ' + word)

if __name__ == '__main__':
    unittest.main()

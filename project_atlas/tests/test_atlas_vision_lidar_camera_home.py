"""Fusion camera-forward gate reads the calibrated camera home (2026-11-26).

Before: atlas_vision_lidar_fusion.py used FORWARD_PAN_US = 2300 while mission control
centres the camera to camera-home.conf (pan 1801 / tilt 1501, owner-confirmed straight
ahead), so fusion was always SUSPENDED_CAMERA_NOT_FORWARD during goals.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from atlas_vision_lidar_core import camera_forward_state, read_camera_home  # noqa: E402

HOME_CONF = """[Service]
# Saved from the ATLAS web dashboard using fresh PCA9685 feedback.
Environment=ATLAS_CAMERA_PAN_HOME_US=1801
Environment=ATLAS_CAMERA_TILT_HOME_US=1501
"""


def write(text):
    handle = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False)
    handle.write(text)
    handle.close()
    return handle.name


class ReadCameraHomeTests(unittest.TestCase):
    def test_reads_live_format(self):
        self.assertEqual(read_camera_home(write(HOME_CONF)), (1801, 1501))

    def test_missing_file_is_unknown(self):
        self.assertEqual(read_camera_home("/nonexistent/camera-home.conf"), (None, None))

    def test_missing_key_is_unknown(self):
        self.assertEqual(
            read_camera_home(write("[Service]\nEnvironment=ATLAS_CAMERA_PAN_HOME_US=1801\n")),
            (1801, None),
        )

    def test_bad_number_is_unknown(self):
        self.assertEqual(
            read_camera_home(write("Environment=ATLAS_CAMERA_PAN_HOME_US=abc\n"
                                   "Environment=ATLAS_CAMERA_TILT_HOME_US=1501\n")),
            (None, None),
        )


class CameraForwardStateTests(unittest.TestCase):
    HOME = (1801, 1501)

    def test_at_calibrated_home_is_forward(self):
        self.assertEqual(camera_forward_state(1801, 1501, self.HOME), (True, None))

    def test_within_tolerance_is_forward(self):
        self.assertEqual(camera_forward_state(1801 + 90, 1501 - 180, self.HOME), (True, None))

    def test_old_constant_2300_is_not_forward(self):
        self.assertEqual(
            camera_forward_state(2300, 1500, self.HOME),
            (False, "SUSPENDED_CAMERA_NOT_FORWARD"),
        )

    def test_just_outside_tolerance_is_not_forward(self):
        self.assertFalse(camera_forward_state(1801 + 91, 1501, self.HOME)[0])
        self.assertFalse(camera_forward_state(1801, 1501 + 181, self.HOME)[0])

    def test_no_servo_feedback_yet_is_not_forward(self):
        self.assertEqual(
            camera_forward_state(None, None, self.HOME),
            (False, "SUSPENDED_CAMERA_NOT_FORWARD"),
        )
        self.assertFalse(camera_forward_state(1801, None, self.HOME)[0])

    def test_unknown_home_never_assumes_forward(self):
        for home in ((None, None), (1801, None), (None, 1501)):
            self.assertEqual(
                camera_forward_state(1801, 1501, home),
                (False, "SUSPENDED_CAMERA_HOME_UNKNOWN"),
            )


class FusionNodeSourceTests(unittest.TestCase):
    """The node must not keep a hard-coded forward pose (no rclpy needed)."""

    SOURCE = (Path(__file__).resolve().parents[1] / "scripts" / "atlas_vision_lidar_fusion.py").read_text()

    def test_no_hardcoded_forward_constant(self):
        self.assertNotIn("FORWARD_PAN_US", self.SOURCE)
        self.assertNotIn("2300", self.SOURCE)

    def test_uses_camera_home_and_reports_it(self):
        self.assertIn("read_camera_home", self.SOURCE)
        self.assertIn("camera_forward_state", self.SOURCE)
        self.assertIn('"camera_home_us"', self.SOURCE)

    def test_servo_starts_unknown(self):
        self.assertIn("self.pan_us = None", self.SOURCE)
        self.assertIn("self.tilt_us = None", self.SOURCE)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression tests for the shared ATLAS encoder calibration source."""

from pathlib import Path
import sys
import tempfile
import unittest

try:
    import yaml
except ImportError:  # Windows bundled test runtime does not include PyYAML.
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

from atlas_closed_loop_control import load_drive_config
from atlas_encoder_calibration import load_encoder_calibration


ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = ROOT / "config" / "encoder_calibration.yaml"
DRIVE_PID = ROOT / "config" / "drive_pid.yaml"


class EncoderCalibrationTests(unittest.TestCase):
    @unittest.skipUnless(yaml is not None, "PyYAML is required")
    def test_repository_mapping_signs_and_values_are_canonical(self):
        calibration = load_encoder_calibration(CALIBRATION)
        self.assertEqual(
            calibration.positions,
            ("rear_left", "rear_right", "front_left", "front_right"),
        )
        self.assertEqual(calibration.encoder_signs, (-1.0, 1.0, 1.0, 1.0))
        self.assertEqual(
            calibration.counts_per_revolution,
            (4048.7, 3300.6, 4080.1, 2697.8),
        )
        self.assertTrue(all(
            motor.confidence != "commissioned" for motor in calibration.motors
        ))

    @unittest.skipUnless(yaml is not None, "PyYAML is required")
    def test_pid_loads_physical_encoder_fields_only_from_canonical_file(self):
        config = load_drive_config(DRIVE_PID)
        calibration = load_encoder_calibration(CALIBRATION)
        self.assertEqual(
            tuple(wheel.position for wheel in config.wheels),
            calibration.positions,
        )
        self.assertEqual(
            tuple(wheel.encoder_sign for wheel in config.wheels),
            calibration.encoder_signs,
        )
        self.assertEqual(
            tuple(wheel.counts_per_revolution for wheel in config.wheels),
            calibration.counts_per_revolution,
        )

        drive_root = yaml.safe_load(DRIVE_PID.read_text(encoding="utf-8"))[
            "atlas_drive_pid"
        ]
        self.assertEqual(
            drive_root["encoder_calibration_file"], "encoder_calibration.yaml"
        )
        for wheel in drive_root["wheels"].values():
            self.assertNotIn("position", wheel)
            self.assertNotIn("encoder_sign", wheel)
            self.assertNotIn("counts_per_revolution", wheel)

    @unittest.skipUnless(yaml is not None, "PyYAML is required")
    def test_one_temporary_source_drives_pid_and_telemetry_math(self):
        calibration_raw = yaml.safe_load(CALIBRATION.read_text(encoding="utf-8"))
        calibration_raw["encoder_calibration"]["motors"]["m2"][
            "encoder_sign"
        ] = -1.0
        calibration_raw["encoder_calibration"]["motors"]["m2"][
            "counts_per_revolution"
        ] = 6601.2
        drive_raw = yaml.safe_load(DRIVE_PID.read_text(encoding="utf-8"))
        drive_raw["atlas_drive_pid"][
            "encoder_calibration_file"
        ] = "temporary_encoder_calibration.yaml"

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            calibration_path = directory / "temporary_encoder_calibration.yaml"
            drive_path = directory / "drive_pid.yaml"
            calibration_path.write_text(
                yaml.safe_dump(calibration_raw, sort_keys=False), encoding="utf-8"
            )
            drive_path.write_text(
                yaml.safe_dump(drive_raw, sort_keys=False), encoding="utf-8"
            )
            calibration = load_encoder_calibration(calibration_path)
            config = load_drive_config(drive_path)

        self.assertEqual(config.wheels[1].encoder_sign, -1.0)
        self.assertEqual(config.wheels[1].counts_per_revolution, 6601.2)
        rpm, speed_mps, distance_m = calibration.telemetry(1, 6601.2, 6601.2)
        self.assertAlmostEqual(rpm, -60.0)
        self.assertAlmostEqual(speed_mps, -calibration.wheel_circumference_m)
        self.assertAlmostEqual(distance_m, -calibration.wheel_circumference_m)

    @unittest.skipUnless(yaml is not None, "PyYAML is required")
    def test_wrong_channel_position_fails_closed(self):
        calibration_raw = yaml.safe_load(CALIBRATION.read_text(encoding="utf-8"))
        calibration_raw["encoder_calibration"]["motors"]["m1"][
            "position"
        ] = "front_right"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.yaml"
            path.write_text(
                yaml.safe_dump(calibration_raw, sort_keys=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "must be rear_left"):
                load_encoder_calibration(path)

    @unittest.skipUnless(yaml is not None, "PyYAML is required")
    def test_pid_geometry_must_match_canonical_encoder_geometry(self):
        drive_raw = yaml.safe_load(DRIVE_PID.read_text(encoding="utf-8"))
        for field, value in (("wheelbase_m", 0.368), ("wheel_diameter_m", 0.126)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                calibration_path = directory / "encoder_calibration.yaml"
                drive_path = directory / "drive_pid.yaml"
                calibration_path.write_text(
                    CALIBRATION.read_text(encoding="utf-8"), encoding="utf-8"
                )
                changed = yaml.safe_load(yaml.safe_dump(drive_raw))
                changed["atlas_drive_pid"]["geometry"][field] = value
                drive_path.write_text(
                    yaml.safe_dump(changed, sort_keys=False), encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, "canonical encoder calibration"):
                    load_drive_config(drive_path)

    def test_base_validates_calibration_before_any_hardware_open(self):
        source = (ROOT / "scripts" / "yahboom_base.py").read_text(
            encoding="utf-8"
        )
        calibration_load = source.index(
            "self._encoder_calibration = load_encoder_calibration("
        )
        self.assertLess(calibration_load, source.index("link = open_verified("))
        self.assertLess(calibration_load, source.index("self.bot = Rosmaster("))


if __name__ == "__main__":
    unittest.main()

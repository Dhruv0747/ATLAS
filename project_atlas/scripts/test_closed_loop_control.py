#!/usr/bin/env python3
import math
from pathlib import Path
import sys
import unittest
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atlas_closed_loop_control import (
    AtlasClosedLoopController, BoundedPID, ControlState, FourWheelSteeringKinematics,
    DriveConfig, GeometryConfig, PIDConfig, SafetyConfig, WheelConfig,
    YawConfig, load_drive_config,
)


CONFIG = Path(__file__).resolve().parents[1] / "config" / "drive_pid.yaml"


def pid_config(**overrides):
    values = dict(kp=10.0, ki=2.0, kd=0.0, feed_forward=5.0,
                  static_feed_forward=0.0, output_limit=20.0,
                  integral_limit=1.0, derivative_alpha=0.2,
                  slew_per_s=1000.0, target_deadband=0.001)
    values.update(overrides)
    return PIDConfig(**values)


def armed_config():
    pid = pid_config(kp=10.0, feed_forward=10.0, output_limit=60.0)
    wheels = tuple(WheelConfig(f"M{i}", position, encoder_sign, output_sign,
                               4000.0, pid)
                   for i, position, encoder_sign, output_sign in (
                       (1, "rear_left", -1.0, -1.0),
                       (2, "rear_right", 1.0, 1.0),
                       (3, "front_left", 1.0, -1.0),
                       (4, "front_right", 1.0, 1.0)))
    return DriveConfig(
        True, True, True, (), GeometryConfig(0.367, 0.30, 0.125, 0.35, 35.0),
        YawConfig(False, True, 1.0, 0.0, 0.0, 4.0, 1.0, 0.03, 0.2, 8.0, 0.25, 0.3),
        SafetyConfig(0.45, 0.35, 0.75, 1.5, 0.03, 0.4, 0.015, 0.8,
                     True, True), wheels)


def update(controller, **overrides):
    values = dict(linear_x=0.10, linear_y=0.0, angular_z=0.0,
                  source="REMOTE", command_age_s=0.01, owner_age_s=0.01,
                  measured_speeds=(0.0, 0.0, 0.0, 0.0),
                  encoder_ages=(0.01, 0.01, 0.01, 0.01),
                  encoder_valid=(True, True, True, True),
                  measured_yaw_rate=0.0, yaw_age_s=0.01,
                  controller_link_ok=True, emergency_stop=False,
                  commissioning=False, dt=0.1)
    values.update(overrides)
    return controller.update(**values)


class ClosedLoopControlTests(unittest.TestCase):
    def test_repository_config_is_safely_disabled_and_m4_excluded(self):
        if importlib.util.find_spec("yaml"):
            config = load_drive_config(CONFIG)
            self.assertFalse(config.enabled)
            self.assertFalse(config.hardware_commissioned)
            self.assertFalse(config.navigation_validated)
            self.assertEqual(config.excluded_encoders, (4,))
            self.assertIsNone(config.geometry.track_width_m)
        else:
            # The Windows development Python does not ship PyYAML. Preserve a
            # deterministic safety-default check here; the Jetson static stage
            # exercises the real loader before deployment.
            text = CONFIG.read_text(encoding="utf-8")
            for expected in (
                "enabled: false", "hardware_commissioned: false",
                "navigation_validated: false", "excluded_encoders: [4]",
                "track_width_m: null",
            ):
                self.assertIn(expected, text)

    def test_no_lateral_mecanum_motion(self):
        result = update(AtlasClosedLoopController(armed_config()), linear_y=0.1)
        self.assertEqual(result.state, ControlState.FAULT_STOP)
        self.assertEqual(result.motor_outputs, (0.0,) * 4)
        self.assertEqual(result.fault_reason, "lateral_command_not_supported")

    def test_four_wheel_targets_preserve_curvature_and_inside_outside_ratio(self):
        k = FourWheelSteeringKinematics(GeometryConfig(0.367, 0.30, 0.125, 1.0, 35.0))
        rl, rr, fl, fr = k.targets(0.3, 0.4)
        self.assertLess(rl, rr); self.assertLess(fl, fr)
        self.assertTrue(all(value > 0 for value in (rl, rr, fl, fr)))
        self.assertTrue(all(value < 0 for value in k.targets(-0.3, 0.4)))

    def test_missing_track_width_prevents_activation(self):
        config = armed_config(); object.__setattr__(config.geometry, "track_width_m", None)
        self.assertEqual(update(AtlasClosedLoopController(config)).fault_reason,
                         "track_width_not_commissioned")

    def test_m4_exclusion_prevents_four_wheel_pid(self):
        config = armed_config(); object.__setattr__(config, "excluded_encoders", (4,))
        self.assertEqual(update(AtlasClosedLoopController(config)).fault_reason,
                         "required_encoder_excluded")

    def test_encoder_dropout_names_specific_wheel(self):
        for index in range(4):
            valid = [True] * 4; valid[index] = False
            result = update(AtlasClosedLoopController(armed_config()), encoder_valid=valid)
            self.assertEqual(result.fault_reason, f"encoder_invalid_M{index + 1}")

    def test_encoder_timeout_and_large_jump_stop(self):
        controller = AtlasClosedLoopController(armed_config())
        self.assertEqual(update(controller, encoder_ages=(0.01, 0.4, 0.01, 0.01)).fault_reason,
                         "encoder_timeout_M2")
        controller.clear_fault(True)
        self.assertEqual(update(controller, measured_speeds=(0.0, 0.0, 2.0, 0.0)).fault_reason,
                         "encoder_jump_M3")

    def test_encoder_reconnection_requires_explicit_fault_clear(self):
        controller = AtlasClosedLoopController(armed_config())
        self.assertEqual(update(controller, encoder_valid=(False, True, True, True)).state,
                         ControlState.FAULT_STOP)
        self.assertEqual(update(controller).state, ControlState.FAULT_STOP)
        self.assertTrue(controller.clear_fault(True))
        self.assertTrue(update(controller).active)

    def test_command_and_imu_timeout(self):
        controller = AtlasClosedLoopController(armed_config())
        self.assertEqual(update(controller, command_age_s=1.0).fault_reason, "cmd_vel_timeout")
        controller.clear_fault(True)
        self.assertEqual(update(controller, source="NAV2", yaw_age_s=1.0).fault_reason,
                         "yaw_feedback_timeout")

    def test_motor_link_owner_timeout_and_nonfinite_input_stop(self):
        controller = AtlasClosedLoopController(armed_config())
        self.assertEqual(update(controller, controller_link_ok=False).fault_reason,
                         "motor_controller_communication_loss")
        controller.clear_fault(True)
        self.assertEqual(update(controller, owner_age_s=1.0).fault_reason,
                         "controller_ownership_timeout")
        controller.clear_fault(True)
        self.assertEqual(update(controller, linear_x=math.nan).fault_reason,
                         "nan_or_infinite_input")

    def test_autonomous_mode_requires_separate_physical_validation_gate(self):
        config = armed_config(); object.__setattr__(config, "navigation_validated", False)
        result = update(AtlasClosedLoopController(config), source="NAV2")
        self.assertEqual(result.fault_reason, "navigation_not_physically_validated")
        self.assertEqual(result.motor_outputs, (0.0,) * 4)

    def test_emergency_stop_and_ownership_transition(self):
        controller = AtlasClosedLoopController(armed_config())
        self.assertEqual(update(controller, emergency_stop=True).fault_reason, "emergency_stop")
        self.assertTrue(controller.clear_fault(True))
        result = update(controller, source="STOPPED", linear_x=0.0)
        self.assertEqual(result.state, ControlState.DISABLED)
        self.assertEqual(result.motor_outputs, (0.0,) * 4)

    def test_restart_has_zero_output_and_requires_fresh_command(self):
        controller = AtlasClosedLoopController(armed_config())
        self.assertTrue(all(pid.output == 0.0 for pid in controller.wheel_pids))
        self.assertEqual(update(controller, command_age_s=2.0).motor_outputs, (0.0,) * 4)

    def test_pid_saturation_anti_windup_and_reversal_reset(self):
        pid = BoundedPID(pid_config(kp=100.0, ki=50.0, output_limit=10.0))
        first = pid.update(1.0, 0.0, 0.1)
        self.assertTrue(first.saturated and first.anti_windup)
        self.assertLessEqual(abs(first.output), 10.0); self.assertEqual(pid.integral, 0.0)
        pid.update(0.5, 0.0, 0.1)
        self.assertLessEqual(pid.update(-0.5, 0.0, 0.1).i, 0.0)

    def test_frozen_count_is_detected_by_age_policy(self):
        result = update(AtlasClosedLoopController(armed_config()),
                        encoder_ages=(0.01, 0.01, 0.5, 0.01))
        self.assertEqual(result.fault_reason, "encoder_timeout_M3")

    def test_reversed_encoder_drives_bounded_correction(self):
        controller = AtlasClosedLoopController(armed_config())
        result = None
        for _ in range(4):
            result = update(controller, measured_speeds=(-0.1, 0.1, 0.1, 0.1))
        self.assertEqual(result.fault_reason, "encoder_reversed_M1")

    def test_frozen_encoder_faults_after_grace_not_immediately(self):
        controller = AtlasClosedLoopController(armed_config())
        for _ in range(7):
            result = update(controller, measured_speeds=(0.0, 0.1, 0.1, 0.1))
            self.assertNotEqual(result.fault_reason, "encoder_frozen_M1")
        result = update(controller, measured_speeds=(0.0, 0.1, 0.1, 0.1))
        self.assertEqual(result.fault_reason, "encoder_frozen_M1")

    def test_steering_alignment_inhibits_without_latching_fault(self):
        controller = AtlasClosedLoopController(armed_config())
        blocked = update(controller, steering_aligned=False)
        self.assertEqual(blocked.inhibited_reason, "steering_alignment_pending")
        self.assertEqual(blocked.motor_outputs, (0.0,) * 4)
        self.assertTrue(update(controller, steering_aligned=True).active)

    def test_commissioning_mode_always_inhibits_traction(self):
        result = update(AtlasClosedLoopController(armed_config()), commissioning=True)
        self.assertEqual(result.state, ControlState.COMMISSIONING)
        self.assertEqual(result.motor_outputs, (0.0,) * 4)

    def test_diagnostic_contains_all_four_wheels_without_nan(self):
        result = update(AtlasClosedLoopController(armed_config()))
        payload = result.diagnostic((0.1,) * 4, (True,) * 4)
        self.assertEqual(len(__import__("json").loads(payload)["wheels"]), 4)
        self.assertNotIn("NaN", payload)


if __name__ == "__main__":
    unittest.main()

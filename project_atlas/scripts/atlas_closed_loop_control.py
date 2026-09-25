#!/usr/bin/env python3
"""Pure, hardware-independent low-level control for the ATLAS 4WS rover.

The module deliberately has no ROS or serial imports.  ``yahboom_base.py`` is
the sole hardware owner and may use this controller only after the explicit
hardware commissioning gates in ``drive_pid.yaml`` pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from atlas_encoder_calibration import (
    EXPECTED_POSITIONS, EncoderCalibration, load_encoder_calibration,
)

WHEEL_NAMES = ("M1_REAR_LEFT", "M2_REAR_RIGHT", "M3_FRONT_LEFT", "M4_FRONT_RIGHT")


class ControlState(str, Enum):
    DISABLED = "DISABLED"
    COMMISSIONING = "COMMISSIONING"
    MANUAL = "MANUAL"
    AUTONOMOUS = "AUTONOMOUS"
    FAULT_STOP = "FAULT_STOP"


def _finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass(frozen=True)
class PIDConfig:
    kp: float
    ki: float
    kd: float
    feed_forward: float
    static_feed_forward: float
    output_limit: float
    integral_limit: float
    derivative_alpha: float
    slew_per_s: float
    target_deadband: float


@dataclass(frozen=True)
class WheelConfig:
    name: str
    position: str
    encoder_sign: float
    output_sign: float
    counts_per_revolution: float
    pid: PIDConfig


@dataclass(frozen=True)
class GeometryConfig:
    wheelbase_m: float
    track_width_m: Optional[float]
    wheel_diameter_m: float
    max_wheel_speed_mps: float
    max_steering_deg: float


@dataclass(frozen=True)
class YawConfig:
    enabled_manual: bool
    enabled_autonomous: bool
    kp: float
    ki: float
    kd: float
    correction_limit_deg: float
    integral_limit: float
    deadband_rad_s: float
    derivative_alpha: float
    rate_limit_deg_s: float
    low_pass_alpha: float
    feedback_timeout_s: float


@dataclass(frozen=True)
class SafetyConfig:
    command_timeout_s: float
    encoder_timeout_s: float
    owner_timeout_s: float
    max_encoder_jump_mps: float
    reverse_speed_threshold_mps: float
    reverse_fault_s: float
    frozen_speed_threshold_mps: float
    frozen_fault_s: float
    require_all_four_encoders: bool
    require_yaw_autonomous: bool


@dataclass(frozen=True)
class DriveConfig:
    enabled: bool
    hardware_commissioned: bool
    navigation_validated: bool
    excluded_encoders: Tuple[int, ...]
    geometry: GeometryConfig
    yaw: YawConfig
    safety: SafetyConfig
    wheels: Tuple[WheelConfig, ...]


@dataclass
class PIDTerms:
    target: float = 0.0
    measured: float = 0.0
    error: float = 0.0
    p: float = 0.0
    i: float = 0.0
    d: float = 0.0
    ff: float = 0.0
    output: float = 0.0
    saturated: bool = False
    anti_windup: bool = False


class BoundedPID:
    """PID with filtered derivative, conditional integration and output slew."""

    def __init__(self, config: PIDConfig):
        self.config = config
        self.integral = 0.0
        self.last_error: Optional[float] = None
        self.derivative = 0.0
        self.output = 0.0
        self.last_target = 0.0

    def reset(self) -> None:
        self.integral = 0.0
        self.last_error = None
        self.derivative = 0.0
        self.output = 0.0
        self.last_target = 0.0

    def update(self, target: float, measured: float, dt: float) -> PIDTerms:
        if not all(_finite(v) for v in (target, measured, dt)) or dt <= 0.0:
            self.reset()
            raise ValueError("non-finite PID input or invalid dt")
        if target * self.last_target < 0.0:
            self.reset()
        self.last_target = target
        if abs(target) <= self.config.target_deadband:
            self.reset()
            return PIDTerms(target=target, measured=measured)

        error = target - measured
        raw_derivative = 0.0 if self.last_error is None else (error - self.last_error) / dt
        alpha = _clamp(self.config.derivative_alpha, 0.0, 1.0)
        self.derivative = alpha * raw_derivative + (1.0 - alpha) * self.derivative
        candidate_integral = _clamp(
            self.integral + error * dt,
            -self.config.integral_limit,
            self.config.integral_limit,
        )
        p = self.config.kp * error
        d = self.config.kd * self.derivative
        ff = self.config.feed_forward * target
        if self.config.static_feed_forward:
            ff += math.copysign(self.config.static_feed_forward, target)
        candidate = p + self.config.ki * candidate_integral + d + ff
        limited = _clamp(candidate, -self.config.output_limit, self.config.output_limit)
        saturated = not math.isclose(candidate, limited, abs_tol=1.0e-9)
        drives_out_of_saturation = (candidate > limited and error < 0.0) or (
            candidate < limited and error > 0.0
        )
        anti_windup = saturated and not drives_out_of_saturation
        if not anti_windup:
            self.integral = candidate_integral
        i = self.config.ki * self.integral
        desired = _clamp(p + i + d + ff, -self.config.output_limit, self.config.output_limit)
        max_step = max(0.0, self.config.slew_per_s) * dt
        if max_step:
            desired = _clamp(desired, self.output - max_step, self.output + max_step)
        self.output = desired
        self.last_error = error
        return PIDTerms(target, measured, error, p, i, d, ff, desired, saturated, anti_windup)


class FourWheelSteeringKinematics:
    """Symmetric counter-steer 4WS kinematics; no lateral/mecanum command."""

    def __init__(self, config: GeometryConfig):
        self.config = config

    def ready(self) -> Tuple[bool, str]:
        if not _finite(self.config.wheelbase_m) or self.config.wheelbase_m <= 0.0:
            return False, "wheelbase_not_commissioned"
        if self.config.track_width_m is None:
            return False, "track_width_not_commissioned"
        if not _finite(self.config.track_width_m) or self.config.track_width_m <= 0.0:
            return False, "track_width_invalid"
        if not _finite(self.config.wheel_diameter_m) or self.config.wheel_diameter_m <= 0.0:
            return False, "wheel_diameter_invalid"
        return True, "ready"

    def targets(self, linear_x: float, angular_z: float) -> Tuple[float, float, float, float]:
        ready, reason = self.ready()
        if not ready:
            raise ValueError(reason)
        if not _finite(linear_x) or not _finite(angular_z):
            raise ValueError("non_finite_command")
        if abs(linear_x) < 1.0e-6:
            # ATLAS cannot spin in place and has no lateral drive mode.
            return (0.0, 0.0, 0.0, 0.0)
        half_l = self.config.wheelbase_m / 2.0
        half_t = float(self.config.track_width_m) / 2.0
        positions = (
            (-half_l, +half_t),  # M1 rear-left
            (-half_l, -half_t),  # M2 rear-right
            (+half_l, +half_t),  # M3 front-left
            (+half_l, -half_t),  # M4 front-right
        )
        direction = 1.0 if linear_x > 0.0 else -1.0
        speeds = []
        for x, y in positions:
            local_x = linear_x - angular_z * y
            local_y = angular_z * x
            speeds.append(direction * math.hypot(local_x, local_y))
        peak = max(abs(v) for v in speeds)
        if peak > self.config.max_wheel_speed_mps > 0.0:
            scale = self.config.max_wheel_speed_mps / peak
            speeds = [v * scale for v in speeds]
        return tuple(speeds)

    def nominal_steering_deg(self, linear_x: float, angular_z: float) -> float:
        if abs(linear_x) < 1.0e-6:
            return 0.0
        value = math.degrees(math.atan(self.config.wheelbase_m * angular_z / (2.0 * linear_x)))
        return _clamp(value, -self.config.max_steering_deg, self.config.max_steering_deg)


@dataclass
class ControlResult:
    state: ControlState
    active: bool
    motor_outputs: Tuple[float, float, float, float]
    wheel_targets: Tuple[float, float, float, float]
    wheel_terms: Tuple[PIDTerms, PIDTerms, PIDTerms, PIDTerms]
    steering_correction_deg: float
    commanded_yaw_rate: float
    measured_yaw_rate: Optional[float]
    fault_reason: str = ""
    inhibited_reason: str = ""

    def diagnostic(self, encoder_ages: Sequence[float], encoder_valid: Sequence[bool]) -> str:
        wheels = []
        for index, terms in enumerate(self.wheel_terms):
            wheels.append({
                "wheel": WHEEL_NAMES[index], "target_mps": round(terms.target, 5),
                "measured_mps": round(terms.measured, 5), "error_mps": round(terms.error, 5),
                "p": round(terms.p, 5), "i": round(terms.i, 5), "d": round(terms.d, 5),
                "feed_forward": round(terms.ff, 5), "output": round(terms.output, 3),
                "saturated": terms.saturated, "anti_windup": terms.anti_windup,
                "encoder_age_s": round(float(encoder_ages[index]), 3),
                "encoder_valid": bool(encoder_valid[index]),
            })
        return json.dumps({
            "schema": 1, "state": self.state.value, "active": self.active,
            "fault_reason": self.fault_reason, "inhibited_reason": self.inhibited_reason,
            "commanded_yaw_rate": self.commanded_yaw_rate,
            "measured_yaw_rate": self.measured_yaw_rate,
            "steering_correction_deg": round(self.steering_correction_deg, 4),
            "wheels": wheels,
        }, separators=(",", ":"), allow_nan=False)


class AtlasClosedLoopController:
    """Safety-gated wheel-speed and bounded yaw-correction controller."""

    MANUAL_SOURCES = {"REMOTE", "WEB", "FOXGLOVE"}
    AUTONOMOUS_SOURCES = {"NAV2", "RECOVERY"}

    def __init__(self, config: DriveConfig):
        self.config = config
        self.kinematics = FourWheelSteeringKinematics(config.geometry)
        self.wheel_pids = [BoundedPID(wheel.pid) for wheel in config.wheels]
        yaw_pid_config = PIDConfig(
            config.yaw.kp, config.yaw.ki, config.yaw.kd, 0.0, 0.0,
            config.yaw.correction_limit_deg, config.yaw.integral_limit,
            config.yaw.derivative_alpha, config.yaw.rate_limit_deg_s,
            config.yaw.deadband_rad_s,
        )
        self.yaw_pid = BoundedPID(yaw_pid_config)
        self.filtered_correction = 0.0
        self.fault_reason = ""
        self.reverse_duration = [0.0] * 4
        self.frozen_duration = [0.0] * 4

    def reset(self) -> None:
        for pid in self.wheel_pids:
            pid.reset()
        self.yaw_pid.reset()
        self.filtered_correction = 0.0
        self.reverse_duration = [0.0] * 4
        self.frozen_duration = [0.0] * 4

    def clear_fault(self, command_is_zero: bool) -> bool:
        if command_is_zero:
            self.fault_reason = ""
            self.reset()
            return True
        return False

    def _fault(self, reason: str, commanded_yaw: float = 0.0,
               measured_yaw: Optional[float] = None) -> ControlResult:
        self.fault_reason = reason
        self.reset()
        empty = tuple(PIDTerms() for _ in range(4))
        return ControlResult(ControlState.FAULT_STOP, False, (0.0,) * 4,
                             (0.0,) * 4, empty, 0.0, commanded_yaw,
                             measured_yaw, fault_reason=reason)

    def update(
        self, *, linear_x: float, linear_y: float, angular_z: float,
        source: str, command_age_s: float, owner_age_s: float,
        measured_speeds: Sequence[float], encoder_ages: Sequence[float],
        encoder_valid: Sequence[bool], measured_yaw_rate: Optional[float],
        yaw_age_s: float, controller_link_ok: bool, emergency_stop: bool,
        commissioning: bool, steering_aligned: bool = True, dt: float = 0.1,
    ) -> ControlResult:
        source = str(source).upper()
        zeros = tuple(PIDTerms() for _ in range(4))
        if commissioning:
            self.reset()
            return ControlResult(ControlState.COMMISSIONING, False, (0.0,) * 4,
                                 (0.0,) * 4, zeros, 0.0, angular_z, measured_yaw_rate,
                                 inhibited_reason="commissioning_traction_inhibited")
        if self.config.enabled and self.config.hardware_commissioned and not steering_aligned:
            self.reset()
            return ControlResult(ControlState.COMMISSIONING, False, (0.0,) * 4,
                                 (0.0,) * 4, zeros, 0.0, angular_z, measured_yaw_rate,
                                 inhibited_reason="steering_alignment_pending")
        if not self.config.enabled or not self.config.hardware_commissioned:
            self.reset()
            reason = "controller_disabled" if not self.config.enabled else "hardware_not_commissioned"
            return ControlResult(ControlState.DISABLED, False, (0.0,) * 4,
                                 (0.0,) * 4, zeros, 0.0, angular_z, measured_yaw_rate,
                                 inhibited_reason=reason)
        ready, reason = self.kinematics.ready()
        if not ready:
            return self._fault(reason, angular_z, measured_yaw_rate)
        if self.config.safety.require_all_four_encoders and self.config.excluded_encoders:
            return self._fault("required_encoder_excluded", angular_z, measured_yaw_rate)
        if emergency_stop:
            return self._fault("emergency_stop", angular_z, measured_yaw_rate)
        if not controller_link_ok:
            return self._fault("motor_controller_communication_loss", angular_z, measured_yaw_rate)
        if source not in self.MANUAL_SOURCES | self.AUTONOMOUS_SOURCES:
            self.reset()
            return ControlResult(ControlState.DISABLED, False, (0.0,) * 4,
                                 (0.0,) * 4, zeros, 0.0, angular_z, measured_yaw_rate,
                                 inhibited_reason="no_controller_owner")
        if owner_age_s > self.config.safety.owner_timeout_s:
            return self._fault("controller_ownership_timeout", angular_z, measured_yaw_rate)
        if command_age_s > self.config.safety.command_timeout_s:
            return self._fault("cmd_vel_timeout", angular_z, measured_yaw_rate)
        values = [linear_x, linear_y, angular_z, command_age_s, owner_age_s, dt]
        values += list(measured_speeds) + list(encoder_ages)
        if not all(_finite(value) for value in values):
            return self._fault("nan_or_infinite_input", angular_z, measured_yaw_rate)
        if abs(linear_y) > 1.0e-6:
            return self._fault("lateral_command_not_supported", angular_z, measured_yaw_rate)
        if len(measured_speeds) != 4 or len(encoder_ages) != 4 or len(encoder_valid) != 4:
            return self._fault("invalid_encoder_vector", angular_z, measured_yaw_rate)
        for index in range(4):
            if not encoder_valid[index]:
                return self._fault(f"encoder_invalid_M{index + 1}", angular_z, measured_yaw_rate)
            if encoder_ages[index] > self.config.safety.encoder_timeout_s:
                return self._fault(f"encoder_timeout_M{index + 1}", angular_z, measured_yaw_rate)
            if abs(measured_speeds[index]) > self.config.safety.max_encoder_jump_mps:
                return self._fault(f"encoder_jump_M{index + 1}", angular_z, measured_yaw_rate)
        state = ControlState.MANUAL if source in self.MANUAL_SOURCES else ControlState.AUTONOMOUS
        if state == ControlState.AUTONOMOUS and not self.config.navigation_validated:
            return self._fault("navigation_not_physically_validated", angular_z, measured_yaw_rate)
        if self.fault_reason:
            return self._fault(self.fault_reason, angular_z, measured_yaw_rate)
        if abs(linear_x) <= 1.0e-6 and abs(angular_z) <= 1.0e-6:
            self.reset()
            return ControlResult(state, True, (0.0,) * 4, (0.0,) * 4,
                                 zeros, 0.0, angular_z, measured_yaw_rate)

        yaw_enabled = (state == ControlState.MANUAL and self.config.yaw.enabled_manual) or (
            state == ControlState.AUTONOMOUS and self.config.yaw.enabled_autonomous
        )
        correction = 0.0
        if yaw_enabled:
            yaw_valid = measured_yaw_rate is not None and _finite(measured_yaw_rate)
            yaw_valid = yaw_valid and yaw_age_s <= self.config.yaw.feedback_timeout_s
            if not yaw_valid:
                self.yaw_pid.reset()
                if state == ControlState.AUTONOMOUS and self.config.safety.require_yaw_autonomous:
                    return self._fault("yaw_feedback_timeout", angular_z, measured_yaw_rate)
            else:
                yaw_terms = self.yaw_pid.update(angular_z, float(measured_yaw_rate), dt)
                correction = yaw_terms.output
                alpha = _clamp(self.config.yaw.low_pass_alpha, 0.0, 1.0)
                self.filtered_correction = alpha * correction + (1.0 - alpha) * self.filtered_correction
                correction = self.filtered_correction
        else:
            self.yaw_pid.reset()
            self.filtered_correction = 0.0

        targets = self.kinematics.targets(linear_x, angular_z)
        for index, (target, measured) in enumerate(zip(targets, measured_speeds)):
            moving_target = abs(target) >= self.config.safety.frozen_speed_threshold_mps
            reversed_feedback = (
                moving_target
                and abs(measured) >= self.config.safety.reverse_speed_threshold_mps
                and target * measured < 0.0
            )
            frozen_feedback = moving_target and abs(measured) < self.config.safety.frozen_speed_threshold_mps
            self.reverse_duration[index] = self.reverse_duration[index] + dt if reversed_feedback else 0.0
            self.frozen_duration[index] = self.frozen_duration[index] + dt if frozen_feedback else 0.0
            if self.reverse_duration[index] + 1e-9 >= self.config.safety.reverse_fault_s:
                return self._fault(f"encoder_reversed_M{index + 1}", angular_z, measured_yaw_rate)
            if self.frozen_duration[index] + 1e-9 >= self.config.safety.frozen_fault_s:
                return self._fault(f"encoder_frozen_M{index + 1}", angular_z, measured_yaw_rate)
        terms: List[PIDTerms] = []
        outputs: List[float] = []
        for index, pid in enumerate(self.wheel_pids):
            item = pid.update(targets[index], measured_speeds[index], dt)
            item.output *= self.config.wheels[index].output_sign
            if not _finite(item.output):
                return self._fault(f"invalid_controller_output_M{index + 1}", angular_z, measured_yaw_rate)
            outputs.append(item.output)
            terms.append(item)
        return ControlResult(state, True, tuple(outputs), targets, tuple(terms),
                             correction, angular_z, measured_yaw_rate)


def _number(mapping: Mapping, key: str, *, positive: bool = False) -> float:
    value = mapping.get(key)
    if not _finite(value) or (positive and float(value) <= 0.0):
        raise ValueError(f"invalid configuration value: {key}")
    return float(value)


def _unit_interval(value: float, name: str) -> float:
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def _sign(value: float, name: str) -> float:
    if value not in (-1.0, 1.0):
        raise ValueError(f"{name} must be -1 or +1")
    return value


def load_drive_config(
    path: Path | str,
    *,
    encoder_calibration: Optional[EncoderCalibration] = None,
) -> DriveConfig:
    import yaml
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    root = raw.get("atlas_drive_pid", {})
    if encoder_calibration is None:
        calibration_ref = root.get("encoder_calibration_file")
        if not isinstance(calibration_ref, str) or not calibration_ref.strip():
            raise ValueError("encoder_calibration_file must name the canonical YAML file")
        calibration_path = Path(calibration_ref)
        if not calibration_path.is_absolute():
            calibration_path = config_path.parent / calibration_path
        encoder_calibration = load_encoder_calibration(calibration_path)
    geometry_raw = root.get("geometry", {})
    track = geometry_raw.get("track_width_m")
    if track is not None and not _finite(track):
        raise ValueError("track_width_m must be a measured number or null")
    wheelbase_m = _number(geometry_raw, "wheelbase_m", positive=True)
    wheel_diameter_m = _number(
        geometry_raw, "wheel_diameter_m", positive=True
    )
    if not math.isclose(
        wheelbase_m, encoder_calibration.wheelbase_m,
        rel_tol=0.0, abs_tol=1.0e-9,
    ):
        raise ValueError(
            "geometry.wheelbase_m must match canonical encoder calibration"
        )
    if not math.isclose(
        wheel_diameter_m, encoder_calibration.wheel_diameter_m,
        rel_tol=0.0, abs_tol=1.0e-9,
    ):
        raise ValueError(
            "geometry.wheel_diameter_m must match canonical encoder calibration"
        )
    geometry = GeometryConfig(
        wheelbase_m,
        None if track is None else float(track),
        wheel_diameter_m,
        _number(geometry_raw, "max_wheel_speed_mps", positive=True),
        _number(geometry_raw, "max_steering_deg", positive=True),
    )
    safety_raw = root.get("safety", {})
    safety = SafetyConfig(
        _number(safety_raw, "command_timeout_s", positive=True),
        _number(safety_raw, "encoder_timeout_s", positive=True),
        _number(safety_raw, "owner_timeout_s", positive=True),
        _number(safety_raw, "max_encoder_jump_mps", positive=True),
        _number(safety_raw, "reverse_speed_threshold_mps", positive=True),
        _number(safety_raw, "reverse_fault_s", positive=True),
        _number(safety_raw, "frozen_speed_threshold_mps", positive=True),
        _number(safety_raw, "frozen_fault_s", positive=True),
        bool(safety_raw.get("require_all_four_encoders", True)),
        bool(safety_raw.get("require_yaw_autonomous", True)),
    )
    yaw_raw = root.get("yaw_control", {})
    yaw = YawConfig(
        bool(yaw_raw.get("enabled_manual", False)), bool(yaw_raw.get("enabled_autonomous", True)),
        _number(yaw_raw, "kp"), _number(yaw_raw, "ki"), _number(yaw_raw, "kd"),
        _number(yaw_raw, "correction_limit_deg", positive=True),
        _number(yaw_raw, "integral_limit", positive=True),
        _number(yaw_raw, "deadband_rad_s"), _number(yaw_raw, "derivative_alpha"),
        _number(yaw_raw, "rate_limit_deg_s", positive=True),
        _number(yaw_raw, "low_pass_alpha"), _number(yaw_raw, "feedback_timeout_s", positive=True),
    )
    _unit_interval(yaw.derivative_alpha, "yaw_control.derivative_alpha")
    _unit_interval(yaw.low_pass_alpha, "yaw_control.low_pass_alpha")
    wheels_raw = root.get("wheels", {})
    wheels = []
    for index, canonical in enumerate(WHEEL_NAMES, 1):
        item = wheels_raw.get(f"m{index}", {})
        encoder = encoder_calibration.motors[index - 1]
        pid_raw = item.get("pid", {})
        pid = PIDConfig(
            _number(pid_raw, "kp"), _number(pid_raw, "ki"), _number(pid_raw, "kd"),
            _number(pid_raw, "feed_forward"), _number(pid_raw, "static_feed_forward"),
            _number(pid_raw, "output_limit", positive=True),
            _number(pid_raw, "integral_limit", positive=True),
            _number(pid_raw, "derivative_alpha"), _number(pid_raw, "slew_per_s", positive=True),
            _number(pid_raw, "target_deadband"),
        )
        wheels.append(WheelConfig(
            canonical, encoder.position, encoder.encoder_sign,
            _sign(_number(item, "output_sign"), f"m{index}.output_sign"),
            encoder.counts_per_revolution, pid,
        ))
        _unit_interval(pid.derivative_alpha, f"m{index}.pid.derivative_alpha")
    if tuple(wheel.position for wheel in wheels) != EXPECTED_POSITIONS:
        raise ValueError(f"wheel positions must be {EXPECTED_POSITIONS}")
    excluded = tuple(sorted(int(value) for value in root.get("excluded_encoders", [])))
    if any(value not in (1, 2, 3, 4) for value in excluded):
        raise ValueError("excluded_encoders must contain only M1..M4 numbers")
    return DriveConfig(
        bool(root.get("enabled", False)), bool(root.get("hardware_commissioned", False)),
        bool(root.get("navigation_validated", False)), excluded, geometry, yaw, safety,
        tuple(wheels),
    )

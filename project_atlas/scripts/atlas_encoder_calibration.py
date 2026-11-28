#!/usr/bin/env python3
"""Validated canonical physical encoder calibration for Project ATLAS.

This module is deliberately hardware- and ROS-independent.  The Yahboom
telemetry owner and the optional closed-loop controller both load the same
``encoder_calibration.yaml`` data through this module so channel identity,
encoder direction and counts/revolution cannot silently diverge.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Mapping, Tuple


EXPECTED_CHANNELS = ("m1", "m2", "m3", "m4")
EXPECTED_POSITIONS = ("rear_left", "rear_right", "front_left", "front_right")


def _mapping(value, name: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _positive_number(values: Mapping, key: str, name: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}.{key} must be a number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name}.{key} must be finite and greater than zero")
    return result


def _encoder_sign(values: Mapping, name: str) -> float:
    value = values.get("encoder_sign")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}.encoder_sign must be -1 or +1")
    result = float(value)
    if result not in (-1.0, 1.0):
        raise ValueError(f"{name}.encoder_sign must be -1 or +1")
    return result


@dataclass(frozen=True)
class MotorEncoderCalibration:
    channel: str
    position: str
    encoder_sign: float
    counts_per_revolution: float
    confidence: str
    method: str


@dataclass(frozen=True)
class EncoderCalibration:
    wheelbase_m: float
    wheel_diameter_m: float
    wheel_circumference_m: float
    motors: Tuple[
        MotorEncoderCalibration,
        MotorEncoderCalibration,
        MotorEncoderCalibration,
        MotorEncoderCalibration,
    ]

    @property
    def positions(self) -> Tuple[str, str, str, str]:
        return tuple(motor.position for motor in self.motors)

    @property
    def encoder_signs(self) -> Tuple[float, float, float, float]:
        return tuple(motor.encoder_sign for motor in self.motors)

    @property
    def counts_per_revolution(self) -> Tuple[float, float, float, float]:
        return tuple(motor.counts_per_revolution for motor in self.motors)

    def telemetry(self, index: int, counts_per_second: float,
                  relative_counts: float) -> Tuple[float, float, float]:
        """Return signed RPM, speed (m/s), and distance (m) for one channel."""
        if index not in range(4):
            raise IndexError("encoder channel index must be 0..3")
        if not all(math.isfinite(float(value)) for value in
                   (counts_per_second, relative_counts)):
            raise ValueError("encoder telemetry input must be finite")
        motor = self.motors[index]
        signed_cps = float(counts_per_second) * motor.encoder_sign
        signed_counts = float(relative_counts) * motor.encoder_sign
        rpm = signed_cps * 60.0 / motor.counts_per_revolution
        speed_mps = (
            signed_cps * self.wheel_circumference_m
            / motor.counts_per_revolution
        )
        distance_m = (
            signed_counts * self.wheel_circumference_m
            / motor.counts_per_revolution
        )
        return rpm, speed_mps, distance_m


def load_encoder_calibration(path: Path | str) -> EncoderCalibration:
    """Load and strictly validate the four physical Yahboom channels."""
    import yaml

    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    root = _mapping(raw.get("encoder_calibration"), "encoder_calibration")
    motors_raw = _mapping(root.get("motors"), "encoder_calibration.motors")
    unknown = set(motors_raw) - set(EXPECTED_CHANNELS)
    missing = set(EXPECTED_CHANNELS) - set(motors_raw)
    if unknown or missing:
        raise ValueError(
            "encoder_calibration.motors must contain exactly m1..m4 "
            f"(missing={sorted(missing)}, unknown={sorted(unknown)})"
        )

    motors = []
    for channel, expected_position in zip(EXPECTED_CHANNELS, EXPECTED_POSITIONS):
        name = f"encoder_calibration.motors.{channel}"
        item = _mapping(motors_raw[channel], name)
        position = str(item.get("position", ""))
        if position != expected_position:
            raise ValueError(
                f"{name}.position must be {expected_position}, got {position!r}"
            )
        motors.append(MotorEncoderCalibration(
            channel=channel,
            position=position,
            encoder_sign=_encoder_sign(item, name),
            counts_per_revolution=_positive_number(
                item, "counts_per_revolution", name
            ),
            confidence=str(item.get("confidence", "unknown")),
            method=str(item.get("method", "unknown")),
        ))

    return EncoderCalibration(
        wheelbase_m=_positive_number(root, "wheelbase_m", "encoder_calibration"),
        wheel_diameter_m=_positive_number(
            root, "wheel_diameter_m", "encoder_calibration"
        ),
        wheel_circumference_m=_positive_number(
            root, "wheel_circumference_m", "encoder_calibration"
        ),
        motors=tuple(motors),
    )

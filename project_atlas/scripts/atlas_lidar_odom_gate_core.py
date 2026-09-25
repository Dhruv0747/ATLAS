"""Pure validation logic for the ATLAS LiDAR-odometry candidate."""

from __future__ import annotations

import math
from dataclasses import dataclass


def wrap_angle(value: float) -> float:
    return math.atan2(math.sin(value), math.cos(value))


@dataclass(frozen=True)
class GateDecision:
    accepted: bool
    reason: str
    translation_delta_m: float = 0.0
    yaw_delta_rad: float = 0.0


class LidarOdomGate:
    """Reject non-finite, out-of-order, or physically impossible RF2O updates."""

    def __init__(
        self,
        max_linear_speed_mps: float = 1.2,
        max_angular_speed_rps: float = 2.5,
        translation_margin_m: float = 0.08,
        yaw_margin_rad: float = 0.12,
        max_gap_s: float = 1.0,
    ) -> None:
        self.max_linear_speed_mps = float(max_linear_speed_mps)
        self.max_angular_speed_rps = float(max_angular_speed_rps)
        self.translation_margin_m = float(translation_margin_m)
        self.yaw_margin_rad = float(yaw_margin_rad)
        self.max_gap_s = float(max_gap_s)
        self.last = None

    def evaluate(self, stamp_s: float, x_m: float, y_m: float, yaw_rad: float) -> GateDecision:
        values = (stamp_s, x_m, y_m, yaw_rad)
        if not all(math.isfinite(value) for value in values):
            return GateDecision(False, "NONFINITE")

        current = (float(stamp_s), float(x_m), float(y_m), wrap_angle(float(yaw_rad)))
        if self.last is None:
            self.last = current
            return GateDecision(True, "INITIALIZED")

        dt = current[0] - self.last[0]
        if dt <= 0.0:
            return GateDecision(False, "NON_MONOTONIC_TIME")
        if dt > self.max_gap_s:
            self.last = current
            return GateDecision(True, "REINITIALIZED_AFTER_GAP")

        translation = math.hypot(current[1] - self.last[1], current[2] - self.last[2])
        yaw_delta = abs(wrap_angle(current[3] - self.last[3]))
        allowed_translation = self.translation_margin_m + self.max_linear_speed_mps * dt
        allowed_yaw = self.yaw_margin_rad + self.max_angular_speed_rps * dt
        if translation > allowed_translation:
            return GateDecision(False, "TRANSLATION_JUMP", translation, yaw_delta)
        if yaw_delta > allowed_yaw:
            return GateDecision(False, "YAW_JUMP", translation, yaw_delta)

        self.last = current
        return GateDecision(True, "OK", translation, yaw_delta)


class StationaryPoseStabilizer:
    """Integrate RF2O deltas while continuously rebasing stationary scan drift."""

    def __init__(self) -> None:
        self.last_raw = None
        self.output = (0.0, 0.0, 0.0)

    def update(self, x_m: float, y_m: float, yaw_rad: float, stationary: bool):
        raw = (float(x_m), float(y_m), wrap_angle(float(yaw_rad)))
        if self.last_raw is None:
            self.last_raw = raw
            return self.output

        world_dx = raw[0] - self.last_raw[0]
        world_dy = raw[1] - self.last_raw[1]
        yaw_delta = wrap_angle(raw[2] - self.last_raw[2])
        previous_raw_yaw = self.last_raw[2]
        self.last_raw = raw
        if stationary:
            return self.output

        # Convert the RF2O world delta to a body delta, then rotate it through
        # the stabilized output heading. This prevents stationary bias updates
        # from changing the reference used for later real motion.
        body_dx = math.cos(previous_raw_yaw) * world_dx + math.sin(previous_raw_yaw) * world_dy
        body_dy = -math.sin(previous_raw_yaw) * world_dx + math.cos(previous_raw_yaw) * world_dy
        out_x, out_y, out_yaw = self.output
        out_x += math.cos(out_yaw) * body_dx - math.sin(out_yaw) * body_dy
        out_y += math.sin(out_yaw) * body_dx + math.cos(out_yaw) * body_dy
        out_yaw = wrap_angle(out_yaw + yaw_delta)
        self.output = (out_x, out_y, out_yaw)
        return self.output

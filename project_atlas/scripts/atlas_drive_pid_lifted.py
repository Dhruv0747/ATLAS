#!/usr/bin/env python3
"""Pure safety state machine for supervised, lifted-wheel drive tests.

This module deliberately owns no hardware and imports neither ROS nor a motor
driver.  The sole hardware owner is expected to apply every returned demand
and to write ``(0, 0, 0, 0)`` synchronously whenever a command is rejected or
the state becomes :class:`LiftedState.ABORTED`.

It is a commissioning aid, not a safety-rated stop.  A reachable physical
motor-power cut-off remains mandatory because a killed or wedged process can
leave PWM latched in the motor controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hmac
import math
import re
import secrets
from typing import Any, Mapping, Optional, Sequence, Tuple


CONFIRMATION_PHRASE = "LIFTED CLEAR PHYSICAL POWER CUT READY"
WHEEL_COUNT = 4
ZERO_PWM = (0.0, 0.0, 0.0, 0.0)
ZERO_SPEED = (0.0, 0.0, 0.0, 0.0)

MAX_HEARTBEAT_LEASE_S = 0.50
MAX_POLICY_AGE_S = 0.50
MAX_ENCODER_AGE_S = 0.35
MAX_MEASURED_SPEED_MPS = 1.50
MAX_STATIONARY_SPEED_MPS = 0.02
MIN_STATIONARY_DWELL_S = 0.50
MIN_REST_S = 1.00

# Commissioning bounds, not advertised component limits.  Lifted testing adds
# no value while the computer is thermally stressed or the 4S LiFePO4 pack is
# stale, unhealthy, outside its normal cell envelope, or materially
# unbalanced.  Missing telemetry is never interpreted as healthy.
MAX_JETSON_TEMP_C = 80.0
MAX_BMS_AGE_S = 10.0
MIN_BMS_CELL_V = 3.00
MAX_BMS_CELL_V = 3.65
MAX_BMS_CELL_SPREAD_V = 0.10

MAX_RAW_PWM = 50
MIN_RAW_DURATION_S = 0.20
MAX_RAW_DURATION_S = 0.50

MAX_PID_TARGET_MPS = 0.10
MIN_PID_DURATION_S = 0.80
MAX_PID_DURATION_S = 1.00
MAX_PID_PWM = 60.0
MAX_PID_SLEW_PWM_PER_S = 80.0

REVERSE_SPEED_THRESHOLD_MPS = 0.03
REVERSE_FAULT_S = 0.40
FROZEN_TARGET_THRESHOLD_MPS = 0.015
FROZEN_SPEED_THRESHOLD_MPS = 0.015
FROZEN_FAULT_S = 0.80

_TOKEN = re.compile(r"[0-9a-f]{32}")


class LiftedState(str, Enum):
    IDLE = "IDLE"
    LOCKED = "LOCKED"
    ARMED = "ARMED"
    PULSE = "PULSE"
    REST = "REST"
    ABORTED = "ABORTED"


class PulseMode(str, Enum):
    RAW_PULSE = "raw_pulse"
    PID_SINGLE = "pid_single"
    PID_FOUR = "pid_four"


class CommissioningRejected(ValueError):
    """A request or live condition failed closed."""


def _is_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _all_finite(values: Sequence[Any], length: int) -> bool:
    return (
        isinstance(values, (tuple, list))
        and len(values) == length
        and all(_is_number(value) for value in values)
    )


@dataclass(frozen=True)
class SafetySnapshot:
    """Inputs the hardware owner must refresh before every request/tick."""

    stop_latched: bool
    policy_age_s: float
    drive_mode: str
    cmd_vel: Tuple[float, float, float]
    applied_pwm: Tuple[float, float, float, float]
    controller_link_ok: bool
    encoder_valid: Tuple[bool, bool, bool, bool]
    encoder_ages_s: Tuple[float, float, float, float]
    measured_speeds_mps: Tuple[float, float, float, float]
    jetson_temp_c: float
    bms_ok: bool
    bms_age_s: float
    bms_cell_voltages_v: Tuple[float, float, float, float]
    stationary_duration_s: float
    physical_power_cut_ready: bool
    remote_b_stop: bool = False
    emergency_stop: bool = False
    voice_stop: bool = False
    shutdown: bool = False


@dataclass(frozen=True)
class CommissionDemand:
    """The only traction demand authorized by the current state."""

    state: LiftedState
    motor_pwm: Tuple[float, float, float, float]
    speed_targets_mps: Tuple[float, float, float, float]
    traction_locked: bool
    pulse_active: bool
    mode: Optional[PulseMode]
    fault_reason: str


class LiftedDriveCommission:
    """Lease-bound, fail-zero state machine for lifted-wheel commissioning.

    ``mapping_reviewed`` and ``single_wheel_reviewed`` must come from reviewed
    configuration/evidence.  They cannot be supplied by a pulse request, so a
    remote caller cannot bypass the staged PID gates or inject arbitrary gains.
    """

    def __init__(
        self,
        *,
        mapping_reviewed: bool = False,
        single_wheel_reviewed: Sequence[bool] = (False, False, False, False),
        heartbeat_lease_s: float = MAX_HEARTBEAT_LEASE_S,
        rest_s: float = MIN_REST_S,
        pid_slew_pwm_per_s: float = MAX_PID_SLEW_PWM_PER_S,
    ) -> None:
        if type(mapping_reviewed) is not bool:
            raise ValueError("mapping_reviewed must be boolean")
        if (
            not isinstance(single_wheel_reviewed, (tuple, list))
            or len(single_wheel_reviewed) != WHEEL_COUNT
            or any(type(value) is not bool for value in single_wheel_reviewed)
        ):
            raise ValueError("single_wheel_reviewed must contain four booleans")
        if (
            not _is_number(heartbeat_lease_s)
            or not 0.0 < float(heartbeat_lease_s) <= MAX_HEARTBEAT_LEASE_S
        ):
            raise ValueError("heartbeat lease must be positive and at most 0.5 s")
        if not _is_number(rest_s) or float(rest_s) < MIN_REST_S:
            raise ValueError("zero-output rest must be at least 1.0 s")
        if (
            not _is_number(pid_slew_pwm_per_s)
            or not 0.0 < float(pid_slew_pwm_per_s) <= MAX_PID_SLEW_PWM_PER_S
        ):
            raise ValueError("PID slew bound must be positive and at most 80 PWM/s")

        self.mapping_reviewed = mapping_reviewed
        self.single_wheel_reviewed = tuple(single_wheel_reviewed)
        self.heartbeat_lease_s = float(heartbeat_lease_s)
        self.rest_s = float(rest_s)
        self.pid_slew_pwm_per_s = float(pid_slew_pwm_per_s)

        self.state = LiftedState.IDLE
        self.session: Optional[str] = None
        self.sequence = -1
        self.lease_deadline = 0.0
        self.pulse_deadline = 0.0
        self.rest_deadline = 0.0
        self.mode: Optional[PulseMode] = None
        self.wheel_index: Optional[int] = None
        self.raw_pwm = 0
        self.target_mps = 0.0
        self.fault_reason = ""

        self._last_event_at: Optional[float] = None
        self._last_output_at = 0.0
        self._last_feedback_at = 0.0
        self._last_pwm = ZERO_PWM
        self._reverse_duration = [0.0] * WHEEL_COUNT
        self._frozen_duration = [0.0] * WHEEL_COUNT

    @staticmethod
    def new_session_token() -> str:
        """Return the required 128-bit random, lower-case hexadecimal token."""

        return secrets.token_hex(16)

    @property
    def locked(self) -> bool:
        return self.state != LiftedState.IDLE

    def demand(self) -> CommissionDemand:
        targets = ZERO_SPEED
        if self.state == LiftedState.PULSE:
            if self.mode == PulseMode.PID_SINGLE and self.wheel_index is not None:
                values = [0.0] * WHEEL_COUNT
                values[self.wheel_index] = self.target_mps
                targets = tuple(values)
            elif self.mode == PulseMode.PID_FOUR:
                targets = (self.target_mps,) * WHEEL_COUNT
        pwm = self._last_pwm if self.state == LiftedState.PULSE else ZERO_PWM
        return CommissionDemand(
            state=self.state,
            motor_pwm=pwm,
            speed_targets_mps=targets,
            traction_locked=self.locked,
            pulse_active=self.state == LiftedState.PULSE,
            mode=self.mode if self.state == LiftedState.PULSE else None,
            fault_reason=self.fault_reason,
        )

    def status(self) -> Mapping[str, Any]:
        demand = self.demand()
        return {
            "state": demand.state.value,
            "traction_locked": demand.traction_locked,
            "pulse_active": demand.pulse_active,
            "mode": demand.mode.value if demand.mode is not None else None,
            "wheel": None if self.wheel_index is None else self.wheel_index + 1,
            "motor_pwm": list(demand.motor_pwm),
            "speed_targets_mps": list(demand.speed_targets_mps),
            "fault_reason": self.fault_reason,
            "sequence": self.sequence,
            "session_active": self.session is not None,
        }

    def command(
        self,
        request: Mapping[str, Any],
        now: float,
        safety: SafetySnapshot,
    ) -> CommissionDemand:
        """Validate and apply one sequenced operator request.

        Any rejected request while a session is locked transitions to the
        latched, zero-output ``ABORTED`` state.  ``exit`` is the sole recovery
        from that state.
        """

        priority = self._priority_stop(safety)
        if priority:
            if self.locked:
                self._abort(priority)
            raise CommissioningRejected(priority)
        self._validate_time(now)
        if not isinstance(request, Mapping):
            self._reject("request_not_mapping")

        action = request.get("op")
        if action == "enter":
            return self._enter(request, float(now), safety)
        if self.state == LiftedState.IDLE:
            raise CommissioningRejected("no_active_session")

        if action == "exit":
            return self._exit(request, float(now), safety)
        if action == "abort":
            self._only_fields(request, {"op", "session", "seq", "reason"})
            self._validate_active_identity(request)
            reason = request.get("reason", "operator_abort")
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 80:
                self._reject("invalid_abort_reason")
            self.sequence = int(request["seq"])
            self._abort(reason.strip())
            return self.demand()
        if self.state == LiftedState.ABORTED:
            raise CommissioningRejected("aborted_latch_requires_exit")

        problem = self._snapshot_problem(safety, require_latched=None)
        if problem:
            self._abort(problem)
            raise CommissioningRejected(problem)
        if self.state in (LiftedState.ARMED, LiftedState.PULSE, LiftedState.REST):
            if safety.stop_latched:
                self._abort("software_stop_latched")
                raise CommissioningRejected("software_stop_latched")
        if float(now) >= self.lease_deadline:
            self._abort("heartbeat_expired")
            raise CommissioningRejected("heartbeat_expired")

        # Request callbacks can run before the periodic watchdog callback.  A
        # heartbeat at/after a pulse deadline must therefore zero first; it
        # must never extend a pulse merely because callback ordering changed.
        if self.state == LiftedState.PULSE and self.mode in (
            PulseMode.PID_SINGLE, PulseMode.PID_FOUR
        ):
            feedback_dt = max(0.0, float(now) - self._last_feedback_at)
            self._last_feedback_at = float(now)
            feedback_fault = self._feedback_problem(safety, feedback_dt)
            if feedback_fault:
                self._abort(feedback_fault)
                raise CommissioningRejected(feedback_fault)
        if self.state == LiftedState.PULSE and float(now) >= self.pulse_deadline:
            self._start_rest(float(now))
        elif self.state == LiftedState.REST and float(now) >= self.rest_deadline:
            self._zero_output()
            self.state = LiftedState.ARMED

        self._validate_active_identity(request)
        self.sequence = int(request["seq"])
        self.lease_deadline = float(now) + self.heartbeat_lease_s

        if action == "heartbeat":
            self._only_fields(request, {"op", "session", "seq"})
        elif action == "arm":
            self._only_fields(request, {"op", "session", "seq"})
            if self.state != LiftedState.LOCKED:
                self._reject("arm_requires_locked_state")
            if safety.stop_latched is not False:
                self._reject("reset_software_stop_before_arm")
            stationary_problem = self._stationary_problem(safety)
            if stationary_problem:
                self._reject(stationary_problem)
            self.state = LiftedState.ARMED
            self._zero_output()
        elif action == "pulse":
            if self.state != LiftedState.ARMED:
                self._reject("pulse_requires_armed_state")
            stationary_problem = self._stationary_problem(safety)
            if stationary_problem:
                self._reject(stationary_problem)
            self._start_pulse(request, float(now))
        elif action == "end":
            self._only_fields(request, {"op", "session", "seq"})
            if self.state != LiftedState.PULSE:
                self._reject("end_requires_active_pulse")
            self._start_rest(float(now))
        else:
            self._reject("unsupported_operation")
        return self.demand()

    def tick(
        self,
        now: float,
        safety: SafetySnapshot,
        pid_outputs: Optional[Sequence[float]] = None,
    ) -> CommissionDemand:
        """Run the watchdog and authorize at most one bounded motor demand."""

        priority = self._priority_stop(safety)
        if priority:
            if self.locked:
                self._abort(priority)
            return self.demand()
        self._validate_time(now)
        if self.state == LiftedState.IDLE:
            self._zero_output()
            return self.demand()
        if self.state == LiftedState.ABORTED:
            self._zero_output()
            return self.demand()

        problem = self._snapshot_problem(safety, require_latched=None)
        if problem:
            self._abort(problem)
            return self.demand()
        if self.state in (LiftedState.ARMED, LiftedState.PULSE, LiftedState.REST):
            if safety.stop_latched:
                self._abort("software_stop_latched")
                return self.demand()
        if float(now) >= self.lease_deadline:
            self._abort("heartbeat_expired")
            return self.demand()

        # Evaluate PID feedback before the deadline transition.  Otherwise a
        # pulse can end "cleanly" at the exact instant a reverse/frozen fault
        # becomes observable.
        if self.state == LiftedState.PULSE and self.mode in (
            PulseMode.PID_SINGLE, PulseMode.PID_FOUR
        ):
            feedback_dt = max(0.0, float(now) - self._last_feedback_at)
            self._last_feedback_at = float(now)
            feedback_fault = self._feedback_problem(safety, feedback_dt)
            if feedback_fault:
                self._abort(feedback_fault)
                return self.demand()

        if self.state == LiftedState.PULSE and float(now) >= self.pulse_deadline:
            self._start_rest(float(now))
            return self.demand()
        if self.state == LiftedState.REST:
            self._zero_output()
            if float(now) >= self.rest_deadline:
                # This merely permits another deliberate pulse request.  It
                # never starts, repeats, or reverses a pulse automatically.
                self.state = LiftedState.ARMED
            return self.demand()
        if self.state != LiftedState.PULSE:
            self._zero_output()
            return self.demand()

        if self.mode == PulseMode.RAW_PULSE:
            values = [0.0] * WHEEL_COUNT
            if self.wheel_index is None:
                self._abort("invalid_single_wheel_state")
                return self.demand()
            values[self.wheel_index] = float(self.raw_pwm)
            self._last_pwm = tuple(values)
            self._last_output_at = float(now)
            return self.demand()

        output_fault = self._apply_pid_outputs(pid_outputs, float(now))
        if output_fault:
            self._abort(output_fault)
        return self.demand()

    def abort(self, reason: str) -> CommissionDemand:
        """Synchronously clear the demand and latch an external fault."""

        if self.locked:
            text = str(reason).strip() or "external_abort"
            self._abort(text)
        else:
            self._zero_output()
        return self.demand()

    def _enter(
        self,
        request: Mapping[str, Any],
        now: float,
        safety: SafetySnapshot,
    ) -> CommissionDemand:
        if self.state != LiftedState.IDLE:
            self._reject("session_already_locked")
        self._only_fields(
            request, {"op", "session", "seq", "confirm", "lifted"}, active=False
        )
        token = request.get("session")
        seq = request.get("seq")
        if not self._valid_token(token):
            raise CommissioningRejected("invalid_session_token")
        if type(seq) is not int or seq < 0:
            raise CommissioningRejected("invalid_command_sequence")
        if request.get("confirm") != CONFIRMATION_PHRASE:
            raise CommissioningRejected("exact_confirmation_required")
        if request.get("lifted") is not True:
            raise CommissioningRejected("lifted_wheels_confirmation_required")
        problem = self._snapshot_problem(safety, require_latched=True)
        if problem:
            raise CommissioningRejected(problem)
        stationary_problem = self._stationary_problem(safety)
        if stationary_problem:
            raise CommissioningRejected(stationary_problem)

        self.state = LiftedState.LOCKED
        self.session = str(token)
        self.sequence = int(seq)
        self.lease_deadline = now + self.heartbeat_lease_s
        self.fault_reason = ""
        self.mode = None
        self.wheel_index = None
        self._zero_output()
        self._last_output_at = now
        self._last_feedback_at = now
        return self.demand()

    def _exit(
        self,
        request: Mapping[str, Any],
        now: float,
        safety: SafetySnapshot,
    ) -> CommissionDemand:
        self._only_fields(request, {"op", "session", "seq"})
        self._validate_active_identity(request)
        release_problem = self._release_problem(safety)
        if release_problem:
            self._abort(release_problem)
            raise CommissioningRejected(release_problem)
        self._zero_output()
        self.state = LiftedState.IDLE
        self.session = None
        self.sequence = -1
        self.lease_deadline = 0.0
        self.pulse_deadline = 0.0
        self.rest_deadline = 0.0
        self.mode = None
        self.wheel_index = None
        self.raw_pwm = 0
        self.target_mps = 0.0
        self.fault_reason = ""
        self._last_event_at = now
        self._reset_feedback_timers()
        return self.demand()

    def _start_pulse(self, request: Mapping[str, Any], now: float) -> None:
        try:
            mode = PulseMode(request.get("mode"))
        except (TypeError, ValueError):
            self._reject("unknown_pulse_mode")
            return

        duration = request.get("duration_s")
        if not _is_number(duration):
            self._reject("invalid_pulse_duration")
        duration = float(duration)

        self.mode = mode
        self.wheel_index = None
        self.raw_pwm = 0
        self.target_mps = 0.0

        if mode == PulseMode.RAW_PULSE:
            self._only_fields(
                request,
                {"op", "session", "seq", "mode", "wheel", "pwm", "duration_s"},
            )
            wheel = request.get("wheel")
            pwm = request.get("pwm")
            if type(wheel) is not int or wheel not in (1, 2, 3, 4):
                self._reject("raw_pulse_requires_one_wheel")
            if type(pwm) is not int or pwm == 0 or abs(pwm) > MAX_RAW_PWM:
                self._reject("raw_pwm_out_of_bounds")
            if not MIN_RAW_DURATION_S <= duration <= MAX_RAW_DURATION_S:
                self._reject("raw_duration_out_of_bounds")
            self.wheel_index = int(wheel) - 1
            self.raw_pwm = int(pwm)
            values = [0.0] * WHEEL_COUNT
            values[self.wheel_index] = float(self.raw_pwm)
            self._last_pwm = tuple(values)
        elif mode == PulseMode.PID_SINGLE:
            self._only_fields(
                request,
                {"op", "session", "seq", "mode", "wheel", "target_mps", "duration_s"},
            )
            wheel = request.get("wheel")
            target = request.get("target_mps")
            if not self.mapping_reviewed:
                self._reject("mapping_sign_cpr_review_required")
            if type(wheel) is not int or wheel not in (1, 2, 3, 4):
                self._reject("pid_single_requires_one_wheel")
            if not _is_number(target) or not 0.0 < abs(float(target)) <= MAX_PID_TARGET_MPS:
                self._reject("pid_target_out_of_bounds")
            if not MIN_PID_DURATION_S <= duration <= MAX_PID_DURATION_S:
                self._reject("pid_duration_out_of_bounds")
            self.wheel_index = int(wheel) - 1
            self.target_mps = float(target)
            self._last_pwm = ZERO_PWM
        else:
            self._only_fields(
                request,
                {"op", "session", "seq", "mode", "target_mps", "duration_s", "angular_z"},
            )
            target = request.get("target_mps")
            angular_z = request.get("angular_z", 0.0)
            if not self.mapping_reviewed:
                self._reject("mapping_sign_cpr_review_required")
            if not all(self.single_wheel_reviewed):
                self._reject("all_single_wheel_reviews_required")
            if not _is_number(target) or not 0.0 < abs(float(target)) <= MAX_PID_TARGET_MPS:
                self._reject("pid_target_out_of_bounds")
            if not _is_number(angular_z) or float(angular_z) != 0.0:
                self._reject("pid_four_must_be_straight")
            if not MIN_PID_DURATION_S <= duration <= MAX_PID_DURATION_S:
                self._reject("pid_duration_out_of_bounds")
            self.target_mps = float(target)
            self._last_pwm = ZERO_PWM

        self.state = LiftedState.PULSE
        self.pulse_deadline = now + duration
        self._last_output_at = now
        self._last_feedback_at = now
        self._reset_feedback_timers()

    def _start_rest(self, now: float) -> None:
        self._zero_output()
        self.state = LiftedState.REST
        self.pulse_deadline = 0.0
        self.rest_deadline = now + self.rest_s
        self.mode = None
        self.wheel_index = None
        self.raw_pwm = 0
        self.target_mps = 0.0
        self._reset_feedback_timers()

    def _apply_pid_outputs(
        self, pid_outputs: Optional[Sequence[float]], now: float
    ) -> str:
        if pid_outputs is None:
            return "pid_output_missing"
        if not _all_finite(pid_outputs, WHEEL_COUNT):
            return "pid_output_invalid"
        values = tuple(float(value) for value in pid_outputs)
        if any(abs(value) > MAX_PID_PWM for value in values):
            return "pid_output_limit_exceeded"
        if self.mode == PulseMode.PID_SINGLE:
            if self.wheel_index is None:
                return "invalid_single_wheel_state"
            if any(
                value != 0.0
                for index, value in enumerate(values)
                if index != self.wheel_index
            ):
                return "pid_nonselected_wheel_output"

        dt = max(0.0, now - self._last_output_at)
        max_step = self.pid_slew_pwm_per_s * dt
        if any(
            abs(value - previous) > max_step + 1.0e-9
            for value, previous in zip(values, self._last_pwm)
        ):
            return "pid_output_slew_exceeded"
        self._last_pwm = values
        self._last_output_at = now
        return ""

    def _feedback_problem(self, safety: SafetySnapshot, dt: float) -> str:
        if self.mode not in (PulseMode.PID_SINGLE, PulseMode.PID_FOUR):
            self._reset_feedback_timers()
            return ""
        targets = self.demand().speed_targets_mps
        for index, (target, measured) in enumerate(
            zip(targets, safety.measured_speeds_mps)
        ):
            moving = abs(target) >= FROZEN_TARGET_THRESHOLD_MPS
            reversed_feedback = (
                moving
                and abs(measured) >= REVERSE_SPEED_THRESHOLD_MPS
                and target * measured < 0.0
            )
            frozen_feedback = (
                moving and abs(measured) < FROZEN_SPEED_THRESHOLD_MPS
            )
            self._reverse_duration[index] = (
                self._reverse_duration[index] + dt if reversed_feedback else 0.0
            )
            self._frozen_duration[index] = (
                self._frozen_duration[index] + dt if frozen_feedback else 0.0
            )
            if self._reverse_duration[index] + 1.0e-9 >= REVERSE_FAULT_S:
                return "encoder_reversed_M{}".format(index + 1)
            if self._frozen_duration[index] + 1.0e-9 >= FROZEN_FAULT_S:
                return "encoder_frozen_M{}".format(index + 1)
        return ""

    def _snapshot_problem(
        self, safety: SafetySnapshot, require_latched: Optional[bool]
    ) -> str:
        if not isinstance(safety, SafetySnapshot):
            return "invalid_safety_snapshot"
        boolean_values = (
            safety.stop_latched,
            safety.controller_link_ok,
            safety.physical_power_cut_ready,
            safety.remote_b_stop,
            safety.emergency_stop,
            safety.voice_stop,
            safety.shutdown,
        )
        if any(type(value) is not bool for value in boolean_values):
            return "invalid_safety_snapshot"
        if not safety.physical_power_cut_ready:
            return "physical_power_cut_not_confirmed"
        if not _is_number(safety.policy_age_s) or float(safety.policy_age_s) < 0.0:
            return "invalid_safety_snapshot"
        if float(safety.policy_age_s) > MAX_POLICY_AGE_S:
            return "control_policy_stale"
        if not isinstance(safety.drive_mode, str):
            return "invalid_safety_snapshot"
        if not _all_finite(safety.cmd_vel, 3):
            return "invalid_safety_snapshot"
        if not _all_finite(safety.applied_pwm, WHEEL_COUNT):
            return "invalid_safety_snapshot"
        if (
            not isinstance(safety.encoder_valid, (tuple, list))
            or len(safety.encoder_valid) != WHEEL_COUNT
            or any(type(value) is not bool for value in safety.encoder_valid)
        ):
            return "invalid_safety_snapshot"
        if not _all_finite(safety.encoder_ages_s, WHEEL_COUNT):
            return "invalid_safety_snapshot"
        if not _all_finite(safety.measured_speeds_mps, WHEEL_COUNT):
            return "invalid_safety_snapshot"
        if (
            not _is_number(safety.stationary_duration_s)
            or float(safety.stationary_duration_s) < 0.0
        ):
            return "invalid_safety_snapshot"
        if any(float(age) < 0.0 for age in safety.encoder_ages_s):
            return "invalid_safety_snapshot"
        if not _is_number(safety.jetson_temp_c):
            return "jetson_temperature_unavailable"
        if float(safety.jetson_temp_c) >= MAX_JETSON_TEMP_C:
            return "jetson_over_temperature"
        if type(safety.bms_ok) is not bool or safety.bms_ok is not True:
            return "bms_unhealthy"
        if not _is_number(safety.bms_age_s) or float(safety.bms_age_s) < 0.0:
            return "bms_telemetry_unavailable"
        if float(safety.bms_age_s) > MAX_BMS_AGE_S:
            return "bms_telemetry_stale"
        if not _all_finite(safety.bms_cell_voltages_v, WHEEL_COUNT):
            return "bms_cells_unavailable"
        cells = tuple(float(value) for value in safety.bms_cell_voltages_v)
        for index, voltage in enumerate(cells):
            if voltage < MIN_BMS_CELL_V:
                return "bms_cell_undervoltage_C{}".format(index + 1)
            if voltage > MAX_BMS_CELL_V:
                return "bms_cell_overvoltage_C{}".format(index + 1)
        if max(cells) - min(cells) > MAX_BMS_CELL_SPREAD_V:
            return "bms_cell_imbalance"
        if any(value != 0.0 for value in safety.cmd_vel):
            return "nonzero_cmd_vel"
        if safety.drive_mode.strip().upper() != "STOPPED":
            return "drive_owner_not_stopped"
        if not safety.controller_link_ok:
            return "motor_controller_link_lost"
        for index, valid in enumerate(safety.encoder_valid):
            if not valid:
                return "encoder_invalid_M{}".format(index + 1)
            if float(safety.encoder_ages_s[index]) > MAX_ENCODER_AGE_S:
                return "encoder_stale_M{}".format(index + 1)
            if abs(float(safety.measured_speeds_mps[index])) > MAX_MEASURED_SPEED_MPS:
                return "encoder_speed_out_of_bounds_M{}".format(index + 1)

        if self.state == LiftedState.PULSE:
            limit = MAX_RAW_PWM if self.mode == PulseMode.RAW_PULSE else MAX_PID_PWM
            if any(abs(float(value)) > limit for value in safety.applied_pwm):
                return "applied_pwm_out_of_bounds"
            if self.mode in (PulseMode.RAW_PULSE, PulseMode.PID_SINGLE):
                if self.wheel_index is None:
                    return "invalid_single_wheel_state"
                if any(
                    value != 0.0
                    for index, value in enumerate(safety.applied_pwm)
                    if index != self.wheel_index
                ):
                    return "applied_pwm_nonselected_wheel"
        elif any(value != 0.0 for value in safety.applied_pwm):
            return "applied_pwm_not_zero"

        if require_latched is True and safety.stop_latched is not True:
            return "fresh_latched_stop_required"
        if require_latched is False and safety.stop_latched is not False:
            return "software_stop_must_be_reset"
        return ""

    def _release_problem(self, safety: SafetySnapshot) -> str:
        if not isinstance(safety, SafetySnapshot):
            return "invalid_safety_snapshot"
        boolean_values = (
            safety.stop_latched,
            safety.controller_link_ok,
            safety.remote_b_stop,
            safety.emergency_stop,
            safety.voice_stop,
            safety.shutdown,
        )
        if any(type(value) is not bool for value in boolean_values):
            return "invalid_safety_snapshot"
        if (
            not _is_number(safety.policy_age_s)
            or float(safety.policy_age_s) < 0.0
            or float(safety.policy_age_s) > MAX_POLICY_AGE_S
            or safety.stop_latched is not True
        ):
            return "fresh_latched_stop_required_for_exit"
        if not safety.controller_link_ok:
            return "motor_controller_link_lost"
        if not _all_finite(safety.cmd_vel, 3) or not _all_finite(
            safety.applied_pwm, WHEEL_COUNT
        ):
            return "invalid_safety_snapshot"
        if any(value != 0.0 for value in safety.cmd_vel):
            return "nonzero_cmd_vel"
        if any(value != 0.0 for value in safety.applied_pwm):
            return "applied_pwm_not_zero"
        if not isinstance(safety.drive_mode, str) or safety.drive_mode.strip().upper() != "STOPPED":
            return "drive_owner_not_stopped"
        stationary_problem = self._stationary_problem(safety)
        if stationary_problem:
            return stationary_problem
        return ""

    @staticmethod
    def _stationary_problem(safety: SafetySnapshot) -> str:
        if not _all_finite(safety.measured_speeds_mps, WHEEL_COUNT):
            return "invalid_safety_snapshot"
        if any(
            abs(float(speed)) > MAX_STATIONARY_SPEED_MPS
            for speed in safety.measured_speeds_mps
        ):
            return "wheels_not_stationary"
        if (
            not _is_number(safety.stationary_duration_s)
            or float(safety.stationary_duration_s) < MIN_STATIONARY_DWELL_S
        ):
            return "stationary_dwell_incomplete"
        return ""

    @staticmethod
    def _priority_stop(safety: Any) -> str:
        # Raw joystick B and the physical/firmware E-stop outrank every other
        # protocol, lease, feedback, or controller fault.
        if isinstance(safety, SafetySnapshot):
            if safety.remote_b_stop is True:
                return "remote_b_stop"
            if safety.emergency_stop is True:
                return "emergency_stop"
            if safety.voice_stop is True:
                return "voice_stop"
            if safety.shutdown is True:
                return "service_shutdown"
        return ""

    def _validate_active_identity(self, request: Mapping[str, Any]) -> None:
        token = request.get("session")
        seq = request.get("seq")
        if not self._valid_token(token) or self.session is None or not hmac.compare_digest(
            str(token), self.session
        ):
            self._reject("invalid_or_foreign_session")
        if type(seq) is not int or seq <= self.sequence:
            self._reject("old_or_invalid_command_sequence")

    @staticmethod
    def _valid_token(token: Any) -> bool:
        return isinstance(token, str) and _TOKEN.fullmatch(token) is not None

    def _validate_time(self, now: Any) -> None:
        if not _is_number(now):
            self._reject("invalid_monotonic_time")
        value = float(now)
        if self._last_event_at is not None and value < self._last_event_at:
            self._reject("monotonic_time_regressed")
        self._last_event_at = value

    def _only_fields(
        self, request: Mapping[str, Any], allowed: set, active: bool = True
    ) -> None:
        if any(key not in allowed for key in request):
            if active:
                self._reject("unexpected_request_field")
            raise CommissioningRejected("unexpected_request_field")

    def _reject(self, reason: str) -> None:
        if self.locked:
            self._abort(reason)
        raise CommissioningRejected(reason)

    def _abort(self, reason: str) -> None:
        self._zero_output()
        self.state = LiftedState.ABORTED
        self.fault_reason = str(reason)
        self.pulse_deadline = 0.0
        self.rest_deadline = 0.0
        self.mode = None
        self.wheel_index = None
        self.raw_pwm = 0
        self.target_mps = 0.0
        self._reset_feedback_timers()

    def _zero_output(self) -> None:
        self._last_pwm = ZERO_PWM

    def _reset_feedback_timers(self) -> None:
        self._reverse_duration = [0.0] * WHEEL_COUNT
        self._frozen_duration = [0.0] * WHEEL_COUNT

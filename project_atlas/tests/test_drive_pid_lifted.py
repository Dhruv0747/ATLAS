import math
from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from atlas_drive_pid_lifted import (  # noqa: E402
    CONFIRMATION_PHRASE,
    CommissioningRejected,
    LiftedDriveCommission,
    LiftedState,
    PulseMode,
    SafetySnapshot,
)


TOKEN = "0123456789abcdef0123456789abcdef"


def snapshot(**changes):
    values = {
        "stop_latched": False,
        "policy_age_s": 0.0,
        "drive_mode": "STOPPED",
        "cmd_vel": (0.0, 0.0, 0.0),
        "applied_pwm": (0.0, 0.0, 0.0, 0.0),
        "controller_link_ok": True,
        "encoder_valid": (True, True, True, True),
        "encoder_ages_s": (0.0, 0.0, 0.0, 0.0),
        "measured_speeds_mps": (0.02, 0.02, 0.02, 0.02),
        "jetson_temp_c": 55.0,
        "bms_ok": True,
        "bms_age_s": 0.0,
        "bms_cell_voltages_v": (3.35, 3.35, 3.35, 3.35),
        "stationary_duration_s": 0.5,
        "physical_power_cut_ready": True,
    }
    values.update(changes)
    return SafetySnapshot(**values)


class LiftedDriveCommissionTests(unittest.TestCase):
    def setUp(self):
        self.core = LiftedDriveCommission(
            mapping_reviewed=True,
            single_wheel_reviewed=(True, True, True, True),
        )
        self.now = 0.0
        self.seq = 0

    def request(self, op, safety=None, **fields):
        self.seq += 1
        message = {"op": op, "session": TOKEN, "seq": self.seq}
        message.update(fields)
        return self.core.command(message, self.now, safety or snapshot())

    def enter(self):
        return self.request(
            "enter",
            snapshot(stop_latched=True),
            confirm=CONFIRMATION_PHRASE,
            lifted=True,
        )

    def arm(self):
        return self.request("arm")

    def raw_pulse(self, **overrides):
        fields = {"mode": "raw_pulse", "wheel": 2, "pwm": 40, "duration_s": 0.4}
        fields.update(overrides)
        return self.request("pulse", **fields)

    def pid_single(self, **overrides):
        fields = {"mode": "pid_single", "wheel": 2, "target_mps": 0.08, "duration_s": 1.0}
        fields.update(overrides)
        return self.request("pulse", **fields)

    def pid_four(self, **overrides):
        fields = {"mode": "pid_four", "target_mps": 0.08, "duration_s": 1.0, "angular_z": 0.0}
        fields.update(overrides)
        return self.request("pulse", **fields)

    def assert_zero(self):
        demand = self.core.demand()
        self.assertEqual(demand.motor_pwm, (0.0,) * 4)
        self.assertEqual(demand.speed_targets_mps, (0.0,) * 4)

    def test_initial_state_is_unlocked_zero(self):
        demand = self.core.demand()
        self.assertEqual(demand.state, LiftedState.IDLE)
        self.assertFalse(demand.traction_locked)
        self.assertFalse(demand.pulse_active)
        self.assert_zero()

    def test_session_tokens_are_128_bit_hex(self):
        first = LiftedDriveCommission.new_session_token()
        second = LiftedDriveCommission.new_session_token()
        self.assertRegex(first, r"^[0-9a-f]{32}$")
        self.assertNotEqual(first, second)

    def test_enter_requires_exact_phrase_lifted_and_token(self):
        cases = (
            {"confirm": CONFIRMATION_PHRASE.lower(), "lifted": True},
            {"confirm": CONFIRMATION_PHRASE, "lifted": False},
        )
        for fields in cases:
            with self.subTest(fields=fields):
                core = LiftedDriveCommission()
                with self.assertRaises(CommissioningRejected):
                    core.command(
                        {"op": "enter", "session": TOKEN, "seq": 0, **fields},
                        0.0,
                        snapshot(stop_latched=True),
                    )
                self.assertEqual(core.state, LiftedState.IDLE)
                self.assertEqual(core.demand().motor_pwm, (0.0,) * 4)
        with self.assertRaises(CommissioningRejected):
            self.core.command(
                {"op": "enter", "session": "predictable", "seq": 0,
                 "confirm": CONFIRMATION_PHRASE, "lifted": True},
                0.0,
                snapshot(stop_latched=True),
            )

    def test_enter_locks_without_movement_then_arm_needs_reset_stop(self):
        demand = self.enter()
        self.assertEqual(demand.state, LiftedState.LOCKED)
        self.assertTrue(demand.traction_locked)
        self.assert_zero()
        demand = self.arm()
        self.assertEqual(demand.state, LiftedState.ARMED)
        self.assert_zero()

    def test_arm_while_stop_still_latched_aborts(self):
        self.enter()
        with self.assertRaisesRegex(CommissioningRejected, "reset_software_stop"):
            self.request("arm", snapshot(stop_latched=True))
        self.assertEqual(self.core.state, LiftedState.ABORTED)
        self.assert_zero()

    def test_entry_checks_every_zero_and_fresh_gate(self):
        cases = {
            "fresh_latched_stop_required": {"stop_latched": False},
            "control_policy_stale": {"stop_latched": True, "policy_age_s": 0.51},
            "nonzero_cmd_vel": {"stop_latched": True, "cmd_vel": (0.01, 0.0, 0.0)},
            "applied_pwm_not_zero": {"stop_latched": True, "applied_pwm": (1.0, 0.0, 0.0, 0.0)},
            "drive_owner_not_stopped": {"stop_latched": True, "drive_mode": "REMOTE"},
            "motor_controller_link_lost": {"stop_latched": True, "controller_link_ok": False},
            "encoder_invalid_M3": {"stop_latched": True, "encoder_valid": (True, True, False, True)},
            "encoder_stale_M4": {"stop_latched": True, "encoder_ages_s": (0.0, 0.0, 0.0, 0.351)},
            "encoder_speed_out_of_bounds_M1": {"stop_latched": True, "measured_speeds_mps": (1.51, 0.0, 0.0, 0.0)},
        }
        for reason, changes in cases.items():
            with self.subTest(reason=reason):
                core = LiftedDriveCommission()
                with self.assertRaisesRegex(CommissioningRejected, reason):
                    core.command(
                        {"op": "enter", "session": TOKEN, "seq": 0,
                         "confirm": CONFIRMATION_PHRASE, "lifted": True},
                        0.0,
                        snapshot(**changes),
                    )
                self.assertEqual(core.state, LiftedState.IDLE)
                self.assertEqual(core.demand().motor_pwm, (0.0,) * 4)

    def test_entry_fails_closed_on_cutoff_thermal_and_bms_gates(self):
        cases = {
            "physical_power_cut_not_confirmed": {
                "physical_power_cut_ready": False,
            },
            "jetson_temperature_unavailable": {"jetson_temp_c": float("nan")},
            "jetson_over_temperature": {"jetson_temp_c": 80.0},
            "bms_unhealthy": {"bms_ok": False},
            "bms_telemetry_stale": {"bms_age_s": 10.001},
            "bms_cell_undervoltage_C1": {
                "bms_cell_voltages_v": (2.999, 3.35, 3.35, 3.35),
            },
            "bms_cell_overvoltage_C4": {
                "bms_cell_voltages_v": (3.35, 3.35, 3.35, 3.651),
            },
            "bms_cell_imbalance": {
                "bms_cell_voltages_v": (3.50, 3.61, 3.55, 3.54),
            },
        }
        for reason, changes in cases.items():
            with self.subTest(reason=reason):
                core = LiftedDriveCommission()
                with self.assertRaisesRegex(CommissioningRejected, reason):
                    core.command(
                        {"op": "enter", "session": TOKEN, "seq": 0,
                         "confirm": CONFIRMATION_PHRASE, "lifted": True},
                        0.0,
                        snapshot(stop_latched=True, **changes),
                    )
                self.assertEqual(core.state, LiftedState.IDLE)
                self.assertEqual(core.demand().motor_pwm, (0.0,) * 4)

    def test_enter_arm_and_pulse_require_stationary_dwell(self):
        with self.assertRaisesRegex(CommissioningRejected, "wheels_not_stationary"):
            self.core.command(
                {"op": "enter", "session": TOKEN, "seq": 1,
                 "confirm": CONFIRMATION_PHRASE, "lifted": True},
                0.0,
                snapshot(
                    stop_latched=True,
                    measured_speeds_mps=(0.021, 0.0, 0.0, 0.0),
                ),
            )

        self.setUp()
        with self.assertRaisesRegex(CommissioningRejected, "stationary_dwell"):
            self.core.command(
                {"op": "enter", "session": TOKEN, "seq": 1,
                 "confirm": CONFIRMATION_PHRASE, "lifted": True},
                0.0,
                snapshot(stop_latched=True, stationary_duration_s=0.499),
            )

        self.setUp()
        self.enter()
        with self.assertRaisesRegex(CommissioningRejected, "stationary_dwell"):
            self.request("arm", snapshot(stationary_duration_s=0.499))
        self.assertEqual(self.core.state, LiftedState.ABORTED)

        self.setUp()
        self.enter()
        self.arm()
        with self.assertRaisesRegex(CommissioningRejected, "stationary_dwell"):
            self.request(
                "pulse",
                snapshot(stationary_duration_s=0.499),
                mode="raw_pulse", wheel=1, pwm=20, duration_s=0.2,
            )
        self.assertEqual(self.core.state, LiftedState.ABORTED)

    def test_nonfinite_and_malformed_safety_fail_closed(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(bad=bad):
                core = LiftedDriveCommission()
                with self.assertRaisesRegex(CommissioningRejected, "invalid_safety_snapshot"):
                    core.command(
                        {"op": "enter", "session": TOKEN, "seq": 0,
                         "confirm": CONFIRMATION_PHRASE, "lifted": True},
                        0.0,
                        snapshot(stop_latched=True, measured_speeds_mps=(bad, 0.0, 0.0, 0.0)),
                    )
                self.assertEqual(core.demand().motor_pwm, (0.0,) * 4)

    def test_heartbeat_expiry_is_latched_zero(self):
        self.enter()
        self.now = 0.5
        demand = self.core.tick(self.now, snapshot(stop_latched=True))
        self.assertEqual(demand.state, LiftedState.ABORTED)
        self.assertEqual(demand.fault_reason, "heartbeat_expired")
        self.assert_zero()
        with self.assertRaisesRegex(CommissioningRejected, "requires_exit"):
            self.request("heartbeat", snapshot(stop_latched=True))
        self.assertEqual(self.core.state, LiftedState.ABORTED)

    def test_lease_and_rest_configuration_cannot_be_weakened(self):
        with self.assertRaises(ValueError):
            LiftedDriveCommission(heartbeat_lease_s=0.501)
        with self.assertRaises(ValueError):
            LiftedDriveCommission(rest_s=0.999)
        with self.assertRaises(ValueError):
            LiftedDriveCommission(pid_slew_pwm_per_s=80.01)

    def test_replayed_or_foreign_session_aborts_active_session(self):
        for message in (
            {"op": "heartbeat", "session": TOKEN, "seq": 0},
            {"op": "heartbeat", "session": "f" * 32, "seq": 1},
        ):
            with self.subTest(message=message):
                core = LiftedDriveCommission()
                core.command(
                    {"op": "enter", "session": TOKEN, "seq": 0,
                     "confirm": CONFIRMATION_PHRASE, "lifted": True},
                    0.0,
                    snapshot(stop_latched=True),
                )
                with self.assertRaises(CommissioningRejected):
                    core.command(message, 0.1, snapshot(stop_latched=True))
                self.assertEqual(core.state, LiftedState.ABORTED)
                self.assertEqual(core.demand().motor_pwm, (0.0,) * 4)

    def test_raw_pulse_moves_exactly_one_wheel_within_bounds(self):
        self.enter()
        self.arm()
        demand = self.raw_pulse(wheel=3, pwm=-50, duration_s=0.2)
        self.assertEqual(demand.state, LiftedState.PULSE)
        self.assertEqual(demand.mode, PulseMode.RAW_PULSE)
        self.assertEqual(demand.motor_pwm, (0.0, 0.0, -50.0, 0.0))
        self.assertEqual(demand.speed_targets_mps, (0.0,) * 4)

    def test_raw_pulse_rejects_invalid_wheel_pwm_duration_and_extra_fields(self):
        cases = (
            {"wheel": 0},
            {"wheel": 1.0},
            {"pwm": 0},
            {"pwm": 51},
            {"pwm": 20.5},
            {"duration_s": 0.199},
            {"duration_s": 0.501},
            {"kp": 1.0},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.setUp()
                self.enter()
                self.arm()
                with self.assertRaises(CommissioningRejected):
                    self.raw_pulse(**changes)
                self.assertEqual(self.core.state, LiftedState.ABORTED)
                self.assert_zero()

    def test_pulse_deadline_is_immediate_zero_then_full_rest(self):
        self.enter()
        self.arm()
        self.raw_pulse(duration_s=0.2)
        self.now = 0.19
        self.request("heartbeat")
        demand = self.core.tick(self.now, snapshot())
        self.assertEqual(demand.state, LiftedState.PULSE)
        self.assertNotEqual(demand.motor_pwm, (0.0,) * 4)
        self.now = 0.2
        demand = self.core.tick(self.now, snapshot())
        self.assertEqual(demand.state, LiftedState.REST)
        self.assert_zero()
        self.now = 0.6
        self.request("heartbeat")
        self.now = 1.0
        self.request("heartbeat")
        self.now = 1.19
        self.request("heartbeat")
        self.assertEqual(self.core.tick(self.now, snapshot()).state, LiftedState.REST)
        self.now = 1.2
        self.assertEqual(self.core.tick(self.now, snapshot()).state, LiftedState.ARMED)
        self.assert_zero()

    def test_heartbeat_callback_cannot_extend_expired_pulse(self):
        self.enter()
        self.arm()
        self.raw_pulse(duration_s=0.2)
        self.now = 0.2
        demand = self.request("heartbeat")
        self.assertEqual(demand.state, LiftedState.REST)
        self.assert_zero()

    def test_premature_second_pulse_aborts_instead_of_auto_repeat(self):
        self.enter()
        self.arm()
        self.raw_pulse(duration_s=0.2)
        self.now = 0.1
        self.request("end")
        self.assertEqual(self.core.state, LiftedState.REST)
        with self.assertRaisesRegex(CommissioningRejected, "pulse_requires_armed"):
            self.raw_pulse()
        self.assertEqual(self.core.state, LiftedState.ABORTED)
        self.assert_zero()

    def test_explicit_end_stops_without_slew(self):
        self.enter()
        self.arm()
        self.raw_pulse()
        self.assertNotEqual(self.core.demand().motor_pwm, (0.0,) * 4)
        demand = self.request("end")
        self.assertEqual(demand.state, LiftedState.REST)
        self.assertEqual(demand.motor_pwm, (0.0,) * 4)

    def test_actual_single_wheel_output_on_another_motor_aborts(self):
        self.enter()
        self.arm()
        self.raw_pulse(wheel=2)
        self.now = 0.1
        demand = self.core.tick(
            self.now,
            snapshot(applied_pwm=(10.0, 40.0, 0.0, 0.0)),
        )
        self.assertEqual(demand.state, LiftedState.ABORTED)
        self.assertEqual(demand.fault_reason, "applied_pwm_nonselected_wheel")
        self.assert_zero()

    def test_pid_single_requires_mapping_review(self):
        core = LiftedDriveCommission(mapping_reviewed=False)
        core.command(
            {"op": "enter", "session": TOKEN, "seq": 0,
             "confirm": CONFIRMATION_PHRASE, "lifted": True},
            0.0,
            snapshot(stop_latched=True),
        )
        core.command({"op": "arm", "session": TOKEN, "seq": 1}, 0.0, snapshot())
        with self.assertRaisesRegex(CommissioningRejected, "mapping_sign_cpr"):
            core.command(
                {"op": "pulse", "session": TOKEN, "seq": 2, "mode": "pid_single",
                 "wheel": 1, "target_mps": 0.05, "duration_s": 0.5},
                0.0,
                snapshot(),
            )
        self.assertEqual(core.state, LiftedState.ABORTED)
        self.assertEqual(core.demand().motor_pwm, (0.0,) * 4)

    def test_pid_single_bounds_target_duration_and_one_wheel(self):
        cases = (
            {"wheel": 5},
            {"target_mps": 0.0},
            {"target_mps": 0.1001},
            {"target_mps": float("nan")},
            {"duration_s": 0.0},
            {"duration_s": 0.799},
            {"duration_s": 1.001},
            {"ki": 1.0},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.setUp()
                self.enter()
                self.arm()
                with self.assertRaises(CommissioningRejected):
                    self.pid_single(**changes)
                self.assertEqual(self.core.state, LiftedState.ABORTED)
                self.assert_zero()

    def test_pid_single_targets_one_wheel_and_authorizes_bounded_slewed_output(self):
        self.enter()
        self.arm()
        demand = self.pid_single(wheel=2, target_mps=-0.1)
        self.assertEqual(demand.speed_targets_mps, (0.0, -0.1, 0.0, 0.0))
        self.now = 0.1
        demand = self.core.tick(self.now, snapshot(measured_speeds_mps=(0.0, -0.02, 0.0, 0.0)),
                                pid_outputs=(0.0, -8.0, 0.0, 0.0))
        self.assertEqual(demand.motor_pwm, (0.0, -8.0, 0.0, 0.0))

    def test_pid_missing_invalid_nonselected_limit_and_slew_fail_zero(self):
        cases = (
            (None, 0.1, "missing"),
            ((0.0, float("nan"), 0.0, 0.0), 0.1, "invalid"),
            ((1.0, 1.0, 0.0, 0.0), 0.1, "nonselected"),
            ((0.0, 60.1, 0.0, 0.0), 0.4, "limit"),
            ((0.0, 8.1, 0.0, 0.0), 0.1, "slew"),
        )
        for outputs, when, reason in cases:
            with self.subTest(reason=reason):
                self.setUp()
                self.enter()
                self.arm()
                self.pid_single()
                self.now = when
                demand = self.core.tick(self.now, snapshot(), pid_outputs=outputs)
                self.assertEqual(demand.state, LiftedState.ABORTED)
                self.assertIn(reason, demand.fault_reason)
                self.assert_zero()

    def test_pid_four_requires_all_single_wheel_reviews(self):
        core = LiftedDriveCommission(
            mapping_reviewed=True,
            single_wheel_reviewed=(True, True, True, False),
        )
        core.command(
            {"op": "enter", "session": TOKEN, "seq": 0,
             "confirm": CONFIRMATION_PHRASE, "lifted": True},
            0.0,
            snapshot(stop_latched=True),
        )
        core.command({"op": "arm", "session": TOKEN, "seq": 1}, 0.0, snapshot())
        with self.assertRaisesRegex(CommissioningRejected, "all_single_wheel"):
            core.command(
                {"op": "pulse", "session": TOKEN, "seq": 2, "mode": "pid_four",
                 "target_mps": 0.05, "duration_s": 0.5, "angular_z": 0.0},
                0.0,
                snapshot(),
            )
        self.assertEqual(core.state, LiftedState.ABORTED)

    def test_pid_four_is_straight_and_bounded(self):
        self.enter()
        self.arm()
        demand = self.pid_four(target_mps=-0.1)
        self.assertEqual(demand.speed_targets_mps, (-0.1,) * 4)
        self.now = 0.25
        outputs = (-20.0, 20.0, -20.0, 20.0)
        demand = self.core.tick(
            self.now,
            snapshot(measured_speeds_mps=(-0.03,) * 4),
            pid_outputs=outputs,
        )
        self.assertEqual(demand.motor_pwm, outputs)

    def test_pid_four_rejects_turn_and_out_of_bounds_output(self):
        self.enter()
        self.arm()
        with self.assertRaisesRegex(CommissioningRejected, "must_be_straight"):
            self.pid_four(angular_z=0.01)
        self.assertEqual(self.core.state, LiftedState.ABORTED)
        self.assert_zero()

        self.setUp()
        self.enter()
        self.arm()
        self.pid_four()
        self.now = 0.8
        demand = self.core.tick(self.now, snapshot(), pid_outputs=(60.0, 60.0, 60.0, 60.01))
        self.assertEqual(demand.state, LiftedState.ABORTED)
        self.assert_zero()

    def test_stop_sources_outrank_protocol_and_force_zero(self):
        cases = (
            ("remote_b_stop", "remote_b_stop"),
            ("emergency_stop", "emergency_stop"),
            ("voice_stop", "voice_stop"),
            ("shutdown", "service_shutdown"),
        )
        for field, reason in cases:
            with self.subTest(field=field):
                self.setUp()
                self.enter()
                self.arm()
                self.raw_pulse()
                bad = {"op": "heartbeat", "session": "bad", "seq": 0}
                with self.assertRaisesRegex(CommissioningRejected, reason):
                    self.core.command(bad, 0.1, snapshot(**{field: True}))
                self.assertEqual(self.core.state, LiftedState.ABORTED)
                self.assertEqual(self.core.fault_reason, reason)
                self.assert_zero()

    def test_emergency_stop_outranks_bad_time(self):
        self.enter()
        self.arm()
        self.raw_pulse()
        demand = self.core.tick(-1.0, snapshot(emergency_stop=True))
        self.assertEqual(demand.state, LiftedState.ABORTED)
        self.assertEqual(demand.fault_reason, "emergency_stop")
        self.assert_zero()

    def test_live_policy_command_owner_link_and_encoder_faults_abort(self):
        cases = {
            "software_stop_latched": {"stop_latched": True},
            "control_policy_stale": {"policy_age_s": 0.51},
            "nonzero_cmd_vel": {"cmd_vel": (0.0, 0.0, 0.1)},
            "drive_owner_not_stopped": {"drive_mode": "NAV2"},
            "motor_controller_link_lost": {"controller_link_ok": False},
            "encoder_invalid_M2": {"encoder_valid": (True, False, True, True)},
            "encoder_stale_M1": {"encoder_ages_s": (0.36, 0.0, 0.0, 0.0)},
        }
        for reason, changes in cases.items():
            with self.subTest(reason=reason):
                self.setUp()
                self.enter()
                self.arm()
                self.raw_pulse()
                self.now = 0.1
                demand = self.core.tick(self.now, snapshot(**changes))
                self.assertEqual(demand.state, LiftedState.ABORTED)
                self.assertEqual(demand.fault_reason, reason)
                self.assert_zero()

    def test_reversed_encoder_aborts_at_400_ms(self):
        self.enter()
        self.arm()
        self.pid_single(wheel=1, target_mps=0.08)
        reverse = snapshot(measured_speeds_mps=(-0.04, 0.0, 0.0, 0.0))
        self.now = 0.2
        self.request("heartbeat", reverse)
        demand = self.core.tick(self.now, reverse, pid_outputs=(8.0, 0.0, 0.0, 0.0))
        self.assertEqual(demand.state, LiftedState.PULSE)
        self.now = 0.399
        demand = self.core.tick(self.now, reverse, pid_outputs=(8.0, 0.0, 0.0, 0.0))
        self.assertEqual(demand.state, LiftedState.PULSE)
        self.now = 0.4
        demand = self.core.tick(self.now, reverse, pid_outputs=(8.0, 0.0, 0.0, 0.0))
        self.assertEqual(demand.state, LiftedState.ABORTED)
        self.assertEqual(demand.fault_reason, "encoder_reversed_M1")
        self.assert_zero()

    def test_frozen_encoder_aborts_at_800_ms(self):
        self.enter()
        self.arm()
        self.pid_single(wheel=1, target_mps=0.08)
        frozen = snapshot(measured_speeds_mps=(0.0, 0.0, 0.0, 0.0))
        self.now = 0.4
        self.request("heartbeat", frozen)
        demand = self.core.tick(self.now, frozen, pid_outputs=(8.0, 0.0, 0.0, 0.0))
        self.assertEqual(demand.state, LiftedState.PULSE)
        self.now = 0.79
        self.request("heartbeat", frozen)
        demand = self.core.tick(self.now, frozen, pid_outputs=(8.0, 0.0, 0.0, 0.0))
        self.assertEqual(demand.state, LiftedState.PULSE)
        self.now = 0.8
        demand = self.core.tick(self.now, frozen, pid_outputs=(8.0, 0.0, 0.0, 0.0))
        self.assertEqual(demand.state, LiftedState.ABORTED)
        self.assertEqual(demand.fault_reason, "encoder_frozen_M1")
        self.assert_zero()

    def test_monotonic_time_regression_aborts_and_zeros(self):
        self.enter()
        self.arm()
        self.raw_pulse()
        self.now = 0.2
        self.request("heartbeat")
        with self.assertRaisesRegex(CommissioningRejected, "regressed"):
            self.core.tick(0.1, snapshot())
        self.assertEqual(self.core.state, LiftedState.ABORTED)
        self.assert_zero()

    def test_abort_is_latched_until_explicit_safe_exit(self):
        self.enter()
        self.arm()
        self.raw_pulse()
        demand = self.core.abort("operator_stop")
        self.assertEqual(demand.state, LiftedState.ABORTED)
        self.assert_zero()
        with self.assertRaises(CommissioningRejected):
            self.request("arm")
        demand = self.request("exit", snapshot(stop_latched=True))
        self.assertEqual(demand.state, LiftedState.IDLE)
        self.assertFalse(demand.traction_locked)
        self.assert_zero()

    def test_protocol_abort_is_authenticated_sequenced_and_zero(self):
        self.enter()
        self.arm()
        self.raw_pulse()
        demand = self.request("abort", reason="operator_complete")
        self.assertEqual(demand.state, LiftedState.ABORTED)
        self.assertEqual(demand.fault_reason, "operator_complete")
        self.assertEqual(self.core.sequence, self.seq)
        self.assert_zero()

        core = LiftedDriveCommission()
        core.command(
            {"op": "enter", "session": TOKEN, "seq": 0,
             "confirm": CONFIRMATION_PHRASE, "lifted": True},
            0.0,
            snapshot(stop_latched=True),
        )
        with self.assertRaisesRegex(CommissioningRejected, "foreign_session"):
            core.command(
                {"op": "abort", "session": "f" * 32, "seq": 1,
                 "reason": "operator_complete"},
                0.0,
                snapshot(),
            )
        self.assertEqual(core.state, LiftedState.ABORTED)
        self.assertEqual(core.demand().motor_pwm, (0.0,) * 4)

    def test_exit_requires_fresh_relatched_stop_link_and_stationary_dwell(self):
        cases = (
            (snapshot(stop_latched=False), "fresh_latched_stop"),
            (snapshot(stop_latched=True, policy_age_s=0.501), "fresh_latched_stop"),
            (snapshot(stop_latched=True, controller_link_ok=False), "link_lost"),
            (snapshot(stop_latched=True, stationary_duration_s=0.499), "stationary_dwell"),
        )
        for release_snapshot, reason in cases:
            with self.subTest(reason=reason):
                self.setUp()
                self.enter()
                self.core.abort("operator_stop")
                with self.assertRaisesRegex(CommissioningRejected, reason):
                    self.request("exit", release_snapshot)
                self.assertEqual(self.core.state, LiftedState.ABORTED)
                self.assert_zero()

    def test_exit_refuses_pending_motion(self):
        self.enter()
        with self.assertRaisesRegex(CommissioningRejected, "nonzero_cmd_vel"):
            self.request(
                "exit",
                snapshot(stop_latched=True, cmd_vel=(0.1, 0.0, 0.0)),
            )
        self.assertEqual(self.core.state, LiftedState.ABORTED)
        self.assert_zero()

    def test_core_has_no_hardware_ros_or_serial_imports(self):
        source = (SCRIPTS / "atlas_drive_pid_lifted.py").read_text(encoding="utf-8")
        for forbidden in (
            "Rosmaster",
            "import serial",
            "from serial",
            "import rclpy",
            "from rclpy",
            "set_motor(",
            "create_publisher(",
            "create_subscription(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

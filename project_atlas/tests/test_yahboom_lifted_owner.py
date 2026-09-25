import ast
import hashlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from atlas_drive_pid_lifted import (  # noqa: E402
    CONFIRMATION_PHRASE,
    MAX_BMS_AGE_S,
    MAX_BMS_CELL_SPREAD_V,
    MAX_BMS_CELL_V,
    MAX_JETSON_TEMP_C,
    MAX_RAW_PWM,
    MAX_STATIONARY_SPEED_MPS,
    MIN_BMS_CELL_V,
    CommissioningRejected,
    LiftedDriveCommission,
    LiftedState,
    PulseMode,
    SafetySnapshot,
)


TOKEN = "0123456789abcdef0123456789abcdef"
OWNER_METHODS = {
    "_cal_policy",
    "_cal_joy",
    "_write_motor_outputs",
    "_force_motor_zero",
    "_read_jetson_temperature_c",
    "_on_lifted_bms",
    "_lifted_snapshot",
    "_lifted_owner_gate",
    "_start_lifted_pulse_observation",
    "_schedule_lifted_pulse_observation",
    "_finalize_lifted_pulse_observation",
    "_publish_lifted_status",
    "_abort_lifted",
    "_apply_lifted_demand",
    "_service_lifted_commission",
    "_on_lifted_request",
    "_on_cmd_vel",
    "_on_drive_mode",
}


class FakeClock:
    def __init__(self):
        self.now = 10.0

    def monotonic(self):
        return self.now

    def time(self):
        return self.now


class Message:
    def __init__(self, data=None):
        self.data = data


class Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message.data)


class Logger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(str(message))

    def warn(self, _message):
        pass


class Bot:
    def __init__(self):
        self.writes = []
        self.fail_next = False

    def set_motor(self, *values):
        if self.fail_next:
            self.fail_next = False
            raise OSError("injected motor write failure")
        self.writes.append(tuple(values))


class TemperaturePath:
    def __init__(self, millidegrees="55000"):
        self.millidegrees = millidegrees

    def read_text(self, **_kwargs):
        return self.millidegrees


def load_owner_class(clock, temperature_path):
    source = (SCRIPTS / "yahboom_base.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    original = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "YahboomBase"
    )
    methods = [
        node for node in original.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in OWNER_METHODS
    ]
    missing = OWNER_METHODS - {node.name for node in methods}
    if missing:
        raise AssertionError(f"owner methods missing from source: {sorted(missing)}")
    owner = ast.ClassDef(
        name="OwnerAdapter",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[owner], type_ignores=[]))
    namespace = {
        "hashlib": hashlib,
        "json": json,
        "math": math,
        "time": clock,
        "String": Message,
        "Twist": object,
        "MAX_PWM": 100,
        "MAX_BMS_AGE_S": MAX_BMS_AGE_S,
        "MAX_BMS_CELL_SPREAD_V": MAX_BMS_CELL_SPREAD_V,
        "MAX_BMS_CELL_V": MAX_BMS_CELL_V,
        "MAX_JETSON_TEMP_C": MAX_JETSON_TEMP_C,
        "MAX_RAW_PWM": MAX_RAW_PWM,
        "MIN_BMS_CELL_V": MIN_BMS_CELL_V,
        "CommissioningRejected": CommissioningRejected,
        "LiftedDriveCommission": LiftedDriveCommission,
        "LiftedState": LiftedState,
        "PulseMode": PulseMode,
        "SafetySnapshot": SafetySnapshot,
        "JETSON_TEMPERATURE_PATH": temperature_path,
    }
    exec(compile(module, str(SCRIPTS / "yahboom_base.py"), "exec"), namespace)
    return namespace["OwnerAdapter"]


def make_twist(linear_x=0.0, linear_y=0.0, angular_z=0.0):
    return SimpleNamespace(
        linear=SimpleNamespace(x=linear_x, y=linear_y, z=0.0),
        angular=SimpleNamespace(x=0.0, y=0.0, z=angular_z),
    )


class YahboomLiftedOwnerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.temperature_path = TemperaturePath()
        owner_class = load_owner_class(self.clock, self.temperature_path)
        self.node = owner_class()
        self.node.bot = Bot()
        self.node._logger = Logger()
        self.node.get_logger = lambda: self.node._logger
        self.node._cal_abort = lambda _reason: None
        self.node._pub_lifted_status = Publisher()
        self.node._drive_pid_config = SimpleNamespace(
            enabled=False,
            hardware_commissioned=False,
            navigation_validated=False,
            safety=SimpleNamespace(owner_timeout_s=0.75),
            wheels=tuple(
                SimpleNamespace(output_sign=value)
                for value in (-1.0, 1.0, -1.0, 1.0)
            ),
        )
        self.node._encoder_calibration = SimpleNamespace(
            motors=tuple(
                SimpleNamespace(encoder_sign=value)
                for value in (-1.0, 1.0, 1.0, 1.0)
            )
        )
        self.node._steering_cal = SimpleNamespace(locked=False)
        self.node._lifted_raw_enabled = True
        self.node._lifted_physical_cut_ready = True
        self.node._lifted_commission = LiftedDriveCommission(
            mapping_reviewed=False,
            single_wheel_reviewed=(False, False, False, False),
        )
        self.node._lifted_result = "IDLE"
        self.node._lifted_last_sequence_ack = -1
        self.node._lifted_remote_b_stop = False
        self.node._lifted_encoder_baseline = None
        self.node._lifted_pulse_wheel = None
        self.node._lifted_pulse_pwm = 0
        self.node._lifted_expected_sign = None
        self.node._lifted_pulse_observation = None
        self.node._lifted_observation_pending = False
        self.node._lifted_observation_zero_packet_stamp = 0.0
        self.node._lifted_bms_ok = True
        self.node._lifted_bms_at = self.clock.now
        self.node._lifted_bms_cells = (3.35, 3.35, 3.35, 3.35)
        self.node._lifted_last_temperature_c = None
        self.node._lifted_stationary_since = self.clock.now - 0.6
        self.node._cal_stop_latched = True
        self.node._cal_policy_time = self.clock.now
        self.node._drive_source = "STOPPED"
        self.node._drive_source_time = self.clock.now
        self.node._encoder_packet_stamp = self.clock.now
        self.node._encoder_packet_fresh = True
        self.node._encoder_fault_since = {}
        self.node._wheel_mps = [0.0, 0.0, 0.0, 0.0]
        self.node._applied_motor_outputs = (0, 0, 0, 0)
        self.node._applied_pwm = 0
        self.node._last_vx = self.node._last_vy = self.node._last_vz = 0.0
        self.node._last_cmd_time = self.clock.now
        self.node._last_enc = (100, 200, 300, 400)
        self.node._front_applied_angle = 90
        self.node._rear_applied_angle = 90
        self.node._front_target_angle = 90
        self.node._rear_target_angle = 90

    def send(self, op, seq, **fields):
        request = {"op": op, "session": TOKEN, "seq": seq}
        request.update(fields)
        self.node._on_lifted_request(Message(json.dumps(request)))

    def enter(self):
        self.send(
            "enter",
            1,
            confirm=CONFIRMATION_PHRASE,
            lifted=True,
        )
        self.assertEqual(self.node._lifted_commission.state, LiftedState.LOCKED)

    def arm(self):
        self.node._cal_policy(Message(json.dumps({"stop_latched": False})))
        status = json.loads(self.node._pub_lifted_status.messages[-1])
        self.assertTrue(status["arm_ready"])
        self.send("arm", 2)
        self.assertEqual(self.node._lifted_commission.state, LiftedState.ARMED)

    def pulse(self):
        self.send(
            "pulse", 3, mode="raw_pulse", wheel=2,
            pwm=40, duration_s=0.2,
        )
        self.assertEqual(self.node._lifted_commission.state, LiftedState.PULSE)
        self.assertEqual(self.node.bot.writes[-1], (0, 40, 0, 0))

    def refresh_live_inputs(self):
        self.node._drive_source_time = self.clock.now
        self.node._encoder_packet_stamp = self.clock.now
        self.node._cal_policy_time = self.clock.now
        self.node._lifted_bms_at = self.clock.now

    def test_nominal_raw_pulse_abort_relatch_and_safe_exit(self):
        self.enter()
        self.arm()
        self.pulse()

        self.clock.now += 0.21
        self.refresh_live_inputs()
        self.node._service_lifted_commission()
        self.assertEqual(self.node._lifted_commission.state, LiftedState.REST)
        self.assertEqual(self.node.bot.writes[-1], (0, 0, 0, 0))
        self.assertTrue(self.node._lifted_observation_pending)
        self.node._last_enc = (100, 210, 300, 400)
        self.node._encoder_packet_stamp += 0.01
        self.node._finalize_lifted_pulse_observation()
        self.assertEqual(self.node._lifted_pulse_observation, {
            "wheel": 2,
            "baseline_count": 200,
            "final_count": 210,
            "delta_count": 10,
            "expected_sign": 1,
            "observed_sign": 1,
            "result": "MATCH",
        })

        self.send("abort", 4, reason="operator_observed_channel")
        self.assertEqual(self.node._lifted_commission.state, LiftedState.ABORTED)
        self.assertEqual(self.node._lifted_commission.sequence, 4)
        self.assertEqual(self.node.bot.writes[-1], (0, 0, 0, 0))

        self.node._lifted_stationary_since = self.clock.now - 0.6
        self.node._cal_policy(Message(json.dumps({"stop_latched": True})))
        exit_status = json.loads(self.node._pub_lifted_status.messages[-1])
        self.assertTrue(exit_status["exit_ready"])
        self.assertEqual(exit_status["sequence_ack"], 4)
        self.assertEqual(
            exit_status["session_fingerprint"],
            hashlib.sha256(TOKEN.encode("ascii")).hexdigest(),
        )
        self.assertNotIn(TOKEN, self.node._pub_lifted_status.messages[-1])

        self.send("exit", 5)
        self.assertEqual(self.node._lifted_commission.state, LiftedState.IDLE)
        self.assertEqual(self.node.bot.writes[-1], (0, 0, 0, 0))
        final_status = json.loads(self.node._pub_lifted_status.messages[-1])
        self.assertTrue(final_status["final_zero"])
        self.assertFalse(final_status["session_active"])
        self.assertEqual(self.node._lifted_commission.sequence, -1)
        self.assertEqual(final_status["sequence"], 5)
        self.assertEqual(final_status["sequence_ack"], 5)

    def test_remote_b_press_aborts_and_release_is_published_live(self):
        self.enter()
        self.arm()
        self.pulse()
        self.node._cal_joy(SimpleNamespace(buttons=[0, 1]))
        self.assertEqual(self.node._lifted_commission.state, LiftedState.ABORTED)
        self.assertEqual(self.node.bot.writes[-1], (0, 0, 0, 0))
        pressed = json.loads(self.node._pub_lifted_status.messages[-1])
        self.assertIs(pressed["remote_b_stop"], True)

        self.node._cal_joy(SimpleNamespace(buttons=[0, 0]))
        released = json.loads(self.node._pub_lifted_status.messages[-1])
        self.assertIs(released["remote_b_stop"], False)

    def test_exit_keeps_abort_latch_when_pre_exit_zero_write_fails(self):
        self.enter()
        self.node._abort_lifted("operator_stop")
        self.node._lifted_stationary_since = self.clock.now - 0.6
        self.node._cal_policy(Message(json.dumps({"stop_latched": True})))
        self.node.bot.fail_next = True
        self.send("exit", 2)
        self.assertEqual(self.node._lifted_commission.state, LiftedState.ABORTED)
        self.assertTrue(self.node._lifted_commission.session is not None)
        self.assertIn("exit_zero_write_failed", self.node._lifted_result)

    def test_nonzero_cmd_vel_aborts_and_zeros_active_pulse(self):
        self.enter()
        self.arm()
        self.pulse()
        self.node._on_cmd_vel(make_twist(linear_x=0.1))
        self.assertEqual(self.node._lifted_commission.state, LiftedState.ABORTED)
        self.assertEqual(self.node.bot.writes[-1], (0, 0, 0, 0))

    def test_pid_request_is_rejected_by_owner_and_latches_zero(self):
        self.enter()
        self.arm()
        self.send(
            "pulse", 3, mode="pid_single", wheel=1,
            target_mps=0.05, duration_s=1.0,
        )
        self.assertEqual(self.node._lifted_commission.state, LiftedState.ABORTED)
        self.assertIn("pid_modes_not_authorized", self.node._lifted_result)
        self.assertEqual(self.node.bot.writes[-1], (0, 0, 0, 0))

    def test_hot_stale_unbalanced_or_unconfirmed_inputs_reject_entry(self):
        cases = (
            ("hot", lambda: setattr(self.temperature_path, "millidegrees", "88000"),
             "jetson_over_temperature"),
            ("stale_bms", lambda: setattr(
                self.node, "_lifted_bms_at", self.clock.now - MAX_BMS_AGE_S - 0.01
            ), "bms_telemetry_stale"),
            ("unbalanced_bms", lambda: setattr(
                self.node, "_lifted_bms_cells", (3.50, 3.61, 3.55, 3.54)
            ), "bms_cell_imbalance"),
            ("no_cutoff", lambda: setattr(
                self.node, "_lifted_physical_cut_ready", False
            ), "physical_power_cut_not_confirmed"),
        )
        for name, mutate, reason in cases:
            with self.subTest(name=name):
                self.setUp()
                mutate()
                self.send(
                    "enter", 1, confirm=CONFIRMATION_PHRASE, lifted=True
                )
                self.assertEqual(self.node._lifted_commission.state, LiftedState.IDLE)
                self.assertIn(reason, self.node._lifted_result)
                self.assertEqual(self.node.bot.writes[-1], (0, 0, 0, 0))

    def test_unhealthy_bms_update_aborts_pulse_immediately(self):
        self.enter()
        self.arm()
        self.pulse()
        self.node._on_lifted_bms(Message(json.dumps({"ok": False})))
        self.assertEqual(self.node._lifted_commission.state, LiftedState.ABORTED)
        self.assertEqual(self.node.bot.writes[-1], (0, 0, 0, 0))

    def test_source_has_one_motor_write_site_and_default_off_gates(self):
        source = (SCRIPTS / "yahboom_base.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("self.bot.set_motor("), 1)
        self.assertIn("ATLAS_PID_LIFTED_RAW_ENABLED', '0'", source)
        self.assertIn("ATLAS_PID_LIFTED_PHYSICAL_CUTOFF_READY', '0'", source)
        self.assertIn("'/atlas/drive_pid/lifted/request'", source)
        self.assertIn("'/atlas/drive_pid/lifted/status'", source)
        self.assertIn("pid_modes_authorized': False", source)
        self.assertIn("reliability=ReliabilityPolicy.RELIABLE", source)
        self.assertIn("durability=DurabilityPolicy.TRANSIENT_LOCAL", source)


if __name__ == "__main__":
    unittest.main()

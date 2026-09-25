#!/usr/bin/env python3
"""Unit tests for the topic-only lifted-wheel operator client."""

from __future__ import annotations

import contextlib
import hmac
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from atlas_drive_pid_lifted_client import (  # noqa: E402
    CONFIRMATION_PHRASE,
    EvidenceRecorder,
    LiftedPulseOperator,
    OperatorError,
    PulsePlan,
    RuntimeSessionStore,
    STATUS_QOS_DURABILITY,
    main,
    session_fingerprint,
)
from atlas_drive_pid_lifted import (  # noqa: E402
    CommissioningRejected,
    LiftedDriveCommission,
    LiftedState,
    SafetySnapshot,
)


TOKEN = "0123456789abcdef0123456789abcdef"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += max(0.0, float(seconds))


class FakeOwnerTransport:
    """Small deterministic owner model; it never represents real hardware."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        release_after_heartbeats: int = 2,
        relatch_after_polls: int = 2,
        fail_poll: bool = False,
    ) -> None:
        self.clock = clock
        self.release_after_heartbeats = release_after_heartbeats
        self.relatch_after_polls = relatch_after_polls
        self.fail_poll = fail_poll
        self.messages = []
        self.send_times = []
        self.statuses = []
        self.session = None
        self.heartbeat_count = 0
        self.state = "IDLE"
        self.stop_latched = True
        self.arm_ready = False
        self.exit_ready = False
        self.abort_polls = 0
        self.rest_at = None
        self.last_seq = -1
        self.pulse_observation = None
        self.closed = False
        self.statuses.append(self._status())

    def _status(self):
        payload = {
            "state": self.state,
            "sequence": self.last_seq,
            "sequence_ack": self.last_seq,
            "stop_latched": self.stop_latched,
            "arm_ready": self.arm_ready,
            "fault_reason": "",
            "remote_b_stop": False,
            "exit_ready": self.exit_ready,
        }
        if self.state != "IDLE":
            payload["session_fingerprint"] = session_fingerprint(self.session)
        if self.pulse_observation is not None:
            payload["pulse_observation"] = dict(self.pulse_observation)
        return payload

    def publish(self, message):
        data = dict(message)
        self.messages.append(data)
        self.send_times.append(self.clock())
        self.last_seq = int(data["seq"])
        op = data["op"]
        if op == "enter":
            self.session = data["session"]
            self.state = "LOCKED"
            self.stop_latched = True
            self.arm_ready = False
            self.exit_ready = False
            self.statuses.append(self._status())
        elif op == "heartbeat":
            self.heartbeat_count += 1
            if self.state == "LOCKED" and self.heartbeat_count >= self.release_after_heartbeats:
                self.stop_latched = False
                self.arm_ready = True
            self.statuses.append(self._status())
        elif op == "arm":
            self.state = "ARMED"
            self.statuses.append(self._status())
        elif op == "pulse":
            self.state = "PULSE"
            self.pulse_observation = {
                "wheel": int(data["wheel"]),
                "baseline_count": 100,
                "final_count": None,
                "delta_count": None,
                "expected_sign": 1,
                "observed_sign": None,
                "result": "UNAVAILABLE",
            }
            self.rest_at = self.clock() + float(data["duration_s"])
            self.statuses.append(self._status())
        elif op == "end":
            self.state = "REST"
            if self.pulse_observation is not None:
                self.pulse_observation.update({
                    "final_count": 120,
                    "delta_count": 20,
                    "observed_sign": 1,
                    "result": "MATCH",
                })
            self.statuses.append(self._status())
        elif op == "abort":
            self.state = "ABORTED"
            self.stop_latched = False
            self.exit_ready = False
            self.abort_polls = 0
            self.statuses.append(self._status())
        elif op == "exit":
            self.state = "IDLE"
            self.stop_latched = True
            self.arm_ready = False
            self.statuses.append(self._status())

    def poll(self, timeout_s):
        if self.fail_poll:
            raise KeyboardInterrupt("fake interrupt")
        self.clock.advance(timeout_s)
        if self.state == "ABORTED" and not self.exit_ready:
            self.abort_polls += 1
            if self.abort_polls >= self.relatch_after_polls:
                self.stop_latched = True
                self.exit_ready = True
                self.statuses.append(self._status())
        if self.rest_at is not None and self.clock() >= self.rest_at and self.state == "PULSE":
            self.state = "REST"
            if self.pulse_observation is not None:
                self.pulse_observation.update({
                    "final_count": 120,
                    "delta_count": 20,
                    "observed_sign": 1,
                    "result": "MATCH",
                })
            self.statuses.append(self._status())
            self.rest_at = None
        return self.statuses.pop(0) if self.statuses else None

    def close(self):
        self.closed = True


class CoreOwnerTransport:
    """Topic-adapter model backed by the real commissioning safety core."""

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.core = LiftedDriveCommission()
        self.messages = []
        self.statuses = []
        self.last_ack = -1
        self.stop_latched = True
        self.applied_pwm = (0.0, 0.0, 0.0, 0.0)
        self.heartbeat_count = 0
        self.abort_polls = 0
        self.observation = None
        self.closed = False
        self._last_state = self.core.state
        self.statuses.append(self._status())

    def _safety(self):
        return SafetySnapshot(
            stop_latched=self.stop_latched,
            policy_age_s=0.0,
            drive_mode="STOPPED",
            cmd_vel=(0.0, 0.0, 0.0),
            applied_pwm=tuple(self.applied_pwm),
            controller_link_ok=True,
            encoder_valid=(True, True, True, True),
            encoder_ages_s=(0.0, 0.0, 0.0, 0.0),
            measured_speeds_mps=(0.0, 0.0, 0.0, 0.0),
            jetson_temp_c=60.0,
            bms_ok=True,
            bms_age_s=0.0,
            bms_cell_voltages_v=(3.50, 3.50, 3.50, 3.50),
            stationary_duration_s=2.0,
            physical_power_cut_ready=True,
        )

    def _exit_ready(self):
        return (
            self.core.state == LiftedState.ABORTED
            and self.stop_latched
            and self.applied_pwm == (0.0, 0.0, 0.0, 0.0)
        )

    def _status(self):
        status = dict(self.core.status())
        status.update({
            "sequence_ack": self.last_ack,
            "stop_latched": self.stop_latched,
            "remote_b_stop": False,
            "arm_ready": self.core.state == LiftedState.LOCKED and not self.stop_latched,
            "exit_ready": self._exit_ready(),
        })
        if self.core.session is not None:
            status["session_fingerprint"] = session_fingerprint(self.core.session)
        if self.observation is not None:
            status["pulse_observation"] = dict(self.observation)
        return status

    def publish(self, message):
        request = dict(message)
        self.messages.append(request)
        op = request["op"]
        if op == "heartbeat":
            self.heartbeat_count += 1
            if self.core.state == LiftedState.LOCKED and self.heartbeat_count >= 2:
                self.stop_latched = False
        if op == "abort":
            token = request.get("session")
            sequence = request.get("seq")
            if (
                self.core.session is None
                or not isinstance(token, str)
                or not hmac.compare_digest(token, self.core.session)
                or type(sequence) is not int
                or sequence <= self.core.sequence
            ):
                self.core.abort("invalid_abort_identity")
                raise CommissioningRejected("invalid_abort_identity")
            self.core.sequence = sequence
            self.last_ack = sequence
            demand = self.core.abort(str(request.get("reason") or "operator_abort"))
        else:
            demand = self.core.command(request, self.clock(), self._safety())
            self.last_ack = int(request["seq"])
        self.applied_pwm = tuple(demand.motor_pwm)
        if op == "pulse":
            wheel = int(request["wheel"])
            self.observation = {
                "wheel": wheel,
                "baseline_count": 1000,
                "final_count": None,
                "delta_count": None,
                "expected_sign": 1,
                "observed_sign": None,
                "result": "UNAVAILABLE",
            }
        self.statuses.append(self._status())

    def poll(self, timeout_s):
        self.clock.advance(timeout_s)
        if self.core.state not in (LiftedState.IDLE, LiftedState.ABORTED):
            previous = self.core.state
            demand = self.core.tick(self.clock(), self._safety())
            self.applied_pwm = tuple(demand.motor_pwm)
            if previous == LiftedState.PULSE and self.core.state == LiftedState.REST:
                self.observation.update({
                    "final_count": 1021,
                    "delta_count": 21,
                    "observed_sign": 1,
                    "result": "MATCH",
                })
                self.statuses.append(self._status())
        if self.core.state == LiftedState.ABORTED and not self.stop_latched:
            self.abort_polls += 1
            if self.abort_polls >= 2:
                self.stop_latched = True
                self.statuses.append(self._status())
        return self.statuses.pop(0) if self.statuses else None

    def close(self):
        self.closed = True


class RecorderFixture:
    def __init__(self, clock: FakeClock):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "evidence.jsonl"
        self.recorder = EvidenceRecorder(self.path, clock=clock)

    def close(self):
        self.recorder.close()
        self.directory.cleanup()


class LiftedClientTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.fixture = RecorderFixture(self.clock)

    def tearDown(self):
        self.fixture.close()

    def make_operator(self, transport=None, **plan_changes):
        values = {
            "wheel": 2,
            "pwm": 30,
            "duration_s": 0.25,
            "heartbeat_s": 0.20,
            "status_timeout_s": 1.0,
            "operator_timeout_s": 2.0,
        }
        values.update(plan_changes)
        transport = transport or FakeOwnerTransport(self.clock)
        return LiftedPulseOperator(
            transport,
            self.fixture.recorder,
            PulsePlan(**values),
            session=TOKEN,
            clock=self.clock,
        ), transport

    def test_plan_rejects_unsafe_bounds(self):
        invalid = (
            {"wheel": 0},
            {"pwm": 0},
            {"pwm": 51},
            {"duration_s": 0.19},
            {"duration_s": 0.51},
            {"heartbeat_s": 0.251},
            {"heartbeat_s": 0.049},
            {"status_timeout_s": float("nan")},
            {"operator_timeout_s": float("inf")},
        )
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises(OperatorError):
                    self.make_operator(**changes)

    def test_plan_validates_without_ros_or_hardware(self):
        plan = PulsePlan(wheel=4, pwm=-50, duration_s=0.5, heartbeat_s=0.25)
        plan.validate()

    def test_volatile_status_reader_is_compatible_with_durable_owner(self):
        self.assertEqual(STATUS_QOS_DURABILITY, "volatile")

    def test_exact_confirmation_required_before_any_publish(self):
        operator, transport = self.make_operator()
        with self.assertRaisesRegex(OperatorError, "exact confirmation"):
            operator.execute("almost correct")
        self.assertEqual(transport.messages, [])

    def test_one_pulse_sequence_waits_for_operator_release(self):
        operator, transport = self.make_operator()
        final = operator.execute(CONFIRMATION_PHRASE)
        ops = [message["op"] for message in transport.messages]
        self.assertEqual(ops.count("pulse"), 1)
        self.assertEqual(transport.messages[ops.index("pulse")]["mode"], "raw_pulse")
        self.assertEqual(final["state"], "IDLE")
        self.assertTrue(operator.closed)

        arm_index = ops.index("arm")
        self.assertGreaterEqual(transport.heartbeat_count, 2)
        self.assertGreater(arm_index, ops.index("enter"))
        sequences = [message["seq"] for message in transport.messages]
        self.assertEqual(sequences, sorted(sequences))
        self.assertEqual(len(sequences), len(set(sequences)))

    def test_heartbeats_remain_at_or_below_quarter_second(self):
        operator, transport = self.make_operator(
            FakeOwnerTransport(self.clock, release_after_heartbeats=5)
        )
        operator.execute(CONFIRMATION_PHRASE)
        heartbeat_times = [
            sent_at
            for message, sent_at in zip(transport.messages, transport.send_times)
            if message["op"] == "heartbeat"
        ]
        self.assertGreaterEqual(len(heartbeat_times), 5)
        intervals = [right - left for left, right in zip(heartbeat_times, heartbeat_times[1:])]
        self.assertTrue(all(interval <= 0.25 + 1e-9 for interval in intervals), intervals)

    def test_foreign_status_cannot_acknowledge_arm(self):
        operator, transport = self.make_operator()
        transport.statuses.append({
            "state": "ARMED",
            "session_fingerprint": session_fingerprint("f" * 32),
            "sequence_ack": 999,
            "stop_latched": False,
            "arm_ready": True,
        })
        final = operator.execute(CONFIRMATION_PHRASE)
        self.assertEqual(final["state"], "IDLE")

    def test_second_execute_never_sends_a_second_pulse(self):
        operator, transport = self.make_operator()
        operator.execute(CONFIRMATION_PHRASE)
        with self.assertRaises(OperatorError):
            operator.execute(CONFIRMATION_PHRASE)
        self.assertEqual([m["op"] for m in transport.messages].count("pulse"), 1)

    def test_interrupt_cleanup_attempts_end_abort_and_exit(self):
        operator, transport = self.make_operator()
        operator.entered = True
        transport.fail_poll = True
        with self.assertRaises(KeyboardInterrupt):
            transport.poll(0.01)
        operator.fail_safe_cleanup("KeyboardInterrupt: fake interrupt")
        self.assertEqual([m["op"] for m in transport.messages][-3:], ["end", "abort", "exit"])

    def test_evidence_contains_requests_status_and_completion(self):
        operator, _ = self.make_operator()
        operator.execute(CONFIRMATION_PHRASE)
        self.fixture.recorder.close()
        rows = [json.loads(line) for line in self.fixture.path.read_text().splitlines()]
        events = [row["event"] for row in rows]
        self.assertIn("request", events)
        self.assertIn("status", events)
        self.assertIn("complete", events)
        complete = next(row for row in rows if row["event"] == "complete")
        self.assertEqual(complete["pulse_count"], 1)
        observation = next(row for row in rows if row["event"] == "pulse_observation")
        self.assertEqual(observation["observation"]["result"], "MATCH")
        self.assertFalse(observation["physical_pass_claimed"])
        self.assertNotIn(TOKEN, self.fixture.path.read_text(encoding="utf-8"))

    def test_runtime_store_crash_restart_and_authenticated_release(self):
        store_path = Path(self.fixture.directory.name) / "active.session"
        store = RuntimeSessionStore(store_path)
        store.save(TOKEN, 0)
        transport = FakeOwnerTransport(self.clock, release_after_heartbeats=1)
        first = LiftedPulseOperator(
            transport,
            self.fixture.recorder,
            PulsePlan(
                wheel=3,
                pwm=20,
                duration_s=0.2,
                heartbeat_s=0.2,
                status_timeout_s=1.0,
                operator_timeout_s=2.0,
            ),
            session=TOKEN,
            session_store=store,
            clock=self.clock,
        )
        # Model a process death after the owner locked the session.  There is
        # deliberately no cleanup call here.
        initial = transport.poll(0.0)
        first._accept_status(initial)
        first._send("enter", confirm=CONFIRMATION_PHRASE, lifted=True)
        locked = transport.poll(0.0)
        first._accept_status(locked)
        persisted = store.load()
        self.assertGreaterEqual(persisted["next_seq"], 1)
        self.assertEqual(persisted["session"], TOKEN)

        # Owner lease expiry is a fail-zero ABORTED latch.  A fresh process can
        # only release it using the same token from the private runtime file.
        transport.statuses.clear()
        transport.state = "ABORTED"
        transport.stop_latched = False
        transport.exit_ready = False
        transport.abort_polls = 0
        transport.statuses.append(transport._status())
        recovered = store.load()
        second = LiftedPulseOperator(
            transport,
            self.fixture.recorder,
            first.plan,
            session=recovered["session"],
            session_store=store,
            next_sequence=recovered["next_seq"],
            clock=self.clock,
        )
        final = second.resume_release()
        self.assertEqual(final["state"], "IDLE")
        self.assertFalse(store_path.exists())
        self.assertEqual([m["op"] for m in transport.messages].count("pulse"), 0)
        self.assertEqual(transport.messages[-1]["op"], "exit")

    def test_real_safety_core_and_client_contract_complete_without_pid_enable(self):
        transport = CoreOwnerTransport(self.clock)
        operator = LiftedPulseOperator(
            transport,
            self.fixture.recorder,
            PulsePlan(
                wheel=1,
                pwm=20,
                duration_s=0.2,
                heartbeat_s=0.2,
                status_timeout_s=1.0,
                operator_timeout_s=2.0,
            ),
            session=TOKEN,
            clock=self.clock,
        )
        final = operator.execute(CONFIRMATION_PHRASE)
        self.assertEqual(final["state"], "IDLE")
        self.assertEqual([m["op"] for m in transport.messages].count("pulse"), 1)
        self.assertEqual(transport.observation["result"], "MATCH")
        self.assertFalse(transport.core.mapping_reviewed)
        self.assertEqual(transport.core.single_wheel_reviewed, (False, False, False, False))

    def test_source_has_no_direct_motor_or_serial_access(self):
        source = (SCRIPTS / "atlas_drive_pid_lifted_client.py").read_text(encoding="utf-8")
        for forbidden in (
            "Rosmaster",
            "import serial",
            "from serial",
            "set_motor(",
            "set_motor_speed(",
            "/dev/tty",
            "/dev/serial",
        ):
            self.assertNotIn(forbidden, source)


class LiftedClientCliTests(unittest.TestCase):
    def test_default_cli_is_dry_run_and_records_zero_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "dry.jsonl"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main([
                    "--wheel", "1",
                    "--pwm", "20",
                    "--duration", "0.2",
                    "--evidence", str(evidence),
                ])
            self.assertEqual(result, 0)
            self.assertIn("DRY RUN ONLY", stdout.getvalue())
            rows = [json.loads(line) for line in evidence.read_text().splitlines()]
            self.assertEqual(rows[-1]["event"], "dry_run_complete")
            self.assertEqual(rows[-1]["messages_published"], 0)


if __name__ == "__main__":
    unittest.main()

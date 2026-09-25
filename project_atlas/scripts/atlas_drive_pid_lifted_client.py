#!/usr/bin/env python3
"""Operator client for ATLAS lifted-wheel drive commissioning.

This program is deliberately *not* a motor driver.  It only exchanges JSON in
``std_msgs/msg/String`` messages with the sole hardware owner on:

* ``/atlas/drive_pid/lifted/request``
* ``/atlas/drive_pid/lifted/status``

The default is a dry run.  An executing invocation can request exactly one
bounded, raw, one-wheel pulse.  The owner remains responsible for every safety
interlock and for writing zero to the controller on any fault.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import sys
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional, Protocol


REQUEST_TOPIC = "/atlas/drive_pid/lifted/request"
STATUS_TOPIC = "/atlas/drive_pid/lifted/status"
STATUS_QOS_DURABILITY = "volatile"
CONFIRMATION_PHRASE = "LIFTED CLEAR PHYSICAL POWER CUT READY"
SESSION_PATTERN = re.compile(r"^[0-9a-f]{32}$")

DEFAULT_HEARTBEAT_S = 0.20
MAX_HEARTBEAT_S = 0.25
MIN_HEARTBEAT_S = 0.05
MIN_RAW_DURATION_S = 0.20
MAX_RAW_DURATION_S = 0.50
MAX_RAW_PWM = 50


class OperatorError(RuntimeError):
    """The owner rejected, timed out, or reported an unsafe operation."""


class OperatorInterrupted(KeyboardInterrupt):
    """Raised by SIGINT/SIGTERM so fail-safe cleanup follows one path."""


class Transport(Protocol):
    """Minimal transport used by the operator core and its unit tests."""

    def publish(self, message: Mapping[str, Any]) -> None:
        ...

    def poll(self, timeout_s: float) -> Optional[Mapping[str, Any]]:
        ...

    def close(self) -> None:
        ...


class EvidenceRecorder:
    """Append-only JSONL evidence with a flush after every record."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.monotonic):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._stream = self.path.open("a", encoding="utf-8", newline="\n")

    def record(self, event: str, **values: Any) -> None:
        row = {
            "event": str(event),
            "monotonic_s": round(float(self._clock()), 6),
            "time_utc": datetime.now(timezone.utc).isoformat(),
        }
        row.update(values)
        self._stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        self._stream.flush()

    def close(self) -> None:
        if not self._stream.closed:
            self._stream.close()


def session_fingerprint(token: str) -> str:
    """Return the correlation value published by the owner, never the token."""

    return hashlib.sha256(token.encode("ascii")).hexdigest()


def redacted_request(message: Mapping[str, Any]) -> Dict[str, Any]:
    """Copy a request for evidence without retaining its bearer token."""

    safe = dict(message)
    token = safe.pop("session", None)
    if isinstance(token, str) and SESSION_PATTERN.fullmatch(token):
        safe["session_fingerprint"] = session_fingerprint(token)
    return safe


class RuntimeSessionStore:
    """Ephemeral 0600 crash-recovery state outside the source/evidence tree."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def save(self, token: str, next_seq: int) -> None:
        if not SESSION_PATTERN.fullmatch(token):
            raise OperatorError("refusing to store an invalid session token")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(
            {
                "version": 1,
                "session": token,
                "session_fingerprint": session_fingerprint(token),
                "next_seq": int(next_seq),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def load(self) -> Dict[str, Any]:
        try:
            metadata = self.path.stat()
            if os.name != "nt" and stat.S_IMODE(metadata.st_mode) & 0o077:
                raise OperatorError("runtime session file permissions are not 0600")
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise OperatorError(f"cannot load runtime commissioning session: {exc}") from exc
        token = values.get("session")
        fingerprint = values.get("session_fingerprint")
        next_seq = values.get("next_seq")
        if not isinstance(token, str) or not SESSION_PATTERN.fullmatch(token):
            raise OperatorError("runtime session contains an invalid token")
        if fingerprint != session_fingerprint(token):
            raise OperatorError("runtime session fingerprint does not match its token")
        if type(next_seq) is not int or next_seq < 0:
            raise OperatorError("runtime session contains an invalid sequence")
        return {
            "session": token,
            "session_fingerprint": fingerprint,
            "next_seq": next_seq,
        }

    def remove(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class PulsePlan:
    wheel: int
    pwm: int
    duration_s: float
    heartbeat_s: float = DEFAULT_HEARTBEAT_S
    status_timeout_s: float = 5.0
    operator_timeout_s: float = 120.0

    def validate(self) -> None:
        if type(self.wheel) is not int or self.wheel not in (1, 2, 3, 4):
            raise OperatorError("wheel must be one of 1, 2, 3, or 4")
        if type(self.pwm) is not int or self.pwm == 0 or abs(self.pwm) > MAX_RAW_PWM:
            raise OperatorError("raw PWM must be a non-zero integer from -50 to 50")
        if (
            not math.isfinite(float(self.duration_s))
            or not MIN_RAW_DURATION_S <= float(self.duration_s) <= MAX_RAW_DURATION_S
        ):
            raise OperatorError("raw duration must be from 0.20 to 0.50 seconds")
        if (
            not math.isfinite(float(self.heartbeat_s))
            or not MIN_HEARTBEAT_S <= float(self.heartbeat_s) <= MAX_HEARTBEAT_S
        ):
            raise OperatorError("heartbeat period must be from 0.05 to 0.25 seconds")
        if not math.isfinite(float(self.status_timeout_s)) or float(self.status_timeout_s) <= 0.0:
            raise OperatorError("status timeout must be positive")
        if not math.isfinite(float(self.operator_timeout_s)) or float(self.operator_timeout_s) <= 0.0:
            raise OperatorError("operator timeout must be positive")


class LiftedPulseOperator:
    """Sequenced fail-closed client for one raw pulse.

    Status messages must identify the active session and acknowledge the latest
    command sequence.  Before ``arm`` the owner must explicitly publish both
    ``stop_latched: false`` and ``arm_ready: true``.  This client cannot and
    does not unlatch the stop itself.
    """

    def __init__(
        self,
        transport: Transport,
        evidence: EvidenceRecorder,
        plan: PulsePlan,
        *,
        session: Optional[str] = None,
        session_store: Optional[RuntimeSessionStore] = None,
        next_sequence: int = 0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        plan.validate()
        token = session or secrets.token_hex(16)
        if not SESSION_PATTERN.fullmatch(token):
            raise OperatorError("session must be exactly 32 lower-case hexadecimal characters")
        self.transport = transport
        self.evidence = evidence
        self.plan = plan
        self.session = token
        self.fingerprint = session_fingerprint(token)
        self.session_store = session_store
        self.clock = clock
        if type(next_sequence) is not int or next_sequence < 0:
            raise OperatorError("next sequence must be a non-negative integer")
        self.sequence = int(next_sequence) - 1
        self.latest_status: Dict[str, Any] = {}
        self.next_heartbeat_at = float("inf")
        self.entered = False
        self.pulse_sent = False
        self.closed = False
        self.allow_aborted_status = False

    def _next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence

    def _send(self, op: str, **values: Any) -> Dict[str, Any]:
        message: Dict[str, Any] = {
            "op": str(op),
            "session": self.session,
            "seq": self._next_sequence(),
        }
        message.update(values)
        # Reserve the sequence before publishing.  A crash can therefore skip
        # a number, but can never reuse an already-published command number.
        if self.session_store is not None:
            self.session_store.save(self.session, self.sequence + 1)
        self.transport.publish(message)
        self.evidence.record("request", request=redacted_request(message))
        if op == "enter":
            self.entered = True
            self.next_heartbeat_at = self.clock() + self.plan.heartbeat_s
        elif op == "heartbeat" and self.entered:
            self.next_heartbeat_at = self.clock() + self.plan.heartbeat_s
        return message

    def _heartbeat_if_due(self) -> None:
        if not self.entered or self.closed:
            return
        if self.clock() >= self.next_heartbeat_at:
            self._send("heartbeat")

    def _status_belongs_to_session(self, status: Mapping[str, Any]) -> bool:
        # IDLE is the safe, released terminal state and intentionally has no
        # active session.  Every locked state must echo the random token.
        if str(status.get("state", "")).upper() == "IDLE":
            return True
        return status.get("session_fingerprint") == self.fingerprint

    def _accept_status(self, status: Mapping[str, Any]) -> None:
        if not isinstance(status, Mapping):
            self.evidence.record("invalid_status", reason="not_mapping")
            return
        payload = dict(status)
        self.evidence.record("status", status=payload)
        if not self._status_belongs_to_session(payload):
            self.evidence.record("ignored_status", reason="session_mismatch", status=payload)
            return
        self.latest_status = payload
        state = str(payload.get("state", "")).upper()
        if state == "ABORTED" and not self.allow_aborted_status:
            reason = str(payload.get("fault_reason") or "owner_aborted")
            raise OperatorError(f"owner aborted: {reason}")

    def _acknowledges(self, request: Mapping[str, Any]) -> bool:
        try:
            acknowledged = self.latest_status.get(
                "sequence_ack", self.latest_status.get("sequence", -1)
            )
            return int(acknowledged) >= int(request["seq"])
        except (TypeError, ValueError):
            return False

    def _record_pulse_observation(self, status: Mapping[str, Any]) -> Mapping[str, Any]:
        observation = status.get("pulse_observation")
        required = {
            "wheel",
            "baseline_count",
            "final_count",
            "delta_count",
            "expected_sign",
            "observed_sign",
            "result",
        }
        if not isinstance(observation, Mapping) or not required.issubset(observation):
            raise OperatorError("owner did not publish a complete pulse_observation")
        copied = dict(observation)
        if copied.get("wheel") != self.plan.wheel:
            raise OperatorError("owner pulse_observation names the wrong wheel")
        if copied.get("result") not in {"MATCH", "REVERSED", "NO_DELTA", "UNAVAILABLE"}:
            raise OperatorError("owner pulse_observation has an unknown result")
        self.evidence.record(
            "pulse_observation",
            observation=copied,
            physical_pass_claimed=False,
            calibration_changed=False,
        )
        return copied

    def _pulse_complete_with_observation(self, status: Mapping[str, Any]) -> bool:
        state_ready = str(status.get("state", "")).upper() in {"REST", "ARMED"}
        observation = status.get("pulse_observation")
        return (
            state_ready
            and isinstance(observation, Mapping)
            and observation.get("wheel") == self.plan.wheel
            and observation.get("result") in {
                "MATCH", "REVERSED", "NO_DELTA", "UNAVAILABLE"
            }
            and all(
                key in observation
                for key in (
                    "baseline_count", "final_count", "delta_count",
                    "expected_sign", "observed_sign",
                )
            )
        )

    def _wait_for(
        self,
        predicate: Callable[[Mapping[str, Any]], bool],
        timeout_s: float,
        description: str,
        *,
        request: Optional[Mapping[str, Any]] = None,
        heartbeat: bool = True,
    ) -> Mapping[str, Any]:
        deadline = self.clock() + float(timeout_s)
        while self.clock() < deadline:
            if heartbeat:
                self._heartbeat_if_due()
            remaining = max(0.0, deadline - self.clock())
            until_heartbeat = (
                max(0.0, self.next_heartbeat_at - self.clock())
                if heartbeat and self.entered
                else remaining
            )
            wait_s = min(0.05, remaining, until_heartbeat)
            status = self.transport.poll(max(0.0, wait_s))
            if status is not None:
                self._accept_status(status)
            if (
                predicate(self.latest_status)
                and (request is None or self._acknowledges(request))
            ):
                return dict(self.latest_status)
        raise OperatorError(f"timed out waiting for {description}")

    @staticmethod
    def _state_is(expected: str) -> Callable[[Mapping[str, Any]], bool]:
        wanted = expected.upper()
        return lambda status: str(status.get("state", "")).upper() == wanted

    @staticmethod
    def _operator_ready(status: Mapping[str, Any]) -> bool:
        return (
            str(status.get("state", "")).upper() == "LOCKED"
            and status.get("stop_latched") is False
            and status.get("arm_ready") is True
        )

    @staticmethod
    def _release_ready(status: Mapping[str, Any]) -> bool:
        return (
            str(status.get("state", "")).upper() == "ABORTED"
            and status.get("stop_latched") is True
            and status.get("remote_b_stop") is False
            and status.get("exit_ready") is True
        )

    def _resume_status_matches(self, status: Mapping[str, Any]) -> bool:
        if status.get("session_fingerprint") == self.fingerprint:
            return True
        if str(status.get("state", "")).upper() != "IDLE":
            return False
        try:
            acknowledged = int(
                status.get("sequence_ack", status.get("sequence", -1))
            )
        except (TypeError, ValueError):
            return False
        return acknowledged >= self.sequence

    def execute(self, confirmation: str) -> Mapping[str, Any]:
        if self.pulse_sent:
            raise OperatorError("this invocation already used its one permitted pulse")
        if confirmation != CONFIRMATION_PHRASE:
            raise OperatorError(
                f'exact confirmation required: "{CONFIRMATION_PHRASE}"'
            )

        self._wait_for(
            self._state_is("IDLE"),
            self.plan.status_timeout_s,
            "an online, released owner",
            heartbeat=False,
        )

        enter = self._send(
            "enter",
            confirm=CONFIRMATION_PHRASE,
            lifted=True,
        )
        self._wait_for(
            self._state_is("LOCKED"),
            self.plan.status_timeout_s,
            "owner LOCKED acknowledgement",
            request=enter,
        )

        print(
            "Owner is LOCKED. Explicitly unlatch the operator software stop; "
            "the client will wait for stop_latched=false and arm_ready=true.",
            flush=True,
        )
        self._wait_for(
            self._operator_ready,
            self.plan.operator_timeout_s,
            "explicit operator stop release and ARM readiness",
        )

        arm = self._send("arm")
        self._wait_for(
            self._state_is("ARMED"),
            self.plan.status_timeout_s,
            "owner ARMED acknowledgement",
            request=arm,
        )

        pulse = self._send(
            "pulse",
            mode="raw_pulse",
            wheel=self.plan.wheel,
            pwm=self.plan.pwm,
            duration_s=float(self.plan.duration_s),
        )
        self.pulse_sent = True
        self._wait_for(
            self._state_is("PULSE"),
            self.plan.status_timeout_s,
            "owner PULSE acknowledgement",
            request=pulse,
        )

        # The owner bounds pulse duration.  Continue the lease and observe it
        # entering REST; never send a second pulse automatically.
        final = self._wait_for(
            self._pulse_complete_with_observation,
            self.plan.duration_s + self.plan.status_timeout_s,
            "bounded pulse completion and fresh encoder observation",
        )
        observation = self._record_pulse_observation(final)
        print(
            "Owner recorded pulse observation "
            f"{observation['result']}; this is evidence, not a physical PASS.",
            flush=True,
        )

        # Returning to IDLE is intentionally symmetric with entry: the
        # operator must re-latch the software stop and release the raw B button
        # so the owner can verify a fresh stopped/zero/link/stationary snapshot.
        self.allow_aborted_status = True
        abort_request = self._send("abort", reason="commissioning_complete")
        self._wait_for(
            self._state_is("ABORTED"),
            self.plan.status_timeout_s,
            "owner zero-output ABORTED latch",
            request=abort_request,
            heartbeat=False,
        )
        print(
            "Pulse is complete. Re-latch the operator software stop, then "
            "release the raw B button; waiting for stop_latched=true and "
            "exit_ready=true.",
            flush=True,
        )
        self._wait_for(
            self._release_ready,
            self.plan.operator_timeout_s,
            "fresh re-latched stop and safe release readiness",
            heartbeat=False,
        )

        exit_request = self._send("exit")
        final = self._wait_for(
            self._state_is("IDLE"),
            self.plan.status_timeout_s,
            "released IDLE state",
            request=exit_request,
            heartbeat=False,
        )
        self.closed = True
        self.entered = False
        if self.session_store is not None:
            self.session_store.remove()
        self.evidence.record("complete", pulse_count=1, final_status=dict(final))
        return final

    def resume_release(self) -> Mapping[str, Any]:
        """Safely release one authenticated session left by a dead client."""

        self.allow_aborted_status = True
        status = self._wait_for(
            self._resume_status_matches,
            self.plan.status_timeout_s,
            "the recorded owner session",
            heartbeat=False,
        )
        if str(status.get("state", "")).upper() == "IDLE":
            if self.session_store is not None:
                self.session_store.remove()
            self.closed = True
            self.evidence.record("resume_already_idle")
            return status

        try:
            owner_sequence = int(status.get("sequence_ack", status.get("sequence", -1)))
        except (TypeError, ValueError):
            raise OperatorError("owner status has no valid command sequence")
        self.sequence = max(self.sequence, owner_sequence)
        self.entered = True

        if str(status.get("state", "")).upper() != "ABORTED":
            abort_request = self._send("abort", reason="client_resume_release")
            status = self._wait_for(
                self._state_is("ABORTED"),
                self.plan.status_timeout_s,
                "owner ABORTED latch during resume",
                request=abort_request,
                heartbeat=False,
            )
        print(
            "Recovered commissioning session is stopped. Re-latch the "
            "operator software stop and release raw B; waiting for exit_ready.",
            flush=True,
        )
        self._wait_for(
            self._release_ready,
            self.plan.operator_timeout_s,
            "safe resumed-session release",
            heartbeat=False,
        )
        exit_request = self._send("exit")
        final = self._wait_for(
            self._state_is("IDLE"),
            self.plan.status_timeout_s,
            "released IDLE state",
            request=exit_request,
            heartbeat=False,
        )
        self.closed = True
        self.entered = False
        if self.session_store is not None:
            self.session_store.remove()
        self.evidence.record("resume_release_complete", final_status=dict(final))
        return final

    def fail_safe_cleanup(self, reason: str) -> None:
        """Best-effort zero/abort/release messages for exceptions and signals.

        All three operations are attempted even if an earlier publish fails.
        The hardware owner is authoritative and must fail zero independently.
        """

        self.evidence.record("cleanup_begin", reason=str(reason))
        for op in ("end", "abort", "exit"):
            try:
                self._send(op, reason=str(reason)) if op == "abort" else self._send(op)
                self.evidence.record("cleanup_request_sent", op=op)
            except BaseException as exc:  # Cleanup must continue to the next stop path.
                self.evidence.record(
                    "cleanup_request_failed",
                    op=op,
                    error=f"{type(exc).__name__}: {exc}",
                )
        self.closed = True
        self.entered = False
        try:
            # Briefly service ROS so queued best-effort publications can leave.
            for _ in range(3):
                status = self.transport.poll(0.02)
                if status is not None:
                    try:
                        self._accept_status(status)
                    except OperatorError:
                        pass
        except BaseException:
            pass
        self.evidence.record("cleanup_complete")


class RosStringTransport:
    """ROS 2 String transport; no serial or motor APIs exist here."""

    def __init__(self) -> None:
        try:
            import rclpy
            from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
            from std_msgs.msg import String
        except ImportError as exc:  # pragma: no cover - depends on a ROS host.
            raise OperatorError(f"ROS 2 Python runtime unavailable: {exc}") from exc

        self._rclpy = rclpy
        self._String = String
        rclpy.init(args=None)
        self.node = rclpy.create_node("atlas_drive_pid_lifted_operator")
        request_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=20,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        status_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=20,
            reliability=ReliabilityPolicy.RELIABLE,
            # A VOLATILE reader is compatible with the owner's durable
            # TRANSIENT_LOCAL writer and remains safe with a VOLATILE fallback.
            durability=DurabilityPolicy.VOLATILE,
        )
        self.publisher = self.node.create_publisher(String, REQUEST_TOPIC, request_qos)
        self._lock = threading.Lock()
        self._statuses = []
        self.subscription = self.node.create_subscription(
            String,
            STATUS_TOPIC,
            self._on_status,
            status_qos,
        )

    def _on_status(self, message: Any) -> None:
        try:
            decoded = json.loads(message.data)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = {"state": "INVALID", "fault_reason": "malformed_status_json"}
        with self._lock:
            self._statuses.append(decoded)

    def publish(self, message: Mapping[str, Any]) -> None:
        ros_message = self._String()
        ros_message.data = json.dumps(dict(message), sort_keys=True, separators=(",", ":"))
        self.publisher.publish(ros_message)

    def poll(self, timeout_s: float) -> Optional[Mapping[str, Any]]:
        self._rclpy.spin_once(self.node, timeout_sec=max(0.0, float(timeout_s)))
        with self._lock:
            return self._statuses.pop(0) if self._statuses else None

    def close(self) -> None:
        try:
            self.node.destroy_node()
        finally:
            if self._rclpy.ok():
                self._rclpy.shutdown()


def default_evidence_path(fingerprint: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "project_atlas" / "lifted_pid" / f"{stamp}_{fingerprint[:16]}.jsonl"


def runtime_session_directory() -> Path:
    configured = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if configured:
        root = Path(configured)
    elif os.name == "nt":
        root = Path(os.environ.get("TEMP", Path.home()))
    else:
        root = Path(f"/run/user/{os.getuid()}")
    return root / "project_atlas" / "lifted_pid"


def new_runtime_session_store(fingerprint: str) -> RuntimeSessionStore:
    return RuntimeSessionStore(
        runtime_session_directory() / f"active_{fingerprint[:16]}.session"
    )


def discover_runtime_session_store() -> RuntimeSessionStore:
    directory = runtime_session_directory()
    candidates = sorted(directory.glob("active_*.session")) if directory.is_dir() else []
    if not candidates:
        raise OperatorError("no recoverable lifted commissioning session was found")
    if len(candidates) != 1:
        raise OperatorError("multiple runtime commissioning sessions exist; refusing ambiguity")
    return RuntimeSessionStore(candidates[0])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Request one supervised raw wheel pulse through the ATLAS motor owner.",
        epilog=(
            "Default is dry-run. Production PID remains disabled; this tool "
            "does not commission or enable it."
        ),
    )
    parser.add_argument("--wheel", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--pwm", type=int)
    parser.add_argument("--duration", type=float, default=0.25)
    parser.add_argument("--heartbeat", type=float, default=DEFAULT_HEARTBEAT_S)
    parser.add_argument("--status-timeout", type=float, default=5.0)
    parser.add_argument("--operator-timeout", type=float, default=120.0)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--resume-release",
        action="store_true",
        help="authenticate from the 0600 runtime record and safely release a crashed session",
    )
    parser.add_argument("--confirm", default="")
    return parser


def _install_signal_handlers() -> Dict[int, Any]:
    previous: Dict[int, Any] = {}

    def interrupted(signum: int, _frame: Any) -> None:
        raise OperatorInterrupted(f"signal {signum}")

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, interrupted)
    return previous


def _restore_signal_handlers(previous: Mapping[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if not args.resume_release and (args.wheel is None or args.pwm is None):
        print("REFUSED: --wheel and --pwm are required for a pulse plan.", file=sys.stderr)
        return 2

    session_store: Optional[RuntimeSessionStore] = None
    next_sequence = 0
    if args.resume_release:
        try:
            session_store = discover_runtime_session_store()
            recovered = session_store.load()
        except OperatorError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        session = recovered["session"]
        next_sequence = recovered["next_seq"]
    else:
        session = secrets.token_hex(16)
    fingerprint = session_fingerprint(session)
    plan = PulsePlan(
        wheel=args.wheel if args.wheel is not None else 1,
        pwm=args.pwm if args.pwm is not None else 1,
        duration_s=args.duration if not args.resume_release else MIN_RAW_DURATION_S,
        heartbeat_s=args.heartbeat,
        status_timeout_s=args.status_timeout,
        operator_timeout_s=args.operator_timeout,
    )
    try:
        plan.validate()
    except OperatorError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    evidence_path = args.evidence or default_evidence_path(fingerprint)
    evidence = EvidenceRecorder(evidence_path)
    evidence.record(
        "resume_plan" if args.resume_release else "plan",
        session_fingerprint=fingerprint,
        execute=bool(args.execute or args.resume_release),
        request_topic=REQUEST_TOPIC,
        status_topic=STATUS_TOPIC,
        wheel=None if args.resume_release else plan.wheel,
        pwm=None if args.resume_release else plan.pwm,
        duration_s=None if args.resume_release else plan.duration_s,
        heartbeat_s=plan.heartbeat_s,
        production_pid_enabled=False,
    )

    if not args.execute:
        evidence.record("dry_run_complete", messages_published=0)
        evidence.close()
        if args.resume_release:
            print(
                "DRY RUN ONLY: a recoverable session was validated, but no "
                "ROS messages or owner-state changes were made.\n"
                f"Session fingerprint: {fingerprint}\n"
                f"Evidence: {evidence_path}\n"
                "Add --execute --resume-release only after the software stop "
                "is re-latched and raw B is released.",
                flush=True,
            )
            return 0
        print(
            "DRY RUN ONLY: no ROS messages and no motor commands were sent.\n"
            f"Session fingerprint: {fingerprint}\n"
            f"Planned one-wheel pulse: M{plan.wheel}, PWM {plan.pwm}, "
            f"{plan.duration_s:.2f} s\n"
            f"Evidence: {evidence_path}\n"
            "Use --execute with the exact --confirm phrase only after the "
            "physical lifted-wheel safety check.",
            flush=True,
        )
        return 0

    if args.execute and not args.resume_release and args.confirm != CONFIRMATION_PHRASE:
        evidence.record("refused", reason="exact_confirmation_required")
        evidence.close()
        print(
            f'REFUSED: exact --confirm "{CONFIRMATION_PHRASE}" is required.',
            file=sys.stderr,
        )
        return 2

    if args.execute and not args.resume_release:
        session_store = new_runtime_session_store(fingerprint)
        try:
            session_store.save(session, next_sequence)
        except (OSError, OperatorError) as exc:
            evidence.record("refused", reason="runtime_session_store_failed")
            evidence.close()
            print(f"REFUSED: could not secure runtime recovery state: {exc}", file=sys.stderr)
            return 2

    transport: Optional[RosStringTransport] = None
    operator: Optional[LiftedPulseOperator] = None
    previous_handlers: Dict[int, Any] = {}
    try:
        transport = RosStringTransport()
        operator = LiftedPulseOperator(
            transport,
            evidence,
            plan,
            session=session,
            session_store=session_store,
            next_sequence=next_sequence,
        )
        previous_handlers = _install_signal_handlers()
        if args.resume_release:
            operator.resume_release()
            print(f"Recovered commissioning session safely returned IDLE. Evidence: {evidence_path}")
        else:
            operator.execute(args.confirm)
            print(f"Lifted pulse complete and owner returned IDLE. Evidence: {evidence_path}")
        return 0
    except BaseException as exc:
        if operator is not None:
            operator.fail_safe_cleanup(f"{type(exc).__name__}: {exc}")
        else:
            evidence.record("failed_before_session", error=f"{type(exc).__name__}: {exc}")
            if args.execute and not args.resume_release and session_store is not None:
                session_store.remove()
        if isinstance(exc, (KeyboardInterrupt, OperatorInterrupted)):
            print(f"INTERRUPTED; best-effort stop/abort/exit sent. Evidence: {evidence_path}", file=sys.stderr)
            return 130
        print(f"FAILED: {exc}. Best-effort stop/abort/exit sent. Evidence: {evidence_path}", file=sys.stderr)
        return 1
    finally:
        if previous_handlers:
            _restore_signal_handlers(previous_handlers)
        if transport is not None:
            transport.close()
        evidence.close()


if __name__ == "__main__":
    raise SystemExit(main())

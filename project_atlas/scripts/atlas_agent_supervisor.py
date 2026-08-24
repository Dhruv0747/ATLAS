#!/usr/bin/env python3
"""Safety-constrained observe-plan-act-verify supervisor for Project ATLAS."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from threading import Event, Lock, RLock, get_ident
import time
from typing import Any

import requests
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Empty, Float32, String
from std_srvs.srv import SetBool, Trigger

from atlas_agent_core import (
    TOOL_POLICIES,
    evaluate_action_status,
    enforce_request_policy,
    fallback_plan,
    plan_is_stop_only,
    plan_requires_motion,
)


API_BASE = "https://api.openai.com/v1"
MOTION_PHASE_BLOCKLIST = {"FAULT", "BLOCKED", "TRACTION_FAULT"}
REQUIRED_MOTION_SENSORS = ("lidar", "odometry", "slam_map")


class AtlasAgentSupervisor(Node):
    """Turn natural mission requests into allowlisted, verified ROS actions."""

    def __init__(self):
        super().__init__("atlas_agent_supervisor")
        self.declare_parameter("enabled", True)
        self.declare_parameter("execution_enabled", False)
        self.declare_parameter("llm_enabled", True)
        self.declare_parameter("require_confirmation", True)
        self.declare_parameter("confirmation_timeout_s", 60.0)
        self.declare_parameter("state_timeout_s", 3.0)
        self.declare_parameter("battery_timeout_s", 12.0)
        self.declare_parameter("verification_timeout_s", 12.0)
        self.declare_parameter("minimum_battery_percent", 20.0)
        self.declare_parameter("model", os.getenv("ATLAS_AGENT_MODEL", "gpt-4o-mini"))
        self.declare_parameter(
            "memory_file", str(Path.home() / ".config/project_atlas/agent_memory.json")
        )

        self.enabled = bool(self.get_parameter("enabled").value)
        self.execution_enabled = bool(self.get_parameter("execution_enabled").value)
        self.phase = "MONITOR_ONLY" if not self.execution_enabled else "READY"
        self.summary = "Agent online; waiting for a mission request"
        self.decision = "No action selected"
        self.request_text = ""
        self.pending_plan: dict[str, Any] | None = None
        self.pending_deadline = 0.0
        self.current_step = ""
        self.last_error = ""
        self.last_autonomy_state: dict[str, Any] = {}
        self.last_autonomy_at = 0.0
        self.safety_status = "UNKNOWN"
        self.mission_status = "UNKNOWN"
        self.mission_status_at = 0.0
        self.recovery_status = "UNKNOWN"
        self.recovery_status_at = 0.0
        self.recovery_state: dict[str, Any] = {}
        self.experience_recommendation: dict[str, Any] = {}
        self.traction_battery_percent: float | None = None
        self.traction_battery_at = 0.0
        self.aux_battery_percent: float | None = None
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="atlas-agent")
        self.busy_lock = Lock()
        self.memory_lock = RLock()
        self.cancel_requested = Event()

        self.status_pub = self.create_publisher(String, "/atlas/agent/status", 10)
        self.state_pub = self.create_publisher(String, "/atlas/agent/state", 10)
        self.plan_pub = self.create_publisher(String, "/atlas/agent/plan", 10)
        self.decision_pub = self.create_publisher(String, "/atlas/agent/decision", 10)
        self.response_pub = self.create_publisher(String, "/atlas/agent/response", 10)

        self.tool_pubs = {
            "set_home": self.create_publisher(Empty, "/atlas/set_home", 10),
            "start_mapping": self.create_publisher(Empty, "/atlas/start_exploration", 10),
            "stop_mapping": self.create_publisher(Empty, "/atlas/stop_exploration", 10),
            "return_home": self.create_publisher(Empty, "/atlas/return_home", 10),
            "save_named_place": self.create_publisher(String, "/atlas/save_named_place", 10),
            "navigate_named_place": self.create_publisher(String, "/atlas/navigate_named_place", 10),
            "cancel_navigation": self.create_publisher(
                Empty, "/atlas/cancel_navigation", 10
            ),
            "request_tight_recovery": self.create_publisher(
                Empty, "/atlas/tight_recovery_request", 10
            ),
        }

        self.create_subscription(String, "/atlas/agent/command", self.on_command, 10)
        self.create_subscription(
            String, "/atlas/agent/confirmation", self.on_confirmation, 10
        )
        self.create_subscription(
            Empty, "/atlas/agent/cancel_request", lambda _msg: self.cancel("topic"), 10
        )
        self.create_subscription(
            String, "/atlas/autonomy_state", self.on_autonomy_state, 10
        )
        self.create_subscription(
            String, "/atlas/safety_status", self.on_safety_status, 10
        )
        self.create_subscription(
            String, "/atlas/mission_status", self.on_mission_status, 10
        )
        self.create_subscription(
            String, "/atlas/tight_recovery_status", self.on_recovery_status, 10
        )
        self.create_subscription(
            String, "/atlas/recovery_state", self.on_recovery_state, 10
        )
        self.create_subscription(
            String,
            "/atlas/experience/recommendation",
            self.on_experience_recommendation,
            10,
        )
        self.create_subscription(
            Float32, "/battery/percent", self.on_aux_battery_percent, 10
        )
        self.create_subscription(
            Float32, "/bms/percent", self.on_traction_battery_percent, 10
        )

        self.create_service(SetBool, "/atlas/agent/set_enabled", self.set_enabled)
        self.create_service(
            SetBool, "/atlas/agent/set_execution_enabled", self.set_execution_enabled
        )
        self.create_service(Trigger, "/atlas/agent/confirm_plan", self.confirm_service)
        self.create_service(Trigger, "/atlas/agent/cancel_plan", self.cancel_service)
        self.create_service(Trigger, "/atlas/agent/clear_memory", self.clear_memory_service)

        self.memory_path = Path(str(self.get_parameter("memory_file").value))
        self.memory = self.load_memory()
        self.create_timer(0.5, self.publish_state)
        self.create_timer(1.0, self.expire_pending_plan)
        self.record("boot", "Agent supervisor started in " + self.phase)
        self.publish_message(self.summary)

    def load_memory(self) -> dict[str, Any]:
        try:
            data = json.loads(self.memory_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("events"), list):
                return data
        except (OSError, ValueError):
            pass
        return {"version": 1, "events": [], "successful_missions": 0}

    def save_memory(self) -> None:
        with self.memory_lock:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.memory_path.with_name(
                f"{self.memory_path.name}.tmp.{os.getpid()}.{get_ident()}"
            )
            temporary.write_text(
                json.dumps(self.memory, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            temporary.replace(self.memory_path)

    def record(self, kind: str, message: str, **extra: Any) -> None:
        event = {
            "unix_time": round(time.time(), 3),
            "kind": kind[:40],
            "message": message[:300],
            **extra,
        }
        try:
            with self.memory_lock:
                self.memory.setdefault("events", []).append(event)
                self.memory["events"] = self.memory["events"][-200:]
                self.save_memory()
        except OSError as exc:
            self.get_logger().error(f"Could not save agent memory: {exc}")

    def publish_message(self, text: str) -> None:
        self.summary = text
        self.status_pub.publish(String(data=text))
        self.response_pub.publish(String(data=text))
        self.get_logger().info(text)

    def on_autonomy_state(self, msg: String) -> None:
        try:
            state = json.loads(msg.data)
            if isinstance(state, dict):
                self.last_autonomy_state = state
                self.last_autonomy_at = time.monotonic()
        except ValueError:
            self.last_error = "Invalid /atlas/autonomy_state JSON"

    def on_safety_status(self, msg: String) -> None:
        self.safety_status = msg.data

    def on_mission_status(self, msg: String) -> None:
        self.mission_status = msg.data
        self.mission_status_at = time.monotonic()

    def on_recovery_status(self, msg: String) -> None:
        self.recovery_status = msg.data
        self.recovery_status_at = time.monotonic()

    def on_recovery_state(self, msg: String) -> None:
        try:
            value = json.loads(msg.data)
            self.recovery_state = value if isinstance(value, dict) else {}
        except ValueError:
            self.recovery_state = {}

    def on_experience_recommendation(self, msg: String) -> None:
        try:
            value = json.loads(msg.data)
            self.experience_recommendation = value if isinstance(value, dict) else {}
        except ValueError:
            self.experience_recommendation = {}

    def on_traction_battery_percent(self, msg: Float32) -> None:
        value = float(msg.data)
        if 0.0 <= value <= 100.0:
            self.traction_battery_percent = value
            self.traction_battery_at = time.monotonic()

    def on_aux_battery_percent(self, msg: Float32) -> None:
        value = float(msg.data)
        if 0.0 <= value <= 100.0:
            self.aux_battery_percent = value

    def snapshot(self) -> dict[str, Any]:
        age = (
            round(time.monotonic() - self.last_autonomy_at, 2)
            if self.last_autonomy_at
            else None
        )
        return {
            "autonomy": self.last_autonomy_state,
            "autonomy_age_s": age,
            "safety_status": self.safety_status,
            "mission_status": self.mission_status,
            "recovery_status": self.recovery_status,
            "recovery_state": self.recovery_state,
            "past_recovery_evidence": self.experience_recommendation,
            "traction_battery_percent": self.traction_battery_percent,
            "traction_battery_age_s": (
                round(time.monotonic() - self.traction_battery_at, 2)
                if self.traction_battery_at else None
            ),
            "aux_battery_percent": self.aux_battery_percent,
        }

    def set_enabled(self, request: SetBool.Request, response: SetBool.Response):
        self.enabled = bool(request.data)
        if not self.enabled:
            self.cancel("agent disabled")
        self.record("configuration", f"enabled={self.enabled}")
        response.success = True
        response.message = f"agent enabled={self.enabled}"
        return response

    def set_execution_enabled(
        self, request: SetBool.Request, response: SetBool.Response
    ):
        self.execution_enabled = bool(request.data)
        self.phase = "READY" if self.execution_enabled else "MONITOR_ONLY"
        self.pending_plan = None
        self.record("configuration", f"execution_enabled={self.execution_enabled}")
        response.success = True
        response.message = (
            "execution enabled; confirmation and preflight remain mandatory"
            if self.execution_enabled
            else "monitor-only mode enabled; no physical action can be dispatched"
        )
        self.publish_message(response.message)
        return response

    def clear_memory_service(self, _request, response: Trigger.Response):
        self.memory = {"version": 1, "events": [], "successful_missions": 0}
        self.save_memory()
        response.success = True
        response.message = "agent event memory cleared"
        return response

    def confirm_service(self, _request, response: Trigger.Response):
        accepted, message = self.confirm("service")
        response.success = accepted
        response.message = message
        return response

    def cancel_service(self, _request, response: Trigger.Response):
        self.cancel("service")
        response.success = True
        response.message = "pending plan canceled; Nav2 cancel requested"
        return response

    def on_confirmation(self, msg: String) -> None:
        value = msg.data.strip().lower()
        if value in {"confirm", "yes", "proceed", "go", "haan", "हाँ"}:
            self.confirm("topic")
        elif value in {"cancel", "no", "stop", "nahi", "नहीं"}:
            self.cancel("confirmation topic")

    def on_command(self, msg: String) -> None:
        request = " ".join(msg.data.strip().split())
        if not request:
            return
        if not self.enabled:
            self.publish_message("Agent is disabled; request ignored")
            return
        if self.phase in {"AWAITING_CONFIRMATION", "EXECUTING", "VERIFYING"}:
            self.publish_message(
                "Finish or cancel the current agent plan before sending another mission"
            )
            return
        if not self.busy_lock.acquire(blocking=False):
            self.publish_message("Agent is busy; wait for the current plan")
            return
        self.request_text = request[:500]
        self.cancel_requested.clear()
        self.phase = "OBSERVING"
        self.decision = "Collecting live safety and mission state"
        self.record("request", self.request_text)
        self.worker.submit(self.build_plan_worker, self.request_text)

    def call_cloud_planner(self, request: str) -> dict[str, Any]:
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        allowed = {
            name: {
                "description": policy.description,
                "motion_capable": policy.motion_capable,
            }
            for name, policy in TOOL_POLICIES.items()
        }
        system = (
            "You are the Project ATLAS mission planner. Return one JSON object only "
            "with intent, summary, and steps. Each step must contain action and a "
            "short operator-visible reason. Use only the supplied allowlisted tools. "
            "Use no more than four steps. Prefer inspect_status when the request is "
            "unclear. Never invent sensor readings, shell commands, raw motor control, "
            "or coordinates. For save_named_place and navigate_named_place, include a "
            "target field containing the operator's place name. Never invent a place. "
            "A separate deterministic safety gate will approve or "
            "reject execution. Do not include hidden reasoning or chain of thought."
        )
        body = {
            "model": str(self.get_parameter("model").value),
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "request": request,
                            "live_state": self.snapshot(),
                            "allowed_tools": allowed,
                            "recent_memory": self.memory.get("events", [])[-8:],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0.1,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        }
        response = requests.post(
            f"{API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=25,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    def build_plan_worker(self, request: str) -> None:
        try:
            self.phase = "PLANNING"
            self.decision = "Selecting only allowlisted high-level tools"
            use_cloud = bool(self.get_parameter("llm_enabled").value)
            try:
                raw = self.call_cloud_planner(request) if use_cloud else fallback_plan(request)
                if use_cloud:
                    raw["planner"] = "openai"
            except Exception as exc:
                self.get_logger().warning(f"Cloud planner unavailable; using rules: {exc}")
                raw = fallback_plan(request)
            try:
                plan = enforce_request_policy(
                    raw,
                    request,
                    str(self.last_autonomy_state.get("phase", "")),
                )
            except (TypeError, ValueError, KeyError) as exc:
                if not use_cloud:
                    raise
                self.get_logger().warning(
                    f"Cloud plan failed policy validation; using rules: {exc}"
                )
                plan = enforce_request_policy(
                    fallback_plan(request),
                    request,
                    str(self.last_autonomy_state.get("phase", "")),
                )
            self.pending_plan = plan
            self.pending_deadline = time.monotonic() + float(
                self.get_parameter("confirmation_timeout_s").value
            )
            requires_confirmation = (
                self.execution_enabled
                and not plan_is_stop_only(plan)
                and bool(self.get_parameter("require_confirmation").value)
            )
            if requires_confirmation:
                # Publish the plan only after confirm() can safely see it as
                # pending. This closes the DDS delivery race between the plan
                # topic and the confirmation service.
                self.phase = "AWAITING_CONFIRMATION"
            self.plan_pub.publish(String(data=json.dumps(plan, separators=(",", ":"))))
            actions = ", ".join(step["action"] for step in plan["steps"])
            self.decision = plan["summary"]
            self.record("plan", plan["summary"], actions=actions, planner=plan["planner"])

            # A cancel can arrive as soon as the plan topic is observed.  Do
            # not let the planner worker overwrite cancel() with a later
            # AWAITING_CONFIRMATION transition.
            if self.cancel_requested.is_set():
                self.pending_plan = None
                self.pending_deadline = 0.0
                self.phase = "READY" if self.execution_enabled else "MONITOR_ONLY"
                self.decision = "Plan canceled before dispatch"
                return
            if requires_confirmation and self.phase != "AWAITING_CONFIRMATION":
                # confirm() already accepted/rejected the plan while this
                # worker was finishing its operator-visible record.
                return

            if not self.execution_enabled:
                self.phase = "MONITOR_ONLY"
                self.publish_message(
                    f"Plan ready in monitor-only mode: {actions}. No action dispatched."
                )
            elif plan_is_stop_only(plan):
                self.phase = "EXECUTING"
                self.publish_message(f"Executing safety action: {actions}")
                self.execute_plan_worker(plan)
            elif requires_confirmation:
                self.publish_message(
                    f"Plan ready: {actions}. Confirm within "
                    f"{int(self.get_parameter('confirmation_timeout_s').value)} seconds."
                )
            else:
                accepted, reason = self.preflight(plan)
                if not accepted:
                    self.fail_plan(reason)
                else:
                    self.execute_plan_worker(plan)
        except Exception as exc:
            self.fail_plan(f"Planning failed: {exc}")
        finally:
            if self.phase not in {"EXECUTING", "VERIFYING"}:
                self.busy_lock.release()

    def preflight(self, plan: dict[str, Any]) -> tuple[bool, str]:
        if not self.enabled:
            return False, "agent is disabled"
        if not self.execution_enabled:
            return False, "agent is in monitor-only mode"
        if not plan_requires_motion(plan):
            return True, "non-motion plan"
        timeout = float(self.get_parameter("state_timeout_s").value)
        if not self.last_autonomy_at or time.monotonic() - self.last_autonomy_at > timeout:
            return False, "live autonomy safety state is stale"
        phase = str(self.last_autonomy_state.get("phase", "UNKNOWN")).upper()
        actions = {step["action"] for step in plan["steps"]}
        if phase in MOTION_PHASE_BLOCKLIST and "request_tight_recovery" not in actions:
            return False, f"autonomy phase {phase} blocks motion"
        sensors = self.last_autonomy_state.get("sensors", {})
        missing = [name for name in REQUIRED_MOTION_SENSORS if sensors.get(name) != "ONLINE"]
        if missing:
            return False, "required safety sensors unavailable: " + ", ".join(missing)
        minimum = float(self.get_parameter("minimum_battery_percent").value)
        if (
            self.traction_battery_percent is None
            or not self.traction_battery_at
            or time.monotonic() - self.traction_battery_at
            > float(self.get_parameter("battery_timeout_s").value)
        ):
            return False, "main traction BMS percentage is unavailable or stale"
        if self.traction_battery_percent < minimum:
            return False, (
                f"main traction battery {self.traction_battery_percent:.0f}% "
                f"is below {minimum:.0f}%"
            )
        drive_mode = str(self.last_autonomy_state.get("drive_mode", "")).upper()
        if drive_mode in {"REMOTE", "WEB", "FOXGLOVE"}:
            return False, f"manual channel {drive_mode} currently has control"
        return True, "preflight passed"

    def confirm(self, source: str) -> tuple[bool, str]:
        plan = self.pending_plan
        if plan is None or self.phase != "AWAITING_CONFIRMATION":
            message = "No plan is waiting for confirmation"
            self.publish_message(message)
            return False, message
        if time.monotonic() > self.pending_deadline:
            self.pending_plan = None
            self.phase = "READY"
            message = "Plan confirmation expired"
            self.publish_message(message)
            return False, message
        accepted, reason = self.preflight(plan)
        if not accepted:
            self.fail_plan("Preflight rejected: " + reason)
            if self.busy_lock.locked():
                self.busy_lock.release()
            return False, reason
        self.record("confirmation", f"confirmed via {source}")
        self.phase = "EXECUTING"
        self.worker.submit(self.execute_confirmed_worker, plan)
        return True, "plan confirmed; safe execution queued"

    def execute_confirmed_worker(self, plan: dict[str, Any]) -> None:
        try:
            self.execute_plan_worker(plan)
        finally:
            if self.busy_lock.locked():
                self.busy_lock.release()

    def execute_plan_worker(self, plan: dict[str, Any]) -> None:
        self.pending_plan = None
        self.phase = "EXECUTING"
        for index, step in enumerate(plan["steps"], start=1):
            if self.cancel_requested.is_set():
                return
            action = step["action"]
            self.current_step = action
            self.decision = f"Step {index}/{len(plan['steps'])}: {step['reason']}"
            self.decision_pub.publish(String(data=self.decision))
            accepted, reason = self.preflight(
                {**plan, "steps": [step]}
            )
            if not accepted and not TOOL_POLICIES[action].always_safe:
                self.fail_plan(f"{action} blocked: {reason}")
                return
            if action == "inspect_status":
                self.publish_message(
                    "Live ATLAS state: " + json.dumps(self.snapshot(), separators=(",", ":"))
                )
                continue
            publisher = self.tool_pubs[action]
            if publisher.get_subscription_count() < 1:
                self.fail_plan(f"{action} tool has no active ROS subscriber")
                return
            before = self.observation_value(action)
            if action in {"save_named_place", "navigate_named_place"}:
                publisher.publish(String(data=step["target"]))
            else:
                publisher.publish(Empty())
            self.record("tool", action, reason=step["reason"])
            self.phase = "VERIFYING"
            verified, detail = self.verify_action(action, before)
            if not verified:
                if self.cancel_requested.is_set():
                    return
                if TOOL_POLICIES[action].motion_capable:
                    self.tool_pubs["cancel_navigation"].publish(Empty())
                self.fail_plan(f"{action} was not verified: {detail}")
                return
            if self.cancel_requested.is_set():
                return
            self.phase = "EXECUTING"
            self.publish_message(f"Verified {action}: {detail}")

        self.phase = "READY" if self.execution_enabled else "MONITOR_ONLY"
        self.current_step = ""
        self.last_error = ""
        self.decision = "Mission plan completed and verified"
        self.memory["successful_missions"] = int(
            self.memory.get("successful_missions", 0)
        ) + 1
        self.record("success", plan["summary"])
        self.publish_message("ATLAS agent mission completed and verified")

    def observation_value(self, action: str) -> tuple[str, float]:
        if action == "request_tight_recovery":
            return self.recovery_status, self.recovery_status_at
        return self.mission_status, self.mission_status_at

    def verify_action(
        self, action: str, before: tuple[str, float]
    ) -> tuple[bool, str]:
        if action == "inspect_status":
            return True, "state snapshot published"
        base_timeout = float(self.get_parameter("verification_timeout_s").value)
        timeout = {
            "set_home": 6.0,
            "start_mapping": 18.0,
            "stop_mapping": 45.0,
            # Nav2's progress checker allows 20 seconds for a car-like rover
            # to make measurable progress.  Keep the agent verifier alive
            # beyond that window so it observes Nav2's real terminal result
            # instead of canceling a valid final approach prematurely.
            "return_home": 45.0,
            "save_named_place": 6.0,
            "navigate_named_place": 90.0,
            "cancel_navigation": 8.0,
            "request_tight_recovery": 15.0,
        }.get(action, base_timeout)
        deadline = time.monotonic() + max(base_timeout, timeout)
        while time.monotonic() < deadline:
            if self.cancel_requested.is_set():
                return False, "operator canceled the plan"
            current = self.observation_value(action)
            text, observed_at = current
            if observed_at > before[1]:
                result = evaluate_action_status(action, text)
                if result is not None:
                    return result, text
            time.sleep(0.1)
        return False, f"no expected status after {before[0]!r}"

    def fail_plan(self, reason: str) -> None:
        self.phase = "FAILED"
        self.last_error = reason
        self.current_step = ""
        self.pending_plan = None
        self.decision = "Fail-safe stop; human review required"
        self.record("failure", reason)
        self.publish_message(reason)

    def cancel(self, source: str) -> None:
        self.cancel_requested.set()
        self.pending_plan = None
        self.pending_deadline = 0.0
        self.current_step = ""
        cancel_pub = self.tool_pubs["cancel_navigation"]
        if cancel_pub.get_subscription_count() > 0:
            cancel_pub.publish(Empty())
        self.phase = "READY" if self.execution_enabled else "MONITOR_ONLY"
        self.decision = f"Canceled via {source}; stop tool requested"
        self.record("cancel", self.decision)
        self.publish_message(self.decision)

    def expire_pending_plan(self) -> None:
        if (
            self.phase == "AWAITING_CONFIRMATION"
            and self.pending_plan is not None
            and time.monotonic() > self.pending_deadline
        ):
            self.pending_plan = None
            self.phase = "READY" if self.execution_enabled else "MONITOR_ONLY"
            self.decision = "Confirmation expired; nothing was dispatched"
            self.record("expiry", self.decision)
            self.publish_message(self.decision)
            if self.busy_lock.locked():
                self.busy_lock.release()

    def publish_state(self) -> None:
        plan = self.pending_plan or {}
        state = {
            "enabled": self.enabled,
            "execution_enabled": self.execution_enabled,
            "mode": "ACTIVE" if self.execution_enabled else "MONITOR_ONLY",
            "phase": self.phase,
            "summary": self.summary,
            "decision": self.decision,
            "request": self.request_text,
            "current_step": self.current_step,
            "pending_actions": [step["action"] for step in plan.get("steps", [])],
            "confirmation_remaining_s": max(
                0.0, round(self.pending_deadline - time.monotonic(), 1)
            ) if self.phase == "AWAITING_CONFIRMATION" else 0.0,
            "successful_missions": int(self.memory.get("successful_missions", 0)),
            "last_error": self.last_error,
            "live": self.snapshot(),
        }
        encoded = json.dumps(state, separators=(",", ":"), ensure_ascii=False)
        self.state_pub.publish(String(data=encoded))
        self.status_pub.publish(String(data=self.summary))
        self.decision_pub.publish(String(data=self.decision))

    def destroy_node(self):
        self.worker.shutdown(wait=False, cancel_futures=True)
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = AtlasAgentSupervisor()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

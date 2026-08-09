#!/usr/bin/env python3
"""Pure, testable planning rules for the Project ATLAS mission agent."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class ToolPolicy:
    description: str
    motion_capable: bool
    always_safe: bool = False


TOOL_POLICIES = {
    "inspect_status": ToolPolicy("Summarize live rover state", False, True),
    "set_home": ToolPolicy("Save the current localized pose as home", False),
    "start_mapping": ToolPolicy("Start SLAM frontier exploration", True),
    "stop_mapping": ToolPolicy("Stop exploration, cancel goals, and save map", False, True),
    "return_home": ToolPolicy("Ask Nav2 to return to the saved home pose", True),
    "cancel_navigation": ToolPolicy("Cancel every active Nav2 goal and stop", False, True),
    "request_tight_recovery": ToolPolicy(
        "Request one sensor-guarded bounded recovery pulse", True
    ),
}

MAX_PLAN_STEPS = 4


def evaluate_action_status(action: str, status: str) -> bool | None:
    """Classify a fresh mission status as success, failure, or not-final."""
    text = str(status).upper()
    if action == "return_home":
        if "RETURN HOME FINISHED" not in text:
            return None
        match = re.search(r"STATUS\s*=\s*(\d+)", text)
        return bool(match and int(match.group(1)) == 4)
    if action == "request_tight_recovery":
        if "RECOVERED" in text:
            return True
        if "BLOCKED" in text:
            return False
        return None
    expected = {
        "set_home": "HOME SAVED",
        "start_mapping": "EXPLORATION ACTIVE",
        "stop_mapping": "EXPLORATION STOPPED",
        "cancel_navigation": "NAVIGATION CANCELED",
    }.get(action)
    if expected is None:
        return None
    return True if expected in text else None


def _step(action: str, reason: str) -> dict[str, str]:
    return {"action": action, "reason": reason[:180]}


def fallback_plan(request: str) -> dict[str, Any]:
    """Create a conservative offline plan when the cloud planner is unavailable."""
    text = " ".join((request or "").lower().split())
    if any(word in text for word in ("emergency", "cancel", "stop moving", "stop navigation")):
        steps = [_step("cancel_navigation", "A stop request takes priority")]
        intent = "stop"
    elif "stop" in text and any(word in text for word in ("map", "explor")):
        steps = [_step("stop_mapping", "Stop exploration and preserve the map")]
        intent = "stop_mapping"
    elif any(word in text for word in ("map", "explore", "scan the room")):
        steps = [
            _step("set_home", "Record the mission start before autonomous movement"),
            _step("start_mapping", "Use the commissioned SLAM and Explore Lite stack"),
        ]
        intent = "map_room"
    elif any(phrase in text for phrase in ("return home", "go home", "come home")):
        steps = [_step("return_home", "Use Nav2 and the saved home pose")]
        intent = "return_home"
    elif any(word in text for word in ("stuck", "recover", "escape", "tight space")):
        steps = [
            _step(
                "request_tight_recovery",
                "Use one bounded sensor-verified recovery attempt",
            )
        ]
        intent = "recover"
    elif any(phrase in text for phrase in ("set home", "save home", "home point")):
        steps = [_step("set_home", "Store the current localized pose")]
        intent = "set_home"
    else:
        steps = [_step("inspect_status", "Observe before proposing physical action")]
        intent = "inspect"
    return {
        "intent": intent,
        "summary": f"Conservative ATLAS plan for: {request[:160]}",
        "steps": steps,
        "planner": "offline_rules",
    }


def validate_plan(plan: Any) -> dict[str, Any]:
    """Normalize an untrusted LLM plan into the fixed ATLAS tool allowlist."""
    if not isinstance(plan, dict):
        raise ValueError("plan must be a JSON object")
    raw_steps = plan.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("plan must contain at least one step")
    if len(raw_steps) > MAX_PLAN_STEPS:
        raise ValueError(f"plan exceeds {MAX_PLAN_STEPS} steps")

    steps = []
    for raw in raw_steps:
        if not isinstance(raw, dict):
            raise ValueError("each plan step must be an object")
        action = str(raw.get("action", "")).strip()
        if action not in TOOL_POLICIES:
            raise ValueError(f"tool is not allowed: {action or '<empty>'}")
        reason = str(raw.get("reason", TOOL_POLICIES[action].description)).strip()
        steps.append(_step(action, reason))

    intent = str(plan.get("intent", "mission")).strip()[:80] or "mission"
    summary = str(plan.get("summary", "ATLAS mission plan")).strip()[:240]
    planner = str(plan.get("planner", "cloud_llm")).strip()[:40]
    return {"intent": intent, "summary": summary, "steps": steps, "planner": planner}


def plan_requires_motion(plan: dict[str, Any]) -> bool:
    return any(TOOL_POLICIES[step["action"]].motion_capable for step in plan["steps"])


def plan_is_stop_only(plan: dict[str, Any]) -> bool:
    return all(TOOL_POLICIES[step["action"]].always_safe for step in plan["steps"])


def enforce_request_policy(
    plan: dict[str, Any], request: str, autonomy_phase: str = ""
) -> dict[str, Any]:
    """Apply non-LLM mission sequencing and recovery invariants."""
    normalized = validate_plan(plan)
    text = " ".join((request or "").lower().split())
    phase = (autonomy_phase or "").upper()
    recovery_requested = any(
        word in text for word in ("stuck", "recover", "recovery", "escape")
    )
    recovery_allowed = recovery_requested or phase in {"BLOCKED", "TRACTION_FAULT"}

    steps = []
    for step in normalized["steps"]:
        if step["action"] == "request_tight_recovery" and not recovery_allowed:
            continue
        steps.append(step)

    actions = [step["action"] for step in steps]
    if "start_mapping" in actions:
        # Starting exploration is a long-running mission boundary. Return-home
        # or recovery must be a later, separately observed and confirmed plan.
        steps = [
            step
            for step in steps
            if not TOOL_POLICIES[step["action"]].motion_capable
            or step["action"] == "start_mapping"
        ]
        actions = [step["action"] for step in steps]
        if "set_home" not in actions[: actions.index("start_mapping")]:
            insert_at = actions.index("start_mapping")
            steps.insert(
                insert_at,
                _step("set_home", "Record mission home before exploration starts"),
            )

    # Never dispatch multiple independent motion tools from one LLM response.
    motion_seen = False
    bounded = []
    for step in steps:
        if TOOL_POLICIES[step["action"]].motion_capable:
            if motion_seen:
                continue
            motion_seen = True
        bounded.append(step)
    steps = bounded[:MAX_PLAN_STEPS]
    if not steps:
        steps = [_step("inspect_status", "No policy-approved action remained")]

    normalized["steps"] = steps
    return normalized

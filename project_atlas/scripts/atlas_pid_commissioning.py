#!/usr/bin/env python3
"""Staged, evidence-producing commissioning gate for ATLAS drive PID.

This tool never sends motor commands.  It validates software/configuration and
records operator-observed results from separately controlled physical tests.
Powered stages require an exact confirmation phrase on every invocation.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "drive_pid.yaml"
RESULTS = ROOT / "commissioning" / "drive_pid"
POWERED_STAGES = {
    "lifted_direction": "LIFTED CLEAR ESTOP READY",
    "encoder_counts": "LIFTED CLEAR ESTOP READY",
    "one_wheel_response": "LIFTED CLEAR ESTOP READY",
    "lifted_four_wheel": "LIFTED CLEAR ESTOP READY",
    "ground_straight": "GROUND CLEAR ESTOP READY",
    "distance_forward_reverse": "GROUND CLEAR ESTOP READY",
    "measured_turns": "GROUND CLEAR ESTOP READY",
    "stop_timeout": "GROUND CLEAR ESTOP READY",
    "manual_yaw_tuning": "GROUND CLEAR ESTOP READY",
    "nav2_low_speed": "GROUND CLEAR ESTOP READY",
}
STAGES = ("static", "simulation", *POWERED_STAGES)


def static_check() -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    from atlas_closed_loop_control import load_drive_config

    cfg = load_drive_config(CONFIG)
    checks = {
        "enabled_is_false": not cfg.enabled,
        "hardware_commissioned_is_false": not cfg.hardware_commissioned,
        "navigation_validated_is_false": not cfg.navigation_validated,
        "m4_remains_excluded": 4 in cfg.excluded_encoders,
        "track_width_still_requires_measurement": cfg.geometry.track_width_m is None,
        "all_gains_are_zero": all(
            wheel.pid.kp == wheel.pid.ki == wheel.pid.kd == 0.0
            and wheel.pid.feed_forward == wheel.pid.static_feed_forward == 0.0
            for wheel in cfg.wheels
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def simulation_check() -> dict:
    command = [sys.executable, str(ROOT / "scripts" / "test_closed_loop_control.py"), "-v"]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "passed": completed.returncode == 0,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
    }


def record(args: argparse.Namespace, result: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS / f"{stamp}_{args.stage}.json"
    payload = {
        "schema": 1,
        "utc": datetime.now(timezone.utc).isoformat(),
        "stage": args.stage,
        "operator_observation": args.observation,
        "result": result,
        "safety": {
            "tool_sent_motor_commands": False,
            "autonomy_enabled_by_tool": False,
            "m4_exclusion_changed_by_tool": False,
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--confirm", default="", help="Exact powered-stage confirmation phrase")
    parser.add_argument("--observation", default="", help="Operator-observed result; no secrets")
    args = parser.parse_args()

    if args.stage == "static":
        result = static_check()
    elif args.stage == "simulation":
        result = simulation_check()
    else:
        required = POWERED_STAGES[args.stage]
        if args.confirm != required:
            print(f"BLOCKED: powered stage requires --confirm \"{required}\"", file=sys.stderr)
            print("This script never moves ATLAS. Run the documented bounded test separately.", file=sys.stderr)
            return 2
        if not args.observation.strip():
            print("BLOCKED: provide --observation with the measured result", file=sys.stderr)
            return 2
        result = {
            "passed": None,
            "status": "operator_evidence_recorded_pending_engineering_review",
            "required_confirmation": required,
        }

    evidence = record(args, result)
    print(json.dumps(result, indent=2))
    print(f"Evidence: {evidence}")
    return 0 if result.get("passed") is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())

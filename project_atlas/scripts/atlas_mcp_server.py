#!/usr/bin/env python3
"""Safety-gated MCP tools for Project ATLAS.

The server deliberately talks to ATLAS through its commissioned ROS and web
interfaces.  It never opens the motor-controller serial port and never writes
to /cmd_vel directly.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from mcp.server.fastmcp import FastMCP


STATUS_URL = os.environ.get("ATLAS_STATUS_URL", "http://127.0.0.1:8088/api/status")
CAMERA_URL = os.environ.get("ATLAS_CAMERA_URL", "http://127.0.0.1:8088/camera.jpg")
SNAPSHOT_PATH = Path(os.environ.get("ATLAS_SNAPSHOT_PATH", "/tmp/atlas_mcp_camera.jpg"))
MOTION_ENABLED = os.environ.get("ATLAS_MCP_ENABLE_MOTION", "0") == "1"
TIMEOUT_S = 5.0

mcp = FastMCP("atlas-rover")


def _json_get(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        if response.status != 200:
            raise RuntimeError(f"ATLAS gateway returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _run(command: Sequence[str], timeout: float = 10.0) -> str:
    result = subprocess.run(
        list(command), capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise RuntimeError(detail)
    return result.stdout.strip()


def _call_trigger(service: str) -> str:
    return _run(
        ["ros2", "service", "call", service, "std_srvs/srv/Trigger", "{}"],
        timeout=15.0,
    )


def _require_motion_enabled() -> None:
    if not MOTION_ENABLED:
        raise RuntimeError(
            "Motion-capable MCP tools are locked. Commission the read-only tools "
            "first, then set ATLAS_MCP_ENABLE_MOTION=1 explicitly."
        )


def _finite_pose(x: float, y: float, yaw: float) -> None:
    if not all(math.isfinite(value) for value in (x, y, yaw)):
        raise ValueError("x, y and yaw must be finite numbers")
    if abs(x) > 1000.0 or abs(y) > 1000.0:
        raise ValueError("goal is outside the 1 km MCP safety envelope")


@mcp.tool()
def get_robot_status() -> dict[str, Any]:
    """Return the current ATLAS gateway status and safety telemetry."""
    try:
        status = _json_get(STATUS_URL)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {"ok": False, "state": "OFFLINE", "error": str(exc)}
    return {"ok": True, "motion_tools_enabled": MOTION_ENABLED, **status}


@mcp.tool()
def get_sensor_summary() -> dict[str, Any]:
    """Return a compact sensor, pose, power and safety summary."""
    status = get_robot_status()
    if not status.get("ok"):
        return status
    ros = status.get("ros", {})
    keys = (
        "atlas_health", "atlas_readiness", "motion_safety", "drive_mode",
        "lidar", "us_front", "us_left", "us_right", "radar_count",
        "radar_dist", "radar_zone", "odom", "imu_heading", "bms_percent",
        "bms_voltage", "mission_status",
    )
    return {"ok": True, "sensors": {key: ros.get(key) for key in keys}}


@mcp.tool()
def capture_image() -> str:
    """Save the latest Jetson camera frame to a local file and return its path."""
    request = urllib.request.Request(CAMERA_URL, headers={"Accept": "image/jpeg"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        image = response.read(8 * 1024 * 1024)
    if not image.startswith(b"\xff\xd8"):
        raise RuntimeError("ATLAS camera endpoint did not return a JPEG")
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = SNAPSHOT_PATH.with_suffix(".tmp")
    temporary.write_bytes(image)
    temporary.replace(SNAPSHOT_PATH)
    return str(SNAPSHOT_PATH)


@mcp.tool()
def stop_navigation() -> str:
    """Cancel exploration/Nav2 through the commissioned mission controller."""
    return _call_trigger("/atlas/stop_exploration")


@mcp.tool()
def emergency_stop() -> str:
    """Issue a software stop on every mux input and cancel navigation.

    This is intentionally not described as a replacement for ATLAS's physical,
    independently wired emergency stop.
    """
    commands = []
    for topic in ("/cmd_vel_joy", "/cmd_vel_web", "/cmd_vel_teleop", "/cmd_vel_nav"):
        commands.append(
            _run(
                ["ros2", "topic", "pub", "--once", topic, "geometry_msgs/msg/Twist", "{}"],
                timeout=5.0,
            )
        )
    try:
        commands.append(_call_trigger("/atlas/stop_exploration"))
    except RuntimeError as exc:
        commands.append(f"navigation cancellation unavailable: {exc}")
    return (
        "Software emergency stop issued through all command-mux inputs; "
        "the physical emergency stop remains authoritative. "
        + " | ".join(commands)
    )


@mcp.tool()
def start_mapping(confirm_clear_area: bool = False) -> str:
    """Start guarded exploration after explicit operator-area confirmation."""
    _require_motion_enabled()
    if not confirm_clear_area:
        raise RuntimeError(
            "Operator must confirm a clear area and access to the physical emergency stop."
        )
    return _call_trigger("/atlas/start_exploration")


@mcp.tool()
def save_map_and_stop() -> str:
    """Stop exploration and save the current map through mission control."""
    return _call_trigger("/atlas/stop_exploration")


@mcp.tool()
def return_home(confirm_clear_area: bool = False) -> str:
    """Request the commissioned return-home mission after operator confirmation."""
    _require_motion_enabled()
    if not confirm_clear_area:
        raise RuntimeError(
            "Operator must confirm a clear area and access to the physical emergency stop."
        )
    return _call_trigger("/atlas/return_home")


if __name__ == "__main__":
    mcp.run(transport="stdio")

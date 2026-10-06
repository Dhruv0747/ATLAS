#!/usr/bin/env python3
"""ROS-independent mapping-session readiness rules for ATLAS."""

from typing import Any


def mapping_session_is_active(value: Any) -> bool:
    """Return True only when a mapping session is safe to treat as active.

    Manual teaching is fail-closed: an explicit boolean drive_ready=True is
    required in addition to state=active. Autonomous exploration keeps
    compatibility with its existing active-session format.
    """
    if not isinstance(value, dict):
        return False
    if value.get("state") != "active":
        return False
    if value.get("mode") == "manual_teaching":
        return value.get("drive_ready") is True
    return True

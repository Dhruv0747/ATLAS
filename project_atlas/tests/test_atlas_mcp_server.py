"""Unit tests for MCP validation helpers without requiring ROS hardware."""

import importlib.util
import math
from pathlib import Path
import sys
import types
import unittest


fastmcp = types.ModuleType("mcp.server.fastmcp")


class FakeFastMCP:
    def __init__(self, _name):
        pass

    def tool(self):
        return lambda function: function


fastmcp.FastMCP = FakeFastMCP
sys.modules.setdefault("mcp", types.ModuleType("mcp"))
sys.modules.setdefault("mcp.server", types.ModuleType("mcp.server"))
sys.modules["mcp.server.fastmcp"] = fastmcp

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "atlas_mcp_server.py"
SPEC = importlib.util.spec_from_file_location("atlas_mcp_server", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ValidationTests(unittest.TestCase):
    def test_accepts_normal_pose(self):
        MODULE._finite_pose(1.0, -2.0, math.pi)

    def test_rejects_non_finite_pose(self):
        with self.assertRaises(ValueError):
            MODULE._finite_pose(float("nan"), 0.0, 0.0)

    def test_rejects_goal_outside_envelope(self):
        with self.assertRaises(ValueError):
            MODULE._finite_pose(1000.1, 0.0, 0.0)

    def test_motion_locked_by_default(self):
        if not MODULE.MOTION_ENABLED:
            with self.assertRaises(RuntimeError):
                MODULE._require_motion_enabled()


if __name__ == "__main__":
    unittest.main()

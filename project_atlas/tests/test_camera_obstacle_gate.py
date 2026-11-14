"""2026-11-14: autonomy never runs without fresh Astra camera obstacles (needs ROS to import mission control)."""
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import atlas_mission_control as M
except Exception:  # pragma: no cover - ROS not available
    M = None


@unittest.skipIf(M is None, "atlas_mission_control needs ROS 2")
class CameraGate(unittest.TestCase):
    def node(self, received_at=None, enabled=True, active=0):
        n = object.__new__(M.AtlasMissionControl)
        n.require_camera_obstacles_enabled = enabled
        n.camera_obstacle_max_age_s = 1.5
        n.camera_obstacle_lost_stop_s = 2.0
        n.camera_obstacle_received_at = received_at
        n.autonomy_goals_active = active
        n.camera_lost_stop_sent = False
        n.zero_pub = types.SimpleNamespace(published=[], publish=lambda m: n.zero_pub.published.append(m))
        n.submitted = []
        n.worker = types.SimpleNamespace(submit=lambda f, *a: n.submitted.append((f, a)))
        return n

    def at(self, t):
        return mock.patch.object(M.time, "monotonic", return_value=t)

    def test_never_received_blocks(self):
        with self.at(100.0), self.assertRaisesRegex(RuntimeError, "camera obstacles OFF.*never received"):
            self.node(None).require_camera_obstacles()

    def test_stale_blocks_fresh_allows(self):
        with self.at(100.0):
            with self.assertRaisesRegex(RuntimeError, "last 3.0s ago"):
                self.node(97.0).require_camera_obstacles()
            self.node(99.0).require_camera_obstacles()          # 1.0 s old: allowed

    def test_disabled_never_blocks(self):
        with self.at(100.0):
            self.node(None, enabled=False).require_camera_obstacles()

    def test_watchdog_stops_active_goal_once(self):
        n = self.node(95.0, active=1)
        with self.at(100.0):
            n.camera_obstacle_watchdog(); n.camera_obstacle_watchdog()
        self.assertEqual(len(n.submitted), 1)                   # one cancel request, not repeated
        self.assertEqual(n.submitted[0][0].__name__, "stop_for_camera_loss")
        self.assertEqual(len(n.zero_pub.published), 1)          # immediate zero command

    def test_watchdog_idle_without_goal_or_with_fresh_camera(self):
        idle = self.node(None, active=0)
        fresh = self.node(99.5, active=1)
        with self.at(100.0):
            idle.camera_obstacle_watchdog(); fresh.camera_obstacle_watchdog()
        self.assertEqual(idle.submitted + fresh.submitted, [])

    def test_every_saved_map_dispatch_checks_the_camera(self):
        import inspect
        for fn in (M.AtlasMissionControl.dispatch_pose_goal, M.AtlasMissionControl.dispatch_route_goal,
                   M.AtlasMissionControl.return_home, M.AtlasMissionControl.verify_home_after_settle):
            with self.subTest(fn=fn.__name__):
                self.assertIn("require_camera_obstacles()", inspect.getsource(fn))


if __name__ == "__main__":
    unittest.main()

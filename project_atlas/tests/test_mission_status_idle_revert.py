"""2026-11-14: a finished/failed mission status returns to READY once mission control is idle (needs ROS to import)."""
import sys
import types
import unittest
from pathlib import Path
from threading import Lock
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import atlas_mission_control as M
except Exception as exc:  # pragma: no cover - ROS not available
    M = None
    IMPORT_ERROR = exc


@unittest.skipIf(M is None, "atlas_mission_control needs ROS 2")
class IdleRevert(unittest.TestCase):
    def node(self, text, age_s, session=None, explore_active=False):
        n = object.__new__(M.AtlasMissionControl)
        n.current_status = text
        n.current_status_since = 1000.0 - age_s
        n.operation_lock = Lock()
        n.explore_unit = "atlas-explore.service"
        n.active_mapping_session = lambda: session
        n.statuses = []
        n.status = lambda t: (n.statuses.append(t), setattr(n, "current_status", t))
        n.get_logger = lambda: types.SimpleNamespace(info=lambda *_: None)
        self.explore_rc = 0 if explore_active else 3
        return n

    def run_revert(self, n):
        with mock.patch.object(M.time, "monotonic", return_value=1000.0), \
                mock.patch.object(M.subprocess, "run", return_value=types.SimpleNamespace(returncode=self.explore_rc)):
            n.revert_idle_status_to_ready()
        return n.current_status

    def test_error_reverts_after_hold(self):
        self.assertEqual(self.run_revert(self.node("ERROR stop exploration: rejected", 130)), "READY")

    def test_error_kept_during_hold(self):
        self.assertTrue(self.run_revert(self.node("ERROR stop exploration: rejected", 60)).startswith("ERROR"))

    def test_finished_result_reverts_after_60s(self):
        self.assertEqual(self.run_revert(self.node("PLACE SAVED name=hall frame=map x=1 y=2", 61)), "READY")

    def test_in_progress_never_reverts(self):
        for text in ("NAMED GOAL ACCEPTED name=hall", "RETURN HOME ACCEPTED", "QUEUED stop exploration",
                     "MANUAL MAPPING FINISHING: starting Nav2", "TAUGHT ROUTE DISPATCHED name=x waypoints=3",
                     "EXPLORATION ACTIVE", "something new"):
            self.assertEqual(self.run_revert(self.node(text, 10000)), text)

    def test_not_while_operation_running(self):
        n = self.node("ERROR x", 500)
        n.operation_lock.acquire()
        self.assertEqual(self.run_revert(n), "ERROR x")

    def test_not_during_mapping_session_or_exploration(self):
        self.assertEqual(self.run_revert(self.node("ERROR x", 500, session={"state": "active"})), "ERROR x")
        self.assertEqual(self.run_revert(self.node("ERROR x", 500, explore_active=True)), "ERROR x")


if __name__ == "__main__":
    unittest.main()

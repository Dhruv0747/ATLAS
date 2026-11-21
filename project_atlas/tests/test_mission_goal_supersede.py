"""2026-11-19: a pre-empted (superseded) Nav2 goal must not report FINISHED over the live goal (needs ROS to import).

penalty_test_20261116: "NAMED GOAL FINISHED name=dhruv room test 3 status=6" was published 2 s after the next goal was
dispatched; the narrator said the path failed, the status reverted to READY mid-drive and the camera tracker restarted.
"""
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

NS = types.SimpleNamespace


def done(value):
    return NS(result=lambda: value)


@unittest.skipIf(M is None, "atlas_mission_control needs ROS 2")
class Supersede(unittest.TestCase):
    def node(self):
        n = object.__new__(M.AtlasMissionControl)
        n.statuses, n.logs, n.tracker_restores = [], [], 0
        n.autonomy_goals_active = 0
        n.current_status = "READY"
        n.status = lambda t: (n.statuses.append(t), setattr(n, "current_status", t))
        n.get_logger = lambda: NS(info=lambda m: n.logs.append(m), warn=lambda m: n.logs.append(m))
        def restore():
            n.tracker_restores += 1
        n.restore_goal_tracker = restore
        n.error = lambda what, exc: n.statuses.append(f"ERROR {what}: {exc}")
        return n

    def accept(self, n, label, gen):
        callbacks = []
        handle = NS(accepted=True, get_result_async=lambda: NS(add_done_callback=callbacks.append))
        n.named_goal_response(done(handle), label, gen)
        return callbacks[0]

    def test_old_goal_result_after_new_dispatch_is_logged_only(self):
        n = self.node()
        g1 = n.next_goal_generation()
        finish_old = self.accept(n, "dhruv room test 3", g1)
        g2 = n.next_goal_generation()                      # the owner presses Go again: Nav2 pre-empts g1
        finish_new = self.accept(n, "dhruv room", g2)
        self.assertEqual(n.autonomy_goals_active, 2)
        finish_old(done(NS(status=6)))
        self.assertEqual(n.current_status, "NAMED GOAL ACCEPTED name=dhruv room")
        self.assertFalse(any("FINISHED" in s for s in n.statuses))
        self.assertEqual(n.tracker_restores, 0)
        self.assertTrue(any("superseded" in m for m in n.logs))
        self.assertEqual(n.autonomy_goals_active, 1)
        finish_new(done(NS(status=4)))
        self.assertEqual(n.current_status, "NAMED GOAL FINISHED name=dhruv room status=4")
        self.assertEqual(n.tracker_restores, 1)
        self.assertEqual(n.autonomy_goals_active, 0)

    def test_single_goal_unchanged(self):
        n = self.node()
        finish = self.accept(n, "hall", n.next_goal_generation())
        finish(done(NS(status=6)))
        self.assertEqual(n.current_status, "NAMED GOAL FINISHED name=hall status=6")
        self.assertEqual(n.tracker_restores, 1)

    def test_superseded_home_goal_does_not_verify_or_report(self):
        n = self.node()
        n.worker = NS(submit=lambda *a: n.statuses.append("VERIFY"))
        g1 = n.next_goal_generation()
        n.next_goal_generation()
        n.autonomy_goals_active = 1
        n.home_goal_result(done(NS(status=4)), {"x": 0}, 0, g1)
        self.assertEqual(n.statuses, [])
        self.assertEqual(n.autonomy_goals_active, 0)

    def test_status_never_reverts_to_ready_while_a_goal_drives(self):
        n = self.node()
        n.current_status, n.current_status_since = "NAMED GOAL FINISHED name=x status=6", 0.0
        n.operation_lock = Lock()
        n.autonomy_goals_active = 1
        with mock.patch.object(M.time, "monotonic", return_value=1000.0):
            n.revert_idle_status_to_ready()
        self.assertEqual(n.current_status, "NAMED GOAL FINISHED name=x status=6")


if __name__ == "__main__":
    unittest.main()

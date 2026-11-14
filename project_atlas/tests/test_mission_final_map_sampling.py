"""2026-11-14: mission control samples scans for final-map consistency only when enabled (needs ROS).

Remap 12 collected 0 samples: under the batched executor the scan arrives before odom->base_link for its stamp, so
an immediate lookup always failed. FakeTf below reproduces that (data arrives LATE_S after the scan).
"""
import sys
import types
import unittest
from collections import deque
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import atlas_mission_control as M
except Exception:  # pragma: no cover - ROS not available
    M = None

LATE_S = 0.2


def scan(t):
    return types.SimpleNamespace(header=types.SimpleNamespace(stamp=types.SimpleNamespace(sec=int(t), nanosec=int(round((t % 1) * 1e9)))),
                                 ranges=[1.0] * 10, angle_min=0.0, angle_increment=0.1)


class FakeTf:
    """TF for a stamp exists only LATE_S after that stamp (clock = self.now)."""

    def __init__(self, never=False):
        self.now, self.calls, self.never = 0.0, 0, never

    def lookup_transform(self, _target, _source, stamp, **_k):
        self.calls += 1
        t = stamp.sec + stamp.nanosec * 1e-9
        if self.never or self.now < t + LATE_S:
            raise RuntimeError("Lookup would require extrapolation into the future")
        return types.SimpleNamespace(transform=types.SimpleNamespace(
            translation=types.SimpleNamespace(x=1.0, y=2.0, z=0.0),
            rotation=types.SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)))


@unittest.skipIf(M is None, "atlas_mission_control needs ROS 2")
class Sampling(unittest.TestCase):
    def node(self, enabled, never=False):
        n = object.__new__(M.AtlasMissionControl)
        n.final_map_mode = enabled
        n.final_map_samples = M.final_map.ScanSampleBuffer()
        n.final_map_pending = deque()
        n.tf_buffer = FakeTf(never)
        return n

    def drive(self, n, seconds, hz=8):
        """Scans at hz; the resolve timer at 4 Hz; ROS time == monotonic time."""
        steps = int(seconds * 40)
        for k in range(steps + 1):
            t = k / 40.0
            n.tf_buffer.now = t
            with mock.patch.object(M.time, "monotonic", return_value=t):
                if k % int(40 / hz) == 0:
                    n.update_latest_scan(scan(t))
                if k % 10 == 0:
                    n.resolve_final_map_samples()

    def test_disabled_collects_nothing(self):
        n = self.node(False)
        n.final_map_samples.begin("s")
        self.drive(n, 5)
        self.assertEqual(n.final_map_samples.samples, [])
        self.assertEqual(n.tf_buffer.calls, 0)

    def test_late_tf_still_gives_two_samples_per_second(self):
        n = self.node(True)
        n.final_map_samples.begin("s")
        self.drive(n, 10)
        got = len(n.final_map_samples.samples)
        self.assertGreaterEqual(got, 19)          # 20 queued in 10 s; the last may still be waiting
        self.assertEqual(n.final_map_samples.lookup_failures, 0)
        self.assertEqual(n.final_map_samples.samples[0].pose, (1.0, 2.0, 0.0))

    def test_tf_never_available_is_counted_not_silent(self):
        n = self.node(True, never=True)
        n.final_map_samples.begin("s")
        self.drive(n, 10)
        self.assertEqual(n.final_map_samples.samples, [])
        self.assertGreater(n.final_map_samples.lookup_failures, 10)
        self.assertIn("extrapolation", n.final_map_samples.first_lookup_error)

    def test_no_session_no_samples(self):
        n = self.node(True)
        self.drive(n, 3)
        self.assertEqual(n.final_map_samples.samples, [])

    def test_evidence_fails_closed_for_other_session_and_reports_lookup_failures(self):
        n = self.node(True)
        n.final_map_samples.begin("old")
        n.final_map_samples.note_lookup_failure("X")
        ev = n.final_map_consistency_evidence(Path("x.yaml"), Path("x.pgm"), {"id": "new"})
        self.assertFalse(ev["passed"])
        self.assertEqual(ev["lookup_failures"], 1)
        self.assertIsNone(n.final_map_samples.session_id)

    def test_tf_listener_has_its_own_executor_thread(self):
        """Remap 12: the TF listener must not share the batched executor (one message per topic per 50 ms)."""
        import inspect
        src = inspect.getsource(M.AtlasMissionControl.__init__)
        self.assertIn("TransformListener(self.tf_buffer, self.tf_node)", src)
        self.assertIn("self.tf_thread.start()", src)

    def test_default_parameter_is_off(self):
        import inspect
        self.assertIn('"map_acceptance_final_map_mode", False', inspect.getsource(M.AtlasMissionControl.__init__))


if __name__ == "__main__":
    unittest.main()

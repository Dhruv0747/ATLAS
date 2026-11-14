"""2026-11-14 PROPOSAL: mission control samples scans for final-map consistency only when enabled (needs ROS)."""
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import atlas_mission_control as M
except Exception:  # pragma: no cover - ROS not available
    M = None


def scan(t):
    return types.SimpleNamespace(header=types.SimpleNamespace(stamp=types.SimpleNamespace(sec=int(t), nanosec=int((t % 1) * 1e9))),
                                 ranges=[1.0] * 10, angle_min=0.0, angle_increment=0.1)


class FakeTf:
    def __init__(self):
        self.calls = 0

    def lookup_transform(self, *_a, **_k):
        self.calls += 1
        return types.SimpleNamespace(transform=types.SimpleNamespace(
            translation=types.SimpleNamespace(x=1.0, y=2.0, z=0.0),
            rotation=types.SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)))


@unittest.skipIf(M is None, "atlas_mission_control needs ROS 2")
class Sampling(unittest.TestCase):
    def node(self, enabled):
        n = object.__new__(M.AtlasMissionControl)
        n.final_map_mode = enabled
        n.final_map_samples = M.final_map.ScanSampleBuffer()
        n.tf_buffer = FakeTf()
        return n

    def test_disabled_collects_nothing(self):
        n = self.node(False)
        n.final_map_samples.begin("s")
        for k in range(40):
            n.update_latest_scan(scan(k * 0.125))
        self.assertEqual(n.final_map_samples.samples, [])
        self.assertEqual(n.tf_buffer.calls, 0)

    def test_enabled_samples_two_per_second_without_extra_tf_lookups(self):
        n = self.node(True)
        n.final_map_samples.begin("s")
        for k in range(80):                      # 10 s of 8 Hz scans
            n.update_latest_scan(scan(k * 0.125))
        self.assertEqual(len(n.final_map_samples.samples), 20)
        self.assertEqual(n.tf_buffer.calls, 20)
        self.assertEqual(n.final_map_samples.samples[0].pose, (1.0, 2.0, 0.0))

    def test_no_session_no_samples(self):
        n = self.node(True)
        n.update_latest_scan(scan(1.0))
        self.assertEqual(n.final_map_samples.samples, [])

    def test_evidence_fails_closed_for_other_session(self):
        n = self.node(True)
        n.final_map_samples.begin("old")
        ev = n.final_map_consistency_evidence(Path("x.yaml"), Path("x.pgm"), {"id": "new"})
        self.assertFalse(ev["passed"])
        self.assertIsNone(n.final_map_samples.session_id)   # sampling stops at evaluation

    def test_default_parameter_is_off(self):
        import inspect
        self.assertIn('"map_acceptance_final_map_mode", False', inspect.getsource(M.AtlasMissionControl.__init__))


if __name__ == "__main__":
    unittest.main()

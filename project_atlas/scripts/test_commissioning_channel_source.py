#!/usr/bin/env python3

from pathlib import Path
import unittest


class CommissioningChannelSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = Path(__file__).resolve().parent
        cls.mux = (directory / "atlas_cmd_vel_mux.py").read_text(encoding="utf-8")
        cls.test = (directory / "atlas_straight_distance_test.py").read_text(
            encoding="utf-8"
        )

    def test_channel_is_bounded_and_remote_has_priority(self):
        self.assertIn('"REMOTE", "/cmd_vel_joy", 1', self.mux)
        self.assertIn('"COMMISSION", "/cmd_vel_commission", 2', self.mux)
        self.assertIn("self.commission_until = now + 20.0", self.mux)
        self.assertIn("commissioning lease expired", self.mux)
        self.assertIn("max(-0.12, min(0.12, command.linear.x))", self.mux)

    def test_distance_tool_arms_and_disarms_channel(self):
        self.assertIn('"/atlas/commission/arm"', self.test)
        self.assertIn('"/atlas/commission/disarm"', self.test)
        self.assertIn('"/cmd_vel_commission"', self.test)
        self.assertIn("node.disarm()", self.test)
        self.assertIn("if not self.armed:", self.test)
        self.assertIn(
            "any(value is None for value in self.encoder_counts)", self.test
        )

    def test_every_safety_intervention_revokes_the_lease(self):
        self.assertIn("self.commission_until = 0.0", self.mux)
        self.assertIn("def revoke_commission", self.mux)
        self.assertIn("COMMISSION ABORT: stale", self.mux)
        self.assertIn("COMMISSION ABORT: ENCODER", self.mux)
        self.assertIn("COMMISSION ABORT: {blocked_reason}", self.mux)


if __name__ == "__main__":
    unittest.main()

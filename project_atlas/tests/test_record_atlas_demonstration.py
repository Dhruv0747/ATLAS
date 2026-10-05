from pathlib import Path
import unittest


class DemonstrationRecorderContractTests(unittest.TestCase):
    def test_navigation_failure_evidence_is_recorded(self):
        script = (
            Path(__file__).parents[1]
            / "scripts"
            / "record_atlas_demonstration.sh"
        ).read_text(encoding="utf-8")
        required_topics = {
            "/scan",
            "/scan_raw",
            "/imu/data",
            "/odom",
            "/yahboom/odom",
            "/tf",
            "/cmd_vel",
            "/cmd_vel_nav",
            "/cmd_vel_commission",
            "/cmd_vel_recovery",
            "/atlas/encoder_health",
            "/atlas/control_policy",
            "/atlas/mode",
            "/atlas/mission_status",
            "/im10a/imu/bias_corrected_candidate",
        }
        for topic in required_topics:
            with self.subTest(topic=topic):
                self.assertIn(topic, script)


if __name__ == "__main__":
    unittest.main()

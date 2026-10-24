from pathlib import Path
import unittest


class SchedulingScopeTests(unittest.TestCase):
    def test_isolated_bounded_pc_only(self):
        source = (Path(__file__).parents[1]/'tools/diagnostics/benchmark_startup_scheduling_pc.py').read_text()
        for token in ('PrivateNetwork=yes', 'RuntimeMaxSec=30', 'KillMode=control-group',
                      "platform.machine() != 'x86_64'", 'ROS_LOCALHOST_ONLY=1',
                      'ROS_DOMAIN_ID=214', 'CPUQuota=60%', 'Nice=10'):
            self.assertIn(token, source)
        self.assertNotIn('ssh', source)
        self.assertNotIn("'restart'", source)

    def test_four_cases_no_production_endpoint(self):
        source = (Path(__file__).parents[1]/'tools/diagnostics/benchmark_startup_scheduling_pc.py').read_text()
        for case in ("('baseline',False,False)", "('quota',True,False)",
                     "('udp',False,True)", "('quota_udp',True,True)"):
            self.assertIn(case, source)
        self.assertNotIn('192.168.', source)


if __name__ == '__main__': unittest.main()

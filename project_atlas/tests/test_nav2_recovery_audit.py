"""Step 5 Nav2 recovery budget audit (tools/nav/nav2_recovery_audit.py): pure checks on file texts. 2026-11-23."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'nav'))
import nav2_recovery_audit as a  # noqa: E402

NAV2 = """bt_navigator:
  ros__parameters:
    default_nav_to_pose_bt_xml: "/x/pose.xml"
controller_server:
  ros__parameters:
    progress_checker:
      required_movement_radius: 0.10
      movement_time_allowance: 45.0
"""
MUX = 'self.declare_parameter("watchdog_period", 0.05)\nself.declare_parameter("manual_timeout", 0.35)\n' \
      'self.declare_parameter("nav_timeout", 0.50)\n'
MISSION = 'self.declare_parameter("home_max_retries", 1)\n'
RUNNER = 'RETRY_GAP_S = 8.0\nMAX_ATTEMPTS_PER_PLACE = 25\n'


def bt(inner='', retries='6'):
    return ('<root><BehaviorTree ID="M"><RecoveryNode number_of_retries="%s" name="N"><Sequence/>'
            '<RoundRobin><BackUp backup_dist="0.18" backup_speed="0.12" time_allowance="5.0"/><Wait wait_duration="2"/>'
            '%s</RoundRobin></RecoveryNode></BehaviorTree></root>' % (retries, inner))


class AuditTests(unittest.TestCase):
    def ev(self, bts=None, nav2=NAV2, mux=MUX, mux_exec='', mission=MISSION, mission_exec='', runner=RUNNER):
        return a.evaluate(nav2, bts if bts is not None else {'/x/pose.xml': bt()}, mux, mux_exec, mission,
                          mission_exec, runner)

    def test_repo_files_pass(self):
        # the repo's own behaviour tree, mux, mission control and runner (the live rover Nav2 params use 45 s)
        txt = lambda p: (ROOT / p).read_text(encoding='utf-8')
        r = a.evaluate(NAV2, {'pose': txt('config/atlas_ackermann_fail_stop.xml'),
                              'poses': txt('config/atlas_ackermann_through_poses.xml')},
                       txt('scripts/atlas_cmd_vel_mux.py'), '', txt('scripts/atlas_mission_control.py'), '',
                       txt('scripts/atlas_stage3_runner.py'))
        self.assertEqual(r['verdict'], 'PASS', (r['failed'], r['notes']))
        self.assertEqual(r['measured']['bt_outer_retries'], [6, 6])
        self.assertEqual(r['measured']['worst_case_goal_retry_s'], 679)

    def test_runner_without_budget_fails(self):            # the live runner before 2026-11-23
        self.assertIn('runner_retry_budget', self.ev(runner='RETRY_GAP_S = 8.0\n')['failed'])

    def test_unbounded_or_spinning_trees_fail(self):
        self.assertIn('bt_retries_bounded', self.ev({'p': bt(retries='-1')})['failed'])
        self.assertIn('bt_retries_bounded', self.ev({'p': bt('<KeepRunningUntilFailure><Wait/></KeepRunningUntilFailure>')})['failed'])
        self.assertIn('bt_retries_bounded', self.ev({'p': bt('<Repeat num_cycles="-1"><Wait/></Repeat>')})['failed'])
        self.assertIn('bt_no_spin', self.ev({'p': bt('<Spin spin_dist="1.57"/>')})['failed'])
        self.assertIn('backup_bounded', self.ev({'p': bt('<BackUp backup_dist="1.0" time_allowance="5"/>')})['failed'])
        self.assertIn('bt_files_found', self.ev({'p': None})['failed'])
        self.assertIn('bt_files_found', self.ev({})['failed'])

    def test_stale_twist_and_stuck_detection(self):
        self.assertIn('stale_twist_cut', self.ev(mux=MUX.replace('0.50', '2.0'))['failed'])
        self.assertIn('stale_twist_cut', self.ev(mux_exec="ExecStart=x --ros-args -p nav_timeout:=3.0")['failed'])
        self.assertIn('stuck_detection', self.ev(nav2=NAV2.replace('45.0', '0.0'))['failed'])
        self.assertIn('stuck_detection', self.ev(nav2=NAV2.replace('45.0', '300.0'))['failed'])

    def test_service_override_wins_over_code_default(self):
        r = self.ev(mission_exec='ExecStart=x --ros-args -p home_max_retries:=9')
        self.assertEqual(r['measured']['mission_home_max_retries'], 9.0)
        self.assertIn('mission_home_retries', r['failed'])

    def test_yaml_value(self):
        self.assertEqual(a.yaml_value(NAV2, 'default_nav_to_pose_bt_xml'), '/x/pose.xml')


if __name__ == '__main__':
    unittest.main()

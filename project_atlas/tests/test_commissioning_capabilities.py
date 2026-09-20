"""Offline only. No motor/ROS imports and no hardware I/O."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from atlas_capabilities import load_registry, report
from atlas_commissioning import Console


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry(ROOT)
        self.data = {}
        self.records = []
        self.enc = {'state': 'DEGRADED', 'packet_fresh': True, 'packet_age_s': .01,
                    'selected_encoders': [1, 2, 3], 'excluded_encoders': [4],
                    'faults': [], 'traction': False, 'last_change_age_s': [999] * 4,
                    'navigation_validated': False, 'autonomy_ready': False}
        self.set_value('encoder_health', self.enc)
        for i in range(1, 5):
            self.set_value('enc_m' + str(i), 100)
        self.set_value('odom', {'x': 0, 'y': 0, 'vx': 0, 'wz': 0})

    def set_value(self, key, value, age=.01):
        self.data[key] = {'value': value, 'age': age}

    def result(self, goal='NAVIGATE_ROOM'):
        return report(self.registry, self.records, self.data, goal)

    def sensor(self, name):
        return next(s for s in self.result()['sensors'] if s['id'] == name)

    def test_stationary_constant_counts_not_failed(self):
        for name in ('m1', 'm2', 'm3'):
            self.assertEqual(self.sensor(name)['health'], 'DATA_PRESENT')
        self.assertEqual(self.sensor('m4')['health'], 'EXCLUDED')
        self.assertFalse(self.result()['motion_authorized'])

    def test_stale_shared_link_blocks_all_selected(self):
        self.data['encoder_health']['age'] = 1.1
        for name in ('m1', 'm2', 'm3', 'wheel_odom'):
            self.assertEqual(self.sensor(name)['health'], 'INVALID')

    def test_fresh_status_cannot_hide_stale_packet(self):
        self.enc['packet_age_s'] = 10
        self.assertEqual(self.sensor('wheel_odom')['health'], 'INVALID')

    def test_selected_failure_does_not_select_two_encoder_fallback(self):
        self.enc['faults'] = ['M2_REAR_RIGHT']
        self.enc['state'] = 'CRITICAL'
        self.assertEqual(self.sensor('m2')['health'], 'FAULT_REPORTED')
        self.assertEqual(self.sensor('m1')['health'], 'DATA_PRESENT')
        self.assertEqual(self.sensor('wheel_odom')['health'], 'DEGRADED')
        self.assertIsNone(self.result()['active_profile'])
        self.assertFalse(self.result()['resume_authorized'])

    def test_unknown_fault_not_silently_ignored(self):
        self.enc['faults'] = ['unclassified channel error']
        self.assertEqual(self.sensor('m1')['health'], 'INVALID')

    def test_one_remaining_channel_no_fallback(self):
        self.enc['selected_encoders'] = [1]
        self.enc['excluded_encoders'] = [2, 3, 4]
        self.assertEqual(self.sensor('m1')['health'], 'INVALID')
        self.assertEqual(self.result()['approved_profiles'], [])

    def test_nan_negative_and_missing_ages(self):
        for age in (float('nan'), float('inf'), -1, None, '0'):
            self.data['enc_m1']['age'] = age
            self.assertEqual(self.sensor('m1')['health'], 'STALE_OR_MISSING')
            self.assertIsNone(self.sensor('m1')['age_s'])
            json.dumps(self.result(), allow_nan=False)

    def test_nan_counts_rejected(self):
        self.set_value('enc_m1', float('nan'))
        self.assertEqual(self.sensor('m1')['health'], 'INVALID')

    def test_camera_does_not_become_vo(self):
        self.set_value('camera_info', {'bytes': 1234})
        self.assertEqual(self.sensor('camera')['health'], 'DATA_PRESENT')
        self.assertEqual(self.sensor('camera_vo')['health'], 'NOT_AVAILABLE')
        motion = next(c for c in self.result()['capabilities'] if c['capability'] == 'MOTION_ESTIMATION')
        self.assertNotIn('camera', motion['configured_sources'])
        self.assertFalse(self.result()['motion_authorized'])

    def test_goals_do_not_all_require_encoders(self):
        self.set_value('camera_info', {'bytes': 1234})
        self.data['encoder_health']['age'] = 10
        image = self.result('STATIONARY_IMAGE')
        self.assertEqual([c['capability'] for c in image['capabilities']], ['VISUAL_OBSERVATION'])
        self.assertEqual(image['capabilities'][0]['observed_sources'], ['camera'])
        self.assertFalse(image['motion_authorized'])

    def test_unknown_goal_fail_closed(self):
        self.assertEqual(self.result('invented')['decision'], 'UNKNOWN_GOAL_TYPE')

    def test_missing_or_stub_ultrasonic_status_cannot_mean_clear(self):
        self.set_value('us_front', 4000)
        self.assertEqual(self.sensor('ultrasonic_front')['health'], 'INVALID')
        self.set_value('us_status', 'STUB,front=4000')
        self.assertEqual(self.sensor('ultrasonic_front')['health'], 'INVALID')

    def test_disabled_and_invalid_echoes(self):
        self.set_value('us_status', 'USTAT,F=ONLINE,L=DISABLED,R=DISABLED,B=ONLINE')
        self.set_value('us_left', 1500)
        self.assertEqual(self.sensor('ultrasonic_left')['health'], 'DISABLED')
        for value in (-1, 0, 10000, float('inf'), float('nan')):
            self.set_value('us_front', value)
            self.assertEqual(self.sensor('ultrasonic_front')['health'], 'INVALID')

    def test_positive_echo_still_not_qualified_safety(self):
        self.set_value('us_status', 'USTAT,F=ONLINE,L=DISABLED,R=DISABLED,B=ONLINE')
        self.set_value('us_front', 500)
        s = self.sensor('ultrasonic_front')
        self.assertEqual(s['health'], 'DATA_PRESENT')
        self.assertEqual(s['validation'], 'NOT_VALIDATED')
        self.assertFalse(s['motion_authority_granted'])

    def test_imu_not_promoted_from_live_gyro(self):
        self.set_value('imu_full', dict.fromkeys(('gx', 'gy', 'gz', 'ax', 'ay', 'az'), 0.0))
        self.assertEqual(self.sensor('im10a')['health'], 'DATA_PRESENT')
        heading = next(c for c in self.result()['capabilities'] if c['capability'] == 'HEADING')
        self.assertNotIn('im10a', heading['configured_sources'])

    def test_gps_fix_and_internal_sentence_age(self):
        d = {'transport_open': True, 'fix_valid': False, 'gga_age_s': 0, 'nmea_age_s': 0}
        self.set_value('gps_diagnostics', json.dumps(d))
        self.assertEqual(self.sensor('gps')['health'], 'NO_FIX')
        d.update(fix_valid=True, gga_age_s=9)
        self.set_value('gps_diagnostics', d)
        self.assertEqual(self.sensor('gps')['health'], 'INVALID')

    def test_pass_retained_but_not_autonomy_authority(self):
        self.records = [{'gate': 'encoder_metric', 'status': 'PASS'}]
        self.assertEqual(self.sensor('m1')['validation'], 'PASS_FOR_RECORDED_SCOPE_ONLY')
        self.records[0]['status'] = 'RETEST_REQUIRED'
        self.assertEqual(self.sensor('m1')['validation'], 'NOT_VALIDATED')
        self.assertEqual(self.result()['max_speed_authorized_mps'], 0)

    def test_stop_unknown_or_latched_not_ignored(self):
        self.set_value('control_policy', {'manual_only': False, 'stop_latched': True})
        self.assertIn('Emergency/remote stop latched or unknown', self.result()['runtime_restrictions'])
        self.set_value('control_policy', {})
        self.assertIn('Emergency/remote stop latched or unknown', self.result()['runtime_restrictions'])

    def test_goal_display_does_not_claim_goal_preservation_or_resume(self):
        self.set_value('agent_state', {'live': {'autonomy': {'goal': 'Hall'}, 'autonomy_age_s': .1}})
        self.assertEqual(self.result()['current_goal_report'], 'Hall')
        self.data['agent_state']['age'] = 3
        self.assertIn('UNKNOWN', self.result()['current_goal_report'])
        self.assertIn('not implemented', self.result()['goal_retention'])

    def test_fresh_agent_does_not_hide_stale_goal_source(self):
        self.set_value('agent_state', {'live': {'autonomy': {'goal': 'Hall'}, 'autonomy_age_s': 50}})
        self.assertIn('UNKNOWN', self.result()['current_goal_report'])

    def test_near_field_components_do_not_imply_full_clearance(self):
        self.set_value('us_status', 'USTAT,F=ONLINE,L=DISABLED,R=DISABLED,B=ONLINE')
        self.set_value('us_front', 500)
        c = next(c for c in self.result()['capabilities'] if c['capability'] == 'NEAR_FIELD_PROTECTION')
        self.assertEqual(c['observed_sources'], ['ultrasonic_front'])
        self.assertEqual(c['validated_providers'], [])
        self.assertIn('not full-body clearance', c['reason'])

    def test_registry_cannot_enable_profiles(self):
        registry = copy.deepcopy(self.registry)
        registry['approved_profiles'] = ['unsafe']
        with self.assertRaises(ValueError):
            report(registry, [], {})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config'
            path.mkdir()
            (path / 'capability_registry.json').write_text(json.dumps(registry))
            with self.assertRaises(ValueError):
                load_registry(folder)

    def test_report_does_not_mutate_inputs(self):
        before = copy.deepcopy((self.data, self.records, self.registry))
        self.result()
        self.assertEqual(before, (self.data, self.records, self.registry))

    def test_missing_data_never_grants_authority(self):
        self.data = {}
        r = self.result()
        self.assertFalse(r['motion_authorized'])
        self.assertFalse(r['resume_authorized'])
        self.assertTrue(all(not c['validated_providers'] for c in r['capabilities']))

    def test_missing_registry_preserves_existing_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scripts').mkdir()
            (root / 'scripts/yahboom_base.py').write_text('FRONT_STEER_CENTER=90\n')
            console = Console(root, root / 'results.sqlite3', lambda: {})
            result = console.evidence()
            self.assertEqual(result['readiness']['state'], 'AUTONOMY BLOCKED')
            self.assertEqual(result['readiness']['next_required_step'], 'steering_front')
            self.assertIn('error', result['capabilities'])
            self.assertFalse(result['capabilities']['motion_authorized'])


if __name__ == '__main__':
    unittest.main()

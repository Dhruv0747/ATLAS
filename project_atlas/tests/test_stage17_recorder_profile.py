import sys
import subprocess
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from atlas_motion_recorder import REQUIRED, TOPICS, recording_profile, steering_changed, topic_health
from atlas_motion_recorder_core import RecorderEngine, Sample


class Stage17RecorderTests(unittest.TestCase):
    def test_default_and_stage17_evidence(self):
        self.assertEqual(recording_profile('default'), (TOPICS, REQUIRED, 10))
        topics, required, post = recording_profile('steering-validation')
        self.assertEqual(post, 20)
        for topic in ('/atlas/encoder_update', '/im10a/imu/unvalidated', '/particle_cloud',
                      '/steering/front_angle_deg', '/steering/rear_angle_deg', '/lidar/odom'):
            self.assertIn(topic, topics)
            self.assertIn(topic, required)
        self.assertEqual(len(topics), len(set(topics)))

    def test_stationary_sweep_captures_without_velocity(self):
        class Sink:
            budget_bytes = 10000
            samples = []
            def write(self, sample): self.samples.append(sample)
            def close(self, *args): pass
        sink = Sink()
        recorder = RecorderEngine(lambda: sink, post_s=20)
        for t in range(13):
            recorder.ingest(Sample('/steering/front_angle_deg', 'std_msgs/msg/Float32', b'angle', t, t*10**9))
        self.assertFalse(steering_changed(None, 90))
        self.assertFalse(steering_changed(90, 90.01))
        if steering_changed(90, 91):
            recorder.motion(12)  # Only recorder state is changed.
        self.assertEqual(sink.samples[0].monotonic_s, 2)
        recorder.tick(31)
        self.assertIsNotNone(recorder.sink)
        recorder.tick(32)
        self.assertIsNone(recorder.sink)

    def test_bms_cadence_and_missing_raw_gyro(self):
        recorder = RecorderEngine(lambda: None)
        recorder.last_seen = {'/bms/status': 1, '/scan': 5}
        result = topic_health(recorder, 6, ('/bms/status', '/scan', '/im10a/imu/unvalidated'))
        self.assertEqual(result['missing'], ['/im10a/imu/unvalidated'])
        self.assertEqual(result['stale'], [])
        self.assertEqual(topic_health(recorder, 14, ('/bms/status',))['stale'], ['/bms/status'])

    def test_invalid_steering_does_not_trigger(self):
        with self.assertRaises(ValueError):
            steering_changed(90, float('nan'))

    def test_retired_direct_serial_tool_refuses_actuation(self):
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'atlas_steering_calibrate.py'
        result = subprocess.run([sys.executable, str(script), 'front', '100'],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('No serial port opened', result.stderr)
        self.assertNotIn('Rosmaster_Lib', result.stderr)


if __name__ == '__main__':
    unittest.main()

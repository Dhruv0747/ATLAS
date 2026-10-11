"""Offline tests; no ROS runtime, actuators, or Jetson services required."""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from atlas_motion_recorder import TOPICS, RosbagSink, owned_bytes  # noqa: E402
from atlas_motion_recorder_core import RecorderEngine, Sample  # noqa: E402


class Sink:
    def __init__(self, budget_bytes=10000, fail=False):
        self.budget_bytes = budget_bytes
        self.samples = []
        self.closed = None
        self.fail = fail

    def write(self, sample):
        if self.fail:
            raise OSError('disk full')
        self.samples.append(sample)

    def close(self, reason, dropped, received):
        self.closed = (reason, dropped, received)


def sample(t, topic='/scan', payload=b'abc', ros_ns=None):
    return Sample(topic, 'sensor_msgs/msg/LaserScan', payload, t,
                  ros_ns if ros_ns is not None else int(t * 1e9))


class RecorderTests(unittest.TestCase):
    def test_preroll_motion_postroll_and_timestamp(self):
        sinks = []

        def factory():
            sink = Sink()
            sinks.append(sink)
            return sink

        r = RecorderEngine(factory)
        r.pin(sample(-30, '/tf_static', b'static', 123))
        for t in (0, 1, 5, 9, 10, 11):
            r.ingest(sample(t, ros_ns=int(t * 1e9) + 43))
        r.motion(11)
        self.assertEqual([s.monotonic_s for s in sinks[0].samples[1:]],
                         [1, 5, 9, 10, 11])
        self.assertEqual(sinks[0].samples[0].topic, '/tf_static')
        self.assertEqual(sinks[0].samples[0].ros_time_ns, int(1e9) + 43)
        r.ingest(sample(20))
        r.tick(20.9)
        self.assertIsNone(sinks[0].closed)
        r.tick(21)
        self.assertEqual(sinks[0].closed[0], 'stopped')

    def test_repeated_short_motion_merges_then_new_capture(self):
        sinks = []

        def factory():
            sink = Sink()
            sinks.append(sink)
            return sink

        r = RecorderEngine(factory)
        r.ingest(sample(1))
        r.motion(1)
        r.motion(8)
        r.tick(17)
        self.assertEqual(len(sinks), 1)
        r.tick(18)
        self.assertEqual(sinks[0].closed[0], 'stopped')
        r.ingest(sample(19))
        r.motion(19)
        self.assertEqual(len(sinks), 2)
        r.close()

    def test_missing_sensor_reports_without_stopping_capture(self):
        r = RecorderEngine(lambda: Sink())
        r.ingest(sample(1, '/scan'))
        r.motion(1)
        h = r.health(4, ('/scan', '/odom', '/imu/data'))
        self.assertEqual(h['missing'], ['/imu/data', '/odom'])
        self.assertEqual(h['stale'], ['/scan'])
        self.assertTrue(h['active'])
        r.close()

    def test_next_capture_keeps_ten_seconds_including_previous_postroll(self):
        sinks = []

        def factory():
            sinks.append(Sink())
            return sinks[-1]

        r = RecorderEngine(factory)
        for t in range(31):
            r.ingest(sample(t))
            if t in (10, 11, 25):
                r.motion(t)
            r.tick(t)
        self.assertEqual(len(sinks), 2)
        self.assertEqual(sinks[1].samples[0].monotonic_s, 15)
        self.assertEqual(len({s.monotonic_s for s in sinks[1].samples}),
                         len(sinks[1].samples))
        r.close()

    def test_write_error_fail_closed(self):
        r = RecorderEngine(lambda: Sink(fail=True))
        r.ingest(sample(0))
        r.motion(0)
        self.assertFalse(r.health(0, ())['active'])
        self.assertTrue(r.disabled_reason.startswith('write_error'))

    def test_open_error_and_idle_startup(self):
        def unavailable():
            raise OSError('quota exhausted')

        r = RecorderEngine(unavailable)
        r.ingest(sample(0))
        r.tick(30)
        self.assertFalse(r.health(30, ())['active'])
        r.motion(31)
        self.assertEqual(r.dropped['open_error'], 1)
        self.assertTrue(r.disabled_reason.startswith('open_error'))

    def test_capture_budget_and_old_evidence_preserved(self):
        r = RecorderEngine(lambda: Sink(budget_bytes=8), cap_bytes=100)
        r.ingest(sample(0, payload=b'1234'))
        r.motion(0)
        r.ingest(sample(1, payload=b'12345'))
        self.assertEqual(r.disabled_reason, 'capture_cap')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old = root / 'capture_old'
            old.mkdir()
            evidence = old / 'evidence.db3'
            evidence.write_bytes(b'old evidence')
            self.assertEqual(owned_bytes(root), len(b'old evidence'))
            self.assertEqual(evidence.read_bytes(), b'old evidence')

    def test_topics_reuse_validated_allowlist(self):
        demo = (SCRIPTS / 'record_atlas_demonstration.sh').read_text(encoding='utf-8')
        for topic in TOPICS:
            self.assertIn(topic, demo)
        for required in ('/scan', '/yahboom/odom', '/im10a/imu/bias_corrected_candidate',
                         '/amcl_pose', '/tf', '/cmd_vel_nav', '/atlas/control_policy'):
            self.assertIn(required, TOPICS)

    def test_bag_adapter_manifest_with_mock_writer(self):
        class FakeBag:
            def __init__(self):
                self.topics = []
                self.writes = []

            def open(self, storage, converter):
                Path(storage['uri']).mkdir()

            def create_topic(self, metadata):
                self.topics.append(metadata)

            def write(self, topic, payload, timestamp):
                self.writes.append((topic, payload, timestamp))

            def close(self):
                pass

        class FakeRosbag:
            def __init__(self):
                self.writer = FakeBag()

            def SequentialWriter(self):
                return self.writer

            @staticmethod
            def StorageOptions(**kwargs):
                return kwargs

            @staticmethod
            def ConverterOptions(*args):
                return args

            @staticmethod
            def TopicMetadata(**kwargs):
                return kwargs

        with tempfile.TemporaryDirectory() as td:
            mock = FakeRosbag()
            sink = RosbagSink(Path(td), 6 * 1024 * 1024, mock)
            sink.write(sample(3, ros_ns=123456789))
            sink.close('stopped', {'prebuffer_evicted': 2}, {'/scan': 3})
            self.assertEqual(mock.writer.writes[0], ('/scan', b'abc', 123456789))
            manifest = (sink.path / 'atlas_capture_manifest.json').read_text()
            self.assertIn('prebuffer_evicted', manifest)
            self.assertIn('unmeasured', manifest)


if __name__ == '__main__':
    unittest.main()

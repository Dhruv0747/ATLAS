import unittest
import ast
from pathlib import Path
from atlas_amcl_processing_health import ProcessingHealth


def event(seq, now, **changes):
    data = dict(schema=1,session='boot1',seq=seq,scan_stamp_ns=int(now*1e9),
        processed_stamp_ns=int(now*1e9),pose_seq=1,last_pose_stamp_ns=100000000000,
        filter_update_attempted=False,filter_update_succeeded=False,
        initial_pose_known=True,tf_available=True,valid_returns=100,scan_size=360)
    data.update(changes)
    return data


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.health = ProcessingHealth()

    def feed(self, seq, now, **kwargs):
        return self.health.ingest(event(seq,now,**kwargs),now,now)

    def test_fresh_processing_and_old_pose_are_distinct(self):
        self.feed(1,103); self.feed(2,103.1)
        s=self.health.snapshot(103.1,103.1)
        self.assertEqual(s['processing_state'],'PROCESSING')
        self.assertEqual(s['pose_publication_state'],'NO_RECENT_PUBLICATION')
        self.assertFalse(s['navigation_authorized'])

    def test_timer_cannot_refresh_source(self):
        self.feed(1,100); self.feed(2,100.1)
        for t in (101,102,103):
            self.assertEqual(self.health.snapshot(t,t)['processing_state'],'UNAVAILABLE')

    def test_repeated_scan_rejected_despite_fresh_processing_stamp(self):
        self.feed(1,100)
        self.assertFalse(self.feed(2,100.1,scan_stamp_ns=100000000000))

    def test_duplicate_sequence_rejected(self):
        self.feed(1,100)
        self.assertFalse(self.feed(1,100.1))

    def test_stale_and_future_scan(self):
        self.assertFalse(self.feed(1,100,scan_stamp_ns=99000000000))
        self.assertFalse(self.feed(1,100,scan_stamp_ns=101000000000))

    def test_failure_flags(self):
        for fields in (dict(tf_available=False),dict(initial_pose_known=False),
                       dict(valid_returns=0),dict(filter_update_attempted=True)):
            with self.subTest(fields=fields):
                self.assertFalse(self.feed(1,100,**fields))

    def test_restart_requires_warmup(self):
        self.feed(1,100); self.feed(2,100.1)
        self.feed(1,101,session='boot2')
        self.assertEqual(self.health.snapshot(101,101)['processing_state'],'WARMING_UP')

    def test_clock_reset_invalidates_snapshot(self):
        self.feed(1,100)
        self.assertEqual(self.health.snapshot(99,101)['processing_state'],'UNAVAILABLE')

    def test_frozen_ros_clock_still_expires_on_monotonic_clock(self):
        self.feed(1,100); self.feed(2,100.1)
        self.assertEqual(self.health.snapshot(100.1,101)['processing_state'],'UNAVAILABLE')

    def test_reporter_timer_uses_steady_clock(self):
        tree=ast.parse(Path(__file__).with_name('atlas_amcl_health_reporter.py').read_text())
        timers=[n for n in ast.walk(tree) if isinstance(n,ast.Call)
                and isinstance(n.func,ast.Attribute) and n.func.attr=='create_timer']
        self.assertEqual(len(timers),1)
        self.assertTrue(any(k.arg=='clock' for k in timers[0].keywords))
        self.assertIn('ClockType.STEADY_TIME',ast.unparse(tree))

    def test_cannot_relabel_old_pose_as_fresh(self):
        self.feed(1,100)
        self.assertFalse(self.feed(2,101,last_pose_stamp_ns=101000000000))

    def test_new_pose_publication_advances_separately(self):
        self.feed(1,100)
        self.feed(2,101,pose_seq=2,last_pose_stamp_ns=101000000000)
        s=self.health.snapshot(101,101)
        self.assertEqual(s['pose_publication_state'],'RECENT_PUBLICATION')
        self.assertEqual(s['position_validity'],'NOT_ESTABLISHED')

    def test_malformed_rejected(self):
        for data in (None,{},event(True,100),event(1,100,tf_available='yes')):
            self.assertFalse(self.health.ingest(data,100,100))


if __name__ == '__main__':
    unittest.main()

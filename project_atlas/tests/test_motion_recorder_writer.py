import sys
from pathlib import Path
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from atlas_motion_recorder_core import Sample, RecorderEngine
from atlas_motion_recorder_writer import QueuedWriter


class Sink:
    def __init__(self):
        self.samples = []
        self.closed = []

    def write(self, sample):
        self.samples.append(sample)

    def close(self, *args):
        self.closed.append(args)


class WriterTests(unittest.TestCase):
    def test_blocked_disk_does_not_block_caller_and_overflow_is_bounded(self):
        release, entered = threading.Event(), threading.Event()
        sink = Sink()
        def factory():
            entered.set()
            release.wait(3)
            return sink
        worker = QueuedWriter(factory, max_bytes=4)
        try:
            capture = worker.open_capture()
            self.assertTrue(entered.wait(1))
            capture.write(Sample('/x', 'T', b'1234', 1, 10))
            with self.assertRaises(BufferError):
                capture.write(Sample('/x', 'T', b'x', 2, 20))
            capture.close('done', {}, {})
            self.assertEqual(worker.health()['queue_bytes'], 4)
        finally:
            release.set()
            self.assertTrue(worker.shutdown())
        self.assertEqual(len(sink.samples), 1)
        self.assertEqual(sink.closed[0][1]['worker_queue_overflow'], 1)

    def test_order_bytes_timestamps_and_repeated_captures(self):
        sinks = []
        def factory():
            sink = Sink()
            sinks.append(sink)
            return sink
        worker = QueuedWriter(factory)
        samples = [Sample('/x', 'T', bytes([i]), i, i*123456789) for i in range(12)]
        for _ in range(2):
            capture = worker.open_capture()
            for sample in samples:
                capture.write(sample)
            capture.close('done', {}, {})
        self.assertTrue(worker.shutdown())
        self.assertEqual([s.samples for s in sinks], [samples, samples])
        self.assertEqual(worker.health()['counters']['written'], 24)

    def test_disk_failure_stops_only_recorder(self):
        class Broken(Sink):
            def write(self, sample):
                raise OSError('disk full')
        sink = Broken()
        worker = QueuedWriter(lambda: sink)
        capture = worker.open_capture()
        capture.write(Sample('/x', 'T', b'x', 0, 0))
        self.assertTrue(worker.wait_idle())
        self.assertIn('disk full', worker.error)
        with self.assertRaises(RuntimeError):
            capture.write(Sample('/x', 'T', b'x', 1, 1))
        capture.close('done', {}, {})
        self.assertTrue(worker.shutdown())
        self.assertEqual(sink.closed[0][0], 'worker_error')

    def test_storage_budget_checked_in_worker(self):
        sink = Sink()
        sink.budget_bytes = 1
        worker = QueuedWriter(lambda: sink)
        capture = worker.open_capture()
        capture.write(Sample('/x', 'T', b'xx', 0, 0))
        capture.close('done', {}, {})
        self.assertTrue(worker.shutdown())
        self.assertIn('budget exhausted', worker.error)
        self.assertEqual(sink.samples, [])

    def test_batch_overflow_is_atomic_and_closes_capture(self):
        release = threading.Event()
        sink = Sink()
        def factory():
            release.wait(2)
            return sink
        worker = QueuedWriter(factory, max_bytes=2)
        core = RecorderEngine(worker.open_capture)
        core.ingest(Sample('/x', 'T', b'xxx', 0, 0))
        try:
            core.motion(0)
            self.assertIsNotNone(core.disabled_reason)
            self.assertEqual(worker.health()['queue_bytes'], 0)
        finally:
            release.set()
            self.assertTrue(worker.shutdown())
        self.assertEqual(sink.samples, [])
        self.assertEqual(sink.closed[0][0], 'open_error')

    def test_shutdown_with_pending_preroll_and_restart(self):
        for _ in range(2):
            sink = Sink()
            worker = QueuedWriter(lambda: sink)
            core = RecorderEngine(worker.open_capture)
            for i in range(11):
                core.ingest(Sample('/x', 'T', b'x', i, i))
            core.motion(10)
            core.close('shutdown')
            self.assertTrue(worker.shutdown())
            self.assertEqual(len(sink.samples), 11)
            self.assertEqual(sink.closed[0][0], 'shutdown')


if __name__ == '__main__':
    unittest.main()

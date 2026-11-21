import sys
import time
import tracemalloc
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atlas_flysky_core as C  # noqa: E402
import atlas_flysky_web as W   # noqa: E402


class Overhead(unittest.TestCase):
    """Generous bounds: they catch a runaway, not a few percent.  Measured numbers are written up in the report."""

    def test_decode_cost_per_frame(self):
        frames = [C.encode_sbus([992 + (k % 700)] * 16) for k in range(2000)]
        lab = C.FlyskyLab(); t0 = time.process_time()
        for rep in range(5):
            for k, f in enumerate(frames):
                lab.ingest_message({'proto': 'sbus', 'hex': f.hex()}, rep * 100 + k * 0.014, 0.0)
        per = (time.process_time() - t0) / 10000
        self.assertLess(per, 0.0005, 'each frame must cost well under 0.5 ms of CPU, got %.3f ms' % (per * 1000))

    def test_state_snapshot_cost(self):
        lab = C.FlyskyLab()
        for k in range(600):
            lab.ingest_message({'proto': 'sbus', 'hex': C.encode_sbus([992 + k % 500] * 16).hex()}, k * 0.014, 0.0)
        t0 = time.process_time()
        for _ in range(200):
            lab.snapshot(9.0, True)
        self.assertLess((time.process_time() - t0) / 200, 0.005)

    def test_memory_does_not_grow_with_frames_when_not_recording(self):
        lab = C.FlyskyLab()
        payloads = [C.encode_sbus([172 + (k * 7) % 1600] * 16).hex() for k in range(500)]
        for k in range(5000):                       # warm up the bounded buffers
            lab.ingest_message({'proto': 'sbus', 'hex': payloads[k % 500]}, k * 0.014, 0.0)
        tracemalloc.start(); base = tracemalloc.take_snapshot()
        for k in range(5000, 45000):                # 40k more frames (about 9 min of SBUS)
            lab.ingest_message({'proto': 'sbus', 'hex': payloads[k % 500]}, k * 0.014, 0.0)
        grow = sum(st.size_diff for st in tracemalloc.take_snapshot().compare_to(base, 'filename') if 'atlas_flysky' in str(st.traceback))
        tracemalloc.stop()
        self.assertLess(len(lab.t), 400); self.assertLess(grow, 300_000, 'live state must not grow with frame count')

    def test_recording_memory_is_capped(self):
        lab = C.FlyskyLab(); s = C.LabSession('abcdef012345', 0.0, 0.0); lab.session = s
        payloads = [C.encode_sbus([172 + (k * 7) % 1600] * 16).hex() for k in range(500)]
        tracemalloc.start(); base = tracemalloc.take_snapshot()
        for k in range(31000):                      # more than one session can hold (30,000 rows or 1500 s)
            lab.ingest_message({'proto': 'sbus', 'hex': payloads[k % 500]}, k * 0.05, 0.0)
        grow = sum(st.size_diff for st in tracemalloc.take_snapshot().compare_to(base, 'filename') if 'atlas_flysky' in str(st.traceback))
        tracemalloc.stop()
        self.assertTrue(s.truncated); self.assertLessEqual(len(s.rows), C.MAX_SESSION_ROWS)
        self.assertLess(grow / max(1, len(s.rows)), 400, 'bytes per recorded row')
        self.assertLess(grow, 15_000_000)
        t0 = time.process_time(); csv_text = s.to_csv(); self.assertLess(time.process_time() - t0, 5.0)
        self.assertEqual(csv_text.count('\n'), len(s.rows) + 1)

    def test_idle_service_holds_no_threads_or_subscriptions(self):
        import threading
        before = threading.active_count()
        svc = W.FlyskyService(lambda: type('T', (), {'start': lambda s, cb: None, 'publisher_count': lambda s: 0, 'stop': lambda s: None})(), start_threads=True)
        self.assertEqual(threading.active_count(), before); self.assertIsNone(svc.transport)


if __name__ == '__main__':
    unittest.main()

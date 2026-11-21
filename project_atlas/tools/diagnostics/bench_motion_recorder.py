#!/usr/bin/env python3
"""Offline synthetic recorder-core benchmark; does not start ROS or drive ATLAS."""

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from atlas_motion_recorder_core import RecorderEngine, Sample  # noqa: E402


class FileSink:
    def __init__(self, root):
        self.budget_bytes = 500 * 1024 * 1024
        self.path = root / 'synthetic_payload.bin'
        self.file = self.path.open('wb')

    def write(self, sample):
        self.file.write(sample.payload)

    def close(self, reason, dropped, received):
        self.file.close()


def main():
    with tempfile.TemporaryDirectory(prefix='atlas-recorder-bench-') as td:
        root = Path(td)
        engine = RecorderEngine(lambda: FileSink(root))
        payloads = [('/scan', 4096), ('/odom', 256), ('/yahboom/odom', 256),
                    ('/imu/data', 128), ('/tf', 512), ('/amcl_pose', 256),
                    ('/atlas/control_policy', 128)]
        tracemalloc.start()
        start_wall = time.perf_counter()
        start_cpu = time.process_time()
        for step in range(6000):  # 60 simulated seconds, 100 Hz scheduling.
            t = step / 100.0
            for index, (topic, size) in enumerate(payloads):
                if (step % (10 if index == 0 else 1 if index in (1, 2, 3)
                            else 5 if index == 4 else 20)) == 0:
                    engine.ingest(Sample(topic, 'benchmark/msg/Synthetic',
                                         bytes([index]) * size, t, int(t * 1e9)))
            if 10 <= t < 50:
                engine.motion(t)
            engine.tick(t)
        engine.close()
        cpu = time.process_time() - start_cpu
        wall = time.perf_counter() - start_wall
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result = dict(simulated_seconds=60, wall_seconds=round(wall, 3),
                      cpu_seconds=round(cpu, 3), cpu_one_core_percent=round(100 * cpu / wall, 1),
                      python_peak_mib=round(peak / 1024**2, 2),
                      disk_bytes=engine.completed and (root / 'synthetic_payload.bin').stat().st_size,
                      disk_mib_per_simulated_minute=round(
                          (root / 'synthetic_payload.bin').stat().st_size / 1024**2, 2),
                      message_counts=dict(engine.received), dropped=dict(engine.dropped),
                      host=os.name)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

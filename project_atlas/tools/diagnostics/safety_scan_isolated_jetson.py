"""One bounded, non-ROS benchmark; never installs or controls production."""
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import types
import urllib.request

sys.path.insert(0, '/home/jetson/project_atlas/scripts')
sys.path.insert(0, '/home/jetson/project_atlas/tools/vision3d')
import stationary_gate as G
import stationary_ros_probe as P
import benchmark_safety_scan_transform as B


def main():
    root = Path(__file__).resolve().parent
    result = {'status': 'ABORTED', 'production_changed': False, 'rows': [], 'pairs': []}
    G.UNITS = G.UNITS + ('rover-status-web.service', 'atlas-voice-companion.service', 'atlas-safety-status.service')
    before = G.services()
    result['services_before'] = before

    def safe(cpu):
        G.require_cpu(cpu)
        snapshot = P.safety_snapshot()
        checked = G.check(cpu, snapshot)
        P.extra_safety(snapshot['ros'])
        with urllib.request.urlopen('http://127.0.0.1:8088/api/vision3d/summary', timeout=3) as r:
            camera = json.load(r)
        # Reuse the reviewed OFF predicate, no profiler invocation.
        sys.path.insert(0, '/home/jetson/project-atlas-migration/native-cpu-20261023')
        from native_dashboard_cpu_once import require_off
        require_off(camera, subprocess.run(['pgrep', '-x', 'astra_camera_no'], stdout=subprocess.DEVNULL).returncode)
        return checked

    def interval(phase, work=None):
        ticks = G.ticks()
        start = time.monotonic()
        measurement = work() if work else None
        time.sleep(max(0, 1 - (time.monotonic() - start)))
        cpu = G.cpu_delta(ticks, G.ticks())
        row = {'phase': phase, 'cpu': cpu, 'elapsed': time.monotonic()-start}
        result['rows'].append(row)
        row['safety'] = safe(cpu)
        return measurement

    try:
        if any(v['ActiveState'] != 'active' or v['MainPID'] == '0' for v in before.values()):
            raise RuntimeError('Protected service inactive')
        for _ in range(3):
            interval('baseline')
        raw = Path('/home/jetson/project_atlas/scripts/atlas_safety_status.py').read_bytes()
        patched = B.candidate(raw)
        result['baseline_sha256'] = hashlib.sha256(raw).hexdigest()
        result['candidate_sha256'] = hashlib.sha256(patched).hexdigest()
        funcs = [B.callback(raw), B.callback(patched)]
        rng = random.Random(24010)
        msg = B.scan([rng.uniform(.1, 12) for _ in range(720)])
        for pair in range(10):
            measurements = {}
            for index in ([0, 1] if pair % 2 == 0 else [1, 0]):
                def work():
                    state = types.SimpleNamespace()
                    start = time.process_time()
                    for _ in range(10):
                        funcs[index](state, msg)
                    elapsed = time.process_time() - start
                    return elapsed, vars(state)
                elapsed, state = interval('original' if index == 0 else 'candidate', work)
                measurements[index] = elapsed
                if index == 0:
                    original_state = state
                else:
                    candidate_state = state
            if original_state != candidate_state:
                raise RuntimeError('Callback output mismatch')
            result['pairs'].append(measurements)
        result['median_callback_cpu_saving_pct'] = statistics.median(
            100*(1-p[1]/p[0]) for p in result['pairs'])
        result['original_ms_per_scan'] = statistics.mean(p[0] for p in result['pairs'])*100
        result['candidate_ms_per_scan'] = statistics.mean(p[1] for p in result['pairs'])*100
        interval('postflight')
        result['status'] = 'COMPLETE'
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        result['services_after'] = G.services()
        result['protected_unchanged'] = before == result['services_after']
        if not result['protected_unchanged']:
            result['status'] = 'ABORTED'
        result['max_rss_kib'] = __import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_maxrss
        (root / 'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

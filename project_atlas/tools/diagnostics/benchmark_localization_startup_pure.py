"""PC-only pure startup stages; no ROS initialization, services or robot writes.

Run in a fresh interpreter for cold Python imports. OS filesystem cache is not
cleared. Results do not model DDS discovery or Jetson CPUQuota scheduling.
"""
import hashlib
import json
from pathlib import Path
import sys
import time


def measure(label, operation, rows, wall=time.monotonic, cpu=time.process_time):
    started, cpu_started = wall(), cpu()
    try:
        value = operation()
    except Exception:
        rows.append(dict(stage=label, wall_s=wall()-started,
                         cpu_s=cpu()-cpu_started, outcome='FAILED'))
        raise
    rows.append(dict(stage=label, wall_s=wall()-started,
                     cpu_s=cpu()-cpu_started, outcome='PASSED'))
    return value


def main():
    import platform
    if platform.machine().lower() not in ('x86_64', 'amd64'):
        raise RuntimeError('PC-only benchmark; ARM64 execution not approved')
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / 'scripts'))
    rows = []
    core = measure('numpy_scipy_core_import', lambda: __import__('atlas_localization_verify_core'), rows)
    path = root / 'maps/atlas_latest.yaml'
    m = measure('load_map_distance_transform', lambda: core.load_map(path), rows)
    policy = core.VerifyPolicy()
    index = measure('search_index_cold', lambda: core._search_index(m, policy), rows)
    cached = measure('search_index_cached', lambda: core._search_index(m, policy), rows)
    manual = measure('manual_module_import', lambda: __import__('atlas_location_check_ros'), rows)
    identity = measure('manual_map_identity', lambda: manual.map_identity(path), rows)
    if cached is not index:
        raise RuntimeError('Unexpected search-index cache behavior')
    print(json.dumps(dict(scope='PC pure startup only; not live startup reproduction',
                         machine=platform.machine(), stages=rows, dimensions=[m['w'], m['h']],
                         candidate_cells=len(index['flat']), map_identity=identity,
                         core_sha256=hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest(),
                         ros_initialized=False, production_changed=False)))


if __name__ == '__main__':
    main()

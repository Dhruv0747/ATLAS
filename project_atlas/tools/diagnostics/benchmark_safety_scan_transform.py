"""Offline exact-live candidate: rotate each valid ray once, not per sector.

No ROS imports, live subscriptions, deployment or resource-policy changes.
"""
import ast
import hashlib
import math
import pathlib
import random
import statistics
import sys
import time
import types
import json

SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from atlas_scan_geometry import ray_in_base_sector, sensor_ray_in_base_degrees, wrap_degrees

BASELINE = '57262f6e55aef3f28ba285805619a86f6131643e41cebf20dc49be86d3cf2e1e'


def candidate(raw):
    if hashlib.sha256(raw).hexdigest() != BASELINE:
        raise ValueError('Exact live baseline mismatch')
    source = raw.decode()
    old = '            degrees = math.degrees(angle)'
    new = old + '\n            base_angle = sensor_ray_in_base_degrees(degrees, LASER_YAW_DEG)'
    assert source.count(old) == 1
    source = source.replace(old, new)
    for center, width in [(0., 15.), (180., 15.), (0., 35.), (77.5, 42.5), (-77.5, 42.5), (180., 35.)]:
        old = f'ray_in_base_sector(degrees, {center}, {width}, LASER_YAW_DEG)'
        assert source.count(old) == 1
        source = source.replace(old, f'abs(wrap_degrees(base_angle - {center})) <= {width}')
    # Keep original import; add only the helpers required by this candidate.
    source = source.replace('from atlas_scan_geometry import ray_in_base_sector',
                            'from atlas_scan_geometry import ray_in_base_sector, sensor_ray_in_base_degrees, wrap_degrees')
    compile(source, '<complete-candidate>', 'exec')
    return source.encode()


def callback(raw):
    tree = ast.parse(raw)
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'on_scan')
    method.args.args[1].annotation = None
    module = ast.Module(body=[method], type_ignores=[])
    ns = dict(math=math, time=types.SimpleNamespace(monotonic=lambda: 123.0),
              LASER_YAW_DEG=180., ray_in_base_sector=ray_in_base_sector,
              sensor_ray_in_base_degrees=sensor_ray_in_base_degrees, wrap_degrees=wrap_degrees)
    exec(compile(ast.fix_missing_locations(module), '<isolated-on_scan>', 'exec'), ns)
    return ns['on_scan']


def scan(ranges, start=-math.pi, step=math.pi/360):
    return types.SimpleNamespace(ranges=ranges, angle_min=start, angle_increment=step,
                                 range_min=.1, range_max=12.)


def run(raw):
    patched = candidate(raw)
    funcs = [callback(raw), callback(patched)]
    rng = random.Random(24010)
    cases = [scan([]), scan([float('nan'), float('inf'), -1., 0., .1, 12., 13.])]
    for _ in range(300):
        cases.append(scan([rng.choice([rng.uniform(-1, 15), float('nan'), float('inf')])
                           for _ in range(rng.randrange(0, 1200))], rng.uniform(-10, 10), rng.uniform(-.1, .1)))
    for angle in [-180, -145, -120, -35, -15, 0, 15, 35, 120, 145, 180]:
        for epsilon in [-1e-10, 0, 1e-10]:
            cases.append(scan([.1], math.radians(angle + epsilon), 0))
    for msg in cases:
        states = [types.SimpleNamespace(), types.SimpleNamespace()]
        for f, state in zip(funcs, states):
            f(state, msg)
        assert vars(states[0]) == vars(states[1]), msg
    # Equivalent fixed synthetic workload; alternating order reduces ordering bias.
    msg = scan([rng.uniform(.1, 12.) for _ in range(720)])
    pairs = []
    for pair in range(10):
        measurements = {}
        for index in ([0, 1] if pair % 2 == 0 else [1, 0]):
            state = types.SimpleNamespace()
            start = time.process_time()
            for _ in range(300):
                funcs[index](state, msg)
            measurements[index] = time.process_time() - start
        pairs.append(measurements)
    result = dict(equivalence_cases=len(cases), pairs=pairs,
                  median_callback_cpu_saving_pct=statistics.median(100*(1-p[1]/p[0]) for p in pairs),
                  original_ms_per_scan=1000*statistics.mean(p[0] for p in pairs)/300,
                  candidate_ms_per_scan=1000*statistics.mean(p[1] for p in pairs)/300,
                  candidate_sha256=hashlib.sha256(patched).hexdigest(),
                  scope='PC synthetic callback only; not Jetson whole-system savings; NOT deployed')
    return result


if __name__ == '__main__':
    print(json.dumps(run(pathlib.Path(sys.argv[1]).read_bytes()), indent=2))

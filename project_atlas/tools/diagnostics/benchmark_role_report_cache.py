#!/usr/bin/env python3
"""Offline differential/CPU check. No ROS imports, network or robot access."""
import ast
import json
from pathlib import Path
import random
import statistics
import subprocess
import time
import tracemalloc
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
REL = 'project_atlas/scripts/atlas_agent_team.py'
BASE = 'ee97d85'


def load(source, clock):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    cls.bases = []
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                and n.name in ('update', 'snapshot')]
    ns = {'json': json, 'time': SimpleNamespace(monotonic=lambda: clock[0])}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), REL, 'exec'), ns)
    node = ns['AtlasAgentTeam']()
    node.values, node.seen, node.report_cache = {}, {}, {}
    return node


def seed(node):
    for role in ('mission_director', 'safety_guardian', 'driver', 'mode_manager',
                 'localization', 'perception', 'voice_interface', 'experience_recorder'):
        node.update(role, 'live')
    node.update('control_policy', '{"manual_only":false,"stop_latched":false}')
    node.update('encoder_health', '{"autonomy_ready":true}')
    node.update('recovery_specialist', '{"overall":"HEALTHY"}')
    node.update('readiness', 'AUTO_READY')


def main():
    original = subprocess.check_output(['git', 'show', BASE + ':' + REL], cwd=ROOT, text=True)
    candidate = (ROOT / REL).read_text(encoding='utf-8')
    clock = [100.]
    nodes = [load(source, clock) for source in (original, candidate)]
    for node in nodes:
        seed(node)
    rng = random.Random(23)
    for _ in range(2000):
        clock[0] += rng.choice([0, .1, 1., 7.])
        role = rng.choice(['control_policy', 'encoder_health', 'recovery_specialist', 'readiness'])
        value = rng.choice(['{', 'null', '[]', '', 'AUTO_READY',
                            '{"manual_only":false,"stop_latched":false}',
                            '{"manual_only":true,"stop_latched":true}',
                            '{"autonomy_ready":true}', '{"overall":"HEALTHY"}'])
        for node in nodes:
            node.update(role, value)
        assert nodes[0].snapshot() == nodes[1].snapshot()
    for node in nodes:
        seed(node)
    timings = [[], []]
    for repeat in range(7):
        for index in ([0, 1] if repeat % 2 else [1, 0]):
            start = time.process_time_ns()
            for _ in range(20000):
                nodes[index].snapshot()
            timings[index].append((time.process_time_ns() - start) / 20000 / 1000)
    peaks = []
    for node in nodes:
        tracemalloc.start()
        for _ in range(1000):
            node.snapshot()
        peaks.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    medians = [statistics.median(values) for values in timings]
    print(json.dumps({'baseline_ref': BASE, 'differential_cases': 2000,
                      'cpu_us_per_snapshot_baseline_candidate': medians,
                      'cpu_reduction_percent': 100 * (1 - medians[1] / medians[0]),
                      'tracemalloc_peak_bytes_baseline_candidate': peaks,
                      'note': 'PC synthetic repeated reports; NOT whole-Jetson savings'}, indent=2))


if __name__ == '__main__':
    main()

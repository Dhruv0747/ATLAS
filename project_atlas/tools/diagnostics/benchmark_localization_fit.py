"""Offline exact-live fit allocation experiment. No ROS, network or deployment."""
import ast
import cProfile
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import types
import unittest

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import test_atlas_localization_verify as fixtures

BASE = 'd95828a09b174d109033c4af10fdf2f65599e1c7365ca669dff3428e6e723462'
OLD = """    d = np.full(len(pts), 99.0)
    d[inside] = m['dist'][iy[inside], ix[inside]]
    return float(np.mean(d <= tol))"""
NEW = """    distances = np.asarray(m['dist'][iy[inside], ix[inside]], dtype=float)
    hits = np.count_nonzero(distances <= tol)
    if 99.0 <= tol:
        hits += len(pts) - np.count_nonzero(inside)
    return float(hits / len(pts))"""


def candidate(raw):
    if hashlib.sha256(raw).hexdigest() != BASE:
        raise ValueError('Exact live baseline mismatch')
    text = raw.decode()
    if text.count(OLD) != 1:
        raise ValueError('Expected fit block missing/ambiguous')
    patched = text.replace(OLD, NEW)
    compile(patched, '<candidate>', 'exec')
    return patched.encode()


def load(raw, name):
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(raw, '<' + name + '>', 'exec'), module.__dict__)
    return module


def equivalence(original, modified):
    rng = np.random.default_rng(241024)
    count = 0
    for dtype in (np.float32, np.float64):
        m = dict(origin=(-1., -2.), res=.05, w=40, h=30,
                 dist=rng.uniform(0, 2, (30, 40)).astype(dtype))
        m['dist'][0, :3] = [np.nan, np.inf, -np.inf]
        for n in [0, 1, 2, 60, 720]:
            pts = rng.uniform(-5, 5, (n, 2))
            for tol in [-1., 0., .15, 99., 100., np.nan, np.inf]:
                for pose in [(0., 0., 0.), (1., -2., .7), (100., 100., -2.)]:
                    a = original.fit(m, pts, *pose, tol)
                    b = modified.fit(m, pts, *pose, tol)
                    assert a == b, (dtype, n, tol, pose, a, b)
                    count += 1
        # Inside-cell cases exercise float32->float64 and exact tolerance boundaries.
        for tol in [float(m['dist'][7, 7]), .15, 99.]:
            pts = np.array([[.375, .375], [.025, .025]])
            assert original.fit(m, pts, -1., -2., 0., tol) == modified.fit(m, pts, -1., -2., 0., tol)
            count += 1
    return count


def run(raw):
    patched = candidate(raw)
    original, modified = load(raw, 'fit_original'), load(patched, 'fit_candidate')
    result = {'equivalence_cases': equivalence(original, modified),
              'baseline_sha256': BASE, 'candidate_sha256': hashlib.sha256(patched).hexdigest()}
    def unchanged(data):
        return [ast.dump(n) for n in ast.parse(data).body if not isinstance(n, ast.FunctionDef) or n.name != 'fit']
    assert unchanged(raw) == unchanged(patched)
    saved_core = fixtures.core
    fixtures.core = modified
    try:
        tests = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(fixtures.VerifyCoreTests))
        assert tests.wasSuccessful()
        result['existing_verify_tests_passed'] = tests.testsRun
    finally:
        fixtures.core = saved_core
    with tempfile.TemporaryDirectory() as tmp:
        map_path = fixtures.write_map(tmp, fixtures.ROOM_A + fixtures.ROOM_B)
        maps = [module.load_map(map_path) for module in (original, modified)]
        policy = original.VerifyPolicy()
        poses = [(8., 1.6, -1.7453292519943295), (.8, 1.2, 1.3439035240356338)]
        scans = [original.endpoints(*fixtures.ray_scan(fixtures.ROOM_A + fixtures.ROOM_B, p), (0., 0., 0.), policy) for p in poses]
        for module, m in zip((original, modified), maps):
            module._search_index(m, policy)
        def workload(index):
            module = (original, modified)[index]
            return [module.global_search(maps[index], allp, held, policy) for allp, held in scans]
        profile = cProfile.Profile()
        profile.enable()
        reference = workload(0)
        profile.disable()
        entries = profile.getstats()
        total = next(e.totaltime for e in entries if getattr(e.code, 'co_name', '') == 'workload')
        fit = next(e for e in entries if getattr(e.code, 'co_name', '') == 'fit')
        result['profile'] = {'workload_wall_s': total, 'fit_cumulative_s': fit.totaltime,
                             'fit_calls': fit.callcount, 'fit_share_pct': 100*fit.totaltime/total,
                             'scope': 'PC synthetic search, not live thread attribution'}
        result['profile']['top_self_time'] = [
            {'function': getattr(e.code, 'co_name', str(e.code)), 'self_s': e.inlinetime, 'calls': e.callcount}
            for e in sorted(entries, key=lambda e: -e.inlinetime)[:8]]
        pairs = []
        for pair in range(6):
            row = {}
            for index in ([0, 1] if pair % 2 == 0 else [1, 0]):
                start = time.process_time()
                hypotheses = workload(index)
                row[index] = time.process_time()-start
                assert hypotheses == reference
                for hyp, (pts, _) in zip(hypotheses, scans):
                    assert vars(original.decide(hyp, len(pts), None, policy)) == vars(modified.decide(hyp, len(pts), None, policy))
            pairs.append(row)
        result.update(pairs=pairs, median_search_cpu_saving_pct=statistics.median(100*(1-p[1]/p[0]) for p in pairs),
                      original_cpu_s_mean=statistics.mean(p[0] for p in pairs),
                      candidate_cpu_s_mean=statistics.mean(p[1] for p in pairs),
                      production_changed=False)
    return result


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1]).read_bytes()), indent=2))

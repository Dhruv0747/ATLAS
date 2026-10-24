"""Offline integrity tests for the Dashboard executor ExitStack-removal package (no ROS, no SSH, no deploy)."""
import hashlib, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'tools/diagnostics/dashboard_executor_bookkeeping'
sys.path.insert(0, str(D))
import prepare_variants as P   # noqa: E402
import build_package as BP     # noqa: E402

LIVE_IMPL = D / 'live/atlas_dashboard_executor_impl.py.live'
LIVE_ADAPTER = ROOT / 'scripts/atlas_dashboard_executor.py'
H = lambda b: hashlib.sha256(b).hexdigest()


class Package(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.out = Path(cls.tmp.name) / 'pkg'
        cls.manifest = BP.build(LIVE_IMPL, LIVE_ADAPTER, cls.out)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_live_fixtures_are_the_deployed_versions(self):
        self.assertEqual(H(LIVE_IMPL.read_bytes()), P.LIVE_SHA)
        self.assertEqual(H(LIVE_ADAPTER.read_bytes()), BP.LIVE_ADAPTER_SHA)

    def test_candidate_is_exactly_the_v1_transformation(self):
        cand = (self.out / 'install/atlas_dashboard_executor_impl.py').read_text()
        self.assertEqual(cand, P.v1(LIVE_IMPL.read_text()))
        self.assertNotIn('context_stack', cand); self.assertIn('class _EnteredHandles', cand)
        self.assertEqual(cand.count('entered_handles.append(_h)'), 7)
        live = LIVE_IMPL.read_text()
        # nothing else in the executor changes: QoS/waitable calls, readiness checks and yield order are untouched
        for needle in ('waitable.add_to_wait_set(wait_set)', 'wt.is_ready(wait_set)', 'if wt in waitables and', 'wait_set.wait(timeout_nsec)',
                       'self._make_handler(', 'raise TimeoutException()', 'gc._executor_triggered = True'):
            self.assertEqual(cand.count(needle), live.count(needle), needle)

    def test_adapter_changes_only_the_overlay_hash(self):
        new = (self.out / 'install/atlas_dashboard_executor.py').read_text().splitlines()
        old = LIVE_ADAPTER.read_text().splitlines()
        diff = [(a, b) for a, b in zip(old, new) if a != b]
        self.assertEqual(len(old), len(new)); self.assertEqual(len(diff), 1)
        self.assertIn(H((self.out / 'install/atlas_dashboard_executor_impl.py').read_bytes()), diff[0][1])

    def test_originals_checksums_and_manifest(self):
        self.assertEqual((self.out / 'original/atlas_dashboard_executor_impl.py').read_bytes(), LIVE_IMPL.read_bytes())
        self.assertEqual((self.out / 'original/atlas_dashboard_executor.py').read_bytes(), LIVE_ADAPTER.read_bytes())
        r = subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS'], cwd=self.out); self.assertEqual(r.returncode, 0)
        m = json.loads((self.out / 'manifest.json').read_text()); self.assertFalse(m['installed'])
        self.assertEqual(m['unchanged_required']['atlas_status_web.py'], BP.WEB_SHA)

    def test_build_is_deterministic(self):
        with tempfile.TemporaryDirectory() as t:
            BP.build(LIVE_IMPL, LIVE_ADAPTER, Path(t) / 'p2')
            self.assertEqual((Path(t) / 'p2/SHA256SUMS').read_text(), (self.out / 'SHA256SUMS').read_text())

    def test_wrong_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            bad = Path(t) / 'bad.py'; bad.write_bytes(LIVE_IMPL.read_bytes() + b'\n')
            with self.assertRaises(SystemExit): BP.build(bad, LIVE_ADAPTER, Path(t) / 'x')
            with self.assertRaises(SystemExit): BP.build(LIVE_IMPL, bad, Path(t) / 'y')

    def test_install_script_refuses_without_approval_and_checks_live_files(self):
        sh = self.out / 'dashboard_exitstack.sh'
        env = {k: v for k, v in os.environ.items() if k != 'OWNER_APPROVED'}
        for c in ('apply', 'rollback'):
            r = subprocess.run(['bash', str(sh), c], env=env, capture_output=True, text=True); self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn('owner approval required', r.stderr)
        with tempfile.TemporaryDirectory() as t:
            tgt = Path(t) / 'scripts'; tgt.mkdir()
            (tgt / 'atlas_dashboard_executor_impl.py').write_bytes(LIVE_IMPL.read_bytes()); (tgt / 'atlas_dashboard_executor.py').write_bytes(LIVE_ADAPTER.read_bytes())
            web = tgt / 'atlas_status_web.py'; web.write_bytes(b'not the live dashboard\n')
            r = subprocess.run(['bash', str(sh), 'check'], env=dict(env, TARGET=str(tgt)), capture_output=True, text=True)
            self.assertEqual(r.returncode, 2); self.assertIn('atlas_status_web.py changed', r.stderr)
            live_web = os.environ.get('ATLAS_LIVE_WEB')
            if live_web:
                web.write_bytes(Path(live_web).read_bytes())
                r = subprocess.run(['bash', str(sh), 'check'], env=dict(env, TARGET=str(tgt)), capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('CHECK OK', r.stdout)


class ExitBlockSemantics(unittest.TestCase):
    """_EnteredHandles vs contextlib.ExitStack without ROS (helper extracted from the candidate source)."""
    def test_helper_matches_exitstack_on_random_scenarios(self):
        import contextlib, random
        ns = {'sys': sys}; exec(P.HELPER, ns); EH = ns['_EnteredHandles']
        for seed in range(4000):
            res = []
            for use_stack in (True, False):
                rnd = random.Random(seed); log = []
                class CM:
                    def __init__(s, i): s.i, s.er, s.xr, s.sup = i, rnd.random() < .1, rnd.random() < .15, rnd.random() < .1
                    def __enter__(s):
                        if s.er: raise KeyError(s.i)
                        log.append(('in', s.i))
                    def __exit__(s, t, v, tb):
                        log.append(('out', s.i, t.__name__ if t else None))
                        if s.xr: raise RuntimeError('x%d' % s.i)
                        return s.sup
                cms = [CM(i) for i in range(rnd.randint(0, 10))]; body = rnd.random() < .4
                try:
                    if use_stack:
                        with contextlib.ExitStack() as st:
                            for c in cms:
                                try: st.enter_context(c)
                                except KeyError: log.append(('skip', c.i))
                            if body: raise ValueError('b')
                    else:
                        entered = []
                        with EH(entered):
                            for c in cms:
                                try:
                                    _h = c; _h.__enter__(); entered.append(_h)
                                except KeyError: log.append(('skip', c.i))
                            if body: raise ValueError('b')
                    log.append('ok')
                except Exception as e:
                    log.append((type(e).__name__, str(e)))
                res.append(log)
            self.assertEqual(res[0], res[1], seed)


if __name__ == '__main__':
    unittest.main(verbosity=2)

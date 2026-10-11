"""Visual Cloud local-only, viewer-activated mode and bounded history (no ROS, no network)."""
import ast
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import atlas_visual_cloud_core as core  # noqa: E402


def big_snapshot(failure='NONE', t=None):
    scan = {'ranges': [1.234] * 360}
    traffic = {f'/topic{i}': {'hz': 10.0, 'age_s': 0.1, 'health': 'HEALTHY', 'expected_hz': 10.0,
                              'data_mode': 'live stream', 'value': scan} for i in range(60)}
    traffic['/atlas/mission_status'] = {'hz': 0.1, 'age_s': 3.0, 'health': 'HEALTHY', 'value': 'IDLE'}
    graph = {'nodes': [f'/n{i}' for i in range(80)], 'topics': [{'name': f'/t{i}', 'publishers': ['/a'] * 5} for i in range(300)],
             'services': [], 'actions': []}
    return {'schema': 1, 'robot_id': 'project-atlas-jetson', 'observed_at': t or time.time(), 'git_version': 'abc',
            'system': {'load': [1, 1, 1], 'ram_used_pct': 40, 'temperature_c': 50}, 'traffic': traffic, 'graph': graph,
            'mission_evidence': {'missions': [], 'bags': []}, 'failure_class': failure,
            'authority': 'OBSERVABILITY_ONLY', 'collection_mode': 'IDLE'}


class UploadMode(unittest.TestCase):
    def test_inference_and_explicit(self):
        self.assertEqual(core.upload_mode({'cloud_url': 'https://atlas-visual-cloud.example/api/v1/ingest'}), 'off')
        self.assertEqual(core.upload_mode({'cloud_url': ''}), 'off')
        self.assertEqual(core.upload_mode({'cloud_url': 'http://127.0.0.1:8095/api/v1/ingest'}), 'local')
        self.assertEqual(core.upload_mode({'cloud_url': 'https://cloud.tail1234.ts.net/api/v1/ingest'}), 'remote')
        self.assertEqual(core.upload_mode({'cloud_url': 'http://127.0.0.1:8095/x', 'upload_mode': 'OFF'}), 'off')

    def test_repo_config_is_local_and_never_the_placeholder(self):
        cfg = json.loads((SCRIPTS.parent / 'config' / 'atlas_visual_cloud.json').read_text())
        self.assertEqual(core.upload_mode(cfg), 'local')
        self.assertNotIn('.example', cfg['cloud_url'])
        self.assertEqual(cfg['topics'], json.loads(self._baseline_topics()))

    def _baseline_topics(self):
        import subprocess
        try:
            base = subprocess.run(['git', '-C', str(SCRIPTS), 'show', 'aa93355:project_atlas/config/atlas_visual_cloud.json'],
                                  capture_output=True, text=True, check=True).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.skipTest('git baseline unavailable')
        return json.dumps(json.loads(base)['topics'])


class Gate(unittest.TestCase):
    def test_off_and_remote(self):
        self.assertFalse(core.ViewerGate('off', lambda: 0.0).wanted(0))
        self.assertTrue(core.ViewerGate('remote', lambda: None).wanted(0))

    def test_local_follows_viewer_and_fails_idle(self):
        calls = []
        ages = iter([None, 3.0, 45.0])
        g = core.ViewerGate('local', lambda: calls.append(1) or next(ages), check_s=5, hold_s=30)
        self.assertTrue(g.poll(0)); self.assertFalse(g.wanted(0))          # nobody viewing
        self.assertFalse(g.poll(2)); self.assertEqual(len(calls), 1)        # rate-limited
        g.poll(5); self.assertTrue(g.wanted(5)); self.assertTrue(g.wanted(10.9))
        g.poll(10); self.assertFalse(g.wanted(16.1))                       # viewer gone (45 s > hold)
        def boom(): raise OSError('server down')
        g2 = core.ViewerGate('local', boom); g2.poll(0); self.assertFalse(g2.wanted(0))


class HistoryRow(unittest.TestCase):
    def test_row_is_small_and_keeps_rates(self):
        snap = big_snapshot()
        full, slim = len(json.dumps(snap)), len(json.dumps(core.history_row(snap)))
        self.assertGreater(full, 150_000)
        self.assertLess(slim, full / 20)
        row = core.history_row(snap)
        self.assertEqual(row['traffic']['/topic1'], {'hz': 10.0, 'age_s': 0.1, 'health': 'HEALTHY', 'expected_hz': 10.0, 'data_mode': 'live stream'})
        self.assertEqual(row['graph_counts']['topics'], 300); self.assertEqual(row['mission_status'], 'IDLE')

    def test_persist_due(self):
        self.assertTrue(core.persist_due(None, None, 0, 'NONE'))
        self.assertFalse(core.persist_due(0, None, 59, 'NONE'))
        self.assertTrue(core.persist_due(0, None, 60, 'NONE'))
        self.assertTrue(core.persist_due(0, None, 1, 'LOCALIZATION'))
        self.assertFalse(core.persist_due(0, 0, 5, 'LOCALIZATION'))


class Server(unittest.TestCase):
    def load(self, tmp, **env):
        os.environ.update({'ATLAS_VISUAL_CLOUD_DB': str(tmp / 'history.sqlite3'), 'ATLAS_VISUAL_CLOUD_TOKEN': 'test-token', **env})
        for k in ('ATLAS_VISUAL_CLOUD_HISTORY_DB', 'ATLAS_VISUAL_CLOUD_HISTORY_MAX_MB', 'ATLAS_VISUAL_CLOUD_HISTORY_PERSIST_S'):
            if k not in env:
                os.environ.pop(k, None)
        spec = importlib.util.spec_from_file_location(f'vcs_{time.time_ns()}', SCRIPTS / 'atlas_visual_cloud_server.py')
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

    def test_legacy_db_untouched_and_bounded_db_used(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d); legacy = tmp / 'history.sqlite3'; legacy.write_bytes(b'legacy-25GB-stand-in')
            before = (hashlib.sha256(legacy.read_bytes()).hexdigest(), legacy.stat().st_mtime_ns)
            m = self.load(tmp)
            self.assertEqual(m.DB, tmp / 'history_bounded.sqlite3')
            clock = [1000.0]; m.time = __import__('types').SimpleNamespace(monotonic=lambda: clock[0], time=time.time)
            for i in range(130):                       # 130 s of 1 Hz ingest
                m.store(big_snapshot()); clock[0] += 1.0
            import sqlite3
            rows = sqlite3.connect(m.DB).execute('select count(*), max(length(payload)) from snapshots').fetchone()
            self.assertEqual(rows[0], 3)                 # t=0, 60, 120
            self.assertLess(rows[1], 30_000)
            self.assertEqual((hashlib.sha256(legacy.read_bytes()).hexdigest(), legacy.stat().st_mtime_ns), before)
            self.assertIn('project-atlas-jetson', m.LATEST)   # live view still updates every ingest

    def test_explicit_history_path_cannot_point_at_legacy(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            m = self.load(tmp, ATLAS_VISUAL_CLOUD_HISTORY_DB=str(tmp / 'history.sqlite3'))
            self.assertEqual(m.DB.name, 'history_bounded.sqlite3')

    def test_byte_cap_prunes_oldest(self):
        with tempfile.TemporaryDirectory() as d:
            m = self.load(Path(d), ATLAS_VISUAL_CLOUD_HISTORY_MAX_MB='0.05', ATLAS_VISUAL_CLOUD_HISTORY_PERSIST_S='0')
            clock = [0.0]; m.time = __import__('types').SimpleNamespace(monotonic=lambda: clock[0], time=time.time); m.PRUNE_INTERVAL_S = 0
            for i in range(40):
                m.store(big_snapshot()); clock[0] += 1.0
            import sqlite3
            db = sqlite3.connect(m.DB)
            used = (db.execute('pragma page_count').fetchone()[0] - db.execute('pragma freelist_count').fetchone()[0]) * db.execute('pragma page_size').fetchone()[0]
            self.assertLessEqual(used, int(0.05 * 1024 * 1024) + 32 * 1024)
            self.assertGreaterEqual(db.execute('select count(*) from snapshots').fetchone()[0], 1)

    def test_demand_endpoint_reports_viewer_and_requires_token(self):
        with tempfile.TemporaryDirectory() as d:
            m = self.load(Path(d))

            def get(path, token=None):
                h = m.Handler.__new__(m.Handler)
                h.path, h.wfile = path, io.BytesIO()
                h.headers = {'Authorization': 'Bearer ' + token} if token else {}
                h.send_response = lambda c: setattr(h, 'code', c); h.send_header = lambda *a: None; h.end_headers = lambda: None
                h.do_GET(); return h.code, h.wfile.getvalue()
            self.assertEqual(get('/api/v1/demand')[0], 401)
            code, body = get('/api/v1/demand', 'test-token'); self.assertEqual((code, json.loads(body)['viewer_age_s']), (200, None))
            get('/api/v1/robots')
            age = json.loads(get('/api/v1/demand', 'test-token')[1])['viewer_age_s']
            self.assertIsNotNone(age); self.assertLess(age, 1.0)


class AgentStatic(unittest.TestCase):
    SRC = (SCRIPTS / 'atlas_visual_cloud_agent.py').read_text(encoding='utf-8')

    def method(self, name):
        cls = next(n for n in ast.parse(self.SRC).body if isinstance(n, ast.ClassDef))
        return ast.unparse(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name))

    def test_no_build_without_viewer_and_no_send_when_off(self):
        q = self.method('queue_snapshot')
        self.assertLess(q.index('self.observing(now)'), q.index('self.build_snapshot'))
        s = self.method('send_loop')
        self.assertLess(s.index("self.mode == 'off'"), s.index('urlopen'))
        self.assertLess(s.index('self.viewer.poll('), s.index('urlopen'))

    def test_values_compacted_only_for_viewer_except_activity_and_retained(self):
        m = self.method('on_message')
        self.assertIn('always_compact = topic in ACTIVITY_TOPICS or topic in RETAINED_TOPICS', m)
        self.assertIn('self.observing(now) and', m)

    def test_still_subscription_only(self):
        for forbidden in ('create_publisher', 'create_service', 'ActionClient'):
            self.assertNotIn(forbidden, self.SRC)


class AgentSubscriptionLifecycle(unittest.TestCase):
    """Real observing/manage_subscriptions/discover_subscriptions methods with a fake node."""

    def make(self, mode):
        from types import SimpleNamespace as NS
        import collections, threading
        tree = ast.parse((SCRIPTS / 'atlas_visual_cloud_agent.py').read_text(encoding='utf-8'))
        consts = {}
        for n in tree.body:
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ('ACTIVITY_TOPICS', 'RETAINED_TOPICS'):
                consts[n.targets[0].id] = ast.literal_eval(n.value)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        cls.bases = []
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('observing', 'manage_subscriptions', 'discover_subscriptions')]
        self.now = [100.0]
        scope = dict(time=NS(monotonic=lambda: self.now[0]), qos_profile_sensor_data='sensor', QoSProfile=lambda **k: 'retained',
                     DurabilityPolicy=NS(TRANSIENT_LOCAL=1), ReliabilityPolicy=NS(RELIABLE=1), get_message=lambda name: name, **consts)
        exec(compile(ast.Module(body=[cls], type_ignores=[]), 'agent', 'exec'), scope)
        a = scope[cls.name]()
        topics = {'/scan': 8.0, '/tf': 10.0, '/map': 0.05, '/cmd_vel': 5.0, '/atlas/mission_status': 0.1}
        a.config = {'topics': topics, 'idle_release_s': 10.0}
        a.mode = mode; a.lock = threading.Lock(); a.active_until = 0.0; a.observing_until = 0.0
        a.samples = {t: collections.deque([1.0, 2.0]) for t in topics}; a.values = {t: 'v' for t in topics}
        a.last_value_compaction = {}; a.subscriptions_live = {}; a.subscribed_topics = set()
        self.viewer = [False]; a.viewer = NS(wanted=lambda now: self.viewer[0])
        a.created, a.destroyed = [], []
        a.get_topic_names_and_types = lambda: [(t, ['pkg/msg/T']) for t in topics]
        a.create_subscription = lambda cls_, topic, cb, qos, raw=False: a.created.append(topic) or ('sub', topic)
        a.destroy_subscription = lambda sub: a.destroyed.append(sub[1])
        a.on_message = lambda *x: None
        a.get_logger = lambda: NS(warning=print)
        return a

    def test_local_idle_keeps_only_activity_topics(self):
        a = self.make('local'); a.discover_subscriptions()
        self.assertEqual(sorted(a.created), ['/atlas/mission_status', '/cmd_vel'])

    def test_viewer_subscribes_all_then_releases_after_hold(self):
        a = self.make('local'); a.discover_subscriptions(); a.created.clear()
        self.viewer[0] = True; a.manage_subscriptions()
        self.assertEqual(sorted(a.created), ['/map', '/scan', '/tf'])
        self.viewer[0] = False; self.now[0] += 5; a.manage_subscriptions(); self.assertEqual(a.destroyed, [])   # within hold
        self.now[0] += 6; a.manage_subscriptions()
        self.assertEqual(sorted(a.destroyed), ['/map', '/scan', '/tf'])
        self.assertEqual(sorted(a.subscribed_topics), ['/atlas/mission_status', '/cmd_vel'])
        self.assertEqual(len(a.samples['/scan']), 0); self.assertNotIn('/scan', a.values)    # no stale data
        self.assertEqual(len(a.samples['/cmd_vel']), 2)

    def test_rover_activity_starts_monitoring_without_viewer(self):
        a = self.make('local'); a.discover_subscriptions(); a.created.clear()
        a.active_until = self.now[0] + 30; a.manage_subscriptions()
        self.assertEqual(sorted(a.created), ['/map', '/scan', '/tf'])

    def test_remote_never_releases_and_off_never_observes(self):
        r = self.make('remote'); r.discover_subscriptions(); self.now[0] += 100; r.manage_subscriptions()
        self.assertEqual(r.destroyed, []); self.assertEqual(len(r.created), 5)
        o = self.make('off'); o.discover_subscriptions(); self.viewer[0] = True; o.manage_subscriptions()
        self.assertEqual(sorted(o.created), ['/atlas/mission_status', '/cmd_vel'])


if __name__ == '__main__':
    unittest.main()

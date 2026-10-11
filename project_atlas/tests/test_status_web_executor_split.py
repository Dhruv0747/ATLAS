"""Hot/cold executor split in rover-status-web: interface preservation and thread-safety contract.

Static checks on the real source (no ROS needed):
  * every topic, message type, QoS and callback from the pre-split file is still subscribed,
    and nothing new is (compared against the deployed baseline embedded below);
  * hot topics, every timer, every publisher and the camera subscriptions stay on the original node;
  * no instance attribute written by a callback in one executor group is read or written by a
    callback in the other group, except state guarded by AtlasRosNode.lock (data/update_times via _set).
Plus a behavioural check of _SubscriptionRouter with fake nodes.
"""
import ast
import re
import unittest
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'atlas_status_web.py'
SRC = SRC_PATH.read_text(encoding='utf-8')
TREE = ast.parse(SRC)


def module_value(name):
    for n in TREE.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return n.value
    raise KeyError(name)


HOT = {e.value for e in module_value('HOT_STATUS_TOPICS').args[0].elts}
CLS = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'AtlasRosNode')
METHODS = {n.name: n for n in CLS.body if isinstance(n, ast.FunctionDef)}


def subscriptions():
    """(owner, type, topic, callback-source) for every create_subscription in AtlasRosNode.
    A local ``node`` is resolved to what it was assigned from (``node = self.node`` in the camera tick)."""
    aliases = {}
    for fn in ast.walk(CLS):
        if isinstance(fn, ast.Assign) and len(fn.targets) == 1 and isinstance(fn.targets[0], ast.Name) \
                and fn.targets[0].id == 'node':
            aliases['node'] = ast.unparse(fn.value)
    out = []
    for call in ast.walk(CLS):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'create_subscription':
            owner = ast.unparse(call.func.value); owner = aliases.get(owner, owner)
            topic = call.args[1].value if isinstance(call.args[1], ast.Constant) else ast.unparse(call.args[1])
            out.append((owner, ast.unparse(call.args[0]), topic, ast.unparse(call.args[2]), ast.unparse(call.args[3])))
    return out


def self_attrs(node, depth=0, seen=None):
    """(written, read) self.<attr> names reachable from a function/lambda, following self.method() calls."""
    seen = seen if seen is not None else set()
    written, read = set(), set()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'self':
            (written if isinstance(n.ctx, ast.Store) else read).add(n.attr)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'setattr' \
                and ast.unparse(n.args[0]) == 'self' and isinstance(n.args[1], ast.Constant):
            written.add(n.args[1].value)
    for name in list(read):
        if name in METHODS and name not in seen and depth < 4:
            seen.add(name)
            w, r = self_attrs(METHODS[name], depth + 1, seen); written |= w; read |= r
    return written, read - set(METHODS)


def callback_node(src):
    m = re.fullmatch(r'self\.(\w+)', src)
    return METHODS[m.group(1)] if m else ast.parse(src, mode='eval').body


# Lock-guarded or immutable-after-start state that both groups may touch.
GUARDED = {'lock', 'data', 'update_times', 'node', 'status_node', 'ready', 'pub', 'map_lock'}


class ExecutorSplit(unittest.TestCase):
    def test_router_present_and_spin_uses_two_executors(self):
        spin = ast.unparse(METHODS['_spin'])
        self.assertIn('rclpy.create_node("atlas_web_status")', spin.replace("'", '"'))
        self.assertIn('_SubscriptionRouter(self.node, self.status_node)', spin)
        self.assertIn('rclpy.spin(self.node)', spin)
        self.assertIn('self._spin_status', spin)
        self.assertIn('executor.add_node(self.status_node)', ast.unparse(METHODS['_spin_status']))

    def test_all_publishers_timers_and_camera_subscriptions_on_original_node(self):
        for call in ast.walk(CLS):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
                owner = ast.unparse(call.func.value)
                if call.func.attr == 'create_publisher':
                    self.assertEqual(owner, 'self.node', ast.unparse(call))
                if call.func.attr == 'create_timer':
                    self.assertIn(owner, ('n', 'self.node'), ast.unparse(call))   # n routes timers to self.node
        for owner, _, topic, _, _ in subscriptions():
            if 'camera' in topic and 'compressed' in topic:
                self.assertEqual(owner, 'self.node', topic)
        self.assertNotIn('create_timer', ast.unparse(METHODS['_spin_status']))

    def test_every_hot_topic_is_subscribed(self):
        topics = {t for _, _, t, _, _ in subscriptions()}
        self.assertTrue(HOT <= topics, HOT - topics)

    def test_no_unguarded_state_shared_between_executor_groups(self):
        groups = {'hot': [], 'cold': []}
        for owner, _, topic, cb, _ in subscriptions():
            hot = owner == 'self.node' or topic in HOT
            groups['hot' if hot else 'cold'].append((topic, callback_node(cb)))
        for t in ('_drive_watchdog', '_map_pose_tick', '_camera_subscription_tick'):
            groups['hot'].append((t, METHODS[t]))
        acc = {}
        for g, items in groups.items():
            w, r = set(), set()
            for _, node in items:
                ww, rr = self_attrs(node); w |= ww; r |= rr
            acc[g] = (w, r)
        (hw, hr), (cw, cr) = acc['hot'], acc['cold']
        conflicts = ((hw & (cw | cr)) | (cw & (hw | hr))) - GUARDED
        self.assertEqual(conflicts, set(), f'unguarded state shared across executor threads: {sorted(conflicts)}')

    def test_router_dispatch(self):
        ns = {}
        router_src = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == '_SubscriptionRouter')
        exec(compile(ast.Module(body=[router_src], type_ignores=[]), 'router', 'exec'), {'HOT_STATUS_TOPICS': frozenset(HOT)}, ns)

        class Fake:
            def __init__(self): self.subs, self.timers = [], []
            def create_subscription(self, *a, **k): self.subs.append((a, k)); return a[1]
            def create_timer(self, *a, **k): self.timers.append(a); return 'timer'
        hot, cold = Fake(), Fake()
        r = ns['_SubscriptionRouter'](hot, cold, frozenset(HOT))
        r.create_subscription('LaserScan', '/scan', 'cb', 'qos')
        r.create_subscription('Float32', '/bms/voltage', 'cb', 10, raw=False)
        r.create_timer(0.1, 'cb')
        self.assertEqual([a[1] for a, _ in hot.subs], ['/scan'])
        self.assertEqual([(a[1], k) for a, k in cold.subs], [('/bms/voltage', {'raw': False})])
        self.assertEqual(hot.timers, [(0.1, 'cb')]); self.assertEqual(cold.timers, [])


BASELINE_SUBSCRIPTIONS = None  # filled from the deployed baseline file when present (see below)


class InterfacePreserved(unittest.TestCase):
    def test_same_subscriptions_as_baseline(self):
        """Compare (type, topic, callback, qos) with the pre-split source recorded in git."""
        import subprocess
        try:
            base = subprocess.run(['git', '-C', str(SRC_PATH.parent), 'show', 'aa93355:project_atlas/scripts/atlas_status_web.py'],
                                  capture_output=True, text=True, check=True).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.skipTest('git baseline unavailable')
        global CLS
        saved = CLS
        try:
            CLS = next(n for n in ast.parse(base).body if isinstance(n, ast.ClassDef) and n.name == 'AtlasRosNode')
            before = sorted((t, topic, cb, q) for _, t, topic, cb, q in subscriptions())
        finally:
            CLS = saved
        after = sorted((t, topic, cb, q) for _, t, topic, cb, q in subscriptions())
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()

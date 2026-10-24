"""Correctness suite for the Dashboard executor bookkeeping candidate (V1: ExitStack -> _EnteredHandles).

Every ROS test runs against the overlay file named by ATLAS_EXECUTOR_VARIANT (the live overlay and the candidate
must both pass). Run inside a private network namespace (run_iso.sh) on ROS domain 216:
    ATLAS_EXECUTOR_VARIANT=/path/executor_v1.py python -m unittest test_executor_bookkeeping -v
"""
import contextlib, gc, hashlib, os, random, threading, time, types, unittest
from pathlib import Path

import rclpy
import rclpy.exceptions as _rx
if not hasattr(_rx, 'TimerCancelledError'):   # rclpy 3.3.7 (py3.10 timing env); identical for every variant
    class TimerCancelledError(Exception): pass
    _rx.TimerCancelledError = TimerCancelledError
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rclpy.duration import Duration
from rclpy.qos_event import SubscriptionEventCallbacks, PublisherEventCallbacks
from rclpy.waitable import Waitable, NumberOfEntities
from rclpy.guard_condition import GuardCondition
from std_msgs.msg import String, Int32
from std_srvs.srv import Trigger

VARIANT = os.environ['ATLAS_EXECUTOR_VARIANT']
assert os.environ.get('ROS_DOMAIN_ID') not in (None, '0', '77'), 'private test domain required'


def load_variant():
    src = Path(VARIANT).read_bytes(); m = types.ModuleType('atlas_variant_under_test'); m.__file__ = VARIANT
    exec(compile(src, VARIANT, 'exec'), m.__dict__); m.SHA = hashlib.sha256(src).hexdigest(); return m


EX = load_variant()


def spin_until(ex, cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        ex.spin_once(timeout_sec=0.05)
    return cond()


class CountingWaitable(Waitable):
    """Wraps a guard condition; records enter/exit balance and maximum nesting."""
    def __init__(self, node, cb_group=None):
        super().__init__(cb_group or node.default_callback_group)
        self.gc = GuardCondition(None, cb_group or node.default_callback_group, context=node.context)
        self.enters = self.exits = self.depth = self.max_depth = 0; self.executed = 0; self._idx = None; self._ready = False
        self.lock = threading.Lock()
    def __enter__(self):
        with self.lock:
            self.enters += 1; self.depth += 1; self.max_depth = max(self.max_depth, self.depth)
        self.gc.handle.__enter__()
    def __exit__(self, *a):
        self.gc.handle.__exit__(*a)
        with self.lock:
            self.exits += 1; self.depth -= 1
    def get_num_entities(self): return NumberOfEntities(num_guard_conditions=1)
    def add_to_wait_set(self, ws): self._idx = ws.add_guard_condition(self.gc.handle)
    def is_ready(self, ws):
        if self._idx is not None and ws.is_ready('guard_condition', self._idx): self._ready = True
        return self._ready
    def take_data(self):
        r, self._ready = self._ready, False; return r
    async def execute(self, data):
        if data: self.executed += 1


class _Base(unittest.TestCase):
    def setUp(self):
        self.ctx = rclpy.context.Context(); rclpy.init(context=self.ctx)
        self.node = rclpy.create_node('bk_test_%d' % random.randrange(1 << 30), context=self.ctx)
        self.ex = EX.SingleThreadedExecutor(context=self.ctx); self.ex.add_node(self.node)
    def tearDown(self):
        try: self.ex.shutdown(timeout_sec=2)
        except Exception: pass
        try: self.node.destroy_node()
        except Exception: pass
        if self.ctx.ok(): rclpy.shutdown(context=self.ctx)
    def wait_matched(self, pub, n=1):
        end = time.monotonic() + 5
        while pub.get_subscription_count() < n and time.monotonic() < end: time.sleep(0.01)


class EnteredHandlesEquivalence(unittest.TestCase):
    """_EnteredHandles (candidate only) must reproduce ExitStack semantics for the patterns the executor uses."""
    def setUp(self):
        if not hasattr(EX, '_EnteredHandles'): self.skipTest('variant has no _EnteredHandles (live overlay uses ExitStack)')

    def _scenario(self, seed, use_stack):
        rnd = random.Random(seed); log = []
        class CM:
            def __init__(s, i, enter_raises, exit_raises, suppress): s.i, s.er, s.xr, s.sup = i, enter_raises, exit_raises, suppress
            def __enter__(s):
                if s.er: raise KeyError('enter%d' % s.i)
                log.append(('enter', s.i))
            def __exit__(s, t, v, tb):
                log.append(('exit', s.i, t.__name__ if t else None))
                if s.xr: raise RuntimeError('exit%d' % s.i)
                return s.sup
        cms = [CM(i, rnd.random() < .1, rnd.random() < .15, rnd.random() < .1) for i in range(rnd.randint(0, 12))]
        body_raises = rnd.random() < .4; outcome = None
        try:
            if use_stack:
                with contextlib.ExitStack() as st:
                    for c in cms:
                        try: st.enter_context(c)
                        except KeyError: log.append(('skip', c.i))
                    if body_raises: raise ValueError('body')
            else:
                entered = []
                with EX._EnteredHandles(entered):
                    for c in cms:
                        try:
                            _h = c; _h.__enter__(); entered.append(_h)
                        except KeyError: log.append(('skip', c.i))
                    if body_raises: raise ValueError('body')
            outcome = 'ok'
        except Exception as e:
            outcome = (type(e).__name__, str(e))
        return log, outcome

    def test_random_equivalence_with_exitstack(self):
        for seed in range(3000):
            self.assertEqual(self._scenario(seed, True), self._scenario(seed, False), 'seed %d' % seed)

    def test_generator_closed_inside_block_exits_everything(self):
        log = []
        class CM:
            def __init__(s, i): s.i = i
            def __enter__(s): log.append(('in', s.i))
            def __exit__(s, *a): log.append(('out', s.i, a[0].__name__ if a[0] else None))
        def gen():
            entered = []
            with EX._EnteredHandles(entered):
                for i in range(3):
                    _h = CM(i); _h.__enter__(); entered.append(_h)
                yield 1; yield 2
        g = gen(); next(g); g.close()
        self.assertEqual(log, [('in', 0), ('in', 1), ('in', 2), ('out', 2, 'GeneratorExit'), ('out', 1, 'GeneratorExit'), ('out', 0, 'GeneratorExit')])


class Delivery(_Base):
    def test_ordered_complete_delivery_with_84_subscriptions(self):
        got = {i: [] for i in range(84)}; pubs = {}
        for i in range(84):
            self.node.create_subscription(Int32, '/bk/d%d' % i, lambda m, i=i: got[i].append(m.data), 50)
        for i in range(0, 84, 7):
            pubs[i] = self.node.create_publisher(Int32, '/bk/d%d' % i, 50); self.wait_matched(pubs[i])
        for k in range(30):
            for i, p in pubs.items(): p.publish(Int32(data=k))
        self.assertTrue(spin_until(self.ex, lambda: all(len(got[i]) == 30 for i in pubs), 10), {i: len(got[i]) for i in pubs})
        for i in pubs: self.assertEqual(got[i], list(range(30)))
        self.assertTrue(all(not got[i] for i in got if i not in pubs))


class HandleAccounting(_Base):
    def test_enter_exit_balanced_across_timeouts_dispatch_and_abandoned_generators(self):
        w = CountingWaitable(self.node); self.node.add_waitable(w)
        for i in range(40): self.node.create_subscription(String, '/bk/h%d' % i, lambda m: None, 10)
        for k in range(200):
            if k % 3 == 0: w.gc.trigger()
            self.ex.spin_once(timeout_sec=0)
            if k % 50 == 0:   # abandon a generator that still holds handles: next wait creates a new one
                self.ex._cb_iter = None; gc.collect()
        self.ex._cb_iter = None; gc.collect()
        self.assertEqual(w.enters, w.exits); self.assertEqual(w.max_depth, 1); self.assertGreater(w.executed, 40)

    def test_exception_in_callback_propagates_and_handles_are_released(self):
        w = CountingWaitable(self.node); self.node.add_waitable(w)
        boom = self.node.create_timer(0.01, lambda: (_ for _ in ()).throw(ZeroDivisionError('cb')))
        with self.assertRaises(ZeroDivisionError):
            for _ in range(100): self.ex.spin_once(timeout_sec=0.05)
        self.node.destroy_timer(boom); self.ex._cb_iter = None; gc.collect()
        self.assertEqual(w.enters, w.exits)
        got = []; t = self.node.create_timer(0.01, lambda: got.append(1))        # executor still usable
        self.assertTrue(spin_until(self.ex, lambda: len(got) >= 3)); self.node.destroy_timer(t)


class EntityLifecycle(_Base):
    def test_destroy_and_recreate_subscription_while_spinning_in_another_thread(self):
        errors = []; stop = threading.Event(); got = {'a': 0, 'b': 0}
        pub_a = self.node.create_publisher(String, '/bk/a', 10); pub_b = self.node.create_publisher(String, '/bk/b', 10)
        self.node.create_subscription(String, '/bk/a', lambda m: got.__setitem__('a', got['a'] + 1), 10)
        def spinner():
            while not stop.is_set():
                try: self.ex.spin_once(timeout_sec=0.01)
                except Exception as e: errors.append(repr(e)); return
        th = threading.Thread(target=spinner); th.start()
        try:
            for k in range(60):
                s = self.node.create_subscription(String, '/bk/b', lambda m: got.__setitem__('b', got['b'] + 1), 10)
                pub_a.publish(String(data='a')); pub_b.publish(String(data='b')); time.sleep(0.01)
                self.assertTrue(self.node.destroy_subscription(s))
        finally:
            stop.set(); th.join(5)
        self.assertEqual(errors, []); self.assertGreater(got['a'], 30)
        s = self.node.create_subscription(String, '/bk/b', lambda m: got.__setitem__('b', got['b'] + 1000), 10); self.wait_matched(pub_b)
        before = got['b']; pub_b.publish(String(data='b'))
        self.assertTrue(spin_until(self.ex, lambda: got['b'] >= before + 1000))
        self.assertEqual(len(list(self.node.subscriptions)), 2)

    def test_dynamic_timer_fires_and_cancelled_timer_is_silent(self):
        fired = []; t = self.node.create_timer(0.02, lambda: fired.append(time.monotonic()))
        self.assertTrue(spin_until(self.ex, lambda: len(fired) >= 5)); t.cancel(); n = len(fired)
        end = time.monotonic() + 0.3
        while time.monotonic() < end: self.ex.spin_once(timeout_sec=0.02)
        self.assertEqual(len(fired), n); self.node.destroy_timer(t)

    def test_guard_condition_and_service_client(self):
        hits = []; g = self.node.create_guard_condition(lambda: hits.append(1))
        threading.Timer(0.05, g.trigger).start(); self.assertTrue(spin_until(self.ex, lambda: hits))
        srv = self.node.create_service(Trigger, '/bk/srv', lambda req, resp: (setattr(resp, 'success', True), resp)[1])
        cli = self.node.create_client(Trigger, '/bk/srv'); self.assertTrue(cli.wait_for_service(timeout_sec=5))
        fut = cli.call_async(Trigger.Request()); self.assertTrue(spin_until(self.ex, fut.done)); self.assertTrue(fut.result().success)
        self.node.destroy_client(cli); self.node.destroy_service(srv); self.node.destroy_guard_condition(g)


class QoSEvents(_Base):
    def test_incompatible_qos_events_reach_both_sides(self):
        sub_ev, pub_ev = [], []
        self.node.create_subscription(String, '/bk/q', lambda m: None, QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE),
                                      event_callbacks=SubscriptionEventCallbacks(incompatible_qos=sub_ev.append))
        self.node.create_publisher(String, '/bk/q', QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT),
                                   event_callbacks=PublisherEventCallbacks(incompatible_qos=pub_ev.append))
        self.assertTrue(spin_until(self.ex, lambda: sub_ev and pub_ev, 8), (len(sub_ev), len(pub_ev)))
        self.assertGreaterEqual(sub_ev[0].total_count, 1)

    def test_deadline_missed_event(self):
        missed = []; q = QoSProfile(depth=1, deadline=Duration(seconds=0.1))
        self.node.create_subscription(String, '/bk/dl', lambda m: None, q, event_callbacks=SubscriptionEventCallbacks(deadline=missed.append))
        p = self.node.create_publisher(String, '/bk/dl', q); self.wait_matched(p); p.publish(String(data='once'))
        self.assertTrue(spin_until(self.ex, lambda: len(missed) >= 2, 5))


class ShutdownAndCancellation(_Base):
    def test_executor_shutdown_from_another_thread(self):
        w = CountingWaitable(self.node); self.node.add_waitable(w)
        for i in range(20): self.node.create_subscription(String, '/bk/s%d' % i, lambda m: None, 10)
        th = threading.Thread(target=self.ex.spin); th.start(); time.sleep(0.3)
        t0 = time.monotonic(); self.assertTrue(self.ex.shutdown(timeout_sec=3)); th.join(3)
        self.assertFalse(th.is_alive()); self.assertLess(time.monotonic() - t0, 3)
        gc.collect(); self.assertEqual(w.enters, w.exits)

    def test_context_shutdown_stops_spin(self):
        errors = []
        def run():
            try: self.ex.spin()
            except Exception as e: errors.append(type(e).__name__)
        th = threading.Thread(target=run); th.start(); time.sleep(0.3)
        rclpy.shutdown(context=self.ctx); th.join(3)
        self.assertFalse(th.is_alive())
        self.assertTrue(errors == [] or errors == ['ExternalShutdownException'], errors)

    def test_cancelled_task_is_not_executed(self):
        ran = []
        async def coro(): ran.append(1)
        t = self.ex.create_task(coro); t.cancel()
        for _ in range(10): self.ex.spin_once(timeout_sec=0)
        self.assertEqual(ran, [])


class CallbackGroups(_Base):
    def test_mutually_exclusive_never_concurrent_reentrant_concurrent(self):
        mex = EX.MultiThreadedExecutor(num_threads=4, context=self.ctx); mex.add_node(self.node)
        state = {'me': 0, 'me_max': 0, 're': 0, 're_max': 0}; lk = threading.Lock(); done = []
        def cb(kind):
            def f(m):
                with lk: state[kind] += 1; state[kind + '_max'] = max(state[kind + '_max'], state[kind])
                time.sleep(0.02)
                with lk: state[kind] -= 1; done.append(kind)
            return f
        me, re_ = MutuallyExclusiveCallbackGroup(), ReentrantCallbackGroup()
        for i in range(3):
            self.node.create_subscription(Int32, '/bk/me%d' % i, cb('me'), 10, callback_group=me)
            self.node.create_subscription(Int32, '/bk/re%d' % i, cb('re'), 10, callback_group=re_)
        pubs = [self.node.create_publisher(Int32, '/bk/%s%d' % (k, i), 10) for k in ('me', 're') for i in range(3)]
        for p in pubs: self.wait_matched(p)
        th = threading.Thread(target=mex.spin); th.start()
        try:
            for k in range(5):
                for p in pubs: p.publish(Int32(data=k))
                time.sleep(0.01)
            end = time.monotonic() + 8
            while len(done) < 30 and time.monotonic() < end: time.sleep(0.05)
        finally:
            mex.shutdown(timeout_sec=3); th.join(3)
        self.assertEqual(len(done), 30); self.assertEqual(state['me_max'], 1); self.assertGreater(state['re_max'], 1)


if __name__ == '__main__':
    print('variant', VARIANT, EX.SHA[:12], 'python', __import__('sys').version.split()[0])
    unittest.main(verbosity=2)

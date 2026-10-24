"""Operation-level benchmark: CPU per executor wait cycle, live overlay vs variants, real rclpy entities.
Node shape mirrors atlas_web_status: N subscriptions (std_msgs/String), each with its default QoS event.
idle  : wait_for_ready_callbacks(timeout_sec=0) with nothing ready (full rebuild + TimeoutException)
one   : one message published, cycle until its callback ran (rebuild + take + dispatch)"""
import json, sys, time, types, hashlib
from pathlib import Path
import rclpy
import rclpy.exceptions as _rx
if not hasattr(_rx, 'TimerCancelledError'):   # rclpy 3.3.7 (py3.10 timing env) predates it; identical shim for every variant
    class TimerCancelledError(Exception): pass
    _rx.TimerCancelledError = TimerCancelledError
from rclpy.executors import TimeoutException
from std_msgs.msg import String

def load(path):
    src = Path(path).read_bytes(); m = types.ModuleType('atlas_variant_' + Path(path).stem); m.__file__ = str(path)
    exec(compile(src, str(path), 'exec'), m.__dict__); return m, hashlib.sha256(src).hexdigest()[:12]

def run(mod, n_subs, cycles, mode):
    ctx = rclpy.context.Context(); rclpy.init(context=ctx)
    node = rclpy.create_node('bk_status', context=ctx); got = [0]
    for i in range(n_subs):
        node.create_subscription(String, '/bk/t%d' % i, lambda m: got.__setitem__(0, got[0] + 1), 10)
    pub = node.create_publisher(String, '/bk/t0', 10)
    ex = mod.SingleThreadedExecutor(context=ctx); ex.add_node(node)
    t_end = time.time() + 5
    while pub.get_subscription_count() < 1 and time.time() < t_end: time.sleep(0.01)
    for _ in range(50):
        try: ex.spin_once(timeout_sec=0)
        except Exception: pass
    msg = String(data='x' * 120); w = len(list(node.waitables))
    c0 = time.thread_time(); p0 = time.process_time(); t0 = time.perf_counter(); done = 0
    if mode == 'idle':
        for _ in range(cycles):
            try: ex.wait_for_ready_callbacks(timeout_sec=0)
            except mod.TimeoutException: pass
        done = cycles
    else:
        for _ in range(cycles):
            target = got[0] + 1; pub.publish(msg)
            while got[0] < target: ex.spin_once(timeout_sec=1.0)
        done = got[0]
    c1 = time.thread_time(); p1 = time.process_time(); t1 = time.perf_counter()
    ex.shutdown(); node.destroy_node(); rclpy.shutdown(context=ctx)
    return {"cpu_us_per_cycle": 1e6 * (c1 - c0) / cycles, "proc_cpu_us_per_cycle": 1e6 * (p1 - p0) / cycles, 'wall_us_per_cycle': 1e6 * (t1 - t0) / cycles, 'waitables': w, 'done': done}

if __name__ == '__main__':
    a = json.loads(sys.argv[1]); mods = {v: load(p) for v, p in a['variants'].items()}; rows = []
    order = list(a['variants'])
    for pair in range(a['pairs']):
        seq = order if pair % 2 == 0 else order[::-1]
        for v in seq:
            r = run(mods[v][0], a['subs'], a['cycles'], a['mode']); r.update(variant=v, pair=pair, sha=mods[v][1]); rows.append(r)
    print(json.dumps({'python': sys.version.split()[0], 'rclpy': rclpy.__file__, 'args': a, 'rows': rows}))

"""PC construction-only ROS experiment. Never spins the application node."""
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
CAPTURE = REPO / 'artifacts/localization_cpu_20261024/monitor.py'
SOURCE_SHA = 'cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b'


def constructor_module(raw):
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('Captured monitor hash mismatch')
    tree = ast.parse(raw)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    # Only imports, local yaw function and Monitor class. No main operations.
    body = [n for n in main.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef))]
    if not any(isinstance(n, ast.ClassDef) and n.name == 'Monitor' for n in body):
        raise ValueError('Monitor missing')
    return ast.Module(body=body, type_ignores=[])


def isolation():
    if platform.machine().lower() not in ('x86_64', 'amd64'):
        raise RuntimeError('PC only')
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or os.environ.get('ROS_DOMAIN_ID') != '214':
        raise RuntimeError('Private localhost domain required')
    for key in ('ROS_DISCOVERY_SERVER', 'FASTRTPS_DEFAULT_PROFILES_FILE', 'FASTDDS_DEFAULT_PROFILES_FILE'):
        if os.environ.get(key):
            raise RuntimeError('External discovery/profile forbidden')


def child(arm):
    isolation()
    sys.path.insert(0, str(ROOT / 'scripts'))
    rows = []
    def timed(name, fn, *args, **kwargs):
        w, c = time.monotonic(), time.process_time()
        try:
            result = fn(*args, **kwargs)
        except BaseException:
            rows.append(dict(stage=name, wall_s=time.monotonic()-w, cpu_s=time.process_time()-c, failed=True))
            raise
        rows.append(dict(stage=name, wall_s=time.monotonic()-w, cpu_s=time.process_time()-c))
        return result
    import rclpy
    from rclpy.node import Node
    from rclpy.client import Client
    from rclpy.executors import SingleThreadedExecutor
    from std_msgs.msg import String
    def forbidden(*args, **kwargs):
        raise RuntimeError('Application service calls forbidden')
    Client.call = forbidden
    Client.call_async = forbidden
    timed('rclpy.init', rclpy.init)
    tx, rx = Node('startup_probe_tx'), Node('startup_probe_rx')
    pub = tx.create_publisher(String, '/startup_probe/mission', 10)
    sent, received = [], []
    phase = ['baseline']
    def send():
        row = dict(seq=len(sent), sent=time.monotonic(), phase=phase[0])
        sent.append(row)
        pub.publish(String(data=json.dumps(row)))
    def receive(msg):
        row = json.loads(msg.data)
        received.append(dict(row, received=time.monotonic()))
    tx.create_timer(1.0, send)
    rx.create_subscription(String, '/startup_probe/mission', receive, 10)
    ex = SingleThreadedExecutor()
    ex.add_node(tx); ex.add_node(rx)
    stop = threading.Event()
    def spin():
        while not stop.is_set():
            ex.spin_once(timeout_sec=.05)
    thread = threading.Thread(target=spin)
    thread.start()
    app = None
    try:
        time.sleep(2.5)
        if len(received) < 2:
            raise RuntimeError('Synthetic heartbeat discovery failed')
        phase[0] = 'construction'
        source = CAPTURE.read_bytes()
        module = timed('monitor_import', lambda: __import__('atlas_localization_monitor'))
        env = dict(module.__dict__)
        env['DEFAULT_MAP'] = ROOT / 'maps/atlas_latest.yaml'
        # Definitions only: no call to imported main, init, spin or reseed.
        exec(compile(constructor_module(source), '<captured-constructor>', 'exec'), env)
        for name in ('__init__', 'create_publisher', 'create_subscription', 'create_client', 'create_service', 'create_timer'):
            old = getattr(Node, name)
            def wrapper(self, *a, _old=old, _name=name, **kw):
                value = timed('Node.'+_name, _old, self, *a, **kw)
                if _name == 'create_timer':
                    value.cancel()  # application timers must never fire
                return value
            setattr(Node, name, wrapper)
        for name in ('load_map', '_search_index'):
            old = getattr(env['core'], name)
            setattr(env['core'], name, lambda *a, _old=old, _name=name, **kw: timed(_name, _old, *a, **kw))
        app = timed('Monitor.total', env['Monitor'])
        # The two production arms differ only AFTER construction. Do not spin
        # either one: doing so would invoke search/status/reseed callbacks.
        phase[0] = 'after_construction'
        time.sleep(3)
        timed('destroy_application', app.destroy_node)
        app = None
    finally:
        if app is not None:
            app.destroy_node()
        stop.set(); thread.join(2)
        ex.shutdown(timeout_sec=1)
        tx.destroy_node(); rx.destroy_node(); rclpy.try_shutdown()
    if thread.is_alive():
        raise RuntimeError('Heartbeat thread did not stop')
    seqs = [r['seq'] for r in received]
    expected = list(range(len(sent)))
    if seqs != expected:
        raise RuntimeError('Missing/duplicate synthetic heartbeat')
    gaps = [b['received']-a['received'] for a,b in zip(received,received[1:])]
    latencies = [r['received']-r['sent'] for r in received]
    import resource
    result = dict(arm=arm, stages=rows, sent=sent, received=received,
                  maximum_receive_gap_s=max(gaps), maximum_delivery_s=max(latencies),
                  stale_gaps_over_2s=sum(x>2 for x in gaps), rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  app_spun=False, service_calls_allowed=False, source_sha256=SOURCE_SHA,
                  scheduler_wait='not attributed', jetson_cgroup_quota_reproduced=False)
    print(json.dumps(result))


def main():
    isolation()
    if len(sys.argv) == 3 and sys.argv[1] == '--child' and sys.argv[2] in ('original', 'candidate'):
        child(sys.argv[2]); return
    if len(sys.argv) != 1:
        raise ValueError('Invalid arguments')
    # Separate interpreters/homes; original/candidate share the exact constructor.
    results = []
    for arm in ('original', 'candidate'):
        home = tempfile.mkdtemp(prefix='atlas-startup-pc-')
        env = dict(os.environ, HOME=home)
        run = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', arm],
                             env=env, capture_output=True, text=True, timeout=30)
        if run.returncode:
            raise RuntimeError(run.stdout+run.stderr)  # no retry
        result = json.loads(run.stdout)
        result['isolated_home'] = home
        results.append(result)
    print(json.dumps(dict(scope='PC construction only, synthetic heartbeat, no production access', runs=results), indent=2))


if __name__ == '__main__':
    main()

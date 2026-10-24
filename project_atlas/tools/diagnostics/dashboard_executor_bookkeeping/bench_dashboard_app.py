"""Application-level A/B: the EXACT live atlas_status_web.py ROS layer (imported; HTTP server not started)
under replayed live-rate traffic, with only the Dashboard executor overlay swapped.

  driver <out.json> <pairs> <warm_s> <measure_s> <tree_v0> <tree_cand>   (run inside a private netns)
  pub <tree>                                                            (synthetic live-rate publishers + probes)
  sub <tree> <warm_s> <measure_s>                                       (one measured run, prints JSON)
"""
import json, os, subprocess, sys, threading, time
from pathlib import Path
os.environ.setdefault('ROS_DOMAIN_ID', '216'); assert os.environ['ROS_DOMAIN_ID'] not in ('0', '77')
PROBES = {'/atlas/control_policy': 'control_policy', '/atlas/health': 'atlas_health'}   # hot node / status node

def compat():
    import rclpy.exceptions as rx
    if not hasattr(rx, 'TimerCancelledError'):      # rclpy 3.3.7 timing env only; identical for every variant
        class TimerCancelledError(Exception): pass
        rx.TimerCancelledError = TimerCancelledError

def pub(tree):
    compat(); sys.path.insert(0, str(Path(tree) / 'tools' / 'perf'))
    import bench_status_executor as B, rclpy
    from std_msgs.msg import String
    B.RATES['/atlas/health'] = 2.0
    rclpy.init(); n = rclpy.create_node('bench_pub'); ex = B.SingleThreadedExecutor(); ex.add_node(n)
    for t, typ in B.topic_list():
        hz = B.RATES.get(t, 0.0)
        if hz <= 0: continue
        p = n.create_publisher(B.TYPES[typ], t, B.qos_profile_sensor_data if t == '/scan' else 10)
        if t in PROBES:
            def probe(p=p):
                p.publish(String(data=json.dumps({'probe_t': time.time(), 'pad': 'x' * 380})))
            n.create_timer(1.0 / hz, probe)
        else:
            msg = B.sample(t, typ); n.create_timer(1.0 / hz, lambda p=p, m=msg: p.publish(m))
    tfp = n.create_publisher(B.TFMessage, '/tf', 100)
    def tf():
        a = B.TransformStamped(); a.header.frame_id, a.child_frame_id = 'odom', 'base_link'; a.header.stamp = n.get_clock().now().to_msg(); a.transform.rotation.w = 1.0
        b = B.TransformStamped(); b.header.frame_id, b.child_frame_id = 'map', 'odom'; b.header.stamp = a.header.stamp; b.transform.rotation.w = 1.0
        tfp.publish(B.TFMessage(transforms=[a, b]))
    n.create_timer(1.0 / B.TF_HZ, tf)
    print('PUB READY', flush=True); ex.spin()

def task_cpu(tid):
    f = open('/proc/self/task/%d/stat' % tid).read().rsplit(')', 1)[1].split()
    return (int(f[11]) + int(f[12])) / os.sysconf('SC_CLK_TCK')

def proc_cpu():
    f = open('/proc/self/stat').read().rsplit(')', 1)[1].split()
    return (int(f[11]) + int(f[12])) / os.sysconf('SC_CLK_TCK')

def sub(tree, warm, seconds):
    compat(); scripts = Path(tree) / 'scripts'; sys.path.insert(0, str(scripts)); os.chdir(scripts)
    import atlas_status_web as W
    R = W.ROS; counts = {}; lat = {k: [] for k in PROBES.values()}; lock = threading.Lock(); measuring = [False]
    orig_set = R._set
    def counting_set(key, value):
        if measuring[0]:
            now = time.time()
            with lock:
                counts[key] = counts.get(key, 0) + 1
                if key in lat and isinstance(value, str) and value.startswith('{"probe_t"'):
                    lat[key].append(now - json.loads(value)['probe_t'])
        return orig_set(key, value)
    R._set = counting_set
    t_end = time.time() + 20
    while (R.node is None or R.status_node is None) and time.time() < t_end: time.sleep(0.05)
    time.sleep(1.0)
    periods = {}
    for i, tm in enumerate(list(R.node.timers)):                 # dashboard timers (drive watchdog, map pose, camera tick)
        key = 'timer%d_%.2fs' % (i, tm.timer_period_ns / 1e9); periods[key] = []; cb = tm.callback; last = [None]
        def wrapped(cb=cb, key=key, last=last):
            now = time.monotonic()
            if measuring[0] and last[0] is not None: periods[key].append(now - last[0])
            last[0] = now; return cb()
        tm.callback = wrapped
    time.sleep(warm)
    threads = {t.name: t.native_id for t in threading.enumerate()}
    spin = [v for k, v in threads.items() if '(_spin)' in k]; status = threads.get('atlas-web-status-spin')
    assert spin and status, threads
    c0, s0, st0, w0 = proc_cpu(), task_cpu(spin[0]), task_cpu(status), time.monotonic(); measuring[0] = True
    time.sleep(seconds)
    measuring[0] = False; c1, s1, st1, w1 = proc_cpu(), task_cpu(spin[0]), task_cpu(status), time.monotonic()
    dt = w1 - w0
    def pct(v, q):
        v = sorted(v); return v[min(len(v) - 1, int(q * len(v)))] * 1000 if v else None
    out = {'overlay_sha': __import__('hashlib').sha256((scripts / 'atlas_dashboard_executor_impl.py').read_bytes()).hexdigest()[:12],
           'seconds': dt, 'proc_cpu_pct': 100 * (c1 - c0) / dt, 'control_thread_pct': 100 * (s1 - s0) / dt, 'status_thread_pct': 100 * (st1 - st0) / dt,
           'msgs': sum(counts.values()), 'msgs_per_s': sum(counts.values()) / dt, 'keys': len(counts), 'counts': counts,
           'latency_ms': {k: {'n': len(v), 'p50': pct(v, .5), 'p95': pct(v, .95), 'max': pct(v, 1.0)} for k, v in lat.items()},
           'timer_period_ms': {k: {'n': len(v), 'p50': pct(v, .5), 'max': pct(v, 1.0)} for k, v in periods.items()},
           'web_error': (R.data.get('web_error') or {}).get('value')}
    print('RESULT ' + json.dumps(out), flush=True); os._exit(0)

def driver(out, pairs, warm, seconds, tree_a, tree_b):
    env = dict(os.environ); p = subprocess.Popen([sys.executable, '-I', '-B', __file__, 'pub', tree_a], env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    t_ready = time.time() + 30
    while time.time() < t_ready:
        line = p.stdout.readline()
        if 'PUB READY' in line: break
    else:
        raise SystemExit('publisher not ready')
    threading.Thread(target=lambda: [None for _ in p.stdout], daemon=True).start()   # keep draining
    time.sleep(3); rows = []
    try:
        for pair in range(pairs):
            seq = [('v0', tree_a), ('cand', tree_b)] if pair % 2 == 0 else [('cand', tree_b), ('v0', tree_a)]
            for name, tree in seq:
                r = subprocess.run([sys.executable, '-I', '-B', __file__, 'sub', tree, str(warm), str(seconds)], env=env, capture_output=True, text=True, timeout=warm + seconds + 60)
                line = [l for l in r.stdout.splitlines() if l.startswith('RESULT ')]
                row = json.loads(line[0][7:]) if line else {'error': r.stderr[-800:]}
                row.update(variant=name, pair=pair); rows.append(row)
                print(pair, name, {k: round(row[k], 1) for k in ('proc_cpu_pct', 'control_thread_pct', 'status_thread_pct', 'msgs_per_s') if k in row}, flush=True)
                Path(out).write_text(json.dumps({'python': sys.version.split()[0], 'rows': rows}, indent=1))
    finally:
        p.terminate(); p.wait(5)

if __name__ == '__main__':
    m = sys.argv[1]
    if m == 'pub': pub(sys.argv[2])
    elif m == 'sub': sub(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]))
    else: driver(sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), sys.argv[6], sys.argv[7])

"""Safety adapter for the existing named-place dry-run; no production control."""
import ctypes
import json
import math
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
from collections import deque

LIMIT_S = 30
MAX_AGE = 1.0

def stamp_seconds(msg):
    s = msg.header.stamp
    if type(s.sec) is not int or type(s.nanosec) is not int or not 0 <= s.nanosec < 1000000000:
        raise ValueError('invalid sensor stamp')
    return s.sec + s.nanosec / 1e9

def require_fresh(msg, now, previous=None):
    stamp = stamp_seconds(msg)
    if not math.isfinite(now) or stamp <= 0 or not 0 <= now - stamp <= MAX_AGE:
        raise ValueError('stale/future sensor stamp')
    if previous is not None and stamp <= previous:
        raise ValueError('duplicate/backward sensor stamp')
    if not msg.header.frame_id:
        raise ValueError('missing sensor frame')
    return stamp

def require_transform(t, scan_frame):
    if t.header.frame_id != 'base_link' or t.child_frame_id != scan_frame:
        raise ValueError('unexpected TF frames')
    v, q = t.transform.translation, t.transform.rotation
    vals = [v.x, v.y, v.z, q.x, q.y, q.z, q.w]
    if not all(math.isfinite(x) for x in vals) or abs(sum(x*x for x in vals[3:])-1) > .001:
        raise ValueError('invalid TF geometry')
    return v.x, v.y, math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))

class StrictInputs:
    """One seeder node's subscriptions stay observed while matching runs."""
    def __init__(self, node, heartbeat):
        import rclpy
        from sensor_msgs.msg import LaserScan
        from nav_msgs.msg import Odometry
        from rclpy.qos import qos_profile_sensor_data
        from tf2_ros import Buffer, TransformListener
        self.node, self.heartbeat = node, heartbeat
        self.scans = deque(maxlen=80)
        self.last, self.arrival = {}, {}
        self.error = None
        self.thread = None
        self.stop = threading.Event()
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, node)
        self.subs = [node.create_subscription(LaserScan, '/scan', lambda m:self.receive('scan',m), qos_profile_sensor_data),
                     node.create_subscription(Odometry, '/odom', lambda m:self.receive('odom',m), 10)]

    def receive(self, key, msg):
        try:
            now = self.node.get_clock().now().nanoseconds / 1e9
            stamp = require_fresh(msg, now, self.last.get(key))
            if key == 'odom':
                if msg.header.frame_id != 'odom' or msg.child_frame_id != 'base_link':
                    raise ValueError('invalid odometry frames')
                t = msg.twist.twist
                values = [t.linear.x,t.linear.y,t.linear.z,t.angular.x,t.angular.y,t.angular.z]
                if any(not math.isfinite(v) for v in values) or any(abs(v) > .01 for v in values[:3]) or any(abs(v) > .02 for v in values[3:]):
                    raise ValueError('motion/invalid odometry')
            else:
                if len(msg.ranges) > 4096 or not math.isfinite(msg.angle_min) or not math.isfinite(msg.angle_increment) or msg.angle_increment == 0:
                    raise ValueError('invalid scan dimensions')
                self.scans.append(msg)
            self.last[key], self.arrival[key] = stamp, time.monotonic()
        except Exception as exc:
            self.error = str(exc)

    def check(self):
        from rclpy.time import Time
        from rclpy.duration import Duration
        if self.error: raise ValueError(self.error)
        now = self.node.get_clock().now().nanoseconds / 1e9
        if set(self.last) != {'scan','odom'}: raise ValueError('missing scan/odometry')
        if any(not 0 <= now-s <= MAX_AGE for s in self.last.values()) or any(not 0 <= time.monotonic()-s <= MAX_AGE for s in self.arrival.values()):
            raise ValueError('stale scan/odometry')
        scan = self.scans[-1]
        # Exact scan-time query validates dynamic TF; static TF is valid at all times.
        tf = self.buffer.lookup_transform('base_link', scan.header.frame_id, Time.from_msg(scan.header.stamp), timeout=Duration(seconds=0))
        result = require_transform(tf, scan.header.frame_id)
        self.heartbeat.value = time.monotonic()
        return result

    def collect(self):
        import rclpy
        start = time.monotonic()
        while time.monotonic()-start < 3.0:
            rclpy.spin_once(self.node, timeout_sec=.05)
            if self.error: raise ValueError(self.error)
            if self.last and time.monotonic()-start > 1.0: self.check()
        self.check()
        if len(self.scans) < 5: raise ValueError('too few fresh scans')
        scans = list(self.scans)
        def watch():
            try:
                while not self.stop.is_set():
                    rclpy.spin_once(self.node, timeout_sec=.05)
                    self.check()
            except Exception as exc:
                self.error = str(exc)
                self.heartbeat.value = -1
        self.thread = threading.Thread(target=watch, daemon=True)
        self.thread.start()
        return scans, None

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=.5)
            if self.thread.is_alive(): raise RuntimeError('sensor observer did not stop')
        for sub in self.subs: self.node.destroy_subscription(sub)
        self.listener.unregister()

def worker(seeder, args, region, output, heartbeat, parent):
    # OS deadline also terminates native matching; parent death cannot orphan it.
    if ctypes.CDLL(None).prctl(1, signal.SIGKILL) != 0 or os.getppid() != parent: os._exit(125)
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, LIMIT_S)
    node = inputs = None
    result = dict(state='UNKNOWN', seeded=False, navigation_authorized=False)
    try:
        seeder.rclpy.init()
        node = seeder.Node('atlas_localization_seeder')
        inputs = StrictInputs(node, heartbeat)
        _, result = seeder.verify_start_pose(node, args.map, attempts=1, budget_s=LIMIT_S, region=region, strict_inputs=inputs)
        inputs.check()
        result.update(dry_run=True, seeded=False, navigation_authorized=False)
    except Exception as exc: result.update(state='UNKNOWN', reason=str(exc))
    finally:
        try:
            if inputs: inputs.close()
            if node: node.destroy_node()
            if seeder.rclpy.ok(): seeder.rclpy.shutdown()
        except Exception as exc: result.update(state='UNKNOWN', reason='cleanup: '+str(exc))
        Path(output).write_text(json.dumps(result, allow_nan=False))


def run(seeder, args, region):
    # Existing bounded safety requests, CPU counters and child cleanup, no new ROS observer.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
    import snapshot_benchmark_once as guard
    from stationary_gate import ticks, cpu_delta
    import subprocess
    result = dict(state='UNKNOWN', seeded=False, navigation_authorized=False, dry_run=True)
    samples = []
    child = None
    if signal.getitimer(signal.ITIMER_REAL)[0]:
        raise RuntimeError("existing alarm conflicts with dry-run deadline")
    deadline = time.monotonic() + LIMIT_S + 2
    previous = [ticks(), time.monotonic()]
    def sample():
        now = time.monotonic(); cur = ticks(); dt = now-previous[1]
        if not .9 <= dt <= 1.1: raise ValueError('invalid CPU interval')
        cpu = cpu_delta(previous[0],cur); previous[:] = [cur,now]
        if cpu >= 75: raise ValueError('CPU admission/guard')
        ram, temp = guard.resources()
        if ram >= 80: raise ValueError('RAM admission/guard')
        began=time.monotonic()
        if deadline-began < .5: raise TimeoutError('overall deadline')
        try:
            status=guard.fetch('/api/status')
        finally:
            # Existing fetch uses its own bounded .5s alarm; restore absolute deadline.
            signal.setitimer(signal.ITIMER_REAL, max(.000001,deadline-time.monotonic()))
        row=guard.validate(status,cpu,ram,temp,time.monotonic()-began)
        row.update(monotonic=now, unix=time.time()); samples.append(row)
        if child is not None and child.poll() is None and now-launched[0] > 1.8:
            age=now-heartbeat.value
            if not 0 <= age <= 1.0: raise ValueError('sensor/TF observer failed or stale')
        return row
    class Child:
        def __init__(self,p): self.p=p
        @property
        def returncode(self): return self.p.exitcode
        def poll(self): return self.p.exitcode
        def terminate(self): self.p.terminate()
        def kill(self): self.p.kill()
        def wait(self,timeout):
            self.p.join(timeout)
            if self.p.is_alive(): raise subprocess.TimeoutExpired('dry-run',timeout)
            return self.p.exitcode
    old_handlers={s:signal.signal(s,guard.fail_signal) for s in (signal.SIGTERM,signal.SIGINT,signal.SIGALRM)}
    signal.setitimer(signal.ITIMER_REAL, max(.000001,deadline-time.monotonic()))
    with tempfile.TemporaryDirectory(prefix='atlas-place-dry-') as tmp:
        try:
            guard.run_window(sample,None,1)
            ctx=multiprocessing.get_context('fork'); heartbeat=ctx.Value('d',time.monotonic()); launched=[0.]
            def launch():
                nonlocal child
                launched[0]=time.monotonic()
                p=ctx.Process(target=worker,args=(seeder,args,region,str(Path(tmp)/'result.json'),heartbeat,os.getpid()))
                p.start(); child=Child(p); return child
            # Continue the counter interval across preflight API/launch overhead.
            # The helper first reads its cadence origin, then the real clock.
            origin = [previous[1]]
            def cadence_clock():
                return origin.pop() if origin else time.monotonic()
            guard.run_window(sample,launch,LIMIT_S,clock=cadence_clock)
            raw=(Path(tmp)/'result.json').read_bytes()
            if len(raw)>1024*1024: raise ValueError('result size bound')
            result=json.loads(raw)
            if result.get('seeded') is not False or result.get('navigation_authorized') is not False: raise ValueError('invalid dry result')
        except BaseException as exc:
            result=dict(state='UNKNOWN',reason=str(exc),dry_run=True,seeded=False,navigation_authorized=False)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            try: guard.terminate(child)
            finally:
                for s,h in old_handlers.items(): signal.signal(s,h)
    result.update(safety_samples=samples, finished_unix=time.time())
    print(json.dumps(result,allow_nan=False,indent=2))
    return result
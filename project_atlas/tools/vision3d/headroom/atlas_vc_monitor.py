#!/usr/bin/env python3
"""Read-only Visual Cloud / ROS timing monitor (24 Oct 2026). Subscriptions only; never publishes, never signals or
restarts anything. One JSON line per second: whole-Jetson CPU, runnable, RAM, temperature, per-service cgroup CPU and
memory (incl. both Visual Cloud units), top-8 processes by CPU, subscriber counts + subscriber node names on key topics
(shows when Visual Cloud subscribes/unsubscribes), max inter-arrival gap and age of critical topics, E-STOP/policy.
usage: atlas_vc_monitor.py <out.jsonl> <duration_s>"""
import json, os, sys, time, glob
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan, Imu
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from tf2_msgs.msg import TFMessage
from nav_msgs.msg import OccupancyGrid

OUT, DURATION = Path(sys.argv[1]), float(sys.argv[2])
UID = os.getuid(); CG = '/sys/fs/cgroup/user.slice/user-%d.slice/user@%d.service/app.slice' % (UID, UID)
SERVICES = ('atlas-visual-cloud-agent', 'atlas-visual-cloud-server', 'rover-status-web', 'rover-base-telemetry', 'atlas-lidar',
            'atlas-im10a', 'atlas-cmd-vel-mux', 'atlas-localization', 'atlas-safety-status', 'atlas-camera', 'atlas-voice-companion',
            'atlas-ekf', 'atlas-lidar-odom', 'atlas-localization-monitor')
WATCH_SUBS = ('/scan', '/tf', '/odom', '/yahboom/odom', '/global_costmap/costmap', '/local_costmap/costmap', '/map', '/cmd_vel')
HZ = os.sysconf('SC_CLK_TCK')


def stat():
    a = list(map(int, open('/proc/stat').readline().split()[1:9])); return sum(a), a[3] + a[4]


def runnable():
    for l in open('/proc/stat'):
        if l.startswith('procs_running'): return int(l.split()[1])


def cg(u, f):
    try:
        if f == 'cpu':
            for l in open('%s/%s.service/cpu.stat' % (CG, u)):
                if l.startswith('usage_usec'): return int(l.split()[1])
        return int(open('%s/%s.service/memory.current' % (CG, u)).read())
    except (OSError, ValueError): return None


def procs():
    out = {}
    for d in os.listdir('/proc'):
        if d.isdigit():
            try:
                s = open('/proc/%s/stat' % d).read(); name = s[s.index('(') + 1:s.rindex(')')]; f = s.rsplit(')', 1)[1].split()
                out[int(d)] = (name, int(f[11]) + int(f[12]))
            except (OSError, ValueError, IndexError): pass
    return out


def cmdline(pid):
    try: return open('/proc/%d/cmdline' % pid, 'rb').read().replace(b'\0', b' ').decode(errors='replace')[:90]
    except OSError: return ''


def mem():
    m = {l.split(':')[0]: int(l.split()[1]) for l in open('/proc/meminfo')}
    return round(100.0 * (m['MemTotal'] - m['MemAvailable']) / m['MemTotal'], 1)


def temp():
    v = []
    for z in glob.glob('/sys/class/thermal/thermal_zone*'):
        try:
            if open(z + '/type').read().strip() in ('cpu-thermal', 'gpu-thermal', 'soc0-thermal', 'soc1-thermal', 'soc2-thermal', 'tj-thermal'):
                v.append(int(open(z + '/temp').read()) / 1000)
        except OSError: pass
    return max(v) if v else None


class Mon(Node):
    TOPICS = {'/scan': (LaserScan, qos_profile_sensor_data), '/yahboom/imu/data_calibrated': (Imu, qos_profile_sensor_data),
              '/atlas/encoder_update': (String, 10), '/atlas/control_policy': (String, 10), '/cmd_vel': (Twist, 10),
              '/atlas/safety_status': (String, 10), '/tf': (TFMessage, 10), '/local_costmap/costmap': (OccupancyGrid, 1)}

    def __init__(self):
        super().__init__('atlas_vc_monitor')
        self.last, self.maxgap, self.count, self.policy, self.nonzero = {}, {}, {}, None, False
        for t, (cls, q) in self.TOPICS.items():
            self.create_subscription(cls, t, self.cb(t), q, raw=t in ('/tf', '/local_costmap/costmap', '/scan'))

    def cb(self, t):
        def f(m):
            now = time.monotonic(); p = self.last.get(t)
            if p is not None: self.maxgap[t] = max(self.maxgap.get(t, 0.0), now - p)
            self.last[t] = now; self.count[t] = self.count.get(t, 0) + 1
            if t == '/atlas/control_policy':
                try: self.policy = json.loads(m.data)
                except ValueError: self.policy = None
            elif t == '/cmd_vel':
                self.nonzero = any(abs(v) > 1e-9 for v in (m.linear.x, m.linear.y, m.linear.z, m.angular.x, m.angular.y, m.angular.z))
        return f


def main():
    rclpy.init(); n = Mon(); end = time.monotonic() + DURATION; out = OUT.open('a')
    out.write(json.dumps({'event': 'start', 'unix': time.time()}) + '\n'); out.flush()
    s0, t0 = stat(), time.monotonic(); c0 = {u: cg(u, 'cpu') for u in SERVICES}; p0 = procs()
    while rclpy.ok() and time.monotonic() < end:
        tick = time.monotonic() + 1.0
        while time.monotonic() < tick: rclpy.spin_once(n, timeout_sec=max(0.0, tick - time.monotonic()))
        now = time.monotonic(); s1 = stat(); dt = now - t0; c1 = {u: cg(u, 'cpu') for u in SERVICES}; p1 = procs()
        top = sorted(((100.0 * (p1[k][1] - p0[k][1]) / HZ / dt, k) for k in p1 if k in p0 and p0[k][0] == p1[k][0]), reverse=True)[:8]
        subs = {}
        for t in WATCH_SUBS:
            try: subs[t] = sorted(i.node_name for i in n.get_subscriptions_info_by_topic(t))
            except Exception: subs[t] = None
        p = n.policy or {}
        row = {'unix': round(time.time(), 2), 'cpu': round(100.0 * ((s1[0] - s0[0]) - (s1[1] - s0[1])) / max(1, s1[0] - s0[0]), 1),
               'runnable': runnable(), 'ram': mem(), 'temp': temp(),
               'svc': {u: round((c1[u] - c0[u]) / 1e4 / dt, 1) for u in SERVICES if c1[u] is not None and c0[u] is not None},
               'vc_mem_mb': {u: round((cg(u, 'mem') or 0) / 1048576, 1) for u in ('atlas-visual-cloud-agent', 'atlas-visual-cloud-server')},
               'top': [[round(c, 1), k, p1[k][0], cmdline(k)] for c, k in top],
               'vc_subscribed': sorted(t for t, v in subs.items() if v and 'atlas_visual_cloud_agent' in v),
               'sub_counts': {t: (len(v) if v is not None else None) for t, v in subs.items()},
               'age': {t: (round(now - n.last[t], 3) if t in n.last else None) for t in Mon.TOPICS},
               'maxgap': {t: round(v, 3) for t, v in n.maxgap.items()}, 'msgs': dict(n.count),
               'estop_latched': p.get('stop_latched'), 'manual_only': p.get('manual_only'), 'commission_armed': p.get('commission_armed'),
               'cmd_nonzero': n.nonzero}
        n.maxgap, n.count = {}, {}
        out.write(json.dumps(row) + '\n'); out.flush(); s0, t0, c0, p0 = s1, now, c1, p1
    out.write(json.dumps({'event': 'end', 'unix': time.time()}) + '\n'); out.close(); n.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()

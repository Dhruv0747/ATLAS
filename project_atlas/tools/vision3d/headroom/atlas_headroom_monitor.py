#!/usr/bin/env python3
"""ATLAS headroom monitor for ONE supervised Depth session (24 Oct 2026). Read-only on ROS (subscriptions only).

Every 1 s writes one JSON line: whole-Jetson CPU, runnable tasks (scheduler pressure), RAM, max temperature,
cgroup CPU of key services, CPU of the Astra driver / Vision Lab worker, and the max inter-arrival gap of
critical topics. Safety watchdog: if a critical deadline is missed, E-STOP unlatches, commissioning arms, a nonzero
motor command appears, or RAM/temperature limits fail, it SIGTERMs the Vision Lab worker (its normal cleanup path stops
the driver) and records why. It never publishes, never commands motion and never restarts anything.
usage: atlas_headroom_monitor.py <out.jsonl> <duration_s>
"""
import json, math, os, signal, sys, time, glob
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan, Imu
from std_msgs.msg import String
from geometry_msgs.msg import Twist

OUT, DURATION = Path(sys.argv[1]), float(sys.argv[2])
STATE = Path('/run/user/%d/atlas-vision3d-viewer.json' % os.getuid())
CG = '/sys/fs/cgroup/user.slice/user-%d.slice/user@%d.service/app.slice' % (os.getuid(), os.getuid())
SERVICES = ('rover-status-web', 'rover-base-telemetry', 'atlas-lidar', 'atlas-im10a', 'atlas-cmd-vel-mux', 'atlas-localization',
            'atlas-safety-status', 'atlas-camera', 'atlas-voice-companion', 'atlas-visual-cloud-agent')
# Stop limits (gap = time since last message). Baseline-verified before the session.
LIMITS = {'/scan': 1.0, '/yahboom/imu/data_calibrated': 0.5, '/atlas/encoder_update': 0.5, '/atlas/control_policy': 2.0}
TICK = os.sysconf('SC_CLK_TCK')


def stat():
    a = list(map(int, open('/proc/stat').readline().split()[1:9])); return sum(a), a[3] + a[4]


def runnable():
    for l in open('/proc/stat'):
        if l.startswith('procs_running'): return int(l.split()[1])


def cg_usec(u):
    try:
        for l in open('%s/%s.service/cpu.stat' % (CG, u)):
            if l.startswith('usage_usec'): return int(l.split()[1])
    except OSError: return None


def proc_ticks(pid):
    try: f = open('/proc/%d/stat' % pid).read().rsplit(')', 1)[1].split(); return int(f[11]) + int(f[12])
    except (OSError, ValueError, IndexError): return None


def ram_pct():
    m = {l.split(':')[0]: int(l.split()[1]) for l in open('/proc/meminfo')}
    return 100.0 * (m['MemTotal'] - m['MemAvailable']) / m['MemTotal']


def temp_max():
    vals = []
    for z in glob.glob('/sys/class/thermal/thermal_zone*'):
        try:
            if open(z + '/type').read().strip() in ('cpu-thermal', 'gpu-thermal', 'soc0-thermal', 'soc1-thermal', 'soc2-thermal', 'tj-thermal'):
                vals.append(int(open(z + '/temp').read()) / 1000)
        except OSError: pass
    return max(vals) if vals else None


class Mon(Node):
    def __init__(self):
        super().__init__('atlas_headroom_monitor')
        self.last = {}; self.maxgap = {}; self.policy = None; self.cmd_nonzero = False
        def cb(topic):
            def f(msg):
                now = time.monotonic(); prev = self.last.get(topic)
                if prev is not None: self.maxgap[topic] = max(self.maxgap.get(topic, 0.0), now - prev)
                self.last[topic] = now
                if topic == '/atlas/control_policy':
                    try: self.policy = json.loads(msg.data)
                    except ValueError: self.policy = None
                if topic == '/cmd_vel':
                    self.cmd_nonzero = any(abs(v) > 1e-9 for v in (msg.linear.x, msg.linear.y, msg.linear.z, msg.angular.x, msg.angular.y, msg.angular.z))
            return f
        self.create_subscription(LaserScan, '/scan', cb('/scan'), qos_profile_sensor_data)
        self.create_subscription(Imu, '/yahboom/imu/data_calibrated', cb('/yahboom/imu/data_calibrated'), qos_profile_sensor_data)
        self.create_subscription(String, '/atlas/encoder_update', cb('/atlas/encoder_update'), 10)
        self.create_subscription(String, '/atlas/control_policy', cb('/atlas/control_policy'), 10)
        self.create_subscription(Twist, '/cmd_vel', cb('/cmd_vel'), 10)


def main():
    rclpy.init(); n = Mon(); t_end = time.monotonic() + DURATION
    s0 = stat(); cg0 = {u: cg_usec(u) for u in SERVICES}; p0 = {}; t0 = time.monotonic(); stopped = False
    out = OUT.open('a')
    out.write(json.dumps({'event': 'monitor_start', 'unix': time.time(), 'limits': LIMITS, 'pid': os.getpid()}) + '\n'); out.flush()
    while rclpy.ok() and time.monotonic() < t_end:
        tick_end = time.monotonic() + 1.0
        while time.monotonic() < tick_end: rclpy.spin_once(n, timeout_sec=max(0.0, tick_end - time.monotonic()))
        now = time.monotonic(); s1 = stat(); dt = now - t0
        row = {'unix': round(time.time(), 2), 'cpu': round(100.0 * ((s1[0] - s0[0]) - (s1[1] - s0[1])) / max(1, s1[0] - s0[0]), 1),
               'runnable': runnable(), 'load1': float(open('/proc/loadavg').read().split()[0]), 'ram': round(ram_pct(), 1), 'temp': temp_max()}
        cg1 = {u: cg_usec(u) for u in SERVICES}
        row['svc'] = {u: round((cg1[u] - cg0[u]) / 1e4 / dt, 1) for u in SERVICES if cg1[u] is not None and cg0[u] is not None}
        try: st = json.loads(STATE.read_text())
        except (OSError, ValueError): st = {}
        row['vl_state'] = st.get('state'); row['vl_cpu_policy'] = (st.get('cpu_policy') or '')[:12]
        for key, pid in (('astra', st.get('driver_pid')), ('worker', st.get('worker_pid'))):
            if pid and st.get('state') in ('CHECKING', 'ACTIVE'):
                t = proc_ticks(pid)
                if t is not None and p0.get(key, (None, None))[0] == pid: row[key + '_cpu'] = round(100.0 * (t - p0[key][1]) / TICK / dt, 1)
                if t is not None: p0[key] = (pid, t)
        ages = {k: (round(now - n.last[k], 3) if k in n.last else None) for k in list(LIMITS) + ['/cmd_vel']}
        row['age'] = ages; row['maxgap'] = {k: round(v, 3) for k, v in n.maxgap.items()}; n.maxgap = {}
        p = n.policy or {}
        row['estop_latched'] = p.get('stop_latched'); row['manual_only'] = p.get('manual_only'); row['commission_armed'] = p.get('commission_armed')
        row['cmd_nonzero'] = n.cmd_nonzero
        why = [k for k, lim in LIMITS.items() if ages[k] is None or ages[k] > lim or row['maxgap'].get(k, 0) > lim]
        if p and (p.get('stop_latched') is not True or p.get('manual_only') is not True or p.get('commission_armed') is not False): why.append('policy')
        if n.cmd_nonzero: why.append('cmd_vel nonzero')
        if row['ram'] > 80: why.append('ram')
        if row['temp'] is not None and row['temp'] > 70: why.append('temperature')
        row['violations'] = why
        if why and st.get('state') in ('CHECKING', 'ACTIVE') and st.get('worker_pid') and not stopped:
            try: os.kill(int(st['worker_pid']), signal.SIGTERM); row['action'] = 'SIGTERM worker %s' % st['worker_pid']
            except OSError as e: row['action'] = 'kill failed: %s' % e
            stopped = True
        out.write(json.dumps(row) + '\n'); out.flush()
        s0, cg0, t0 = s1, cg1, now
    out.write(json.dumps({'event': 'monitor_end', 'unix': time.time()}) + '\n'); out.close()
    n.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()

"""Track A G5 stage 2: READ-ONLY monitor while the owner sends a Nav2 goal. Publishes nothing.
Logs goals, goal status, global plans, Nav2 speed commands, odometry and status events to stdout (domain 0)."""
import json, math, sys, time, urllib.request
import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, qos_profile_sensor_data
from geometry_msgs.msg import Twist, PoseStamped
from nav_msgs.msg import Path, Odometry
from action_msgs.msg import GoalStatusArray
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 180
rclpy.init(); n = rclpy.create_node('track_a_g5_drive_monitor')
t0 = time.time()
def log(*a): print(f'{time.time()-t0:6.1f}s', *a, flush=True)
last = {}
def twist(name):
    def cb(m):
        nz = abs(m.linear.x) > 1e-3 or abs(m.angular.z) > 1e-3
        key = (round(m.linear.x, 2), round(m.angular.z, 2))
        if nz or last.get(name) != key: log(f'{name}: lin {m.linear.x:+.3f} ang {m.angular.z:+.3f}')
        last[name] = key
    return cb
for t in ('/cmd_vel', '/cmd_vel_nav', '/cmd_vel_smoothed', '/cmd_vel_mux_out'):
    n.create_subscription(Twist, t, twist(t), 10)
n.create_subscription(PoseStamped, '/goal_pose', lambda m: log(f'GOAL /goal_pose ({m.pose.position.x:.2f},{m.pose.position.y:.2f}) frame {m.header.frame_id}'), 10)
def plan(m):
    if not m.poses: log('PLAN empty'); return
    L = sum(math.hypot(b.pose.position.x-a.pose.position.x, b.pose.position.y-a.pose.position.y) for a, b in zip(m.poses, m.poses[1:]))
    p0, p1 = m.poses[0].pose.position, m.poses[-1].pose.position
    if last.get('plan') != (round(p1.x, 2), round(p1.y, 2), round(L, 1)):
        log(f'PLAN {len(m.poses)} poses, length {L:.2f} m, ({p0.x:.2f},{p0.y:.2f}) -> ({p1.x:.2f},{p1.y:.2f})')
    last['plan'] = (round(p1.x, 2), round(p1.y, 2), round(L, 1))
n.create_subscription(Path, '/plan', plan, 10)
ST = {0: 'UNKNOWN', 1: 'ACCEPTED', 2: 'EXECUTING', 3: 'CANCELING', 4: 'SUCCEEDED', 5: 'CANCELED', 6: 'ABORTED'}
def status(m):
    s = tuple(ST.get(x.status, x.status) for x in m.status_list[-3:])
    if s and last.get('status') != s: log('NAV GOAL STATUS', s)
    last['status'] = s
n.create_subscription(GoalStatusArray, '/navigate_to_pose/_action/status', status,
                      QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL))
odo = {'x0': None}
def odom(m):
    p = m.pose.pose.position
    if odo['x0'] is None: odo['x0'] = (p.x, p.y)
    d = math.hypot(p.x - odo['x0'][0], p.y - odo['x0'][1]); odo['d'] = d
    if d > odo.get('rep', 0) + 0.05: odo['rep'] = d; log(f'ODOM moved {d:.2f} m from start ({p.x:.2f},{p.y:.2f}) v {m.twist.twist.linear.x:+.2f}')
n.create_subscription(Odometry, '/odometry/filtered', odom, 10)
nxt = 0
while time.time() - t0 < dur:
    rclpy.spin_once(n, timeout_sec=0.1)
    if time.time() > nxt:
        nxt = time.time() + 10
        try:
            d = json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/status', timeout=3))
            r = d['ros']; log(f"[10 s] cpu {d['system'].get('cpu_percent')} | cmd_vel {r['cmd_vel']['value']} | motion {r.get('motion_state',{}).get('value')}")
        except Exception as e: log('status read failed', e)
log(f'END: odom moved max {odo.get("rep", 0):.2f} m')
rclpy.shutdown()

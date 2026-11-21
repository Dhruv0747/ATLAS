#!/usr/bin/env python3
"""Synthetic native-EKF check of /odom continuity when switching config A -> B by restart.
Phase 1: EKF A integrates 4 s of 0.3 m/s motion, then 3 s parked; last /odom recorded.
Phase 2: EKF B (or A) starts fresh, optionally with initial_state = that last pose; first /odom
recorded. The difference is the odom->base_link jump AMCL would see.
  ekf_restart_continuity_synthetic.py A.yaml B.yaml [--initial-state]   (isolated domain, sim time)
"""
import math, os, subprocess, sys, tempfile, time, yaml
import rclpy
from rclpy.parameter import Parameter
from rosgraph_msgs.msg import Clock
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from builtin_interfaces.msg import Time
EKF = f"/opt/ros/{os.environ.get('ROS_DISTRO', 'humble')}/lib/robot_localization/ekf_node"
A, B = sys.argv[1], sys.argv[2]; use_init = '--initial-state' in sys.argv
rclpy.init(); n = rclpy.create_node('continuity_feed', parameter_overrides=[Parameter('use_sim_time', value=True)])
pc = n.create_publisher(Clock, '/clock', 10); po = n.create_publisher(Odometry, '/yahboom/odom', 10)
pi = n.create_publisher(Imu, '/im10a/imu/bias_corrected_candidate', 10)
last = {}
n.create_subscription(Odometry, '/odom', lambda m: last.update(
    x=m.pose.pose.position.x, y=m.pose.pose.position.y,
    yaw=2 * math.atan2(m.pose.pose.orientation.z, m.pose.pose.orientation.w), n=last.get('n', 0) + 1), 10)
state = {'t': 1000.0, 'x': 0.0, 'y': 0.0, 'yaw': 0.0}

def feed(seconds, v, wz):
    dt = 0.02
    for k in range(int(seconds / dt)):
        state['t'] += dt; t = state['t']; stamp = Time(sec=int(t), nanosec=int((t % 1) * 1e9))
        pc.publish(Clock(clock=stamp))
        if k % 5 == 0:
            state['yaw'] += wz * 0.1; state['x'] += v * 0.1 * math.cos(state['yaw']); state['y'] += v * 0.1 * math.sin(state['yaw'])
            o = Odometry(); o.header.stamp = stamp; o.header.frame_id = 'odom'; o.child_frame_id = 'base_link'
            o.pose.pose.position.x, o.pose.pose.position.y = state['x'], state['y']
            o.pose.pose.orientation.z, o.pose.pose.orientation.w = math.sin(state['yaw'] / 2), math.cos(state['yaw'] / 2)
            o.twist.twist.linear.x = v
            o.pose.covariance[0] = o.pose.covariance[7] = 0.05; o.pose.covariance[35] = 0.1
            o.twist.covariance[0] = o.twist.covariance[7] = 0.1; o.twist.covariance[35] = 0.2
            po.publish(o)
        i = Imu(); i.header.stamp = stamp; i.header.frame_id = 'base_link'; i.orientation_covariance[0] = -1
        i.angular_velocity.z = wz; i.angular_velocity_covariance[8] = 0.0004; pi.publish(i)
        rclpy.spin_once(n, timeout_sec=0.0); time.sleep(0.004)

def start(params, init=None):
    args = [EKF, '--ros-args', '-r', '__node:=atlas_ekf', '--params-file', params, '-r', 'odometry/filtered:=/odom', '-p', 'use_sim_time:=true']
    if init is not None:
        d = yaml.safe_load(open(params)); d['atlas_ekf']['ros__parameters']['initial_state'] = init
        f = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False); yaml.safe_dump(d, f); f.close()
        args[5] = f.name
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

p = start(A); time.sleep(2)
feed(4, 0.3, 0.15); feed(3, 0.0, 0.0)
for _ in range(20): rclpy.spin_once(n, timeout_sec=0.01)
before = dict(last); p.terminate(); p.wait(5); time.sleep(1); last.clear()
init = None
if use_init:
    init = [float(before['x']), float(before['y']), 0.0, 0.0, 0.0, float(before['yaw'])] + [0.0] * 9
p = start(B, init); time.sleep(2)
feed(3, 0.0, 0.0)
for _ in range(20): rclpy.spin_once(n, timeout_sec=0.01)
after = dict(last); p.terminate(); p.wait(5)
jump = math.hypot(after['x'] - before['x'], after['y'] - before['y'])
print({'initial_state': use_init, 'before': {k: round(before[k], 3) for k in ('x', 'y', 'yaw')},
       'after_restart': {k: round(after[k], 3) for k in ('x', 'y', 'yaw')},
       'odom_jump_m': round(jump, 3), 'odom_jump_deg': round(math.degrees(after['yaw'] - before['yaw']), 2)})

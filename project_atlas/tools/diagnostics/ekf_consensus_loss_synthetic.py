#!/usr/bin/env python3
"""Synthetic native-EKF check (isolated domain, sim time; never on the rover).
Drive 4 s straight at 0.3 m/s with a constant gyro of 0, then stop. During the stop the wheel driver
publishes exactly what yahboom_base publishes when fewer than 3 encoders agree: zero velocity, pose
frozen, covariances x1000. Measures how far the EKF keeps moving over the 20 s stop.
With --anchored the stop is published as yahboom_base does after the fresh-unchanged-counts change:
pose still x1000, twist at normal covariance.
  ekf_consensus_loss_synthetic.py <params.yaml> [--anchored]   (run while no other ekf_node exists)
"""
import math, subprocess, sys, time
import rclpy
from rclpy.parameter import Parameter
from rosgraph_msgs.msg import Clock
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from builtin_interfaces.msg import Time

params = sys.argv[1]
anchored = '--anchored' in sys.argv[2:]
ekf = subprocess.Popen(['/opt/ros/jazzy/lib/robot_localization/ekf_node', '--ros-args', '-r', '__node:=atlas_ekf',
                        '--params-file', params, '-r', 'odometry/filtered:=/odom', '-p', 'use_sim_time:=true'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    rclpy.init()
    n = rclpy.create_node('synthetic_feed', parameter_overrides=[Parameter('use_sim_time', value=True)])
    pc = n.create_publisher(Clock, '/clock', 10); po = n.create_publisher(Odometry, '/yahboom/odom', 10)
    pi = n.create_publisher(Imu, '/im10a/imu/bias_corrected_candidate', 10)
    last = {}
    n.create_subscription(Odometry, '/odom', lambda m: last.update(x=m.pose.pose.position.x, y=m.pose.pose.position.y), 10)
    time.sleep(2.0)
    t, x, dt = 1000.0, 0.0, 0.02
    marks = {}
    for k in range(int(24 / dt)):
        t += dt
        moving = t < 1004.0
        stamp = Time(sec=int(t), nanosec=int((t % 1) * 1e9))
        pc.publish(Clock(clock=stamp))
        if k % 5 == 0:   # wheel odom at 10 Hz
            v = 0.3 if moving else 0.0
            x += v * 0.1
            o = Odometry(); o.header.stamp = stamp; o.header.frame_id = 'odom'; o.child_frame_id = 'base_link'
            o.pose.pose.position.x = x; o.pose.pose.orientation.w = 1.0; o.twist.twist.linear.x = v
            f = 1.0 if moving else 1000.0
            o.pose.covariance[0] = o.pose.covariance[7] = 0.05 * f; o.pose.covariance[35] = 0.10 * f
            g = 1.0 if anchored else f
            o.twist.covariance[0] = o.twist.covariance[7] = 0.10 * g; o.twist.covariance[35] = 0.20 * g
            po.publish(o)
        i = Imu(); i.header.stamp = stamp; i.header.frame_id = 'base_link'; i.orientation_covariance[0] = -1
        i.angular_velocity_covariance[8] = 0.0004; pi.publish(i)
        rclpy.spin_once(n, timeout_sec=0.0); time.sleep(0.004)
        if abs(t - 1004.5) < dt / 2: marks['stop'] = dict(last)
        if abs(t - 1024.0) < dt / 2: marks['end'] = dict(last)
    for _ in range(50): rclpy.spin_once(n, timeout_sec=0.01)
    s, e = marks.get('stop', {}), marks.get('end', last)
    print({'wheel_x_at_stop': round(x, 3), 'ekf_x_at_stop+0.5s': round(s.get('x', float('nan')), 3),
           'ekf_x_after_20s_stop': round(e.get('x', float('nan')), 3),
           'coast_during_stop_m': round(e.get('x', float('nan')) - s.get('x', float('nan')), 3)})
finally:
    ekf.terminate(); ekf.wait(5)

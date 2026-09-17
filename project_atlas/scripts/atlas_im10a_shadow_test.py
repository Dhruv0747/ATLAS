#!/usr/bin/env python3
"""Bounded, non-authoritative EKF comparison. No motor commands or TF output."""
import copy
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = '/atlas_imu_shadow'


def parameters(live, fused):
    p = copy.deepcopy(live)
    for key in list(p):
        if key.startswith('imu'):
            del p[key]
    p.update(publish_tf=False, publish_acceleration=False,
             transform_time_offset=0.0, print_diagnostics=False)
    if fused:
        p.update(imu0=ROOT + '/gyro',
                 imu0_config=[False]*11 + [True] + [False]*3,
                 imu0_queue_size=2, imu0_differential=False,
                 imu0_relative=False, imu0_remove_gravitational_acceleration=False)
    return p


def accepted_gyro(frame, stamp, now, previous, xyz):
    return (frame == 'im10a_sensor_unvalidated' and stamp > previous
            and 0 <= now-stamp <= .2
            and all(math.isfinite(v) and abs(v) <= math.radians(2000) for v in xyz))


def main():
    import yaml
    import rclpy
    from sensor_msgs.msg import Imu
    from nav_msgs.msg import Odometry
    rclpy.init()
    n = rclpy.create_node('atlas_im10a_shadow_audit')
    live_path = Path('/home/jetson/project_atlas/config/atlas_ekf.yaml')
    live_bytes = live_path.read_bytes()
    live = yaml.safe_load(live_bytes)['ekf_filter_node']['ros__parameters']
    directory = Path(tempfile.mkdtemp(prefix='im10a_shadow_', dir='/home/jetson/project-atlas-migration'))
    processes = []
    handles = []
    rows = {name: [] for name in ('baseline', 'fused')}
    counts = dict(accepted=0, rejected=0)
    previous = 0.0
    last_imu = None
    last_wheel = None
    wheel_samples = 0
    pub = n.create_publisher(Imu, ROOT + '/gyro', 2)

    def receive(m):
        nonlocal previous, last_imu
        stamp = m.header.stamp.sec + m.header.stamp.nanosec/1e9
        xyz = (m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z)
        if not accepted_gyro(m.header.frame_id, stamp, n.get_clock().now().nanoseconds/1e9, previous, xyz):
            counts['rejected'] += 1
            return
        previous = stamp
        last_imu = time.monotonic()
        counts['accepted'] += 1
        out = Imu()
        out.header.stamp = m.header.stamp
        # Gyro is a free vector: rotate X/Y by pi, Z unchanged. No lever-arm
        # correction needed for angular velocity; no acceleration is fused.
        out.header.frame_id = live['base_link_frame']
        out.angular_velocity.x, out.angular_velocity.y, out.angular_velocity.z = -xyz[0], -xyz[1], xyz[2]
        out.orientation_covariance[0] = -1.0
        out.linear_acceleration_covariance[0] = -1.0
        # Provisional test variance only; deliberately above stationary noise.
        out.angular_velocity_covariance = [.0001,0.,0.,0.,.0001,0.,0.,0.,.0001]
        pub.publish(out)

    def wheel(m):
        nonlocal last_wheel, wheel_samples
        last_wheel = time.monotonic()
        wheel_samples += 1

    def output(name, m):
        q = m.pose.pose.orientation
        yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        rows[name].append(dict(received=time.monotonic(),
                              stamp=m.header.stamp.sec+m.header.stamp.nanosec/1e9,
                              x=m.pose.pose.position.x,y=m.pose.pose.position.y,
                              yaw=yaw, wz=m.twist.twist.angular.z,
                              yaw_variance=m.pose.covariance[35]))

    n.create_subscription(Imu, '/im10a/imu/unvalidated', receive, 2)
    n.create_subscription(Odometry, live['odom0'], wheel, 5)
    try:
        # Avoid duplicate shadow runs. Never stop an existing node automatically.
        discovery = time.monotonic()
        while time.monotonic()-discovery < 3:
            rclpy.spin_once(n, timeout_sec=.1)
        if any(ns.startswith(ROOT) for _, ns in n.get_node_names_and_namespaces()):
            raise RuntimeError('Existing shadow namespace detected; refusing duplicate test')
        for name in rows:
            cfg = directory / (name + '.yaml')
            cfg.write_text(yaml.safe_dump({'/**': {'ros__parameters': parameters(live, name=='fused')}}))
            log = (directory/(name+'.log')).open('w')
            handles.append(log)
            processes.append(subprocess.Popen([
                '/opt/ros/humble/lib/robot_localization/ekf_node', '--ros-args',
                '-r', '__node:=ekf', '-r', '__ns:='+ROOT+'/'+name,
                '--params-file', str(cfg)], stdout=log, stderr=subprocess.STDOUT))
            n.create_subscription(Odometry, ROOT+'/'+name+'/odometry/filtered',
                                  lambda m, name=name: output(name, m), 20)
        print('SHADOW_STARTED: 60 seconds; no TF, no /odom replacement, no motor commands', flush=True)
        start = time.monotonic()
        while time.monotonic()-start < 60:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError('Shadow EKF exited unexpectedly; inspect saved logs')
            rclpy.spin_once(n, timeout_sec=.1)
        now = time.monotonic()
        report = dict(directory=str(directory), gyro=counts, wheel_samples=wheel_samples,
                      imu_age_s=None if last_imu is None else now-last_imu,
                      wheel_age_s=None if last_wheel is None else now-last_wheel,
                      live_config_unchanged=live_path.read_bytes()==live_bytes,
                      limitation='Stationary shadow only; M4 faulty; covariance provisional; not navigation qualified')
        for name, data in rows.items():
            report[name] = dict(samples=len(data))
            if data:
                report[name].update(all_finite=all(math.isfinite(v) for r in data for v in r.values()),
                    final=data[-1], displacement_m=math.hypot(data[-1]['x']-data[0]['x'],data[-1]['y']-data[0]['y']),
                    yaw_change_deg=math.degrees(sum((b['yaw']-a['yaw']+math.pi)%(2*math.pi)-math.pi for a,b in zip(data,data[1:]))))
        (directory/'samples.json').write_text(json.dumps(rows))
        (directory/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2), flush=True)
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
        for p in processes:
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=5)
        for h in handles: h.close()
        n.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

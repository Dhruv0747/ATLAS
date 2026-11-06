"""Track A (STAGED, inactive): Astra depth -> /astra/obstacle_scan, entirely in the Astra private ROS domain (77).

Chain: astra_camera_node (depth only, 160x120, publishes depth + CameraInfo) -> scripts/atlas_astra_obstacle_scan.py
(runtime-validated FACTORY/driver CameraInfo intrinsics, configured mount, floor..ceiling band, fail-safe publishing) -> /astra/obstacle_scan (base_link).
Only that LaserScan is bridged to domain 0 (atlas-astra-bridge.service). Static TFs are published here for
visualization only; the scan node does its own geometry from the measured mount, so no TF lookup can stall it.

Refuses to launch on: wrong ROS_DOMAIN_ID or incomplete/implausible mount/scan config. The scan node additionally
publishes nothing until the driver's depth CameraInfo passes validation.
Read-only sensor pipeline: no velocity, servo, map or driver-control output.
"""
import math
import os
import sys
from pathlib import Path

import yaml
from launch import LaunchDescription
from launch.actions import EmitEvent, ExecuteProcess
from launch.events import Shutdown
from launch_ros.actions import Node

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_astra_obstacle_core as core  # noqa: E402

RUNTIME = Path('/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2')


def checked_config():
    cfg = yaml.safe_load((ROOT / 'config/astra_obstacles.yaml').read_text())
    try:
        cfg = core.validate_config(cfg)
    except Exception as e:
        raise RuntimeError('Track A not activatable: ' + str(e)) from None
    want = str(cfg['bridge'].get('from_domain', 77))
    if os.environ.get('ROS_DOMAIN_ID') != want:
        raise RuntimeError(f'must run in the Astra private domain ROS_DOMAIN_ID={want}')
    return cfg


def driver_command(astra):
    params = {'camera_name': 'astra', 'use_uvc_camera': 'false', 'enable_color': 'false', 'enable_depth': 'true',
              'enable_ir': 'false', 'enable_point_cloud': 'false', 'enable_colored_point_cloud': 'false',
              'publish_tf': 'false', 'depth_registration': 'false', 'enable_publish_extrinsic': 'false',
              'depth_width': str(astra['depth_width']), 'depth_height': str(astra['depth_height']),
              'depth_fps': str(astra['depth_fps']), 'depth_scale': '1',
              'oni_log_to_file': 'false', 'oni_log_to_console': 'false'}
    cmd = [str(RUNTIME / 'lib/astra_camera/astra_camera_node'), '--ros-args', '-r', '__ns:=/astra']
    for k, v in params.items():
        cmd += ['-p', f'{k}:={v}']
    return cmd


def generate_launch_description():
    cfg = checked_config()
    m = cfg['mount']
    env = dict(os.environ,
               LD_LIBRARY_PATH=f"{RUNTIME/'lib'}:/opt/ros/humble/lib:" + os.environ.get('LD_LIBRARY_PATH', ''),
               AMENT_PREFIX_PATH=f'{RUNTIME}:/opt/ros/humble')
    return LaunchDescription([
        # Sensor-only process: respawned after 3 s if it dies (the scan node reports STALE meanwhile and publishes
        # nothing). Motor / odometry / Nav2 processes are never auto-restarted by this launch.
        ExecuteProcess(cmd=driver_command(cfg['astra']), env=env, cwd=str(RUNTIME), output='log',
                       name='astra_depth_driver', respawn=True, respawn_delay=3.0),
        Node(package='tf2_ros', executable='static_transform_publisher', name='astra_mount_tf',
             arguments=['--x', str(m['x_m']), '--y', str(m['y_m']), '--z', str(m['z_m']),
                        '--yaw', str(math.radians(m['yaw_deg'])), '--pitch', str(math.radians(m['pitch_deg'])),
                        '--roll', '0', '--frame-id', 'base_link', '--child-frame-id', 'astra_link']),
        Node(package='tf2_ros', executable='static_transform_publisher', name='astra_optical_tf',
             arguments=['--yaw', str(-math.pi / 2), '--pitch', '0', '--roll', str(-math.pi / 2),
                        '--frame-id', 'astra_link', '--child-frame-id', 'astra_depth_optical_frame']),
        ExecuteProcess(cmd=[sys.executable, str(ROOT / 'scripts/atlas_astra_obstacle_scan.py')],
                       output='log', name='atlas_astra_obstacle_scan',
                       on_exit=[EmitEvent(event=Shutdown(reason='scan node exited'))]),   # systemd decides
    ])

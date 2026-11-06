"""Track A (STAGED, inactive): Astra depth -> /astra/obstacle_scan, entirely in the Astra private ROS domain (77).

Chain: astra_camera_node (depth only, 160x120) -> atlas_astra_calibrated_info (validated K/D, refuses otherwise)
-> depth_image_proc::PointCloudXyzNode -> pointcloud_to_laserscan (floor..rover-height band, in base_link)
-> /astra/obstacle_scan.  Only that LaserScan is bridged to domain 0 (see atlas-astra-bridge.service.in).

Refuses to launch while any MEASURE value in config/astra_obstacles.yaml is null. Read-only sensor pipeline:
no velocity, servo, map or driver-control output. Requires apt packages depth_image_proc and
pointcloud_to_laserscan (not installed as of 2026-11-06).
"""
import math
import os
from pathlib import Path

import yaml
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path('/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2')


def _cfg():
    c = yaml.safe_load((ROOT / 'config/astra_obstacles.yaml').read_text())
    missing = [f'mount.{k}' for k in ('x_m', 'y_m', 'z_m', 'pitch_deg') if c['mount'].get(k) is None]
    if c['obstacle_scan'].get('max_height_m') is None:
        missing.append('obstacle_scan.max_height_m')
    if missing:
        raise RuntimeError('Track A not activatable: measure and fill ' + ', '.join(missing))
    if os.environ.get('ROS_DOMAIN_ID') != str(c['bridge']['from_domain']):
        raise RuntimeError('must run in the Astra private domain ROS_DOMAIN_ID=%s' % c['bridge']['from_domain'])
    return c


def generate_launch_description():
    c = _cfg()
    m, a, s = c['mount'], c['astra'], c['obstacle_scan']
    driver_env = dict(os.environ,
                      LD_LIBRARY_PATH=f"{RUNTIME/'lib'}:/opt/ros/humble/lib:" + os.environ.get('LD_LIBRARY_PATH', ''),
                      AMENT_PREFIX_PATH=f'{RUNTIME}:/opt/ros/humble')
    params = {'camera_name': 'astra', 'use_uvc_camera': 'false', 'enable_color': 'false', 'enable_depth': 'true',
              'enable_ir': 'false', 'enable_point_cloud': 'false', 'enable_colored_point_cloud': 'false',
              'publish_tf': 'false', 'depth_registration': 'false', 'enable_publish_extrinsic': 'false',
              'depth_width': str(a['depth_width']), 'depth_height': str(a['depth_height']),
              'depth_fps': str(a['depth_fps']), 'depth_scale': '1',
              'oni_log_to_file': 'false', 'oni_log_to_console': 'false'}
    driver_cmd = [str(RUNTIME / 'lib/astra_camera/astra_camera_node'), '--ros-args', '-r', '__ns:=/astra']
    for k, v in params.items():
        driver_cmd += ['-p', f'{k}:={v}']

    # base_link -> camera body (x fwd, y left, z up), then body -> optical (z fwd, x right, y down).
    pitch = math.radians(m['pitch_deg']); yaw = math.radians(m['yaw_deg'])
    return LaunchDescription([
        ExecuteProcess(cmd=driver_cmd, env=driver_env, cwd=str(RUNTIME), output='log', name='astra_depth_driver'),
        Node(package='tf2_ros', executable='static_transform_publisher', name='astra_mount_tf',
             arguments=['--x', str(m['x_m']), '--y', str(m['y_m']), '--z', str(m['z_m']),
                        '--yaw', str(yaw), '--pitch', str(pitch), '--roll', '0',
                        '--frame-id', 'base_link', '--child-frame-id', 'astra_link']),
        Node(package='tf2_ros', executable='static_transform_publisher', name='astra_optical_tf',
             arguments=['--yaw', str(-math.pi / 2), '--pitch', '0', '--roll', str(-math.pi / 2),
                        '--frame-id', 'astra_link', '--child-frame-id', 'astra_depth_optical_frame']),
        Node(executable=str(ROOT / 'scripts/atlas_astra_calibrated_info.py'), name='atlas_astra_calibrated_info',
             output='log'),
        ComposableNodeContainer(
            name='astra_obstacles_container', namespace='', package='rclcpp_components',
            executable='component_container',
            composable_node_descriptions=[
                ComposableNode(package='depth_image_proc', plugin='depth_image_proc::PointCloudXyzNode',
                               name='astra_points',
                               remappings=[('image_rect', '/astra/depth/image_raw'),
                                           ('camera_info', '/astra/depth/camera_info_calibrated'),
                                           ('points', '/astra/obstacle_points')]),
            ]),
        Node(package='pointcloud_to_laserscan', executable='pointcloud_to_laserscan_node',
             name='astra_obstacle_scan',
             remappings=[('cloud_in', '/astra/obstacle_points'), ('scan', '/astra/obstacle_scan')],
             parameters=[{'target_frame': s['target_frame'], 'transform_tolerance': 0.05,
                          'min_height': s['min_height_m'], 'max_height': s['max_height_m'],
                          'angle_min': s['angle_min_rad'], 'angle_max': s['angle_max_rad'],
                          'angle_increment': s['angle_increment_rad'], 'scan_time': s['scan_time_s'],
                          'range_min': s['range_min_m'], 'range_max': s['range_max_m'], 'use_inf': s['use_inf']}]),
    ])

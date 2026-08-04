#!/usr/bin/env python3
"""Read-only Project ATLAS TF/Nav2 readiness check."""
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from tf2_msgs.msg import TFMessage


class Check(Node):
    def __init__(self):
        super().__init__('atlas_tf_nav2_check')
        self.transforms = set()
        self.odom = None
        self.create_subscription(TFMessage, '/tf', self._tf, 20)
        self.create_subscription(TFMessage, '/tf_static', self._tf, 20)
        self.create_subscription(Odometry, '/odom', self._odom, 10)

    def _tf(self, message):
        for transform in message.transforms:
            self.transforms.add((transform.header.frame_id.lstrip('/'), transform.child_frame_id.lstrip('/')))

    def _odom(self, message):
        self.odom = message


def main():
    rclpy.init()
    node = Check()
    end = time.monotonic() + 5.0
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)

    nodes = set(node.get_node_names())
    services = {name for name, _ in node.get_service_names_and_types()}
    topics = {name for name, _ in node.get_topic_names_and_types()}
    required_nodes = ('controller_server', 'planner_server', 'bt_navigator', 'behavior_server')
    print('ODOM', 'OK' if node.odom else 'MISSING')
    print('TF_ODOM_BASE', 'OK' if ('odom', 'base_link') in node.transforms else 'MISSING')
    print('TF_MAP_ODOM', 'OK' if ('map', 'odom') in node.transforms else 'MISSING')
    print('LIDAR', 'OK' if '/scan' in topics else 'MISSING')
    print('COSTMAPS', 'OK' if '/local_costmap/costmap' in topics and '/global_costmap/costmap' in topics else 'MISSING')
    print('SLAM_NODE', 'OK' if 'slam_toolbox' in nodes else 'MISSING')
    print('SLAM_LIFECYCLE', 'OK' if '/slam_toolbox/get_state' in services else 'MISSING')
    print('MAP_TOPIC', 'OK' if '/map' in topics else 'MISSING')
    for required in required_nodes:
        present = required in nodes
        lifecycle = f'/{required}/get_state' in services
        print(f'NAV2_{required.upper()}', 'OK' if present and lifecycle else 'MISSING')
    print('TRANSFORMS', ', '.join(f'{a}->{b}' for a, b in sorted(node.transforms)))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

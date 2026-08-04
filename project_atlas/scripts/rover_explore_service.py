#!/usr/bin/env python3
"""
rover_explore_service.py - one-click exploration via Foxglove Service Call panel.
Run once: nohup python3 /home/jetson/project_atlas/scripts/rover_explore_service.py > /tmp/explore_svc.log 2>&1 &
Then in Foxglove: Add panel -> Service Call -> /explore/start -> Send Request
"""
import sys, os, subprocess, signal

if 'ROS_DISTRO' not in os.environ:
    os.execv('/bin/bash', ['/bin/bash', '-c',
        'source /opt/ros/humble/setup.bash && '
        'source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null; '
        'exec python3 ' + ' '.join(sys.argv)])

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger


class ExploreService(Node):
    def __init__(self):
        super().__init__('explore_launcher')
        self._proc = None
        self.create_service(Trigger, '/explore/start', self._start_cb)
        self.create_service(Trigger, '/explore/stop',  self._stop_cb)
        self.get_logger().info('explore_launcher ready - /explore/start and /explore/stop')

    def _start_cb(self, req, resp):
        if self._proc and self._proc.poll() is None:
            resp.success = False
            resp.message = 'Already running (PID ' + str(self._proc.pid) + ') - stop first'
            return resp
        self._proc = subprocess.Popen(
            ['python3', '/home/jetson/project_atlas/scripts/rover_explore.py', '--radius', '2.5'],
            stdout=open('/tmp/explore.log', 'w'), stderr=subprocess.STDOUT)
        resp.success = True
        resp.message = 'Exploration started (PID ' + str(self._proc.pid) + '). Log: /tmp/explore.log'
        self.get_logger().info(resp.message)
        return resp

    def _stop_cb(self, req, resp):
        if self._proc and self._proc.poll() is None:
            self._proc.send_signal(signal.SIGINT)
            resp.success = True
            resp.message = 'Stopping - map will be saved before exit'
        else:
            resp.success = False
            resp.message = 'No exploration running'
        self.get_logger().info(resp.message)
        return resp


def main():
    rclpy.init()
    node = ExploreService()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, Exception):
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

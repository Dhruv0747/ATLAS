#!/usr/bin/env python3
"""ROS2 service node: /nav2/start and /nav2/stop for Foxglove Service Call panel."""
import subprocess
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

_proc = None

class Nav2Svc(Node):
    def __init__(self):
        super().__init__('nav2_service')
        self.create_service(Trigger, '/nav2/start', self.start_cb)
        self.create_service(Trigger, '/nav2/stop',  self.stop_cb)
        self.get_logger().info('nav2_service ready (/nav2/start, /nav2/stop)')

    def start_cb(self, req, resp):
        global _proc
        if _proc and _proc.poll() is None:
            resp.success = False
            resp.message = 'Nav2 already running'
            return resp
        _proc = subprocess.Popen(['bash', '-c',
            'source /opt/ros/humble/setup.bash && '
            '[ -f ~/ros2_ws/install/setup.bash ] && source ~/ros2_ws/install/setup.bash; '
            'ros2 launch tortoisebot_bringup tortoisebot_all.launch.py'])
        resp.success = True
        resp.message = f'Nav2 started PID {_proc.pid}'
        return resp

    def stop_cb(self, req, resp):
        global _proc
        if _proc is None or _proc.poll() is not None:
            resp.success = False
            resp.message = 'Nav2 not running'
            return resp
        _proc.terminate()
        try: _proc.wait(timeout=5)
        except subprocess.TimeoutExpired: _proc.kill()
        resp.success = True
        resp.message = 'Nav2 stopped'
        return resp

def main():
    rclpy.init()
    rclpy.spin(Nav2Svc())
    rclpy.shutdown()

if __name__ == '__main__':
    main()

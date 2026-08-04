#!/usr/bin/env python3
"""
safety_supervisor.py — ATLAS Project Safety Supervisor v2 (with relay)
Provides:
  - /estop service (std_srvs/srv/SetBool): True=stop, False=release
  - /estop/status topic (std_msgs/Bool)
  - Relay: /cmd_vel_teleop → /cmd_vel when NOT e-stopped (sole publisher)
  - Watchdog: logs warning if /cmd_vel_teleop silent >3s
  - When e-stopped: hammers /cmd_vel with zero twist at 10Hz
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool
from std_srvs.srv import SetBool
from geometry_msgs.msg import Twist
import time

class SafetySupervisor(Node):
    def __init__(self):
        super().__init__('safety_supervisor')
        self._estopped = False
        self._last_teleop = time.time()
        self._watchdog_timeout = 3.0

        # E-stop service
        self._srv = self.create_service(SetBool, '/estop', self._estop_cb)
        # Status publisher
        self._status_pub = self.create_publisher(Bool, '/estop/status', 1)
        # Sole publisher to /cmd_vel — relay from teleop, zero when e-stopped
        self._cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        # Subscribe to teleop commands
        self._teleop_sub = self.create_subscription(
            Twist, '/cmd_vel_teleop', self._teleop_cb, 10)

        self.create_timer(0.1, self._loop)
        self.get_logger().info(
            'Safety supervisor v2 ready — relaying /cmd_vel_teleop → /cmd_vel')

    def _estop_cb(self, req, res):
        self._estopped = req.data
        state = 'ENGAGED' if self._estopped else 'RELEASED'
        self.get_logger().warn(f'E-STOP {state}')
        if self._estopped:
            # Immediate hard stop
            self._cmd_pub.publish(Twist())
        res.success = True
        res.message = f'E-stop {state}'
        return res

    def _teleop_cb(self, msg):
        self._last_teleop = time.time()
        if not self._estopped:
            # Relay teleop command straight through to motors
            self._cmd_pub.publish(msg)

    def _loop(self):
        # Publish e-stop status continuously
        msg = Bool()
        msg.data = self._estopped
        self._status_pub.publish(msg)

        # If e-stopped, keep hammering zero to override any stale commands
        if self._estopped:
            self._cmd_pub.publish(Twist())

        # Watchdog warning (log only — does not stop motors)
        elapsed = time.time() - self._last_teleop
        if elapsed > self._watchdog_timeout and not self._estopped:
            self.get_logger().warn(
                f'Watchdog: no /cmd_vel_teleop for {elapsed:.1f}s',
                throttle_duration_sec=5.0)

def main():
    rclpy.init()
    node = SafetySupervisor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

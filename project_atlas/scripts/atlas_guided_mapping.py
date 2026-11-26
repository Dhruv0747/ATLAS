#!/usr/bin/env python3
"""ATLAS guided mapping assistant, phase 1b live node (2026-11-26; docs/design/guided_mapping_assistant.md).

READ-ONLY ADVICE while the owner drives a manual mapping session: publishes /atlas/mapping_quality (std_msgs/String,
JSON <= 4 KB, every 2 s) for the dashboard mapping page. It publishes nothing else: no cmd_vel, no goals, no places, no
map, no parameters. SLAM and the map acceptance gate are unchanged.

Idle cost ~0: it only reads mission control's mapping session file once a second. Subscriptions (/map, /scan,
/astra/obstacle_scan, /ultrasonic/validity) and the TF listener exist only while the session state is "active"; they are
destroyed when the session ends. It pauses itself (state paused_cpu) when the CPU idle fraction drops below 25 %.
Work is decimated: scans <= 2 Hz (and only after 0.1 m / 5 deg of motion), depth <= 2.5 Hz, ultrasonic <= 4 Hz.
"""
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_guided_mapping_engine as ge  # noqa: E402
from atlas_mapping_guard_core import cpu_idle_fraction  # noqa: E402

SESSION_FILE = Path.home() / '.config/project_atlas/mapping_session.json'
TOPIC = '/atlas/mapping_quality'
TICK_S = 1.0
PUBLISH_ACTIVE_S = 2.0
PUBLISH_IDLE_S = 10.0
SCAN_MIN_S = 0.5
DEPTH_MIN_S = 0.4
US_MIN_S = 0.25


def read_proc_stat():
    try:
        with open('/proc/stat', encoding='ascii') as f:
            return [int(v) for v in f.readline().split()[1:]]
    except (OSError, ValueError):
        return None


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def make_node(rclpy_mod, Node, qos, msgs, tf2, engine=None, session_file=SESSION_FILE, clock=time.monotonic,
              proc_stat=read_proc_stat, wall=time.time):
    """Build the node. Modules are injected so tests can run it with stubs (no DDS participant).
    clock (monotonic) only paces the work; every time given to the engine is ROS/wall time (scan stamps are wall
    time with use_sim_time false), so jump times and scan times compare correctly."""
    String, OccupancyGrid, LaserScan = msgs['String'], msgs['OccupancyGrid'], msgs['LaserScan']

    class GuidedMapping(Node):
        def __init__(self):
            super().__init__('atlas_guided_mapping')
            self.engine = engine or ge.GuidedMappingEngine()
            self.pub = self.create_publisher(String, TOPIC, qos['status'])
            self.subs = []
            self.tf_buffer = self.tf_listener = None
            self.last = {'scan': -1e9, 'depth': -1e9, 'us': -1e9, 'pub': -1e9}
            self.cpu_prev = proc_stat()
            self.create_timer(TICK_S, self.tick)

        # ---------------- session / subscriptions
        def _activate(self):
            if self.subs:
                return
            self.tf_buffer = tf2.Buffer()
            self.tf_listener = tf2.TransformListener(self.tf_buffer, self)
            self.subs = [
                self.create_subscription(OccupancyGrid, '/map', self.on_map, qos['map']),
                self.create_subscription(LaserScan, '/scan', self.on_scan, qos['sensor']),
                self.create_subscription(LaserScan, '/astra/obstacle_scan', self.on_depth, qos['sensor']),
                self.create_subscription(String, '/ultrasonic/validity', self.on_us, qos['sensor']),
            ]
            self.get_logger().info('mapping session active: assistant subscriptions on')

        def _deactivate(self):
            if not self.subs:
                return
            for s in self.subs:
                self.destroy_subscription(s)
            self.subs = []
            if self.tf_listener is not None and hasattr(self.tf_listener, 'unregister'):
                self.tf_listener.unregister()
            self.tf_buffer = self.tf_listener = None
            self.get_logger().info('mapping session ended: assistant subscriptions off')

        # ---------------- helpers
        def _pose(self, parent='map', child='base_link'):
            if self.tf_buffer is None:
                return None
            try:
                tr = self.tf_buffer.lookup_transform(parent, child, rclpy_mod.time.Time())
            except Exception:                                   # noqa: BLE001 - tf2 raises several types
                return None
            t = tr.transform
            return (t.translation.x, t.translation.y, yaw_of(t.rotation))

        @staticmethod
        def _stamp(msg):
            return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9

        def _due(self, key, period):
            now = clock()
            if now - self.last[key] < period:
                return False
            self.last[key] = now
            return True

        # ---------------- callbacks (never raise)
        def on_map(self, msg):
            try:
                self.engine.on_map(ge.grid_from_msg(msg))
            except (ValueError, AttributeError, TypeError) as exc:
                self.get_logger().warn(f'map not usable: {exc}')

        def on_scan(self, msg):
            if not self._due('scan', SCAN_MIN_S):
                return
            try:
                self.engine.on_scan(self._stamp(msg), self._pose(), msg.angle_min, msg.angle_increment,
                                    list(msg.ranges), msg.range_min, msg.range_max)
            except Exception as exc:                            # noqa: BLE001 - advice only, never crash
                self.get_logger().warn(f'scan skipped: {exc}')

        def on_depth(self, msg):
            if not self._due('depth', DEPTH_MIN_S):
                return
            try:
                self.engine.on_depth(self._stamp(msg), self._pose(), msg.angle_min, msg.angle_increment,
                                     list(msg.ranges))
            except Exception as exc:                            # noqa: BLE001
                self.get_logger().warn(f'depth skipped: {exc}')

        def on_us(self, msg):
            if not self._due('us', US_MIN_S):
                return
            try:
                self.engine.on_ultrasonic(wall(), self._pose(), msg.data)
            except Exception as exc:                            # noqa: BLE001
                self.get_logger().warn(f'ultrasonic skipped: {exc}')

        # ---------------- timer
        def tick(self):
            try:
                cur = proc_stat()
                if cur is not None:
                    self.engine.on_cpu_idle(cpu_idle_fraction(self.cpu_prev, cur))
                    self.cpu_prev = cur
                active = self.engine.set_session(ge.read_session(session_file))
                (self._activate if active else self._deactivate)()
                robot = None
                if active:
                    robot = self._pose()
                    mo = self._pose('map', 'odom')
                    if mo is not None and robot is not None:
                        self.engine.on_map_odom(wall(), mo[0], mo[1], mo[2], robot[:2])
                if not self._due('pub', PUBLISH_ACTIVE_S if active else PUBLISH_IDLE_S):
                    return
                out = String()
                out.data = json.dumps(self.engine.payload(wall(), robot), separators=(',', ':'))
                self.pub.publish(out)
            except Exception as exc:                            # noqa: BLE001
                self.get_logger().error(f'tick failed: {exc}')

    return GuidedMapping()


def main():
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    import rclpy.time  # noqa: F401
    import tf2_ros
    from nav_msgs.msg import OccupancyGrid
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import String

    qos = {'map': QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE),
           'sensor': qos_profile_sensor_data,
           'status': QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)}
    rclpy.init()
    node = make_node(rclpy, Node, qos, {'String': String, 'OccupancyGrid': OccupancyGrid, 'LaserScan': LaserScan},
                     tf2_ros)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

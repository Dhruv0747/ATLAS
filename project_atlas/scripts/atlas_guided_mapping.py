#!/usr/bin/env python3
"""ATLAS guided mapping assistant, phase 1b live node (2026-11-26; docs/design/guided_mapping_assistant.md).

READ-ONLY ADVICE. Publishes only /atlas/mapping_quality (std_msgs/String, JSON <= 4 KB, every 2 s) for the dashboard
mapping page. No cmd_vel, goals, places, map or parameter writes. SLAM, the acceptance gate, Nav2 and the mux are
unchanged. Two modes, chosen once a second from mission control's mapping session file:
  * MAPPING (session state "active"): per-area quality, openings, objects the LiDAR cannot see. Subscribes /map,
    /scan, /astra/obstacle_scan, /ultrasonic/validity. Scans <= 2 Hz, depth <= 2.5 Hz, ultrasonic <= 4 Hz.
  * SAVED-MAP CHECK (otherwise; owner 2026-11-26 "where can I see that the map needs updating"): LiDAR objects the
    saved map does not have ("Map change N"), counted only while the scan fits the map. Subscribes /map_nav (accepted
    map + confirmed virtual obstacles), /scan (<= 1 Hz), /amcl_pose (the pose; a scan counts only with an AMCL pose
    within 0.5 s) and /atlas/control_policy; paused while autonomy is armed or the control policy is unreadable.
    No TF listener in this mode: it exists only during mapping sessions (TF runs at 30+ Hz).
Both pause below 25 % CPU idle. Subscriptions of the other mode are destroyed on every switch.
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
PUBLISH_S = 2.0
SCAN_MIN_S = 0.5
CHECK_SCAN_MIN_S = ge.MAP_CHECK_PERIOD_S
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


def autonomy_armed(policy_json):
    """True when /atlas/control_policy says autonomy is armed; also True when unreadable (pause = the safe side)."""
    try:
        return bool(json.loads(policy_json)['autonomy']['armed'])
    except (ValueError, TypeError, KeyError):
        return True


def make_node(rclpy_mod, Node, qos, msgs, tf2, engine=None, monitor=None, session_file=SESSION_FILE,
              clock=time.monotonic, proc_stat=read_proc_stat, wall=time.time):
    """Build the node. Modules are injected so tests can run it with stubs (no DDS participant).
    clock (monotonic) only paces the work; every time given to the engine is ROS/wall time (scan stamps are wall
    time with use_sim_time false), so jump times and scan times compare correctly."""
    String, OccupancyGrid, LaserScan = msgs['String'], msgs['OccupancyGrid'], msgs['LaserScan']
    PoseCov = msgs.get("PoseWithCovarianceStamped", "PoseWithCovarianceStamped")

    class GuidedMapping(Node):
        def __init__(self):
            super().__init__('atlas_guided_mapping')
            self.engine = engine or ge.GuidedMappingEngine()
            self.monitor = monitor or ge.MapChangeMonitor()
            self.pub = self.create_publisher(String, TOPIC, qos['status'])
            self.subs = []
            self.mode = None
            self.check_scan_subs = []           # /scan + /amcl_pose of the saved-map check (dropped while armed)
            self.tf_buffer = self.tf_listener = None
            self.amcl = None
            self.last = {'scan': -1e9, 'depth': -1e9, 'us': -1e9, 'pub': -1e9}
            self.cpu_prev = proc_stat()
            self.create_timer(TICK_S, self.tick)

        # ---------------- modes / subscriptions
        def _set_mode(self, mode):
            if mode == self.mode:
                return
            self._check_scans(False)               # first: it also removes them from self.subs (no double destroy)
            for s in self.subs:
                self.destroy_subscription(s)
            if self.tf_listener is not None and hasattr(self.tf_listener, "unregister"):
                self.tf_listener.unregister()
            self.tf_buffer = self.tf_listener = None
            self.amcl = None
            if mode == "mapping":
                self.tf_buffer = tf2.Buffer()
                self.tf_listener = tf2.TransformListener(self.tf_buffer, self)
                self.subs = [
                    self.create_subscription(OccupancyGrid, '/map', self.on_map, qos['map']),
                    self.create_subscription(LaserScan, '/scan', self.on_scan, qos['sensor']),
                    self.create_subscription(LaserScan, '/astra/obstacle_scan', self.on_depth, qos['sensor']),
                    self.create_subscription(String, '/ultrasonic/validity', self.on_us, qos['sensor']),
                ]
            else:
                self.subs = [
                    self.create_subscription(OccupancyGrid, '/map_nav', self.on_saved_map, qos['map']),
                    self.create_subscription(String, '/atlas/control_policy', self.on_policy, 1),
                ]
                self.check_scan_subs = []
                self._check_scans(not self.monitor.armed)
            self.get_logger().info(f'mode: {"mapping session" if mode == "mapping" else "saved-map check"}')
            self.mode = mode

        def _check_scans(self, on):
            """2026-11-26 owner: drop /scan and /amcl_pose while autonomy is armed (rclpy decodes every 7 Hz scan even
            when the check skips it: measured 3.5 % of one core). /map_nav and /atlas/control_policy always stay."""
            if on and not self.check_scan_subs:
                self.check_scan_subs = [
                    self.create_subscription(LaserScan, '/scan', self.on_check_scan, qos['sensor']),
                    self.create_subscription(PoseCov, '/amcl_pose', self.on_amcl, qos['status']),
                ]
                self.subs += self.check_scan_subs
            elif not on and self.check_scan_subs:
                for s in self.check_scan_subs:
                    self.destroy_subscription(s)
                    if s in self.subs:
                        self.subs.remove(s)
                self.check_scan_subs = []
                self.amcl = None

        # ---------------- helpers
        def _pose(self, parent="map", child="base_link"):
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

        # ---------------- mapping-session callbacks (never raise)
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

        # ---------------- saved-map check callbacks (never raise)
        def on_saved_map(self, msg):
            try:
                self.monitor.on_map(ge.grid_from_msg(msg))
            except (ValueError, AttributeError, TypeError) as exc:
                self.get_logger().warn(f'saved map not usable: {exc}')

        def on_check_scan(self, msg):
            if not self._due('scan', CHECK_SCAN_MIN_S):
                return
            try:
                t = self._stamp(msg)
                pose = self.amcl[1:] if self.amcl and abs(t - self.amcl[0]) <= 0.5 else None
                self.monitor.on_scan(t, pose, msg.angle_min, msg.angle_increment,
                                     list(msg.ranges), msg.range_min, msg.range_max)
            except Exception as exc:                            # noqa: BLE001
                self.get_logger().warn(f'check scan skipped: {exc}')

        def on_policy(self, msg):
            if self.mode != 'check':
                return
            armed = autonomy_armed(getattr(msg, 'data', None))
            self.monitor.set_autonomy_armed(armed)
            self._check_scans(not armed)

        def on_amcl(self, msg):
            try:
                p = msg.pose.pose
                self.amcl = (self._stamp(msg), p.position.x, p.position.y, yaw_of(p.orientation))
            except AttributeError:
                self.amcl = None

        # ---------------- timer
        def tick(self):
            try:
                cur = proc_stat()
                if cur is not None:
                    idle = cpu_idle_fraction(self.cpu_prev, cur)
                    self.engine.on_cpu_idle(idle)
                    self.monitor.on_cpu_idle(idle)
                    self.cpu_prev = cur
                active = self.engine.set_session(ge.read_session(session_file))
                self._set_mode('mapping' if active else 'check')
                robot = None
                if active:
                    robot = self._pose()
                    mo = self._pose('map', 'odom')
                    if mo is not None and robot is not None:
                        self.engine.on_map_odom(wall(), mo[0], mo[1], mo[2], robot[:2])
                if not self._due('pub', PUBLISH_S):
                    return
                payload = self.engine.payload(wall(), robot) if active else self.monitor.payload(wall())
                out = String()
                out.data = json.dumps(payload, separators=(',', ':'))
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
    from geometry_msgs.msg import PoseWithCovarianceStamped
    from nav_msgs.msg import OccupancyGrid
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import String

    qos = {'map': QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE),
           'sensor': qos_profile_sensor_data,
           'status': QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)}
    rclpy.init()
    node = make_node(rclpy, Node, qos, {"String": String, "OccupancyGrid": OccupancyGrid, "LaserScan": LaserScan,
                      "PoseWithCovarianceStamped": PoseWithCovarianceStamped},
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

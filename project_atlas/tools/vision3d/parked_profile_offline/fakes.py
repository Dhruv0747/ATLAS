"""Offline fakes for the parked-profile test: odometry/TF/scan publisher, AMCL initial pose, and a fake Dashboard
HTTP API whose answers are driven by a JSON control file. Synthetic data only; private netns only."""
import json, math, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def sensors(stop_tf_file):
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from geometry_msgs.msg import TransformStamped, PoseWithCovarianceStamped
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import LaserScan
    from tf2_ros import TransformBroadcaster, StaticTransformBroadcaster
    rclpy.init(); n = rclpy.create_node('fake_base')
    tfb = TransformBroadcaster(n); stb = StaticTransformBroadcaster(n)
    s = TransformStamped(); s.header.frame_id, s.child_frame_id = 'base_link', 'laser'; s.transform.rotation.w = 1.0
    s.header.stamp = n.get_clock().now().to_msg(); stb.sendTransform(s)
    odom = n.create_publisher(Odometry, '/odom', 10); scan = n.create_publisher(LaserScan, '/scan', qos_profile_sensor_data)
    initp = n.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10); sent = [0]
    def tick():
        now = n.get_clock().now().to_msg()
        if not Path(stop_tf_file).exists():
            t = TransformStamped(); t.header.stamp = now; t.header.frame_id, t.child_frame_id = 'odom', 'base_link'
            t.transform.translation.x = 5.0; t.transform.translation.y = 5.0; t.transform.rotation.w = 1.0; tfb.sendTransform(t)
        o = Odometry(); o.header.stamp = now; o.header.frame_id = 'odom'; o.child_frame_id = 'base_link'
        o.pose.pose.position.x = 5.0; o.pose.pose.position.y = 5.0; o.pose.pose.orientation.w = 1.0; odom.publish(o)
    def scan_tick():
        m = LaserScan(); m.header.stamp = n.get_clock().now().to_msg(); m.header.frame_id = 'laser'
        m.angle_min, m.angle_max = -math.pi, math.pi; m.angle_increment = 2 * math.pi / 360; m.range_min, m.range_max = 0.15, 12.0
        m.ranges = [4.5] * 360; scan.publish(m)
        if sent[0] < 20:   # keep offering the initial pose until AMCL has had a chance to take it
            p = PoseWithCovarianceStamped(); p.header.frame_id = 'map'; p.header.stamp = m.header.stamp
            p.pose.pose.position.x = 5.0; p.pose.pose.position.y = 5.0; p.pose.pose.orientation.w = 1.0
            p.pose.covariance[0] = p.pose.covariance[7] = 0.05; p.pose.covariance[35] = 0.05; initp.publish(p); sent[0] += 1
    n.create_timer(0.05, tick); n.create_timer(0.1, scan_tick)
    print('FAKE SENSORS READY', flush=True); rclpy.spin(n)


def dashboard(port, control_file):
    def state():
        c = json.loads(Path(control_file).read_text()) if Path(control_file).exists() else {}
        pol = {'stop_latched': c.get('stop_latched', True), 'manual_only': True, 'commission_armed': False, 'source': c.get('source', 'STOPPED')}
        ros = {'control_policy': {'value': json.dumps(pol), 'age': 0.2}, 'cmd_vel': {'value': {'lin': c.get('lin', 0.0), 'ang': 0.0}, 'age': 0.2},
               'mission_status': {'value': c.get('mission', 'READY'), 'age': 0.5}, 'motor_speed': {'value': 0.0, 'age': 0.3},
               'amcl_quality': {'value': {'ok': True}, 'age': c.get('amcl_age', 0.8)}}
        return {'ros': ros}, {'latched': c.get('estop', True)}
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            s, e = state(); body = json.dumps(s if self.path.startswith('/api/status') else e if self.path.startswith('/api/estop') else {}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()


if __name__ == '__main__':
    if sys.argv[1] == 'sensors': sensors(sys.argv[2])
    else: dashboard(int(sys.argv[2]), sys.argv[3])

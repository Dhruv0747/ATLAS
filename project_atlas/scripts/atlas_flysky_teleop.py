#!/usr/bin/env python3
"""ATLAS FlySky teleop node: NOT DEPLOYED / DISABLED BY DEFAULT.

Reads   /atlas/rc/frames (std_msgs/String, the existing read-only RC bridge) and /atlas/control_policy (the mux).
Writes  /cmd_vel_flysky        geometry_msgs/Twist  - only when ATLAS_FLYSKY_DRIVE_ENABLED=1 and the config is reviewed;
                                                     the mux accepts it only while FlySky is the selected controller
        /atlas/flysky/stop     std_msgs/Empty       - stop-only request; the mux latches its normal E-STOP
        /atlas/flysky/drive_status  std_msgs/String - JSON status for the dashboard (always)
        /atlas/flysky/reset_request std_msgs/String - Stage 29 FlySky reset: ONE request per completed SwD gesture,
                                                     only when ATLAS_FLYSKY_RESET_ENABLED=1; the mux re-checks and decides
It never opens a serial port, never talks to the motor board, and never resets the E-STOP. All decisions are in
atlas_flysky_drive_core.py.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_flysky_drive_core as core   # noqa: E402
import atlas_flysky_reset as fsreset     # noqa: E402  (Stage 29 FlySky reset)

GATE_ENV = 'ATLAS_FLYSKY_DRIVE_ENABLED'
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / 'config' / 'atlas_flysky_drive.json'
TICK_S = 0.05            # 20 Hz while armed; zero heartbeats are throttled to 5 Hz
IDLE_ZERO_S = 0.2
STATUS_S = 0.5


def load_config(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        return {'_load_error': str(exc)}


def main(argv=None):                                    # pragma: no cover - needs ROS
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    from std_msgs.msg import Empty, String

    rclpy.init(args=argv)
    node = Node('atlas_flysky_teleop')
    node.declare_parameter('config_path', str(DEFAULT_CONFIG))
    cfg = load_config(node.get_parameter('config_path').value)
    logic = core.DriveLogic(cfg, os.environ.get(GATE_ENV, '0') == '1')
    cmd_pub = node.create_publisher(Twist, '/cmd_vel_flysky', 10) if logic.enabled else None
    stop_pub = node.create_publisher(Empty, '/atlas/flysky/stop', 10)
    status_pub = node.create_publisher(String, '/atlas/flysky/drive_status', 10)
    gesture = fsreset.ResetGesture(os.environ.get(fsreset.GATE_ENV, '0') == '1', seq=int(time.time() * 1000))
    reset_pub = node.create_publisher(String, '/atlas/flysky/reset_request', 10) if gesture.enabled else None
    node.create_subscription(String, '/atlas/rc/frames',
                             lambda m: logic.on_frame(core.parse_message(_json(m.data), time.monotonic())), 10)
    mux_reset = {'v': None}                     # Stage 29 FlySky reset: the mux's verdict, forwarded for the dashboard

    def on_policy(m):
        logic.on_policy(core.parse_policy(m.data, time.monotonic()))
        d = _json(m.data)
        mux_reset['v'] = d.get('flysky_reset') if isinstance(d, dict) else None
    node.create_subscription(String, '/atlas/control_policy', on_policy, 10)
    st = {'last_zero': 0.0, 'last_status': 0.0, 'state': None, 'out': None}

    def tick():
        now = time.monotonic()
        out = logic.step(now)
        req = gesture.step(logic, now)
        if req is not None and reset_pub is not None:
            reset_pub.publish(String(data=json.dumps(req)))
            node.get_logger().warn('FlySky SwD reset requested (seq %d, held %.2f s)' % (req['seq'], req['hold_s']))
        if out.stop_request:
            stop_pub.publish(Empty())
        if cmd_pub is not None and out.command is not None:
            moving = out.command != (0.0, 0.0)
            if moving or now - st['last_zero'] >= IDLE_ZERO_S or st['state'] == 'ARMED' and out.state != 'ARMED':
                t = Twist(); t.linear.x, t.angular.z = float(out.command[0]), float(out.command[1])
                cmd_pub.publish(t)
                if not moving:
                    st['last_zero'] = now
        if out.state != st['state']:
            node.get_logger().info('FlySky drive %s: %s' % (out.state, out.reason))
        st['state'], st['out'] = out.state, out
        if gesture.state != st.get('reset_state'):
            st['reset_state'] = gesture.state
            st['last_status'] = 0.0                      # show reset progress on the dashboard at once
        if now - st['last_status'] >= STATUS_S or out.stop_request:
            st['last_status'] = now
            f = logic.frame
            status_pub.publish(String(data=json.dumps({
                'state': out.state, 'reason': out.reason, 'armed': logic.armed,
                'command': out.command, 'stop_requested': out.stop_request, 'inputs': logic.inputs(),
                'frame_age_s': None if f is None else round(now - f.rx, 3),
                'policy': None if logic.policy is None else {'stop_latched': logic.policy.stop_latched,
                                                             'manual_controller': logic.policy.manual_controller,
                                                             'age_s': round(now - logic.policy.rx, 3)},
                'config': logic.summary(), 'gate_env': GATE_ENV,
                'reset': dict(gesture.status(now), mux=mux_reset['v'])})))

    node.create_timer(TICK_S, tick)
    node.get_logger().info('FlySky teleop %s' % ('ENABLED' if logic.enabled else 'DISABLED: ' + '; '.join(logic.errors)))
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if cmd_pub is not None:
            for _ in range(3):
                cmd_pub.publish(Twist()); time.sleep(0.02)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def _json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


if __name__ == '__main__':
    main()

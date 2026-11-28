#!/usr/bin/env python3
"""Read-only ROS observation. Never creates a publisher or opens board serial."""
import argparse
import json
import math
import time


def main():
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=12.0)
    parser.add_argument('--expect-three', action='store_true')
    parser.add_argument('--excluded', type=int, default=3)
    args = parser.parse_args()
    if not 3 <= args.seconds <= 45:
        parser.error('observation duration must be 3–45 seconds')
    rclpy.init()
    node = rclpy.create_node('atlas_encoder_selection_readonly_check')
    state = dict(commands=0, nonzero_commands=0, odometry_messages=0,
                 invalid_odometry=0, first_pose=None, last_pose=None,
                 max_displacement_m=0.0, health=None, policy=None)
    def command(msg):
        state['commands'] += 1
        if any(not math.isfinite(v) or abs(v) > 1e-6 for v in
               (msg.linear.x, msg.linear.y, msg.linear.z,
                msg.angular.x, msg.angular.y, msg.angular.z)):
            state['nonzero_commands'] += 1
    def odometry(msg):
        state['odometry_messages'] += 1
        p = msg.pose.pose.position
        if not all(math.isfinite(v) for v in (p.x, p.y, msg.twist.twist.linear.x)):
            state['invalid_odometry'] += 1
            return
        if state['first_pose'] is None:
            state['first_pose'] = [p.x, p.y]
        state['last_pose'] = [p.x, p.y]
        state['max_displacement_m'] = max(state['max_displacement_m'], math.hypot(
            p.x-state['first_pose'][0], p.y-state['first_pose'][1]))
    def capture(key, msg):
        try: state[key] = json.loads(msg.data)
        except (TypeError, ValueError): state[key] = {'invalid': True}
    node.create_subscription(Twist, '/cmd_vel', command, 10)
    node.create_subscription(Odometry, '/yahboom/odom', odometry, 10)
    node.create_subscription(String, '/atlas/encoder_health', lambda m: capture('health', m), 10)
    node.create_subscription(String, '/atlas/control_policy', lambda m: capture('policy', m), 10)
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.1)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    health = state['health'] or {}
    # A stopped mux is allowed to publish no Twist messages at all. Requiring
    # a zero heartbeat falsely failed a healthy, quiet command channel.
    state['pass_stationary'] = (state['nonzero_commands'] == 0
        and state['odometry_messages'] > 0 and state['invalid_odometry'] == 0
        and state['max_displacement_m'] < .001)
    if args.expect_three:
        expected_selected = [i for i in range(1, 5) if i != args.excluded]
        state['pass_stationary'] = state['pass_stationary'] and (
            health.get('selected_encoders') == expected_selected
            and health.get('excluded_encoders') == [args.excluded]
            and health.get('packet_fresh') is True
            and health.get('state') == 'DEGRADED'
            and health.get('autonomy_ready') is False)
    print(json.dumps(state, indent=2))
    return 0 if state['pass_stationary'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
import sys, os
if 'ROS_DISTRO' not in os.environ:
    os.execv('/bin/bash', ['/bin/bash', '-c',
        'source /opt/ros/humble/setup.bash && '
        'source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null; '
        f'exec python3 {" ".join(sys.argv)}'])
import math, time, subprocess, argparse, signal, random
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan
SPD = 0.20
TRN = 0.60
DIST = 0.35
ARC = 35
INT = 12

class ReactiveExplorer(Node):
    def __init__(self, speed=SPD):
        super().__init__('rover_explorer')
        self.speed = speed
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.scan = None
        self.create_subscription(LaserScan, '/scan', self._cb, 10)
        self.get_logger().info('Ready â€” waiting for lidar...')

    def _cb(self, msg):
        self.scan = msg

    def _angles(self):
        s = self.scan
        if not s:
            return
        for i, r in enumerate(s.ranges):
            if not (s.range_min < r < s.range_max):
                continue
            angle = s.angle_min + i * s.angle_increment
            angle = angle % (2 * math.pi) - math.pi
            yield angle, r

    def ok(self):
        arc = math.radians(ARC)
        for a, r in self._angles():
            if abs(a) <= arc and r < DIST:
                return False
        return True

    def side(self):
        L = R = 1e9
        for a, r in self._angles():
            if 0.1 < a < 1.6:
                L = min(L, r)
            elif -1.6 < a < -0.1:
                R = min(R, r)
        if L == R == 1e9:
            return random.choice([1, -1])
        return 1 if L > R else -1

    def go(self, lin, ang):
        m = Twist()
        m.linear.x = lin
        m.angular.z = ang
        self.pub.publish(m)

    def stop(self):
        for _ in range(3):
            self.go(0.0, 0.0)
            time.sleep(0.05)


def save_map(node, path='/home/jetson/project_atlas/maps/my_map'):
    node.get_logger().info(f'Saving map to {path}.pgm ...')
    r = subprocess.run(
        ['ros2', 'run', 'nav2_map_server', 'map_saver_cli', '-f', path],
        capture_output=True, text=True, timeout=25)
    if r.returncode == 0:
        print(f'\nMap saved: {path}.pgm + {path}.yaml')
    else:
        print(f'\nMap FAILED:\n{r.stderr}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=float, default=300)
    parser.add_argument('--speed', type=float, default=SPD)
    parser.add_argument('--map', default='/home/jetson/project_atlas/maps/my_map')
    args = parser.parse_args()
    rclpy.init()
    node = ReactiveExplorer(speed=args.speed)
    done = [False]
    signal.signal(signal.SIGINT, lambda *_: done.__setitem__(0, True))
    node.get_logger().info('Waiting for lidar scan (up to 10s)...')
    t = time.time()
    while node.scan is None and time.time() - t < 10 and not done[0]:
        rclpy.spin_once(node, timeout_sec=0.2)
    if node.scan is None:
        node.get_logger().error('No /scan received â€” is RPLidar running?')
        node.destroy_node(); rclpy.shutdown(); return
    node.get_logger().info(
        f'GO! {args.duration:.0f}s  {args.speed}m/s  Ctrl+C to stop+save')
    t0 = time.time()
    lt = t0
    turning = False
    td = 1
    te = 0.0
    try:
        while not done[0] and (time.time() - t0) < args.duration:
            rclpy.spin_once(node, timeout_sec=0.05)
            now = time.time()
            if turning:
                if now >= te:
                    turning = False
                    node.get_logger().info('Turn done -> forward')
                else:
                    node.go(0.0, td * TRN)
                continue
            if now - lt >= INT:
                td = node.side()
                deg = random.uniform(70, 130)
                te = now + math.radians(deg) / TRN
                turning = True
                lt = now
                node.get_logger().info(f'Planned turn {deg:.0f}deg')
                continue
            if not node.ok():
                node.stop()
                td = node.side()
                te = now + 1.4
                turning = True
                node.get_logger().info('Obstacle! Turning')
                continue
            node.go(args.speed, 0.0)
    except Exception as e:
        node.get_logger().error(f'Error: {e}')
    finally:
        node.stop()
        elapsed = time.time() - t0
        node.get_logger().info(f'Done after {elapsed:.0f}s')
        save_map(node, args.map)
        node.destroy_node()
        rclpy.shutdown()
        print('View map: Foxglove -> Map panel -> /map topic')


if __name__ == '__main__':
    main()

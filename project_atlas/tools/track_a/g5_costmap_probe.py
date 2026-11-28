"""G5 read-only probe in production domain 0. Modes: pose | costmap"""
import sys, math, json, time
import numpy as np, rclpy
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import OccupancyGrid
import tf2_ros
mode = sys.argv[1]
rclpy.init(); n = rclpy.create_node('track_a_g5_probe')
def spin(sec, stop=None):
    end = time.monotonic() + sec
    while time.monotonic() < end and not (stop and stop()):
        rclpy.spin_once(n, timeout_sec=0.1)
def yaw(q): return math.degrees(math.atan2(2*(q.w*q.z + q.x*q.y), 1 - 2*(q.y*q.y + q.z*q.z)))
if mode == 'pose':
    got = []
    n.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', got.append, QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE))
    spin(12, lambda: got)
    if got:
        p = got[-1].pose.pose; c = got[-1].pose.covariance
        print(json.dumps({'amcl_x': round(p.position.x, 3), 'amcl_y': round(p.position.y, 3), 'amcl_yaw_deg': round(yaw(p.orientation), 1),
                          'std_xy_m': round(math.sqrt(max(c[0], c[7])), 3), 'std_yaw_deg': round(math.degrees(math.sqrt(c[35])), 1)}))
    else: print('amcl_pose: none received')
if mode == 'costmap':
    from rcl_interfaces.srv import GetParameters
    cli = n.create_client(GetParameters, '/local_costmap/local_costmap/get_parameters')
    if cli.wait_for_service(timeout_sec=8):
        f = cli.call_async(GetParameters.Request(names=['plugins', 'astra_layer.astra.topic', 'astra_layer.astra.inf_is_valid', 'obstacle_layer.scan.topic', 'astra_layer.astra.expected_update_rate']))
        spin(5, lambda: f.done())
        if f.done(): print('local costmap params:', [ (v.string_array_value or v.string_value or v.bool_value or v.double_value) for v in f.result().values])
    else: print('local costmap param service not available')
    print('publishers/subscribers /astra/obstacle_scan:', n.count_publishers('/astra/obstacle_scan'), '/', n.count_subscribers('/astra/obstacle_scan'))
    buf = tf2_ros.Buffer(); tf2_ros.TransformListener(buf, n)
    grids = []
    n.create_subscription(OccupancyGrid, '/local_costmap/costmap', grids.append, QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE))
    spin(10, lambda: len(grids) >= 2)
    if not grids: print('no local costmap received'); sys.exit()
    g = grids[-1]; W, H, res = g.info.width, g.info.height, g.info.resolution
    ox, oy = g.info.origin.position.x, g.info.origin.position.y
    t = buf.lookup_transform(g.header.frame_id, 'base_link', rclpy.time.Time(), timeout=rclpy.duration.Duration(seconds=3))
    bx, by = t.transform.translation.x, t.transform.translation.y; byaw = math.radians(yaw(t.transform.rotation))
    data = np.array(g.data, dtype=np.int16).reshape(H, W)
    def cell_cost(xb, yb):
        wx = bx + xb*math.cos(byaw) - yb*math.sin(byaw); wy = by + xb*math.sin(byaw) + yb*math.cos(byaw)
        i, j = int((wy - oy)/res), int((wx - ox)/res)
        return int(data[i, j]) if 0 <= i < H and 0 <= j < W else None
    print(f'costmap frame {g.header.frame_id} {W}x{H} @ {res} m; robot at ({bx:.2f},{by:.2f}) yaw {math.degrees(byaw):.0f}')
    box = [cell_cost(x, y) for x in np.arange(1.22, 1.36, res/2) for y in np.arange(-0.10, 0.11, res/2)]
    box = [c for c in box if c is not None]
    print('box region (x 1.22-1.35, |y|<=0.10): max cost', max(box), '| lethal(100) cells', sum(c >= 99 for c in box), 'of', len(box))
    lane = [cell_cost(x, y) for x in np.arange(0.35, 1.15, res/2) for y in np.arange(-0.15, 0.16, res/2)]
    lane = [c for c in lane if c is not None]
    print('open floor between rover and box (x 0.35-1.15, |y|<=0.15): max cost', max(lane), '| lethal', sum(c >= 99 for c in lane))
    print('whole local costmap: lethal cells', int((data >= 99).sum()), '| inflated (1-98)', int(((data > 0) & (data < 99)).sum()))
    rows = []
    for x in np.arange(1.5, -0.01, -0.1):
        rows.append(''.join({None: ' ', 0: '.'}.get(c, '#' if c >= 99 else '+') for c in [cell_cost(x, y) for y in np.arange(0.6, -0.61, -0.05)]))
    print('costmap ahead (top = 1.5 m ahead, bottom = robot; # lethal, + inflated, . free; left..right):')
    print('\n'.join('   ' + r for r in rows))
rclpy.shutdown()

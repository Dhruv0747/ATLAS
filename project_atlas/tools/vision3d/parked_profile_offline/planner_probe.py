"""Ask the planner for a path (ComputePathToPose) from the robot to (10, 10); prints SUCCEEDED / REJECTED / ..."""
import time, rclpy
from rclpy.action import ActionClient
from nav2_msgs.action import ComputePathToPose
rclpy.init(); n = rclpy.create_node('planner_probe'); c = ActionClient(n, ComputePathToPose, '/compute_path_to_pose')
if not c.wait_for_server(timeout_sec=10): print('NO_SERVER'); raise SystemExit
g = ComputePathToPose.Goal(); g.goal.header.frame_id = 'map'; g.goal.pose.position.x = 10.0; g.goal.pose.position.y = 10.0; g.goal.pose.orientation.w = 1.0
f = c.send_goal_async(g); end = time.monotonic() + 30
while not f.done() and time.monotonic() < end: rclpy.spin_once(n, timeout_sec=0.1)
h = f.result() if f.done() else None
if h is None: print('NO_RESPONSE'); raise SystemExit
if not h.accepted: print('REJECTED'); raise SystemExit
rf = h.get_result_async(); end = time.monotonic() + 45
while not rf.done() and time.monotonic() < end: rclpy.spin_once(n, timeout_sec=0.1)
if not rf.done(): print('TIMEOUT'); raise SystemExit
st = rf.result().status; print({4: 'SUCCEEDED', 5: 'CANCELED', 6: 'ABORTED'}.get(st, 'STATUS_%d' % st), len(rf.result().result.path.poses))

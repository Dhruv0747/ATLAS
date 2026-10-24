"""TEST ONLY: pause/resume the LOCALIZATION manager to recreate 'no map->odom transform' (boot -3 condition)."""
import sys, time, rclpy
from nav2_msgs.srv import ManageLifecycleNodes
rclpy.init(); n = rclpy.create_node('test_loc_manager'); c = n.create_client(ManageLifecycleNodes, '/lifecycle_manager_localization/manage_nodes')
c.wait_for_service(timeout_sec=10); r = ManageLifecycleNodes.Request(); r.command = {'pause': 1, 'resume': 2}[sys.argv[1]]
f = c.call_async(r); end = time.monotonic() + 60
while not f.done() and time.monotonic() < end: rclpy.spin_once(n, timeout_sec=0.1)
print('LOC', sys.argv[1], f.result().success if f.done() else None)

"""Read-only: collect ~10 s of live /scan, /amcl_pose, /odom and the base->laser TF."""
import math, sys, time
import numpy as np, rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseWithCovarianceStamped
from tf2_ros import Buffer, TransformListener
rclpy.init(); n = rclpy.create_node('atlas_mapfix_readonly_probe')
S, A, O = [], [], []
yaw = lambda q: math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
n.create_subscription(LaserScan, '/scan', lambda m: S.append((time.time(), np.asarray(m.ranges, np.float32), m.angle_min, m.angle_increment, m.header.frame_id)), qos_profile_sensor_data)
n.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', lambda m: A.append((time.time(), m.pose.pose.position.x, m.pose.pose.position.y, yaw(m.pose.pose.orientation))), 10)
n.create_subscription(Odometry, '/odom', lambda m: O.append((time.time(), m.twist.twist.linear.x, m.twist.twist.angular.z)), 10)
tf = Buffer(); TransformListener(tf, n)
end = time.time() + float(sys.argv[2])
while time.time() < end: rclpy.spin_once(n, timeout_sec=0.1)
t = tf.lookup_transform('base_link', S[0][4], rclpy.time.Time()).transform
k = max(len(s[1]) for s in S); R = np.full((len(S), k), np.nan, np.float32)
for i, s in enumerate(S): R[i, :len(s[1])] = s[1]
np.savez_compressed(sys.argv[1], scan_t=np.array([s[0] for s in S]), scan_r=R, scan_meta=np.array([S[0][2], S[0][3]]),
    laser=np.array([t.translation.x, t.translation.y, yaw(t.rotation)]), amcl=np.array(A), odom=np.array(O))
print('scans', len(S), 'amcl', len(A), 'max |v|', max(abs(o[1]) for o in O), 'max |w|', max(abs(o[2]) for o in O))

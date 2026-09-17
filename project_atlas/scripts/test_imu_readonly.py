#!/usr/bin/env python3
"""30-second subscription-only IMU sample audit; never opens the serial port."""
import json
import time
import statistics
import rclpy
from sensor_msgs.msg import Imu
from geometry_msgs.msg import Vector3Stamped

rclpy.init()
node=rclpy.create_node('atlas_imu_readonly_audit')
samples={'imu':[], 'mag':[]}
def imu(m):
    samples['imu'].append((time.monotonic(),m.header.stamp.sec*10**9+m.header.stamp.nanosec,
        (m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z,
         m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z)))
def mag(m):
    samples['mag'].append((time.monotonic(),m.header.stamp.sec*10**9+m.header.stamp.nanosec,
        (m.vector.x,m.vector.y,m.vector.z)))
node.create_subscription(Imu,'/yahboom/imu/data_uncalibrated',imu,10)
node.create_subscription(Vector3Stamped,'/yahboom/imu/mag_raw',mag,10)
end=time.monotonic()+30
while time.monotonic()<end:
    rclpy.spin_once(node,timeout_sec=.2)
result={}
for key,rows in samples.items():
    result[key]={'messages':len(rows),'unique_payloads':len({r[2] for r in rows}),
        'unique_stamps':len({r[1] for r in rows})}
    if len(rows)>1:
        result[key]['hz']=(len(rows)-1)/(rows[-1][0]-rows[0][0])
        result[key]['max_gap_s']=max(b[0]-a[0] for a,b in zip(rows,rows[1:]))
        result[key]['axes']=[{'min':min(v),'max':max(v),'mean':statistics.mean(v),'std':statistics.pstdev(v)} for v in zip(*(r[2] for r in rows))]
print(json.dumps(result,indent=2))
node.destroy_node()
rclpy.shutdown()

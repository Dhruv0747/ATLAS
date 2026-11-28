"""Synthetic ROS fixture only; loopback domain 179, no hardware or control topics."""
import os
from rtabmap_offline import isolated_env
clean_env = isolated_env()
os.environ.clear()
os.environ.update(clean_env)
import math
import time
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, CameraInfo, LaserScan
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from rosgraph_msgs.msg import Clock
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster


def main():
    rclpy.init()
    n = rclpy.create_node('synthetic_rgbd', namespace='/atlas_offline')
    pubs = {k:n.create_publisher(t,'input/'+k,qos_profile_sensor_data)
            for k,t in [('rgb',Image),('depth',Image),('camera_info',CameraInfo),
                        ('odom',Odometry),('scan',LaserScan)]}
    clock = n.create_publisher(Clock, '/clock', 10)
    tf = StaticTransformBroadcaster(n)
    dynamic_tf = TransformBroadcaster(n)
    tr=TransformStamped(); tr.header.frame_id='base_link'; tr.child_frame_id='test_optical_frame'
    tr.transform.rotation.x=-.5; tr.transform.rotation.y=.5
    tr.transform.rotation.z=-.5; tr.transform.rotation.w=.5
    tf.sendTransform(tr)
    start=time.monotonic(); count=0
    try:
        while time.monotonic()-start < 20:
            stamp=rclpy.time.Time(seconds=10+count*.2).to_msg()
            c=Clock(); c.clock=stamp; clock.publish(c)
            rgb=Image(); rgb.header.stamp=stamp; rgb.header.frame_id='test_optical_frame'
            rgb.width=320; rgb.height=240; rgb.encoding='rgb8'; rgb.step=960
            rgb.data=bytes([255,255,255,0,0,0])*38400
            depth=Image(); depth.header=rgb.header; depth.width=320; depth.height=240
            depth.encoding='16UC1'; depth.step=640; depth.data=bytes([232,3])*76800
            info=CameraInfo(); info.header=rgb.header; info.width=320; info.height=240
            info.distortion_model='plumb_bob'; info.d=[0.]*5
            info.k=[300.,0.,160.,0.,300.,120.,0.,0.,1.]
            info.p=[300.,0.,160.,0.,0.,300.,120.,0.,0.,0.,1.,0.]
            odom=Odometry(); odom.header.stamp=stamp; odom.header.frame_id='odom'
            odom.child_frame_id='base_link'; odom.pose.pose.orientation.w=1.
            for i in (0,7,14,21,28,35): odom.pose.covariance[i]=.001
            ot=TransformStamped(); ot.header=odom.header; ot.child_frame_id='base_link'
            ot.transform.rotation.w=1.; dynamic_tf.sendTransform(ot)
            scan=LaserScan(); scan.header=rgb.header; scan.header.frame_id='base_link'
            scan.angle_min=-math.pi; scan.angle_max=math.pi; scan.angle_increment=math.pi/180
            scan.range_min=.1; scan.range_max=5.; scan.ranges=[2.]*361
            for key,msg in [('rgb',rgb),('depth',depth),('camera_info',info),('odom',odom),('scan',scan)]:
                pubs[key].publish(msg)
            rclpy.spin_once(n,timeout_sec=.01); time.sleep(.19); count+=1
    finally:
        n.destroy_node(); rclpy.shutdown()
    print('synthetic bundles published:',count)


if __name__=='__main__': main()

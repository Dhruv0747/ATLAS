"""Twenty independent AMCL cold starts in a synthetic stationary room.

Measures stochastic startup variation, not historical failure reproduction or
robot accuracy. No controller, motor, steering or production DDS access.
"""
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import time
import uuid
from stage19_contract import require_isolation
require_isolation()
import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped,TransformStamped
from sensor_msgs.msg import LaserScan
from lifecycle_msgs.srv import ChangeState
from nav2_msgs.srv import SetInitialPose
from std_srvs.srv import Empty
from tf2_ros import StaticTransformBroadcaster,TransformBroadcaster

root=Path('/tmp/replay')/('ensemble_'+uuid.uuid4().hex[:8]);root.mkdir()
(root/'room.pgm').write_bytes(b'P5\n100 100\n255\n'+bytes(0 if x in (0,99) or y in (0,99) else 254 for y in range(100) for x in range(100)))
(root/'room.yaml').write_text('image: room.pgm\nresolution: 0.05\norigin: [-2.5,-2.5,0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n')
(root/'config.yaml').write_text('''/**:
  ros__parameters:
    base_frame_id: base_link
    odom_frame_id: odom
    global_frame_id: map
    min_particles: 500
    max_particles: 2000
    max_beams: 30
    robot_model_type: nav2_amcl::DifferentialMotionModel
    set_initial_pose: false
'''+f'    yaml_filename: {root}/room.yaml\n')
rclpy.init();n=rclpy.create_node('stage20_ensemble_fixture',enable_rosout=False)
scan=n.create_publisher(LaserScan,'/scan',10)
static=StaticTransformBroadcaster(n);dynamic=TransformBroadcaster(n)
tf=TransformStamped();tf.header.stamp=n.get_clock().now().to_msg();tf.header.frame_id='base_link';tf.child_frame_id='laser';tf.transform.rotation.w=1.;static.sendTransform(tf)
poses=[]
sub=n.create_subscription(PoseWithCovarianceStamped,'/amcl_pose',lambda m:poses.append(m),10)
def call(name,typ,request):
    c=n.create_client(typ,name)
    try:
        if not c.wait_for_service(timeout_sec=8):raise RuntimeError('service unavailable')
        f=c.call_async(request);rclpy.spin_until_future_complete(n,f,timeout_sec=8)
        if not f.done() or f.exception():raise RuntimeError('service failure')
        return f.result()
    finally:n.destroy_client(c)
log=(root/'children.log').open('w');children=[];runs=[]
try:
    server=subprocess.Popen(['/opt/ros/humble/lib/nav2_map_server/map_server','--ros-args','--params-file',str(root/'config.yaml')],stdout=log,stderr=log);children.append(server)
    for transition in (1,3):
        req=ChangeState.Request();req.transition.id=transition;assert call('/map_server/change_state',ChangeState,req).success
    for index in range(20):
        child=subprocess.Popen(['/tmp/replay/amcl_install_r3/lib/nav2_amcl/amcl','--ros-args','--params-file',str(root/'config.yaml')],env=dict(os.environ,ATLAS_CHECKPOINT_EVENTS='1'),stdout=log,stderr=log)
        children.append(child);start=time.monotonic();seeded=False;last_request=0.;first_stamp=None;poses.clear()
        try:
            for transition in (1,3):
                req=ChangeState.Request();req.transition.id=transition;assert call('/amcl/change_state',ChangeState,req).success
            while time.monotonic()-start<5:
                stamp=n.get_clock().now().to_msg()
                if first_stamp is None:first_stamp=stamp.sec*1000000000+stamp.nanosec
                t=TransformStamped();t.header.stamp=stamp;t.header.frame_id='odom';t.child_frame_id='base_link';t.transform.rotation.w=1.;dynamic.sendTransform(t)
                s=LaserScan();s.header.stamp=stamp;s.header.frame_id='laser';s.angle_min=-math.pi;s.angle_max=math.pi;s.angle_increment=2*math.pi/360;s.range_min=.05;s.range_max=10.
                s.ranges=[2.45/max(abs(math.cos(s.angle_min+k*s.angle_increment)),abs(math.sin(s.angle_min+k*s.angle_increment))) for k in range(361)];scan.publish(s)
                rclpy.spin_once(n,timeout_sec=.02)
                if not seeded:
                    req=SetInitialPose.Request();req.pose.header.frame_id='map';req.pose.header.stamp=stamp;req.pose.pose.pose.orientation.w=1.
                    req.pose.pose.covariance[0]=.01;req.pose.pose.covariance[7]=.01;req.pose.pose.covariance[35]=.01
                    call('/set_initial_pose',SetInitialPose,req);seeded=True
                if time.monotonic()-last_request>.5:call('/request_nomotion_update',Empty,Empty.Request());last_request=time.monotonic()
                time.sleep(.1)
            current=[p for p in poses if p.header.stamp.sec*1000000000+p.header.stamp.nanosec>=first_stamp]
            if not current:raise RuntimeError('no current-session AMCL pose')
            xy=[(p.pose.pose.position.x,p.pose.pose.position.y) for p in current]
            jumps=[math.dist(a,b) for a,b in zip(xy,xy[1:])]
            final=current[-1];yaw=2*math.atan2(final.pose.pose.orientation.z,final.pose.pose.orientation.w)
            runs.append({'run':index,'status':'PASS','pose_count':len(current),'jump_count':sum(v>.5 for v in jumps),
                'max_jump_m':max(jumps,default=0.),'final_x':xy[-1][0],'final_y':xy[-1][1],
                'final_yaw_rad':yaw,'xy_std_m':math.sqrt(max(0.,final.pose.covariance[0]+final.pose.covariance[7])),
                'wall_s':time.monotonic()-start})
        except Exception as exc:runs.append({'run':index,'status':'FAILED','error':type(exc).__name__})
        finally:
            child.terminate()
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()
    valid=[r for r in runs if r['status']=='PASS'];variation={}
    for key in ('max_jump_m','final_x','final_y','final_yaw_rad','xy_std_m'):
        values=[r[key] for r in valid]
        if values:variation[key]={'mean':statistics.mean(values),'min':min(values),'max':max(values),'std':statistics.stdev(values) if len(values)>1 else 0.}
    report={'runs':runs,'valid_runs':len(valid),'variation':variation,'historical_failure_reproduced':False,
        'replay_fidelity_verified':False,'fixture':'identical synthetic geometry; live timestamp/service scheduling varies; RNG opaque',
        'max_particles':2000,'production_changed':False}
    (root/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='runs'}))
finally:
    for child in children:
        if child.poll() is None:child.terminate();child.wait(timeout=10)
    n.destroy_node();rclpy.shutdown();log.close()

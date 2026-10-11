"""Bounded read-only costmap/scan/parameter capture; no command publishers."""
import argparse
import json
import math
from pathlib import Path
import time
import rclpy
from rcl_interfaces.srv import GetParameters
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from nav2_msgs.msg import Costmap
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from tf2_ros import Buffer, TransformListener

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():p.error('use a new evidence path')
    rclpy.init();n=rclpy.create_node('atlas_parked_geometry_probe')
    buf=Buffer();listener=TransformListener(buf,n)
    latest={};counts={};first={};last={};rows=[]
    def cb(key,msg):
        t=time.monotonic();latest[key]=msg;counts[key]=counts.get(key,0)+1
        first.setdefault(key,t);last[key]=t
    for key,typ,topic in [('scan',LaserScan,'/scan'),('local',Costmap,'/local_costmap/costmap_raw'),('global',Costmap,'/global_costmap/costmap_raw'),('amcl',PoseWithCovarianceStamped,'/amcl_pose'),('cmd',Twist,'/cmd_vel_nav')]:
        qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL) if key in ('local','global') else qos_profile_sensor_data
        n.create_subscription(typ,topic,lambda m,k=key:cb(k,m),qos)
    requests={
        '/local_costmap/local_costmap':['footprint','footprint_padding','track_unknown_space','inflation_layer.inflation_radius','inflation_layer.cost_scaling_factor','obstacle_layer.observation_sources','obstacle_layer.scan.topic','obstacle_layer.scan.marking','obstacle_layer.scan.clearing','obstacle_layer.scan.expected_update_rate','obstacle_layer.scan.inf_is_valid','update_frequency'],
        '/global_costmap/global_costmap':['footprint','track_unknown_space','inflation_layer.inflation_radius','obstacle_layer.observation_sources','obstacle_layer.scan.topic'],
        '/controller_server':['FollowPath.allow_reversing','FollowPath.use_collision_detection','FollowPath.max_allowed_time_to_collision_up_to_carrot','FollowPath.desired_linear_vel'],
        '/planner_server':['GridBased.motion_model_for_search','GridBased.allow_unknown','GridBased.minimum_turning_radius'],
        '/amcl':['scan_topic','max_beams'],
    }
    clients={k:n.create_client(GetParameters,k+'/get_parameters') for k in requests};futures={};params={}
    start=time.monotonic();next_sample=start
    while time.monotonic()-start<18:
        rclpy.spin_once(n,timeout_sec=.04)
        for k,c in clients.items():
            if k not in futures and c.service_is_ready():futures[k]=c.call_async(GetParameters.Request(names=requests[k]))
            f=futures.get(k)
            if f and f.done() and k not in params:
                try:params[k]={name:{'type':v.type,'bool':v.bool_value,'double':v.double_value,'integer':v.integer_value,'string':v.string_value} for name,v in zip(requests[k],f.result().values)}
                except Exception as e:params[k]={'error':str(e)}
        if time.monotonic()<next_sample:continue
        next_sample=time.monotonic()+.5;row={}
        for k,m in latest.items():
            row[k]={'receipt_age_s':time.monotonic()-last[k]}
            if hasattr(m,'header'):
                stamp=m.header.stamp.sec+m.header.stamp.nanosec/1e9
                row[k].update(stamp=stamp,source_age_s=n.get_clock().now().nanoseconds/1e9-stamp,frame=m.header.frame_id)
            if k in ('local','global'):
                try:
                    tf=buf.lookup_transform(m.header.frame_id,'base_link',rclpy.time.Time.from_msg(m.header.stamp)).transform
                    q=tf.rotation;yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
                    # Previously recorded suspicious beam, not a new matched-ray attribution.
                    x,y=.3618828573,-.358044129
                    wx=tf.translation.x+math.cos(yaw)*x-math.sin(yaw)*y
                    wy=tf.translation.y+math.sin(yaw)*x+math.cos(yaw)*y
                    ox,oy=m.metadata.origin.position.x,m.metadata.origin.position.y
                    oq=m.metadata.origin.orientation;oa=math.atan2(2*(oq.w*oq.z+oq.x*oq.y),1-2*(oq.y*oq.y+oq.z*oq.z))
                    dx,dy=wx-ox,wy-oy
                    ix=math.floor((math.cos(oa)*dx+math.sin(oa)*dy)/m.metadata.resolution)
                    iy=math.floor((-math.sin(oa)*dx+math.cos(oa)*dy)/m.metadata.resolution)
                    row[k].update(robot=[tf.translation.x,tf.translation.y,yaw],historical_ray_cell=[ix,iy],historical_ray_cost=int(m.data[iy*m.metadata.size_x+ix]) if 0<=ix<m.metadata.size_x and 0<=iy<m.metadata.size_y else None)
                except Exception as e:row[k]['tf_error']=str(e)[:140]
            if k=='amcl':row[k]['variance']=[m.pose.covariance[i] for i in (0,7,35)]
            if k=='cmd':row[k]['velocity']=[m.linear.x,m.angular.z]
        rows.append(row)
    out={'parameters':params,'counts':counts,'rows':rows,'hz':{k:(counts[k]-1)/(last[k]-first[k]) if last[k]>first[k] else None for k in counts}}
    m=latest.get('local')
    if m:
        out['local_grid']={'width':m.metadata.size_x,'height':m.metadata.size_y,'resolution':m.metadata.resolution,'origin':[m.metadata.origin.position.x,m.metadata.origin.position.y],'data':list(m.data)}
    a.out.write_text(json.dumps(out));print(json.dumps({'counts':counts,'hz':out['hz'],'parameter_nodes':list(params)}))
    n.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()

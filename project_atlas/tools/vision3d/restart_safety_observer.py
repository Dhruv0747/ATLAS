"""Independent read-only ROS observer. Import is inert; main is approval-gated.

No publishers, services, camera subscriptions or HTTP dependency. Local monotonic
receipt times enforce freshness for the existing unstamped String/Twist topics.
"""
import argparse
import json
import math
import os
from pathlib import Path
import time


class Safety:
    def __init__(self):self.values={};self.failure=None;self.armed=False
    def receive(self,key,value,now):self.values[key]=(value,now)
    def evaluate(self,now):
        try:
            values={}
            for key in ('policy','command','encoders'):
                value,stamp=self.values[key]
                if not math.isfinite(stamp) or not 0<=now-stamp<=1:raise ValueError(key+' stale')
                values[key]=value
            p=values['policy'];c=values['command'];e=values['encoders']
            if p.get('stop_latched') is not True or p.get('manual_only') is not True or p.get('commission_armed') is not False or p.get('source')!='STOPPED':raise ValueError('control policy unsafe')
            if len(c)!=6 or any(type(x) not in (float,int) or not math.isfinite(x) or x!=0 for x in c):raise ValueError('commands not zero')
            age=e['packet_age_s'];delta=e['encoder_interval_delta_m']
            if e['packet_fresh'] is not True or e['link_state']!='LIVE' or type(age) not in (float,int) or not math.isfinite(age) or not 0<=age+now-self.values['encoders'][1]<=1:raise ValueError('encoder link stale')
            if len(delta)!=4 or any(type(x) not in (float,int) or not math.isfinite(x) or x!=0 for x in delta):raise ValueError('encoder motion')
        except (KeyError,ValueError,TypeError,AttributeError) as exc:
            if self.armed:self.failure=self.failure or str(exc)
            return {'safe':False,'reason':self.failure or str(exc)}
        self.armed=True
        return {'safe':self.failure is None,'reason':self.failure,'ages':{k:now-v[1] for k,v in self.values.items()}}


def atomic(path,data):
    temp=path.with_suffix('.tmp')
    with temp.open('w') as f:json.dump(data,f,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def read_observer(path,nonce,now):
    j=json.loads(Path(path).read_text())
    if j.get('nonce')!=nonce or type(j.get('mono')) not in (int,float) or not math.isfinite(j['mono']) or not 0<=now-j['mono']<=.75 or j.get('safe') is not True:
        raise ValueError('independent safety missing/stale/failed')
    return j


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--nonce',required=True);parser.add_argument('--duration',type=float,default=180)
    args=parser.parse_args()
    if not 0<args.duration<=180:raise ValueError('observer duration bound')
    import rclpy
    from std_msgs.msg import String
    from geometry_msgs.msg import Twist
    rclpy.init();node=rclpy.create_node('atlas_web_restart_readonly_observer',enable_rosout=False,start_parameter_services=False);safety=Safety()
    def string(key,msg):
        try:value=json.loads(msg.data)
        except (TypeError,ValueError):value=None
        safety.receive(key,value,time.monotonic())
    node.create_subscription(String,'/atlas/control_policy',lambda m:string('policy',m),10)
    node.create_subscription(String,'/atlas/encoder_health',lambda m:string('encoders',m),10)
    node.create_subscription(Twist,'/cmd_vel',lambda m:safety.receive('command',[m.linear.x,m.linear.y,m.linear.z,m.angular.x,m.angular.y,m.angular.z],time.monotonic()),10)
    deadline=time.monotonic()+args.duration;path=Path(args.output);last_emit=0
    try:
        while time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.1);now=time.monotonic()
            state=safety.evaluate(now)
            if now-last_emit>=.1:
                atomic(path,dict(state,mono=now,nonce=args.nonce,pid=os.getpid()));last_emit=now
    except rclpy.executors.ExternalShutdownException:
        pass
    finally:
        atomic(path,{'safe':False,'reason':'observer ended','mono':time.monotonic(),'nonce':args.nonce})
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()

if __name__=='__main__':main()

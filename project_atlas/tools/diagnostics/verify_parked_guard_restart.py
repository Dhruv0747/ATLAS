"""Finite direct-ROS stop verification; optionally restart only the guard owners.

Never publishes commands, resets E-STOP or changes parameters. Avoids treating
dashboard HTTP latency as ROS control health. Explicit rollback path required
for the approved restart; caller installs/rehearses files separately.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from sensor_msgs.msg import LaserScan,Imu,Joy
from nav_msgs.msg import Odometry

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--restart',action='store_true')
    p.add_argument('--rollback',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('preserve existing evidence')
    if a.restart and (not a.rollback or not a.rollback.is_file() or
        a.rollback.name!='ROLLBACK.sh' or
        a.rollback.resolve().parent.parent!=Path('/home/jetson/project_atlas/data/backups')):
        p.error('exact stage backup rollback required')
    rclpy.init();n=Node('atlas_parked_guard_verifier')
    latest={};counts={};unsafe=[];rows=[]
    def receive(name,msg):
        now=time.monotonic();latest[name]=now;counts[name]=counts.get(name,0)+1
        if name=='cmd' and (msg.linear.x!=0 or msg.angular.z!=0):unsafe.append('nonzero command')
        if name=='policy':
            try:
                if not json.loads(msg.data)['stop_latched']:unsafe.append('stop released')
            except (ValueError,KeyError):unsafe.append('invalid stop policy')
    for cls,topic,name,qos in ((Twist,'/cmd_vel','cmd',10),(String,'/atlas/control_policy','policy',10),
        (Joy,'/joy','joy',qos_profile_sensor_data),
        (LaserScan,'/scan','scan',qos_profile_sensor_data),(Imu,'/imu/data','imu',qos_profile_sensor_data),
        (Odometry,'/odom','odom',qos_profile_sensor_data)):
        n.create_subscription(cls,topic,lambda msg,key=name:receive(key,msg),qos)
    def check_window(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            rclpy.spin_once(n,timeout_sec=.05)
            if unsafe:raise RuntimeError(unsafe[-1])
        now=time.monotonic();ages={key:now-value for key,value in latest.items()}
        rows.append(dict(counts=dict(counts),ages=ages))
        assert all(ages.get(k,999)<=1 for k in ('cmd','policy')),'fresh direct stop evidence missing'
    units=['atlas-cmd-vel-mux','atlas-tight-recovery']
    restarted=False
    try:
        check_window(10)
        for unit in ('atlas-nav2','atlas-explore'):
            assert subprocess.check_output(['systemctl','--user','show',unit,'-p','ActiveState','--value'],text=True).strip()=='inactive'
        if a.restart:
            restarted=True
            subprocess.run(['systemctl','--user','restart',*units],check=True,timeout=20)
            # DDS/Python startup is not instantaneous. No motion is allowed in
            # this interval, and acceptance still requires fresh direct samples.
            check_window(15)
        check_window(10)
        for unit in units:
            assert subprocess.check_output(['systemctl','--user','is-active',unit],text=True).strip()=='active'
        print('DIRECT_ROS_STOP_VERIFIED')
    except Exception:
        if restarted:
            subprocess.run(['bash',str(a.rollback)],check=True,timeout=30)
            subprocess.run(['systemctl','--user','restart',*units],check=True,timeout=20)
        raise
    finally:
        a.output.write_text(json.dumps(dict(restarted=restarted,windows=rows,unsafe=unsafe),indent=2))
        print(json.dumps(dict(windows=rows,unsafe=unsafe),indent=2))
        n.destroy_node();rclpy.shutdown()

if __name__=='__main__':main()

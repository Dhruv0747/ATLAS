"""On-demand read-only location check attached to the EXISTING monitor node.

No velocity, initial-pose, TF or navigation publishers. Shares the monitor's
search mutex so an operator check cannot overlap its passive global search.
"""
import hashlib
import json
import math
from pathlib import Path
import threading
import time
import numpy as np
import atlas_localization_verify_core as core
from atlas_location_check_job import LocationCheckJob

STATE_FILE = Path.home()/'.local/state/project_atlas/manual_location_check.json'


def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))


def stamp(message):
    return message.header.stamp.sec+message.header.stamp.nanosec*1e-9


def checked_age(receipt_age, source_age, label='sensor'):
    if not all(math.isfinite(v) and v >= 0 for v in (receipt_age,source_age)):
        raise ValueError('%s future/invalid timestamp (receipt=%s s, source=%s s)'%(label,receipt_age,source_age))
    return max(receipt_age,source_age)


def command_zero(cmd):
    return all(v == 0 for vector in (cmd.linear,cmd.angular)
               for v in (vector.x,vector.y,vector.z))


def map_identity(path):
    path=Path(path)
    text=path.read_bytes()
    meta={k.strip():v.strip() for line in text.decode().splitlines()
          if ':' in line and not line.lstrip().startswith('#') for k,v in [line.split(':',1)]}
    image=path.with_name(meta['image'])
    return hashlib.sha256(text+b'\0'+image.read_bytes()).hexdigest()


def loaded_map_matches(m, msg):
    info=msg.info
    expected=np.where(m['occupied'],100,np.where(m['free'],0,-1)).astype(np.int8)
    return (msg.header.frame_id=='map' and info.width==m['w'] and info.height==m['h']
        and abs(info.resolution-m['res'])<1e-7
        and abs(info.origin.position.x-m['origin'][0])<1e-6
        and abs(info.origin.position.y-m['origin'][1])<1e-6
        and abs(yaw(info.origin.orientation))<1e-6
        and np.array_equal(np.asarray(msg.data,dtype=np.int8),expected.ravel()))


def scan_coverage(scan, policy):
    """Conservative diagnostic input gate; NOT free-space certification.

Existing minimum endpoint count plus observations in every quadrant prevent a
one-sided scan being called globally unique. This does not cure map distortion.
"""
    if (scan.header.frame_id!='laser_frame' or not 120<=len(scan.ranges)<=1440
        or not all(math.isfinite(v) for v in (scan.angle_min,scan.angle_increment,scan.range_min,scan.range_max))
        or scan.angle_increment<=0 or not 0<=scan.range_min<scan.range_max):
        return False,dict(reason='invalid scan geometry/frame')
    counts=[0]*4
    for i,r in enumerate(scan.ranges):
        if math.isfinite(r) and max(scan.range_min,policy.min_range_m)<=r<=min(scan.range_max,policy.max_range_m):
            a=(scan.angle_min+i*scan.angle_increment)%(2*math.pi)
            counts[min(3,int(a/(math.pi/2)))]+=1
    return sum(counts)>=policy.min_endpoints and min(counts)>=5,dict(valid=sum(counts),quadrants=counts)


def compare(m, scan, laser, amcl, policy, checkpoint):
    ranges=[r if math.isfinite(r) and scan.range_min<=r<=scan.range_max else math.nan for r in scan.ranges]
    allp,held=core.endpoints(scan.angle_min,scan.angle_increment,ranges,laser,policy)
    hypotheses=core.global_search(m,allp,held,policy,checkpoint=checkpoint)
    verdict=core.decide(hypotheses,len(allp),None,policy)
    fit=core.fit(m,held,*amcl,policy.tolerance_m)
    tracking=core.assess_tracking(amcl,fit,verdict,policy)
    state={'DEGRADED':'UNCERTAIN','LOST':'MISMATCH' if verdict.pose else 'LOST'}.get(tracking['state'],tracking['state'])
    if len(hypotheses)<2:
        state='UNCERTAIN'
        tracking['reason']='insufficient distinct candidates to establish ambiguity margin'
    best=verdict.as_dict()
    separation=None
    if len(hypotheses)>=2:
        a,b=hypotheses[:2]
        separation=dict(xy_m=math.hypot(a['x']-b['x'],a['y']-b['y']),heading_deg=core.angle_deg(a['yaw'],b['yaw']))
    return dict(state=state,reason=tracking['reason'],amcl_pose=dict(x=amcl[0],y=amcl[1],yaw_deg=math.degrees(amcl[2])),
                lidar_pose=best['pose'],candidates=best['hypotheses'],best_fit=best['best_fit'],margin=best['margin'],
                candidate_separation=separation,xy_disagreement_m=tracking['distance_m'],heading_disagreement_deg=tracking['heading_deg'],
                amcl_fit=fit,score_definition='Fraction of held-out endpoints within 0.15 m of accepted-map occupied cells; not absolute accuracy',
                map_warning='A distorted or ambiguous map can still mislead scan matching; this check never authorizes driving.')


class ManualLocationCheck:
    def __init__(self,node,map_path):
        from geometry_msgs.msg import Twist
        from nav_msgs.msg import OccupancyGrid,Odometry
        from sensor_msgs.msg import Imu
        from std_msgs.msg import String
        from std_srvs.srv import Trigger
        from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy,qos_profile_sensor_data
        self.node=node;self.path=Path(map_path);self.jobs=LocationCheckJob()
        self.lock=threading.RLock();self.values={};self.motion_epoch=0;self.last_motion=time.monotonic()
        self.map_id=map_identity(self.path);self.loaded_id=None;self.map_epoch=0
        self.last_status=None;self.last_request=0.;self.current_error=None
        if node.map['w']*node.map['h']>1_000_000:
            raise ValueError('accepted map exceeds bounded manual-check workload')
        node.create_subscription(OccupancyGrid,'/map',self.on_map,QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE))
        for cls,topic,key in ((Odometry,'/odom','odom'),(Imu,'/imu/data','imu'),(String,'/atlas/control_policy','policy'),(Twist,'/cmd_vel','cmd')):
            node.create_subscription(cls,topic,lambda m,k=key:self.receive(k,m),qos_profile_sensor_data if key=='imu' else 10)
        self.services=[node.create_service(Trigger,'/atlas/location_check/start',self.start),
                       node.create_service(Trigger,'/atlas/location_check/cancel',self.cancel)]
        node.create_timer(.25,self.tick)
        self.write_status()

    def on_map(self,msg):
        with self.lock:
            current=self.map_id if loaded_map_matches(self.node.map,msg) else None
            if current!=self.loaded_id:self.map_epoch+=1
            self.loaded_id=current

    def receive(self,key,msg):
        with self.lock:
            self.values[key]=(time.monotonic(),msg)
            moving=False
            if key=='odom':
                t=msg.twist.twist
                moving=not all(math.isfinite(v) for v in (t.linear.x,t.linear.y,t.angular.z)) or abs(t.linear.x)>.01 or abs(t.linear.y)>.01 or abs(t.angular.z)>.02
            elif key=='imu':moving=not math.isfinite(msg.angular_velocity.z) or abs(msg.angular_velocity.z)>.02
            elif key=='cmd':moving=not command_zero(msg)
            if moving:
                self.motion_epoch+=1;self.last_motion=time.monotonic()

    def evidence(self,with_tf=False):
        from rclpy.time import Time
        n=self.node
        with self.lock, n.data_lock:
            # Read clocks AFTER acquiring both snapshot locks. A callback may
            # have run while we waited; a pre-lock clock makes its receipt
            # falsely appear to be in the future during an active search.
            now=time.monotonic();ros_now=n.get_clock().now().nanoseconds*1e-9
            if not n.scans or n.amcl is None:raise ValueError('SCAN UNAVAILABLE or AMCL reference unavailable')
            received,scan=n.scans[-1]
            def get(key):
                at,msg=self.values[key]
                if now-at>1.:raise ValueError(key+' receipt stale')
                return at,msg
            oat,odom=get('odom');iat,imu=get('imu');_,policy=get('policy');_,cmd=get('cmd')
            policy=json.loads(policy.data)
            coverage,detail=scan_coverage(scan,n.logic.policy)
            e=dict(scan_age_s=ros_now-stamp(scan),scan_receipt_age_s=now-received,
                   odom_age_s=checked_age(now-oat,ros_now-stamp(odom),'odom'),imu_age_s=checked_age(now-iat,ros_now-stamp(imu),'imu'),
                   amcl_age_s=checked_age(now-(n.amcl_at or 0),ros_now-(n.amcl_stamp or 0),'amcl'),amcl_pose=list(n.amcl),
                   amcl_stamp=n.amcl_stamp,amcl_covariance=n.amcl_covariance,
                   map_id=self.map_id,loaded_map_id=self.loaded_id,stationary_epoch=self.motion_epoch,
                   localization_epoch=self.map_epoch,scan_stamp=stamp(scan),scan_frame=scan.header.frame_id,
                   stationary=now-self.last_motion>=2.,stop_latched=policy.get('stop_latched') is True,
                   commands_zero=command_zero(cmd),tf_at_scan=False,tf_chain_consistent=False,
                   coverage_qualified=coverage,coverage=detail)
        # Lookups are nonblocking at the actual scan stamp, never latest TF.
        when=Time.from_msg(scan.header.stamp)
        laser=n.tf.lookup_transform('base_link',scan.header.frame_id,when).transform
        mo=n.tf.lookup_transform('map','odom',when).transform
        ob=n.tf.lookup_transform('odom','base_link',when).transform
        mb=n.tf.lookup_transform('map','base_link',when).transform
        a=yaw(mo.rotation);b=yaw(ob.rotation)
        x=mo.translation.x+math.cos(a)*ob.translation.x-math.sin(a)*ob.translation.y
        y=mo.translation.y+math.sin(a)*ob.translation.x+math.cos(a)*ob.translation.y
        values=(x,y,a,b,laser.translation.x,laser.translation.y,yaw(laser.rotation))
        e['tf_at_scan']=all(math.isfinite(v) for v in values)
        e['tf_chain_consistent']=math.hypot(x-mb.translation.x,y-mb.translation.y)<1e-4 and core.angle_deg(a+b,yaw(mb.rotation))<.01
        e['laser_in_base']=[laser.translation.x,laser.translation.y,yaw(laser.rotation)]
        if with_tf:
            if map_identity(self.path)!=self.map_id:raise ValueError('accepted map file changed; reload/validation required')
        return e,scan

    def start(self,request,response):
        try:
            if time.monotonic()-self.last_request<2.:raise ValueError('request rate limited')
            self.last_request=time.monotonic()
            if not self.node.search_lock.acquire(False):raise ValueError('existing localization search busy; retry shortly')
            try:
                e,scan=self.evidence(True)
                token=self.jobs.start(e)
                threading.Thread(target=self.run,args=(token,e,scan),daemon=True).start()
            except Exception:
                self.node.search_lock.release();raise
            response.success=True;response.message=json.dumps(self.jobs.snapshot())
        except Exception as exc:
            response.success=False;response.message=json.dumps(dict(state='UNAVAILABLE',reason=str(exc),navigation_authorized=False,correction_enabled=False))
        self.write_status()
        return response

    def run(self,token,e,scan):
        try:
            last_evidence=[0.,e]
            def check():
                if time.monotonic()-last_evidence[0]>=.1:
                    last_evidence[:]=[time.monotonic(),self.evidence()[0]]
                self.jobs.checkpoint(token,last_evidence[1])
            result=compare(self.node.map,scan,e['laser_in_base'],e['amcl_pose'],self.node.logic.policy,check)
            end,_=self.evidence(True)
            self.jobs.finish(token,result,end)
        except Exception as exc:
            self.jobs.finish(token,error=str(exc))
        finally:
            self.node.search_lock.release();self.write_status()

    def cancel(self,request,response):
        try:
            snapshot=self.jobs.snapshot()
            self.jobs.cancel(snapshot['request_id'])
            response.success=True;response.message=json.dumps(self.jobs.snapshot())
        except Exception as exc:
            response.success=False;response.message=json.dumps(dict(state='UNCERTAIN',reason=str(exc)))
        self.write_status();return response

    def tick(self):
        self.write_status()

    def write_status(self):
        # One writer at a time: timer and completed worker share this lock.
        with self.lock:
            data=self.jobs.snapshot()
            data['written_unix']=time.time()
            data['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            STATE_FILE.parent.mkdir(parents=True,exist_ok=True)
            tmp=STATE_FILE.with_suffix('.tmp');tmp.write_text(json.dumps(data,allow_nan=False))
            tmp.chmod(0o600);tmp.replace(STATE_FILE)

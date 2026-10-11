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
SCAN_WINDOW_HINT_S = 2.5   # the monitor keeps scans for PARK_SETTLE_S + 0.5 s (SCAN_WINDOW_S)


class Blocked(ValueError):
    """A precise reason the independent check cannot start, with the stage table."""
    def __init__(self, code, reason, stages=None):
        super().__init__(reason)
        self.code, self.reason, self.stages = code, reason, stages or {}


AMCL_MAX_AGE_S = 2.5   # same limit evidence_error has always applied to the AMCL reference


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
    """Independent global search on the accepted map; AMCL is compared only when it is usable.

    ``amcl`` is None when AMCL has no pose (not initialised, stale, or its TF chain is missing).
    The search itself never uses AMCL. Without AMCL the best outcome is LIDAR_ONLY_MATCH,
    which is NOT a verification of AMCL tracking and never authorizes driving.
    """
    ranges=[r if math.isfinite(r) and scan.range_min<=r<=scan.range_max else math.nan for r in scan.ranges]
    allp,held=core.endpoints(scan.angle_min,scan.angle_increment,ranges,laser,policy)
    hypotheses=core.global_search(m,allp,held,policy,checkpoint=checkpoint)
    verdict=core.decide(hypotheses,len(allp),None,policy)
    best=verdict.as_dict()
    separation=None
    if len(hypotheses)>=2:
        a,b=hypotheses[:2]
        separation=dict(xy_m=math.hypot(a['x']-b['x'],a['y']-b['y']),heading_deg=core.angle_deg(a['yaw'],b['yaw']))
    ambiguous=verdict.state!='VERIFIED' and verdict.reason.startswith('ambiguous')
    if amcl is None:
        if verdict.state=='VERIFIED':
            state='LIDAR_ONLY_MATCH'
            reason=('Unique LiDAR match on the accepted map (fit %.3f, margin %.3f over the next place). '
                    'AMCL has no usable pose, so AMCL tracking is NOT verified.'%(verdict.best_fit,verdict.margin or 0.))
        elif len(allp)<policy.min_endpoints:
            state,reason='INSUFFICIENT_LIDAR_COVERAGE',verdict.reason
        elif ambiguous:
            state,reason='AMBIGUOUS',verdict.reason
        else:
            state,reason='UNCERTAIN',verdict.reason
        tracking=dict(distance_m=None,heading_deg=None)
        fit=None
    else:
        fit=core.fit(m,held,*amcl,policy.tolerance_m)
        tracking=core.assess_tracking(amcl,fit,verdict,policy)
        state={'DEGRADED':'UNCERTAIN','LOST':'MISMATCH' if verdict.pose else 'LOST'}.get(tracking['state'],tracking['state'])
        reason=tracking['reason']
        if state!='VERIFIED' and ambiguous:
            state,reason='AMBIGUOUS',verdict.reason
    if len(hypotheses)<2 and state!='INSUFFICIENT_LIDAR_COVERAGE':   # unchanged rule: no margin, no claim
        state='UNCERTAIN'
        reason='insufficient distinct candidates to establish ambiguity margin'
    return dict(state=state,reason=reason,
                amcl_pose=None if amcl is None else dict(x=amcl[0],y=amcl[1],yaw_deg=math.degrees(amcl[2])),
                lidar_pose=best['pose'],lidar_verdict=dict(state=verdict.state,reason=verdict.reason),
                candidates=best['hypotheses'],best_fit=best['best_fit'],margin=best['margin'],
                endpoints_used=len(allp),candidate_separation=separation,
                xy_disagreement_m=tracking['distance_m'],heading_disagreement_deg=tracking['heading_deg'],
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
        self.last_status=None;self.last_request=0.;self.current_error=None;self.last_block=None
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
        """Fresh, validated snapshot for one check, or Blocked(code, reason, stages).

        Stages that the independent LiDAR search needs (scan, scan-time laser TF, accepted map,
        stationary/stop evidence, coverage) block with a precise code. AMCL is reported
        separately and never blocks: without it the search still runs and no AMCL comparison
        is made. Ages are seconds; every stage names its topic or frame.
        """
        from rclpy.time import Time
        n=self.node
        stages={}
        def stage(name,status,source,**detail):
            stages[name]=dict(status=status,source=source,**detail)
        def block(code,reason):
            raise Blocked(code,reason,stages)
        with self.lock, n.data_lock:
            # Read clocks AFTER acquiring both snapshot locks. A callback may
            # have run while we waited; a pre-lock clock makes its receipt
            # falsely appear to be in the future during an active search.
            now=time.monotonic();ros_now=n.get_clock().now().nanoseconds*1e-9
            if not n.scans:
                stage('scan','missing','/scan')
                block('LIDAR_SCAN_UNAVAILABLE','No LiDAR scan received by the location monitor in the last %.1f s'%SCAN_WINDOW_HINT_S)
            received,scan=n.scans[-1]
            scan_age=ros_now-stamp(scan);receipt_age=now-received
            ok_scan=math.isfinite(scan_age) and 0<=scan_age<=1. and 0<=receipt_age<=1.
            stage('scan','ready' if ok_scan else 'stale','/scan',frame=scan.header.frame_id,age_s=round(scan_age,3),receipt_age_s=round(receipt_age,3))
            if not ok_scan:
                block('LIDAR_SCAN_STALE','LiDAR scan age %.2f s (receipt %.2f s) exceeds 1.0 s'%(scan_age,receipt_age))
            ok_map=bool(self.map_id) and self.loaded_id==self.map_id
            stage('map','ready' if ok_map else 'missing','/map',map_id=self.map_id,loaded_matches=ok_map)
            if not ok_map:
                block('ACCEPTED_MAP_NOT_READY','The /map being served does not match the accepted map file (map server not active, or a different map)')
            def get(key,topic,code):
                if key not in self.values:
                    stage(key,'missing',topic);block(code,topic+' not received since the monitor started')
                at,msg=self.values[key]
                if now-at>1.:
                    stage(key,'stale',topic,receipt_age_s=round(now-at,3));block(code,topic+' receipt stale (%.1f s)'%(now-at))
                stage(key,'ready',topic,receipt_age_s=round(now-at,3))
                return at,msg
            oat,odom=get('odom','/odom','ODOMETRY_UNAVAILABLE');iat,imu=get('imu','/imu/data','IMU_UNAVAILABLE')
            _,policy=get('policy','/atlas/control_policy','STOP_STATE_UNKNOWN');_,cmd=get('cmd','/cmd_vel','MOTOR_COMMAND_STATE_UNKNOWN')
            try:
                policy=json.loads(policy.data)
            except (TypeError,ValueError):
                stage('policy','invalid','/atlas/control_policy');block('STOP_STATE_UNKNOWN','control policy is not valid JSON')
            coverage,detail=scan_coverage(scan,n.logic.policy)
            stage('coverage','ready' if coverage else 'invalid','/scan',**detail)
            amcl=n.amcl;amcl_at=n.amcl_at;amcl_stamp=n.amcl_stamp
            if amcl is None:
                amcl_status,amcl_reason='NOT_INITIALIZED','AMCL has published no pose since the monitor started (no initial pose set)'
                amcl_age=None
            else:
                try:
                    amcl_age=checked_age(now-(amcl_at or 0),ros_now-(amcl_stamp or 0),'amcl')
                except ValueError as exc:
                    amcl_age=None;amcl_status,amcl_reason='INVALID',str(exc)
                else:
                    amcl_status,amcl_reason=('OK','') if amcl_age<=AMCL_MAX_AGE_S else ('STALE','AMCL pose age %.1f s exceeds %.1f s'%(amcl_age,AMCL_MAX_AGE_S))
            ages={}
            for key,at,msg in (('odom',oat,odom),('imu',iat,imu)):
                try:
                    ages[key]=checked_age(now-at,ros_now-stamp(msg),key)
                except ValueError as exc:
                    stages[key]['status']='invalid';stages[key]['error']=str(exc)
                    block('SENSOR_TIMESTAMP_INVALID',str(exc))
            e=dict(scan_age_s=scan_age,scan_receipt_age_s=receipt_age,
                   odom_age_s=ages['odom'],imu_age_s=ages['imu'],
                   amcl_status=amcl_status,amcl_reason=amcl_reason,
                   amcl_age_s=amcl_age,amcl_pose=list(amcl) if amcl_status=='OK' else None,
                   amcl_stamp=amcl_stamp,amcl_covariance=n.amcl_covariance if amcl_status=='OK' else None,
                   map_id=self.map_id,loaded_map_id=self.loaded_id,stationary_epoch=self.motion_epoch,
                   localization_epoch=self.map_epoch,scan_stamp=stamp(scan),scan_frame=scan.header.frame_id,
                   stationary=now-self.last_motion>=2.,stop_latched=policy.get('stop_latched') is True,
                   commands_zero=command_zero(cmd),tf_at_scan=False,tf_chain_consistent=False,
                   coverage_qualified=coverage,coverage=detail,stages=stages)
        if not e['stop_latched']:
            stage('stop','invalid','/atlas/control_policy',stop_latched=False)
            block('STOP_NOT_LATCHED','The drive stop is not latched; latch it (remote B or E-STOP) and keep ATLAS parked')
        stage('stop','ready','/atlas/control_policy',stop_latched=True)
        if not e['commands_zero']:
            block('MOTOR_COMMAND_ACTIVE','A non-zero /cmd_vel was received; wait until all commands are zero')
        if not e['stationary']:
            stage('motion','invalid','/odom,/imu/data,/cmd_vel',seconds_since_motion=round(time.monotonic()-self.last_motion,2))
            block('ROVER_MOVING','Motion seen in the last 2 s; keep ATLAS parked')
        stage('motion','ready','/odom,/imu/data,/cmd_vel')
        if not coverage:
            block('INSUFFICIENT_LIDAR_COVERAGE','Too few valid LiDAR returns or a quadrant without returns (%s)'%json.dumps(detail))
        # Lookups are nonblocking at the actual scan stamp, never latest TF.
        when=Time.from_msg(scan.header.stamp)
        try:
            laser=n.tf.lookup_transform('base_link',scan.header.frame_id,when).transform
        except Exception as exc:
            stage('scan_tf','missing','base_link<-'+scan.header.frame_id,error=type(exc).__name__)
            block('SCAN_TIME_TF_UNAVAILABLE','No base_link<-%s transform at the scan time (%s)'%(scan.header.frame_id,type(exc).__name__))
        lv=(laser.translation.x,laser.translation.y,yaw(laser.rotation))
        e['tf_at_scan']=all(math.isfinite(v) for v in lv)
        stage('scan_tf','ready' if e['tf_at_scan'] else 'invalid','base_link<-'+scan.header.frame_id)
        if not e['tf_at_scan']:
            block('SCAN_TIME_TF_UNAVAILABLE','base_link<-laser transform is not finite')
        e['laser_in_base']=list(lv)
        if e['amcl_status']=='OK':
            try:
                mo=n.tf.lookup_transform('map','odom',when).transform
                ob=n.tf.lookup_transform('odom','base_link',when).transform
                mb=n.tf.lookup_transform('map','base_link',when).transform
                a=yaw(mo.rotation);b=yaw(ob.rotation)
                x=mo.translation.x+math.cos(a)*ob.translation.x-math.sin(a)*ob.translation.y
                y=mo.translation.y+math.sin(a)*ob.translation.x+math.cos(a)*ob.translation.y
                chain=all(math.isfinite(v) for v in (x,y,a,b))
                e['tf_chain_consistent']=chain and math.hypot(x-mb.translation.x,y-mb.translation.y)<1e-4 and core.angle_deg(a+b,yaw(mb.rotation))<.01
                if not e['tf_chain_consistent']:
                    raise ValueError('map->odom->base_link chain inconsistent at scan time')
                stage('amcl','ready','/amcl_pose + map->odom TF',age_s=round(e['amcl_age_s'],3))
            except Exception as exc:
                e.update(amcl_status='TF_UNAVAILABLE',amcl_reason='AMCL pose present but its map->odom TF at the scan time is unusable (%s)'%exc,
                         amcl_pose=None,amcl_covariance=None,tf_chain_consistent=False)
        if e['amcl_status']!='OK':
            stage('amcl','not_available','/amcl_pose + map->odom TF',amcl_status=e['amcl_status'],reason=e['amcl_reason'])
        if with_tf:
            if map_identity(self.path)!=self.map_id:
                stage('map','invalid','accepted map file',map_id=self.map_id)
                block('ACCEPTED_MAP_CHANGED','accepted map file changed; reload/validation required')
        return e,scan

    def start(self,request,response):
        try:
            if time.monotonic()-self.last_request<2.:raise Blocked('RATE_LIMITED','request rate limited; retry in 2 s')
            self.last_request=time.monotonic()
            if not self.node.search_lock.acquire(False):
                raise Blocked('SEARCH_BUSY','the location monitor is running its own search; retry shortly')
            try:
                e,scan=self.evidence(True)
                token=self.jobs.start(e)
                self.last_block=None
                threading.Thread(target=self.run,args=(token,e,scan),daemon=True).start()
            except Exception:
                self.node.search_lock.release();raise
            response.success=True;response.message=json.dumps(self.jobs.snapshot())
        except Blocked as exc:
            self.last_block=dict(code=exc.code,reason=exc.reason,stages=exc.stages,at_unix=time.time())
            response.success=False;response.message=json.dumps(dict(state='UNAVAILABLE',code=exc.code,reason=exc.reason,
                stages=exc.stages,navigation_authorized=False,correction_enabled=False))
        except Exception as exc:
            self.last_block=dict(code='CHECK_REJECTED',reason=str(exc),stages={},at_unix=time.time())
            response.success=False;response.message=json.dumps(dict(state='UNAVAILABLE',code='CHECK_REJECTED',reason=str(exc),
                navigation_authorized=False,correction_enabled=False))
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
        except Blocked as exc:
            # Evidence went bad mid-check (moved, latch released, scan stale...): the result is void.
            self.jobs.abort(token,'STALE','%s: %s'%(exc.code,exc.reason))
            self.jobs.finish(token,error=exc.reason)
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
            if getattr(self,'last_block',None):
                data['last_block']=dict(self.last_block,age_s=max(0.,time.time()-self.last_block['at_unix']))
            data['written_unix']=time.time()
            data['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            STATE_FILE.parent.mkdir(parents=True,exist_ok=True)
            tmp=STATE_FILE.with_suffix('.tmp');tmp.write_text(json.dumps(data,allow_nan=False))
            tmp.chmod(0o600);tmp.replace(STATE_FILE)

"""Read-only native replay measurements. No corrected position ground truth."""
import argparse
import glob
import json
import math
import sqlite3
import sys
from pathlib import Path
import numpy as np
from rosbags.typesys import Stores,get_typestore,get_types_from_msg
from stage19_contract import relative_pose_xy
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from atlas_amcl_motion_replay_summary import Fitter,nearest_scan

TS=get_typestore(Stores.ROS2_HUMBLE)
TS.register({**get_types_from_msg('geometry_msgs/Pose pose\nfloat64 weight','nav2_msgs/msg/Particle'),
    **get_types_from_msg('std_msgs/Header header\nnav2_msgs/Particle[] particles','nav2_msgs/msg/ParticleCloud')})


def load(bag):
    result={}
    for path in sorted(Path(bag).glob('*.db3')):
        with sqlite3.connect('file:'+path.as_posix()+'?mode=ro',uri=True) as db:
            for i,name,typ in db.execute('select id,name,type from topics'):
                if name not in ('/odom','/amcl_pose','/particle_cloud','/tf','/map','/scan','/tf_static'):continue
                result.setdefault(name,[]).extend((t,TS.deserialize_cdr(b,typ)) for t,b in
                    db.execute('select timestamp,data from messages where topic_id=? order by timestamp',(i,)))
    return result


def yaw(q):return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
def stamp(m):return m.header.stamp.sec+m.header.stamp.nanosec*1e-9
def angle(a):return (a+math.pi)%(2*math.pi)-math.pi


def endpoint_fit(data):
    if not all(data.get(n) for n in ('/map','/scan','/tf_static','/amcl_pose')):
        return {'status':'UNKNOWN: required evidence missing'}
    grid=data['/map'][0][1];transforms={}
    for _,m in data['/tf_static']:
        for tr in m.transforms:transforms[tr.child_frame_id.strip('/')]=tr
    laser=transforms.get(data['/scan'][0][1].header.frame_id.strip('/'))
    base=transforms.get('base_footprint')
    if laser is None or laser.header.frame_id.strip('/')!='base_footprint' or base is None:
        return {'status':'UNKNOWN: unsupported static chain'}
    if (base.header.frame_id.strip('/')!='base_link' or
        abs(base.transform.translation.x)+abs(base.transform.translation.y)+abs(yaw(base.transform.rotation))>1e-8):
        return {'status':'UNKNOWN: base footprint transform not identity'}
    if abs(yaw(grid.info.origin.orientation))>1e-8:return {'status':'UNKNOWN: rotated grid'}
    bundle={'map':{'cells':grid.data.tolist(),'height':grid.info.height,'width':grid.info.width,
        'resolution':grid.info.resolution,'origin':[grid.info.origin.position.x,grid.info.origin.position.y]},
        'laser':[laser.transform.translation.x,laser.transform.translation.y],
        'scans':[{'ranges':[float(v) if math.isfinite(v) else None for v in m.ranges],
            'angle_min':m.angle_min+yaw(laser.transform.rotation),'angle_increment':m.angle_increment,
            'range_min':m.range_min,'range_max':m.range_max} for _,m in data['/scan']]}
    fitter=Fitter(bundle);times=np.array([stamp(m) for _,m in data['/scan']]);fits=[];unpaired=0
    for _,m in data['/amcl_pose']:
        k=nearest_scan(times,stamp(m))
        if abs(times[k]-stamp(m))>.25:unpaired+=1;continue
        p=m.pose.pose;v=fitter.fit(k,p.position.x,p.position.y,yaw(p.orientation))
        if v is not None:fits.append(v)
    return {'status':'ENDPOINT_PROXIMITY_PROXY_NOT_AMCL_LIKELIHOOD','fit_samples':len(fits),
        'unpaired_pose_headers':unpaired,'median_fit':float(np.median(fits)) if fits else None,
        'final_fit':fits[-1] if fits else None,'tolerance_m':.15}


def summary(data,stop_s):
    poses=[(stamp(m),m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation),
        math.sqrt(max(0,m.pose.covariance[0]+m.pose.covariance[7])),
        math.degrees(math.sqrt(max(0,m.pose.covariance[35])))) for _,m in data.get('/amcl_pose',[])]
    jumps=[]
    for a,b in zip(poses,poses[1:]):
        step=math.hypot(b[1]-a[1],b[2]-a[2]);dt=b[0]-a[0]
        if 0<dt<=2 and step>.5:jumps.append({'stamp_s':b[0],'step_m':step,'heading_deg':math.degrees(angle(b[3]-a[3])),
            'after_stop_s':b[0]-stop_s,'xy_std_m':b[4]})
    post=[p for p in poses if p[0]>=stop_s]
    clouds=[]
    for received,m in data.get('/particle_cloud',[]):
        xy=np.array([(p.pose.position.x,p.pose.position.y) for p in m.particles])
        if len(xy):clouds.append((received*1e-9,float(np.sqrt(np.var(xy,axis=0).sum()))))
    odom=[(stamp(m),m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation)) for _,m in data.get('/odom',[])]
    stopped=[p for p in odom if p[0]>=stop_s]
    tf=[tr for _,m in data.get('/tf',[]) for tr in m.transforms if tr.header.frame_id.strip('/')=='odom' and tr.child_frame_id.strip('/')=='base_link']
    return {'amcl_poses':len(poses),'amcl_post_stop_poses':len(post),'jumps':jumps,
        'post_stop_jumps':sum(p['after_stop_s']>=0 for p in jumps),
        'max_jump_m':max((j['step_m'] for j in jumps),default=0),
        'post_stop_xy_span_m':max((math.hypot(p[1]-post[0][1],p[2]-post[0][2]) for p in post),default=None),
        'median_xy_std_m':float(np.median([p[4] for p in poses])) if poses else None,
        'median_yaw_std_deg':float(np.median([p[5] for p in poses])) if poses else None,
        'particle_clouds':len(clouds),'particle_spread_median_m':float(np.median([c[1] for c in clouds])) if clouds else None,
        'particle_spread_max_m':max((c[1] for c in clouds),default=None),
        'ekf_samples':len(odom),'ekf_post_stop_xy_span_m':max((math.hypot(p[1]-stopped[0][1],p[2]-stopped[0][2]) for p in stopped),default=None),
        'odom_tf_count':len(tf),'odom_tf_header_backwards':sum(stamp(b)<stamp(a) for a,b in zip(tf,tf[1:])),
        'scan_endpoint_fit':endpoint_fit(data),
        'truth':'UNKNOWN; no surveyed physical trajectory or restored particle checkpoint'}


def trajectory_fidelity(recorded,replay):
    """One initial rigid-frame alignment; no fitted scale/rotation or ground truth."""
    def series(data):
        return np.array([(stamp(m),m.pose.pose.position.x,m.pose.pose.position.y,yaw(m.pose.pose.orientation))
                         for _,m in data.get('/odom',[])])
    a,b=series(recorded),series(replay)
    if len(a)<2 or len(b)<2:return {'status':'UNKNOWN'}
    a=a[(a[:,0]>=b[0,0])&(a[:,0]<=b[-1,0])]
    if len(a)<2:return {'status':'UNKNOWN'}
    t=a[:,0];bn=np.c_[np.interp(t,b[:,0],b[:,1]),np.interp(t,b[:,0],b[:,2]),
        np.interp(t,b[:,0],np.unwrap(b[:,3]))]
    orig=np.array([relative_pose_xy(p[1:3],a[0,1:4]) for p in a])
    native=np.array([relative_pose_xy(p[:2],bn[0]) for p in bn])
    err=np.linalg.norm(orig-native,axis=1)
    head=(bn[:,2]-bn[0,2])-(np.unwrap(a[:,3])-a[0,3]);head=(head+np.pi)%(2*np.pi)-np.pi
    return {'status':'REPLAY_DIFFERENCE_NOT_PHYSICAL_ERROR','overlap_samples':len(a),
        'max_gauge_aligned_xy_difference_m':float(max(err)),'final_xy_difference_m':float(err[-1]),
        'max_relative_heading_difference_deg':float(np.degrees(max(abs(head)))),
        'final_relative_heading_difference_deg':float(np.degrees(head[-1])),
        'initial_recorded_pose':a[0,1:].tolist(),'initial_replay_pose':bn[0].tolist()}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bags',nargs='+');p.add_argument('--stop-ns',type=int,required=True);a=p.parse_args()
    datasets=[load(b) for b in a.bags]
    result={str(Path(b)):summary(data,a.stop_ns*1e-9) for b,data in zip(a.bags,datasets)}
    if len(datasets)==2:result['native_vs_recorded_ekf_fidelity']=trajectory_fidelity(*datasets)
    print(json.dumps(result,indent=2))

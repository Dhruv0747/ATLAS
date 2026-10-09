#!/usr/bin/env python3
"""Compare locked pose hypotheses against identical saved scans and history.

Read-only offline analysis; no ROS context, service or actuator. Hypotheses
are from prior reports, not ground truth. No parameter/configuration edits.
"""
import argparse
import bisect
import json
import math
from pathlib import Path
import sqlite3
import numpy as np


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def inverse(p):
    x, y, a = p
    c, s = math.cos(a), math.sin(a)
    return np.array([-c*x-s*y, s*x-c*y, -a])


def interpolate(series, t, max_gap=.5):
    """Interpolate planar poses at header time; never extrapolate."""
    times = [row[0] for row in series]
    i = bisect.bisect_left(times, t)
    if i < len(series) and times[i] == t:
        return series[i][1]
    if i == 0 or i == len(series) or times[i]-times[i-1] > max_gap:
        return None
    a,b = series[i-1],series[i]
    fraction = (t-a[0])/(b[0]-a[0])
    result = a[1]+fraction*(b[1]-a[1])
    result[2] = a[1][2]+fraction*wrap(b[1][2]-a[1][2])
    return result


def integrate_gyro(series, begin, end, max_gap=.5):
    """Trapezoidal integration with exact interpolated interval boundaries."""
    if end <= begin:
        raise ValueError('invalid integration interval')
    times = np.array([row[0] for row in series])
    values = np.array([row[1] for row in series])
    if len(times)<2 or not np.all(np.isfinite(times)) or not np.all(np.isfinite(values)):
        return None
    if np.any(np.diff(times)<=0) or begin<times[0] or end>times[-1]:
        return None
    lo=max(0,bisect.bisect_right(times,begin)-1)
    hi=min(len(times)-1,bisect.bisect_left(times,end))
    if np.max(np.diff(times[lo:hi+1]), initial=0)>max_gap:
        return None
    selected=(times>begin)&(times<end)
    t=np.concatenate(([begin],times[selected],[end]))
    z=np.concatenate(([np.interp(begin,times,values)],values[selected],
                      [np.interp(end,times,values)]))
    return float(np.sum(.5*(z[:-1]+z[1:])*np.diff(t)))


def summarize(scores):
    keys=('within_15cm_wall_fraction','median_wall_distance_m',
          'premature_mapped_obstacle_fraction','known_endpoint_fraction')
    return {key: {'min': float(min(s[key] for s in scores)),
                  'median': float(np.median([s[key] for s in scores])),
                  'max': float(max(s[key] for s in scores))} for key in keys} if scores else None


def points_for_parity(scan, parity):
    """Split original beam indices before filtering invalid ranges."""
    ranges=np.asarray(scan.ranges,dtype=float)
    indices=np.arange(len(ranges))
    valid=(indices%2==parity)&np.isfinite(ranges)&(ranges>=max(.3,scan.range_min))&(ranges<=min(8.,scan.range_max))
    angles=scan.angle_min+indices[valid]*scan.angle_increment
    return np.column_stack((ranges[valid]*np.cos(angles),ranges[valid]*np.sin(angles)))


def particle_support(points, weights, candidate):
    distances=np.linalg.norm(points[:,:2]-candidate[:2],axis=1)
    angles=np.abs(np.arctan2(np.sin(points[:,2]-candidate[2]),np.cos(points[:,2]-candidate[2])))
    near=distances<=.5
    joint=near&(angles<=math.radians(20))
    if not len(points) or np.any(weights<0) or not np.all(np.isfinite(weights)) or weights.sum()<=0:
        raise ValueError('invalid particle cloud')
    return {'nearest_xy_m':float(distances.min()),'count_within_0_5m':int(near.sum()),
            'nearest_xy_heading_error_deg':math.degrees(float(angles[np.argmin(distances)])),
            'count_within_0_5m_and_20deg':int(joint.sum()),
            'weight_within_0_5m_and_20deg':float(weights[joint].sum()/weights.sum())}


def refine_local(points, seed, laser, model):
    """Identical bounded endpoint-only fitting for every candidate region.

    This is retrospective candidate comparison, not a global localization
    implementation. Training uses one early stopped scan, evaluation later.
    """
    from scipy.optimize import least_squares
    from atlas_amcl_stationary_jump_audit import compose
    seed=np.asarray(seed,dtype=float)
    radius=np.array([.6,.6,math.radians(30)])
    lower,upper=seed-radius,seed+radius
    tree=model[3]
    def residual(p):
        q=compose(p,laser)
        c,s=math.cos(q[2]),math.sin(q[2])
        world=points @ np.array([[c,s],[-s,c]])+q[:2]
        return tree.query(world)[0]
    best=None
    for x in (-.3,0,.3):
        for y in (-.3,0,.3):
            for a in (-.2,0,.2):
                fit=least_squares(residual,seed+[x,y,a],bounds=(lower,upper),
                    loss='soft_l1',f_scale=.1,max_nfev=60,diff_step=1e-4)
                if best is None or fit.cost<best.cost:
                    best=fit
    return {'pose':best.x.tolist(),'training_robust_cost':float(best.cost),
            'optimizer_success':bool(best.success),
            'near_bound':bool(np.any(np.minimum(best.x-lower,upper-best.x)<.005)),
            'starts':27,'bounds_translation_m':.6,'bounds_yaw_deg':30}


def main():
    from atlas_amcl_stationary_jump_audit import (read_bag, map_model,
        scan_points, score_scan, compose, pose)
    from rclpy.serialization import deserialize_message as decode
    from rosidl_runtime_py.utilities import get_message
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('output')
    args=parser.parse_args()
    if Path(args.bag).name!='amcl_roundtrip_20261009_final':
        raise ValueError('locked hypotheses and offsets belong only to amcl_roundtrip_20261009_final')
    segments=list(Path(args.bag).glob('*.db3'))
    if len(segments)!=1:
        raise ValueError('requires one SQLite segment')
    db=sqlite3.connect('file:'+str(segments[0])+'?mode=ro',uri=True)
    start=db.execute('SELECT MIN(timestamp) FROM messages').fetchone()[0]/1e9
    poses,_,scans,_,_,grid,static=read_bag(args.bag,with_clouds=False)
    base=static.get(('base_link','base_footprint'))
    if base is None or np.linalg.norm(base)>1e-8:
        raise ValueError('explicit identity base transform required')
    laser=compose(base,static[('base_footprint','laser_frame')])
    model=map_model(grid)
    # Locked before looking at new comparisons; source provenance in report.
    hypotheses={
        'initial_room_anchor': [.2070126,-1.5453962,1.40799436],
        'prior_scan_room_candidate': [.184,-2.034,1.447],
        'late_hall_anchor': [6.4680112,-2.7635224,-1.66138551],
        'late_false_return_anchor': [3.84039193,-.48244301,2.72681390]}
    topics={n:(i,typ) for i,n,typ in db.execute('SELECT id,name,type FROM topics')}
    odometry,gyros={},{}
    for name in ('/odom','/yahboom/odom','/imu/data','/im10a/imu/bias_corrected_candidate'):
        ident,typ=topics[name]
        cls=get_message(typ)
        rows=[]
        for received,raw in db.execute('SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp',(ident,)):
            msg=decode(raw,cls)
            t=msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9
            value=pose(msg.pose.pose) if name.endswith('odom') else msg.angular_velocity.z
            rows.append((t,value))
        if any(b[0]<=a[0] for a,b in zip(rows,rows[1:])):
            raise ValueError('nonincreasing header timestamps: '+name)
        (odometry if name.endswith('odom') else gyros)[name]=rows
    result={'source_bag':Path(args.bag).name,'hypotheses':hypotheses,
        'navigation_authorized':False,'stationary_comparison':{},'history':{},
        'limitations':['Locked hypotheses are not surveyed ground truth or exhaustive global search',
            'Prior scan room and late false return anchors use this same recording; not independent test-set validation',
            'No scan deskew; dynamic objects and occlusion can affect ray checks',
            'Odometry histories have known heading disagreement; neither is ground truth',
            'Wrapped heading residuals do not establish translation accuracy']}
    training=next((s for s in scans if s[1]>=start+352),None)
    if training is None or training[1]>start+353:
        raise ValueError('early-return training scan missing')
    training_points=points_for_parity(training[2],0)
    refined={name:refine_local(training_points,p,laser,model) for name,p in hypotheses.items()}
    result['refinement']={'training_offset_s':training[1]-start,'hypotheses':refined,
        'evaluation':{},'limitation':'Seeds include retrospective same-bag findings; evaluation scans are later but this is not independent validation'}
    ident,typ=topics['/particle_cloud']
    record=db.execute('SELECT timestamp,data FROM messages WHERE topic_id=? AND timestamp<=? ORDER BY timestamp DESC LIMIT 1',
        (ident,int(training[1]*1e9))).fetchone()
    if record:
        cloud=decode(record[1],get_message(typ))
        pp=np.asarray([pose(p.pose) for p in cloud.particles])
        result['refinement']['particle_support_before_training']={
            'receipt_offset_s':record[0]/1e9-start,'particles':len(pp),
            'candidates':{name:particle_support(pp,np.array([p.weight for p in cloud.particles]),np.asarray(p['pose']))
                for name,p in refined.items()}}
    for label,a,b in [('initial_room',110,118),('hall',270,278),
                       ('early_return',360,368),('late_return',450,458)]:
        chosen=[]; unused=[]; last=-math.inf
        for header,received,msg in scans:
            if start+a<=received<=start+b and received-last>=.9:
                if msg.header.frame_id.strip('/')!='laser_frame':
                    raise ValueError('unexpected scan frame')
                if (msg.angle_min,msg.angle_increment,len(msg.ranges)) != (training[2].angle_min,training[2].angle_increment,len(training[2].ranges)):
                    raise ValueError('beam geometry changed; parity holdout invalid')
                points=points_for_parity(msg,0)
                if len(points)>=30:
                    chosen.append((received,points))
                    unused.append((received,points_for_parity(msg,1)))
                    last=received
        result['stationary_comparison'][label]={name:summarize([
            score_scan(points,p,laser,model) for _,points in chosen])
            for name,p in hypotheses.items()}
        result['stationary_comparison'][label]['scan_count']=len(chosen)
        if label in ('early_return','late_return'):
            result['refinement']['evaluation'][label]={name:summarize([
                score_scan(points,p['pose'],laser,model) for _,points in chosen])
                for name,p in refined.items()}
        if label=='late_return':
            result['refinement']['unused_beam_late_return']={name:summarize([
                score_scan(points,p['pose'],laser,model) for _,points in unused])
                for name,p in refined.items()}
    # Endpoints lie within the previously established stationary intervals.
    # No exact manual endpoint equality is assumed.
    for label,a,b,anchor in [('outbound',118,278,'initial_room_anchor'),
                             ('return',278,450,'late_hall_anchor')]:
        begin,end=start+a,start+b
        h={'offset_s':[a,b],'start_anchor':anchor,'odometry':{},'gyro':{}}
        for name,series in odometry.items():
            first,last=interpolate(series,begin),interpolate(series,end)
            if first is None or last is None:
                h['odometry'][name]={'missing_boundary':True};continue
            delta=compose(inverse(first),last)
            predicted=compose(hypotheses[anchor],delta)
            h['odometry'][name]={'relative_pose':delta.tolist(),
                'predicted_endpoint':predicted.tolist(),
                'residuals':{key:{'xy_m':float(np.linalg.norm(predicted[:2]-np.array(p[:2]))),
                    'heading_deg':math.degrees(abs(wrap(predicted[2]-p[2])))} for key,p in hypotheses.items()}}
        for name,series in gyros.items():
            rotation=integrate_gyro(series,begin,end)
            h['gyro'][name]={'rotation_deg':math.degrees(rotation) if rotation is not None else None,
                'heading_residual_deg':{key:math.degrees(abs(wrap(hypotheses[anchor][2]+rotation-p[2])))
                    for key,p in hypotheses.items()} if rotation is not None else None}
        result['history'][label]=h
    rotation=result['history']['return']['gyro']['/im10a/imu/bias_corrected_candidate']['rotation_deg']
    result['refinement']['return_corrected_gyro_heading_residual_deg']={
        name:math.degrees(abs(wrap(hypotheses['late_hall_anchor'][2]+
            math.radians(rotation)-p['pose'][2]))) for name,p in refined.items()} if rotation is not None else None
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({'output':args.output,'navigation_authorized':False}))


if __name__=='__main__':
    main()

#!/usr/bin/env python3
"""Read-only motion replay; no ROS processes, publications or control changes.

Reuses existing CDR gyro integration and scan ICP. LiDAR uses fixed neutral
seeds, never wheel/EKF initialization. Quality gates are offline screening
assumptions, NOT calibrated sensor confidence or deployment parameters.
"""
import argparse
import hashlib
import json
import math
import sqlite3
import sys
import time
from pathlib import Path
import numpy as np
from rosbags.typesys import Stores, get_typestore

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from atlas_odometry_icp_scale_check import icp, yaw_q, stamp, wrap
from moving_yaw_evidence import load_bag, integrate_gyro, summarize_window
from stage18_motion_model import consistency, geometry, integrate

TS=get_typestore(Stores.ROS2_HUMBLE)


def peak_rss_bytes():
    if sys.platform!='win32': return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[
            (n,ctypes.c_size_t) for n in ('peak_ws','ws','peak_pool_p','pool_p',
                'peak_pool_n','pool_n','pagefile','peak_pagefile')]
    kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=wintypes.HANDLE
    psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
    c=Counters();c.cb=ctypes.sizeof(c)
    return int(c.peak_ws) if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(c),c.cb) else None


def relative(series, t0, t1, max_gap=.5):
    if len(series)<2 or t0<series[0][0] or t1>series[-1][0]: return None
    lo=max(0,int(np.searchsorted(series[:,0],t0))-1)
    hi=min(len(series),int(np.searchsorted(series[:,0],t1))+1)
    gaps=np.diff(series[lo:hi,0])
    if np.any(gaps<=0) or np.any(gaps>max_gap): return None
    out=[]
    for t in (t0,t1):
        i=min(max(int(np.searchsorted(series[:,0],t)),1),len(series)-1)
        a,b=series[i-1],series[i]
        if not 0<b[0]-a[0]<=max_gap: return None
        f=(t-a[0])/(b[0]-a[0])
        out.append((a[1]+f*(b[1]-a[1]),a[2]+f*(b[2]-a[2]),a[3]+f*wrap(b[3]-a[3])))
    a,b=out;dx,dy=b[0]-a[0],b[1]-a[1]
    return [math.cos(a[2])*dx+math.sin(a[2])*dy,-math.sin(a[2])*dx+math.cos(a[2])*dy,wrap(b[2]-a[2])]


def scan_motion(a,b):
    # Later scan transformed into earlier scan = robot's relative displacement.
    candidates=[icp(b,a,(0,0,h)) for h in (-.15,0,.15)]
    good=[r for r in candidates if r is not None and r[3]<=.05 and r[4]>=.6]
    if len(good)!=3: return {'valid':False,'reason':'neutral seed quality failure'}
    best=min(good,key=lambda r:r[3]); reverse=icp(a,b,(0,0,0))
    spread=max(abs(wrap(r[2]-best[2])) for r in good)
    if reverse is None: return {'valid':False,'reason':'reverse registration failed'}
    c,s=math.cos(best[2]),math.sin(best[2])
    closure=math.hypot(best[0]+c*reverse[0]-s*reverse[1],best[1]+s*reverse[0]+c*reverse[1])
    yawclosure=abs(wrap(best[2]+reverse[2]))
    valid=spread<=math.radians(2) and closure<=.04 and yawclosure<=math.radians(2) and reverse[3]<=.05 and reverse[4]>=.6
    return {'valid':valid,'motion':list(best[:3]),'rmse_m':best[3],
        'inliers':best[4],'seed_yaw_spread_deg':math.degrees(spread),
        'reciprocal_error_m':closure,'reciprocal_yaw_deg':math.degrees(yawclosure)}


def audit(bag):
    startcpu=time.process_time();startwall=time.perf_counter()
    bag=Path(bag);updates,gyro=load_bag(bag);data={};digests={}
    for path in sorted(bag.glob('*.db3')):
        with path.open('rb') as handle:
            digests[path.name]=hashlib.file_digest(handle,'sha256').hexdigest()
        with sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True) as db:
            topics={n:(i,t) for i,n,t in db.execute('select id,name,type from topics')}
            for name in ('/scan','/tf_static','/odom','/yahboom/odom','/amcl_pose'):
                if name not in topics: continue
                ident,typ=topics[name]
                data.setdefault(name,[]).extend((ts*1e-9,TS.deserialize_cdr(raw,typ)) for ts,raw in
                    db.execute('select timestamp,data from messages where topic_id=? order by timestamp',(ident,)))
    scans=data.get('/scan',[]);transforms={}
    for _,m in data.get('/tf_static',[]):
        for tr in m.transforms: transforms[tr.child_frame_id.strip('/')]=tr
    if not scans: return {'bag':bag.name,'error':'no scans'}
    frame=scans[0][1].header.frame_id.strip('/'); seen=set();tx=ty=h=0
    while frame!='base_link':
        tr=transforms.get(frame)
        if tr is None or frame in seen:
            return {'bag':bag.name,'error':'explicit static laser-to-base chain required'}
        seen.add(frame);q=tr.transform.rotation
        if abs(q.x)>1e-5 or abs(q.y)>1e-5:
            return {'bag':bag.name,'error':'nonplanar laser transform unsupported'}
        th=yaw_q(q);c,s=math.cos(th),math.sin(th)
        tx,ty=c*tx-s*ty+tr.transform.translation.x,s*tx+c*ty+tr.transform.translation.y
        h+=th;frame=tr.header.frame_id.strip('/')
    rot=np.array([[math.cos(h),math.sin(h)],[-math.sin(h),math.cos(h)]])
    points=[]
    for received,m in scans:
        r=np.asarray(m.ranges);a=m.angle_min+np.arange(len(r))*m.angle_increment
        ok=np.isfinite(r)&(r>max(.3,m.range_min))&(r<min(8,m.range_max))
        if m.header.frame_id.strip('/')!=scans[0][1].header.frame_id.strip('/'):
            return {'bag':bag.name,'error':'scan frame changed'}
        p=np.c_[r[ok]*np.cos(a[ok]),r[ok]*np.sin(a[ok])]@rot+[tx,ty]
        points.append((stamp(m.header),p,received-stamp(m.header)))
    points.sort(key=lambda p:p[0]);times=np.array([p[0] for p in points])
    def poses(name):
        rows=[]
        for _,m in data.get(name,[]):
            p=m.pose.pose; rows.append((stamp(m.header),p.position.x,p.position.y,yaw_q(p.orientation)))
        return np.array(sorted(rows))
    wheel,ekf=poses('/yahboom/odom'),poses('/odom')
    origin=updates[0]['stamp_ns']*1e-9 if updates else times[0]
    windows=[];at=origin
    while at+2<=times[-1]:
        end=at+2;g,coverage=integrate_gyro(gyro,at,end)
        w=relative(wheel,at,end);e=relative(ekf,at,end)
        if w is None or coverage<1.8: at=end;continue
        # Include moving/turning evidence; retain missing exact snapshots explicitly.
        if math.hypot(*w[:2])<.02 and abs(g)<math.radians(3): at=end;continue
        i=int(np.argmin(abs(times-at)));j=int(np.argmin(abs(times-end)))
        r={'valid':False,'reason':'scan time bounds or sparse rays'}
        if max(abs(times[i]-at),abs(times[j]-end))<=.1 and min(len(points[i][1]),len(points[j][1]))>=80:
            # Long-gap neutral ICP can fail. It is rejected, not initialized from wheels.
            r=scan_motion(points[i][1],points[j][1])
        row={'start_s':at-origin,'end_s':end-origin,'wheel':w,'ekf':e,
            'gyro_yaw_deg':math.degrees(g),'gyro_coverage':coverage/2,'lidar':r}
        maxrate=max((abs(z) for t,z in gyro if at<=t<=end),default=0)
        row['gate']=consistency(w[2],g,r.get('motion',[None]*3)[2],
            gyro_coverage=coverage/2,lidar_valid=r['valid'],gyro_uncertainty=math.radians(2),
            lidar_uncertainty=math.radians(2),sync_uncertainty=.1,max_rate=maxrate,wheel_uncertainty=math.radians(3))
        if updates:
            exact=summarize_window(updates,gyro,at,end);row['exact']=exact
            selected=[u for u in updates if at<=u['stamp_ns']*1e-9<end]
            # Compare full 4WS formula under the SAME unmeasured command-angle assumption.
            p=(0,0,0);shadow=(0,0,0);shadow_ok=True;maxlat=0
            previous=selected[0]['stamp_ns']*1e-9-selected[0]['integration_dt_s'] if selected else at
            for u in selected:
                f,b=(math.radians(v-c) for v,c in zip(u['steering_command_deg'],u['steering_centers_deg']))
                geo=geometry(f,b,u['wheelbase_m'],u['track_width_m'])
                maxlat=max(maxlat,abs(geo['lateral_ratio']))
                p=integrate(*p,u['accepted_delta_m'],geo['lateral_ratio'],u['accepted_delta_m']*geo['curvature'])
                current=u['stamp_ns']*1e-9;gi,gcovered=integrate_gyro(gyro,previous,current)
                if current<=previous or gcovered<.9*(current-previous): shadow_ok=False
                shadow=integrate(*shadow,u['accepted_delta_m'],0,gi)
                previous=current
            row['same_commands_full_model']=p;row['max_command_lateral_ratio']=maxlat
            row['gyro_heading_wheel_translation_shadow']=list(shadow) if shadow_ok else None
            row['shadow_limit']='not EKF; same uncalibrated wheel distance; zero lateral assumption retained'
        windows.append(row);at=end
    amcl=poses('/amcl_pose');jumps=[]
    for a,b in zip(amcl,amcl[1:]):
        distance=math.hypot(b[1]-a[1],b[2]-a[2])
        if distance>.5: jumps.append({'at_s':b[0]-origin,'distance_m':distance,'heading_deg':math.degrees(wrap(b[3]-a[3]))})
    classifications={s:sum(w['gate']['classification']==s for w in windows) for s in
        ('WHEEL_SUSPECT','REFERENCES_DISAGREE','UNKNOWN','CONSISTENT_WITH_ASSUMED_BOUNDS')}
    metrics={}
    for key in ('wheel','ekf','same_commands_full_model','gyro_heading_wheel_translation_shadow'):
        valid=[w for w in windows if w['lidar']['valid'] and w.get(key) is not None]
        metrics[key]={'n':len(valid),
            'xy_error_median_m':float(np.median([math.hypot(w[key][0]-w['lidar']['motion'][0],w[key][1]-w['lidar']['motion'][1]) for w in valid])) if valid else None,
            'yaw_error_median_deg':float(np.median([math.degrees(abs(wrap(w[key][2]-w['lidar']['motion'][2]))) for w in valid])) if valid else None}
    result={'bag':bag.name,'sha256':digests,'exact_encoder_updates':len(updates),'windows':windows,
        'screened_relative_motion_metrics':metrics,
        'screening_counts':classifications,'recorded_amcl_steps_over_0_5m':jumps,
        'scan_receipt_lag_p95_s':float(np.percentile([p[2] for p in points],95)),
        'authority':'NONE','candidate_ekf_amcl_replay':'NOT RUN; this is motion comparison, not ROS EKF replay',
        'cpu_seconds':time.process_time()-startcpu,'wall_seconds':time.perf_counter()-startwall}
    result['process_lifetime_peak_rss_bytes']=peak_rss_bytes()
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bags',nargs='+');p.add_argument('--output',required=True)
    a=p.parse_args();out=Path(a.output)
    if out.exists(): p.error('output already exists; preserve evidence')
    result=[audit(b) for b in a.bags]
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps([{k:v for k,v in r.items() if k!='windows'} for r in result],indent=2))


if __name__=='__main__': main()

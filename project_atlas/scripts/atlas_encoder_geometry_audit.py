"""Offline approximate raw-count consensus reconstruction; no hardware I/O.

Uses complete four-topic batches, not board packet timestamps. Current config
must not be assumed identical to historical config. Cases are diagnostic only.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from atlas_encoder_calibration import load_encoder_calibration
from atlas_encoder_selection import EncoderDeltaEstimator, four_wheel_path_scales


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bag'); p.add_argument('config_directory'); p.add_argument('output')
    args=p.parse_args()
    root=Path(args.config_directory)
    calibration=load_encoder_calibration(root/'encoder_calibration.yaml')
    steering=json.loads((root/'steering_calibration.json').read_text())
    import yaml
    width=yaml.safe_load((root/'drive_pid.yaml').read_text())['atlas_drive_pid']['geometry']['track_width_m']
    centers=[steering['steering'][k]['center'] for k in ('front','rear')]
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=args.bag,storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
    types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()}
    topics={f'/yahboom/encoder/m{i+1}':i for i in range(4)}
    steer_topics={'/steering/front_angle_deg':0,'/steering/rear_angle_deg':1}
    estimators={name:EncoderDeltaEstimator() for name in ('commanded_angle','half_angle','no_normalization')}
    totals={name:{'accepted':0,'rejected':0,'abs_integrated_m':0.,'signed_integrated_m':0.} for name in estimators}
    counts=[0]*4; times=[0.]*4; angles=list(centers); angle_times=[0.,0.]; seen=set(); previous=None
    rows=[]; discarded=0; start=None
    while reader.has_next():
        topic,data,record=reader.read_next()
        t=record*1e-9
        if start is None:start=t
        if topic not in topics and topic not in steer_topics: continue
        m=deserialize_message(data,types[topic])
        if topic in steer_topics:
            i=steer_topics[topic]; angles[i]=float(m.data); angle_times[i]=t; continue
        i=topics[topic];counts[i]=int(m.data);times[i]=t;seen.add(i)
        if len(seen)!=4:continue
        seen.clear()
        if max(times)-min(times)>.04 or min(angle_times)==0 or t-min(angle_times)>.5:
            discarded+=1
            for est in estimators.values():est.previous=None;est.previous_valid=set()
            previous=None
            continue
        distances=[calibration.telemetry(i,0,counts[i])[2] for i in range(4)]
        moving=previous is not None and max(abs(distances[i]-previous[i]) for i in range(4))>.004
        previous=distances
        result={}
        for name,est in estimators.items():
            factor={'commanded_angle':1.,'half_angle':.5,'no_normalization':0.}[name]
            front,rear=[math.radians((a-c)*factor) for a,c in zip(angles,centers)]
            curvature=(math.tan(front)-math.tan(rear))/calibration.wheelbase_m
            scales=four_wheel_path_scales(curvature,calibration.wheelbase_m,width,calibration.positions)
            delta=est.update(distances,range(4),scales)
            result[name]={'accepted':list(est.last_accepted),'delta_m':delta,'normalized_deltas':list(est.last_deltas)}
            if moving:
                key='accepted' if len(est.last_accepted)>=3 else 'rejected'
                totals[name][key]+=1
                totals[name]['abs_integrated_m']+=abs(delta)
                totals[name]['signed_integrated_m']+=delta
        if moving: rows.append({'seconds':t-start,'steering':angles.copy(),'cases':result})
    changed=[r for r in rows if len(r['cases']['commanded_angle']['accepted'])<3 and len(r['cases']['no_normalization']['accepted'])>=3]
    worse=[r for r in rows if len(r['cases']['commanded_angle']['accepted'])>=3 and len(r['cases']['no_normalization']['accepted'])<3]
    report={'totals_moving_batches':totals,'discarded_unsynchronized_batches':discarded,
            'rescued_without_normalization':len(changed),'lost_without_normalization':len(worse),
            'examples':changed[:5],'rows':rows,'centers':centers,
            'config_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('encoder_calibration.yaml','steering_calibration.json','drive_pid.yaml')},
            'limitations':'Approximate asynchronous topic batching, current configuration snapshot, all four channels offered without historic private fault-state replay. Cases change odometry math only; more agreement is not proof of accuracy or a safe change. No measured wheel-angle ground truth.'}
    with Path(args.output).open('x') as out:json.dump(report,out,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','examples')},indent=2))


if __name__=='__main__':main()

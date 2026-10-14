"""Read-only source-time/QoS inventory for Stage 19, including missing evidence."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from rosbags.typesys import Stores,get_typestore

REQUIRED=('/scan','/tf','/tf_static','/yahboom/odom','/im10a/imu/bias_corrected_candidate')
CONTEXT=('/atlas/encoder_update','/odom','/amcl_pose','/particle_cloud',
    '/steering/front_angle_deg','/steering/rear_angle_deg','/map',
    '/parameter_events','/initialpose','/request_nomotion_update/_service_event',
    '/im10a/imu/unvalidated')+tuple('/yahboom/encoder/m'+str(i) for i in range(1,5))


def audit(bag):
    ts=get_typestore(Stores.ROS2_HUMBLE);result={};files={};events=0;previous=None
    for path in sorted(Path(bag).glob('*.db3')):
        with path.open('rb') as f: files[path.name]=hashlib.file_digest(f,'sha256').hexdigest()
        with sqlite3.connect('file:'+path.as_posix()+'?mode=ro',uri=True) as db:
            integrity=db.execute('pragma integrity_check').fetchone()[0]
            if integrity!='ok':raise ValueError('SQLite integrity failed')
            topics={n:(i,t,q) for i,n,t,q in db.execute('select id,name,type,offered_qos_profiles from topics')}
            for name in REQUIRED+CONTEXT:
                if name not in topics:continue
                ident,typ,qos=topics[name];count,first,last=db.execute(
                    'select count(*),min(timestamp),max(timestamp) from messages where topic_id=?',(ident,)).fetchone()
                row={'type':typ,'count':count,'first_receipt_ns':first,'last_receipt_ns':last,'offered_qos':qos}
                if name in ('/scan','/odom','/yahboom/odom','/im10a/imu/bias_corrected_candidate'):
                    stamps=[];lags=[]
                    for received,raw in db.execute('select timestamp,data from messages where topic_id=? order by id',(ident,)):
                        m=ts.deserialize_cdr(raw,typ);h=m.header.stamp.sec*1000000000+m.header.stamp.nanosec
                        stamps.append(h);lags.append((received-h)/1e9)
                    row.update(header_backwards=sum(b<a for a,b in zip(stamps,stamps[1:])),
                        header_duplicates=sum(a==b for a,b in zip(stamps,stamps[1:])),
                        receipt_minus_header_min_s=min(lags),receipt_minus_header_max_s=max(lags))
                result[name]=row
            ordered=[t for t, in db.execute('select timestamp from messages order by id')]
            events+=sum(b<a for a,b in zip(ordered,ordered[1:]))
    return {'bag':Path(bag).name,'sha256':files,'topics':result,
        'required_missing':[n for n in REQUIRED if n not in result],
        'context_missing':[n for n in CONTEXT if n not in result],
        'receipt_regressions_in_storage_order':events,'integrity':'ok',
        'filter_rng_internal_state':'NOT RECORDED','authority':'NONE'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bags',nargs='+');a=p.parse_args()
    print(json.dumps([audit(b) for b in a.bags],indent=2))

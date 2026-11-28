"""PC-only bounded raw CDR recorder; live activation intentionally unavailable.

Reuses Stage20 inventory, stamps, RosbagSink and QueuedWriter. No publishers,
service clients, parameter writes or Jetson setup. CLI refuses host networking.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import time

from stage20_capture import (KNOWN_TYPES, TOPIC_LIST, STATIONARY_CONTINUOUS,
                             STATIONARY_ONCE, serialized_source_stamp, RosbagSink,
                             QueuedWriter, Sample)

REQUIRED = tuple(dict.fromkeys(STATIONARY_CONTINUOUS + STATIONARY_ONCE + (
    '/scan_raw', '/lidar/odom', '/atlas/encoder_health', '/im10a/imu/unvalidated')))
TYPES = {t:KNOWN_TYPES.get(t, 'nav_msgs/msg/Odometry' if t=='/lidar/odom' else None)
         for t in REQUIRED}
assert set(REQUIRED)<=set(TOPIC_LIST) and all(TYPES.values())
EVENT_DRIVEN = set(STATIONARY_ONCE)
LIMIT = 500*1024**2


def isolation():
    if (os.environ.get('ROS_DOMAIN_ID')!='187' or
        os.environ.get('ROS_LOCALHOST_ONLY')!='1' or
        os.environ.get('ATLAS_PC_HOST_NET_NS')==os.readlink('/proc/self/ns/net') or
        not os.environ.get('ATLAS_PC_HOST_NET_NS')):
        raise RuntimeError('isolated PC network required; live approval adapter not implemented')
    if 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise RuntimeError('PC WSL only')


def qos(topic):
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    return QoSProfile(depth=200,
        reliability=ReliabilityPolicy.RELIABLE if topic=='/tf_static' else ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.TRANSIENT_LOCAL if topic=='/tf_static' else DurabilityPolicy.VOLATILE)


def bytes_under(root):
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())


class LedgerSink(RosbagSink):
    def __init__(self, root, budget, rosbag):
        super().__init__(root,budget,rosbag)
        self.charged=0
        self.ledger=(self.path/'pc_receipts.jsonl').open('x',encoding='utf-8')

    def write(self,sample):
        row={'topic':sample.topic,'type':sample.type_name,'pc_receive_ns':sample.ros_time_ns,
             'pc_receive_monotonic_ns':int(sample.monotonic_s*1e9),
             'source_header_ns':serialized_source_stamp(sample.payload,sample.type_name),
             'sha256':hashlib.sha256(sample.payload).hexdigest()}
        line=json.dumps(row,separators=(',',':'))+'\n'
        # Conservative logical reservation includes SQLite pages/index and ledger.
        charge=len(sample.payload)+len(line.encode())+16384
        if self.charged+charge>self.budget_bytes:
            raise OSError('conservative disk budget exhausted')
        self.charged+=charge
        super().write(sample)
        self.ledger.write(line)

    def close(self,*args):
        try:
            super().close(*args)
        finally:
            self.ledger.close()


class Recorder:
    def __init__(self,root,duration=30,clock=None):
        if duration!=30:raise ValueError('exact30s capture required')
        isolation()
        import rclpy
        import rosbag2_py
        from rosidl_runtime_py.utilities import get_message
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.lock=self.root/'.offboard-active'
        # Existing lock fails closed; stale-lock removal requires manual evidence review.
        fd=os.open(self.lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        os.close(fd)
        self.worker=None;self.node=None;self.stop_reason=None
        try:
            used=bytes_under(self.root)
            budget=LIMIT-used-2*1024**2
            if budget<5*1024**2 or shutil.disk_usage(self.root).free<1024**3:
                raise OSError('storage admission refused')
            self.worker=QueuedWriter(lambda:LedgerSink(self.root,budget,rosbag2_py),max_bytes=8*1024**2,max_messages=4000)
            self.capture=self.worker.open_capture()
            if not self.worker.wait_idle(5) or self.worker.error:raise RuntimeError('writer startup failed')
            self.node=rclpy.create_node('atlas_pc_offboard_readonly',enable_rosout=False,start_parameter_services=False)
            self.counts=Counter();self.last={};self.started=time.monotonic()
            self.deadline=self.started+duration;self.clock=clock or {'offset_ns':None,'uncertainty_ns':None}
            self.subs=[];self.lost=Counter();self.qos_report={};self.discovery={}
            from rclpy.qos_event import SubscriptionEventCallbacks
            for topic,kind in TYPES.items():
                q=qos(topic)
                self.qos_report[topic]={'type':kind,'reliability':str(q.reliability),'durability':str(q.durability),'depth':q.depth}
                def lost(event,t=topic):self.lost[t]+=event.total_count_change
                self.subs.append(self.node.create_subscription(get_message(kind),topic,
                    lambda raw,t=topic,k=kind:self.receive(t,k,raw),q,raw=True,
                    event_callbacks=SubscriptionEventCallbacks(message_lost=lost)))
        except BaseException:
            if self.node:self.node.destroy_node()
            drained=self.worker is None
            if self.worker:
                try:
                    self.capture.close('initialization_error',{},{})
                    drained=self.worker.shutdown(5)
                except Exception:pass
            if drained:self.lock.unlink(missing_ok=True)
            raise

    def receive(self,topic,kind,raw):
        mono=time.monotonic()
        if mono>=self.deadline or self.stop_reason:return
        self.last[topic]=mono
        try:
            self.capture.write(Sample(topic,kind,bytes(raw),mono,time.time_ns()))
            self.counts[topic]+=1
        except Exception as exc:self.stop_reason='enqueue_error:'+type(exc).__name__

    def tick(self):
        now=time.monotonic()
        if self.worker.error:self.stop_reason='writer_error'
        if now-self.started>5:
            absent=[t for t in REQUIRED if t not in self.last]
            stale=[t for t in REQUIRED if t not in EVENT_DRIVEN and t in self.last and now-self.last[t]>2]
            if absent or stale:self.stop_reason='missing_or_stale_required_source'
        # Discovery only; no service calls. Inspect after handshake and once near finish.
        if not self.discovery and now-self.started>2:
            for t in REQUIRED:
                self.discovery[t]=[{'type':p.topic_type,'node':p.node_name,
                    'reliability':str(p.qos_profile.reliability),'durability':str(p.qos_profile.durability)}
                    for p in self.node.get_publishers_info_by_topic(t)]
                if any(p['type']!=TYPES[t] for p in self.discovery[t]):self.stop_reason='type_mismatch'
        return not self.stop_reason and now<self.deadline

    def close(self):
        reason=self.stop_reason or 'duration_complete'
        self.node.destroy_node()
        self.capture.close(reason,dict(self.lost),dict(self.counts))
        drained=self.worker.shutdown(10)
        health=self.worker.health()
        path=Path(self.worker.last_path)
        missing=sorted(set(REQUIRED)-self.counts.keys())
        result={'reason':reason,'duration_s':time.monotonic()-self.started,'counts':dict(self.counts),
                'missing':missing,'dds_reported_lost':dict(self.lost),'unobservable_transport_loss':'UNKNOWN',
                'writer':health,'clock':self.clock,'qos_requested':self.qos_report,'publishers':self.discovery,
                'capture_complete':reason=='duration_complete' and not missing and drained and not health['error'] and not any(self.lost.values()),
                'estimator_consumption_proven':False,'private_estimator_state_available':False}
        if not drained:result['capture_complete']=False
        result['writer_drained']=drained
        (path/'pc_result.json').write_text(json.dumps(result,indent=2))
        if drained:self.lock.unlink()
        return path,result


def verify(path):
    path=Path(path)
    ledger=[json.loads(x) for x in (path/'pc_receipts.jsonl').read_text().splitlines()]
    from contextlib import closing
    with closing(sqlite3.connect('file:'+str(next(path.glob('*.db3')))+'?mode=ro',uri=True)) as db:
        if db.execute('pragma integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity')
        rows=db.execute('SELECT topics.name,topics.type,messages.timestamp,messages.data FROM messages JOIN topics ON topics.id=messages.topic_id ORDER BY messages.id').fetchall()
    if len(rows)!=len(ledger):raise ValueError('ledger count mismatch')
    for (topic,kind,stamp,raw),r in zip(rows,ledger):
        if (topic,kind,stamp,hashlib.sha256(raw).hexdigest(),serialized_source_stamp(raw,kind))!=(r['topic'],r['type'],r['pc_receive_ns'],r['sha256'],r['source_header_ns']):
            raise ValueError('payload/timestamp mismatch')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir() if p.is_file() and p.name!='pc_integrity.json'}
    result={'messages_verified':len(rows),'file_hashes':hashes,'bytes':bytes_under(path)}
    (path/'pc_integrity.json').write_text(json.dumps(result,indent=2))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record-isolated',action='store_true',required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();isolation()
    import rclpy
    rclpy.init();r=Recorder(args.output)
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:setattr(r,'stop_reason','cancelled'))
    try:
        while r.tick():rclpy.spin_once(r.node,timeout_sec=.02)
    except BaseException:
        r.stop_reason='exception';raise
    finally:
        path,result=r.close();rclpy.shutdown()
        integrity=verify(path) if result['writer_drained'] else {'status':'NOT_VERIFIED_WRITER_STILL_ACTIVE'}
        print(json.dumps({'path':str(path),'result':result,'integrity':integrity},indent=2))


if __name__=='__main__':main()

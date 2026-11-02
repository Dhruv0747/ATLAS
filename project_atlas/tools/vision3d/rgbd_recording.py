"""In-process recording binding for the EXISTING Vision Lab session/cache.

No CLI, ROS node, subscription or implicit activation. Host must supply its
existing timestamped TF/odom/scan cache and bounded safety observer. Missing
providers fail before Start. No web route is enabled by importing this module.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import time

from calibration_capture import Evidence, Supervisor, safety
from onboard_adapter import checked_images, ns
from calibration_validation import validate_calibration
from onboard_store import atomic
from astra_bag_adapter import TOPICS

TYPES={k:('sensor_msgs/msg/CameraInfo' if k.endswith('info') else 'sensor_msgs/msg/Image') for k in TOPICS.values()}
CONTEXT={'tf':'tf2_msgs/msg/TFMessage','tf_static':'tf2_msgs/msg/TFMessage',
         'odom':'nav_msgs/msg/Odometry','scan':'sensor_msgs/msg/LaserScan'}


def metadata(kind,msg,serialize,receipt):
    row=dict(cdr=bytes(serialize(msg)),recorded_timestamp_ns=receipt)
    if kind in TYPES:
        row.update(stamp_sec=msg.header.stamp.sec,stamp_nanosec=msg.header.stamp.nanosec,
                   width=msg.width,height=msg.height,frame_id=msg.header.frame_id)
        if kind.endswith('info'):
            row.update(k=[float(v) for v in msg.k],d=[float(v) for v in msg.d],r=[float(v) for v in msg.r],p=[float(v) for v in msg.p],distortion_model=msg.distortion_model)
        else:
            row.update(encoding=msg.encoding,step=msg.step,data_bytes=len(msg.data),is_bigendian=msg.is_bigendian)
            if kind=='depth':row['units_to_m']={ '16UC1':.001,'32FC1':1. }[msg.encoding]
    else:
        # TFMessage has no header; original per-transform stamps remain in CDR.
        row.update(stamp_sec=receipt//10**9,stamp_nanosec=receipt%10**9,
                   stamp_provenance='receipt; original message stamps retained in CDR')
    return row


def validate_context(messages,stamp,camera_frame,now):
    if set(messages)!=set(CONTEXT):raise ValueError('missing TF/odom/scan evidence')
    from tf2_ros import Buffer
    from rclpy.time import Time
    buffer=Buffer()
    for key in ('tf_static','tf'):
        batches=messages[key] if isinstance(messages[key],list) else [messages[key]]
        if not batches or any(not m.transforms for m in batches):raise ValueError('empty TF evidence')
        for t in (t for m in batches for t in m.transforms):
            v=t.transform.translation;q=t.transform.rotation
            if not all(math.isfinite(x) for x in (v.x,v.y,v.z,q.x,q.y,q.z,q.w)):
                raise ValueError('invalid TF geometry')
            if abs(sum(x*x for x in (q.x,q.y,q.z,q.w))-1)>1e-3:raise ValueError('invalid TF quaternion')
            if key=='tf' and not 0<=now-ns(t)<=500000000:raise ValueError('stale TF')
            (buffer.set_transform_static if key=='tf_static' else buffer.set_transform)(t,'recorded-cache')
    at=Time(nanoseconds=stamp)
    if not buffer.can_transform('base_link',camera_frame,at) or not buffer.can_transform('odom','base_link',at):
        raise ValueError('TF unavailable at original image timestamp')
    odom=messages['odom'];scan=messages['scan']
    if odom.header.frame_id!='odom' or odom.child_frame_id!='base_link':raise ValueError('unexpected odometry frames')
    if not scan.header.frame_id or not buffer.can_transform('base_link',scan.header.frame_id,Time(nanoseconds=ns(scan))):
        raise ValueError('scan TF unavailable')
    if any(not 0<=now-ns(m)<=500000000 for m in (odom,scan)):raise ValueError('stale context')


def export_bag(directory,odom_topic='/odom',scan_topic='/scan'):
    """Read-only original evidence -> standard rosbag2 SQLite, without restamping.

    Explicit offline operation, after shutdown. Never replay an aborted capture.
    Original evidence is retained; conversion has its own 128MiB page bound.
    """
    directory=Path(directory);result=json.loads((directory/'result.json').read_text())
    source=directory/'capture.sqlite'
    if result.get('status')!='COMPLETE' or result.get('shutdown_verified') is not True:
        raise ValueError('capture incomplete or shutdown unverified')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=result['database_sha256']:raise ValueError('capture checksum mismatch')
    if shutil.disk_usage(directory).free<1024**3:raise ValueError('free reserve unavailable')
    output=directory/'replay.db3'
    # Exclusive creation: no overwrite/retry of an existing conversion.
    with output.open('xb'):pass
    topics={v:k for k,v in TOPICS.items()};topics.update(tf='/tf',tf_static='/tf_static',odom=odom_topic,scan=scan_topic)
    try:
        with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(output) as dst:
            if src.execute('pragma integrity_check').fetchone()!=('ok',):raise ValueError('capture integrity failed')
            page=dst.execute('pragma page_size').fetchone()[0]
            dst.execute('pragma max_page_count='+str(128*1024**2//page));dst.execute('pragma synchronous=FULL')
            dst.execute('create table topics(id integer primary key,name text,type text,serialization_format text,offered_qos_profiles text)')
            dst.execute('create table messages(id integer primary key,topic_id integer,timestamp integer,data blob)')
            ids={k:i+1 for i,k in enumerate(topics)};seen=set()
            for k,topic in topics.items():
                qos='- history: 1\n  depth: 100\n  reliability: 1\n  durability: 1\n' if k=='tf_static' else ''
                dst.execute('insert into topics values(?,?,?,?,?)',(ids[k],topic,{**TYPES,**CONTEXT}[k],'cdr',qos))
            for kind,meta,sha,cdr in src.execute('select stream,metadata,sha256,cdr from messages order by id'):
                if kind not in ids or hashlib.sha256(cdr).hexdigest()!=sha:raise ValueError('message integrity failed')
                stamp=json.loads(meta)['recorded_timestamp_ns']
                if type(stamp) is not int or stamp<0:raise ValueError('invalid receipt timestamp')
                dst.execute('insert into messages(topic_id,timestamp,data) values(?,?,?)',(ids[kind],stamp,cdr));seen.add(kind)
            if seen!=set(ids):raise ValueError('missing replay inputs')
            dst.execute('create index timestamp_idx on messages(timestamp)');dst.commit()
            if dst.execute('pragma integrity_check').fetchone()!=('ok',):raise ValueError('bag integrity failed')
        atomic(directory/'replay-result.json',{'status':'CONVERTED_NOT_MAPPED','sha256':hashlib.sha256(output.read_bytes()).hexdigest()})
    except BaseException as e:
        atomic(directory/'replay-result.json',{'status':'FAILED','reason':str(e)[:500]})
        raise
    return output


class Recording:
    """Uses the controller's existing lease and cache, never starts a second driver."""
    def __init__(self,controller,vision,observer,context,*,clock=time.monotonic,wall_ns=time.time_ns,sleep=time.sleep):
        self.controller,self.vision,self.observer,self.context=controller,vision,observer,context
        self.clock,self.wall_ns,self.sleep=clock,wall_ns,sleep
        self.used=False;self.owned=None;self.token=object()

    def stop_owned(self):
        if self.owned is None:return True
        with self.controller.lock:
            if self.controller.child is not self.owned:raise RuntimeError('camera owner changed; refusing stop')
            self.controller.stop()
            if self.owned.poll() is None:raise RuntimeError('camera worker still running')
            state=self.controller.status()
            if (state.get('worker_pid')!=self.owned.pid or state.get('driver_stopped') is not True
                    or state.get('cloud_stopped') is not True):
                raise RuntimeError('owned driver shutdown evidence unavailable')
            for pid in (self.owned.pid,state.get('driver_pid'),state.get('cloud_pid')):
                if pid is None:continue
                if type(pid) is not int or pid<=1:raise RuntimeError('invalid owned process identity')
                try:os.killpg(pid,0)
                except ProcessLookupError:continue
                raise RuntimeError('owned camera process group remains')
            self.controller.release_capture(self.token)
            return True

    def run(self,directory,docs,serial,*,approved=False):
        if self.used:raise RuntimeError('single use recording already consumed')
        self.used=True;start=self.clock();store=Evidence(directory);supervisor=None
        try:
            if approved is not True:raise ValueError('explicit capture approval required')
            if not callable(self.observer) or not callable(self.context):raise ValueError('safety/TF cache provider missing')
            for k in ('rgb','depth'):
                d=docs[k];validate_calibration(d,serial,d['width'],d['height'],d['frame_id'])
            expected={k:tuple(docs['rgb' if k.startswith('rgb') else 'depth'][f] for f in ('width','height','frame_id')) for k in TYPES}
            safety(self.observer(),self.clock())
            # Confirm timestamp-valid context BEFORE any Start operation.
            now=self.wall_ns();initial=self.context();validate_context(initial,ns(initial['odom']),docs['rgb']['frame_id'],now)
            from rclpy.serialization import serialize_message
            supervisor=Supervisor(start,store,self.stop_owned,expected,docs,serial)
            # Admission includes a measured CPU interval, not an unattended
            # recording heartbeat. Keep start for the absolute 60-second bound.
            supervisor.last_tick=self.clock()
            with self.controller.lock:
                if self.controller.child is not None and self.controller.child.poll() is None:raise ValueError('camera already owned')
                if self.vision.transport is not None:raise ValueError('existing viewer transport active')
                if self.clock()-start>=60:raise TimeoutError('startup deadline')
                self.controller.start('concurrent',capture_owner=self.token,deadline=start+60);self.owned=self.controller.child
            last=None
            while not supervisor.closed:
                observation=self.observer();now=self.clock()
                if now-start>=60:
                    supervisor.tick(now,observation);break
                self.controller.touch(capture_owner=self.token)  # only guarded recorder renews capture lease
                self.vision.touch()  # reuse existing transport; browser cannot renew capture lease
                with self.vision.lock:messages={k:self.vision.messages[k] for k in TYPES if k in self.vision.messages}
                rows=None;receipt=self.wall_ns()
                if len(messages)==4:
                    stamps=tuple(ns(messages[k]) for k in TYPES)
                    if (last is None or all(a>b for a,b in zip(stamps,last))) and max(stamps)-min(stamps)<=30000000:
                        checked_images(messages,docs,receipt)
                        context=self.context();validate_context(context,ns(messages['rgb']),docs['rgb']['frame_id'],receipt)
                        rows={k:metadata(k,m,serialize_message,receipt) for k,m in messages.items()}
                        if shutil.disk_usage(store.path).free<1024**3:raise ValueError('free reserve unavailable')
                        # Preserve context CDR in the same bounded evidence DB.
                        if self.clock()-start>=60:
                            supervisor.tick(self.clock(),observation);break
                        batches={k:(v if isinstance(v,list) else [v]) for k,v in context.items()}
                        for i in range(max(map(len,batches.values()))):
                            store.write({k:metadata(k,v[i],serialize_message,receipt) for k,v in batches.items() if i<len(v)})
                        last=stamps
                supervisor.tick(self.clock(),observation,rows,receipt)
                if not supervisor.closed:self.sleep(.1)
        except BaseException as e:
            if supervisor is not None and not supervisor.closed:supervisor.close('ABORTED',str(e))
            elif supervisor is None:store.finish({'status':'ABORTED','reason':str(e),'shutdown_verified':self.owned is None})
            else:raise
        finally:
            if self.owned is not None and self.controller.child is self.owned:
                try:self.vision.stop()  # remove owned transport; no other subscriber created
                except Exception as e:
                    result=json.loads((Path(directory)/'result.json').read_text())
                    result.update(status='ABORTED',transport_cleanup_error=str(e)[:500])
                    atomic(Path(directory)/'result.json',result)
        return json.loads((Path(directory)/'result.json').read_text())


def existing_binding(observer,context):
    """Call in the existing web process only after reviewed route integration.

    Providers MUST reuse its existing bounded safety and TF caches. This factory
    never starts anything; no HTTP route or dashboard control is enabled here.
    """
    from atlas_vision3d_runtime import SESSION
    from atlas_vision3d_web import SERVICE
    return Recording(SESSION,SERVICE,observer,context)


class ExistingSafety:
    """Adapt the existing one-second local guard; no thread/node or HTTP needed.

    Initial CPU interval is included in the Recording's total deadline. Cached
    observations expire after one second; a delayed/failed refresh never renews
    them. Camera worker independently enforces its existing safety lease.
    """
    def __init__(self, observe, *, clock=time.monotonic, sleep=time.sleep, counters=None):
        from stationary_gate import ticks
        self.observe=observe;self.clock=clock;self.sleep=sleep;self.counters=counters or ticks
        self.previous=None;self.previous_at=None;self.cached=None

    def __call__(self):
        from stationary_gate import cpu_delta
        now=self.clock()
        if self.previous is None:
            self.previous=self.counters();self.previous_at=now
            self.sleep(1);now=self.clock()
        if self.cached is not None and now-self.previous_at<1:
            safety(self.cached,now);return self.cached
        current=self.counters();window=now-self.previous_at
        if not .9<=window<=1.1:raise ValueError('CPU sampling interval invalid')
        sample=self.observe(cpu_delta(self.previous,current),window)
        # Resource collection time counts towards observation age, not freshened
        # to completion of potentially slow local reads.
        sample['received_mono']=now
        safety(sample,self.clock())
        self.previous,self.previous_at,self.cached=current,now,sample
        return sample


def host_binding(host):
    """Bind existing web-node caches; disabled unless explicitly provisioned.

    No route/Start control is enabled. A future approved host call must still
    supply validated calibration and run(..., approved=True).
    """
    from onboard_supervisor import observe
    cache=getattr(host,'rgbd_context',None)
    if cache is None:raise ValueError('original-message context cache disabled')
    return existing_binding(ExistingSafety(lambda cpu,window:observe(cpu,window,ros=host.snapshot())),cache.snapshot)

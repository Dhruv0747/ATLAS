"""Opt-in, receive-only Vision Lab. No driver launch, publishers, services or recording.

Import does not create a thread or ROS node. An owner-reviewed exact topic manifest
is required; never subscribe to the existing Pi camera by guessing /camera names.
"""
import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import atlas_vision3d_core as core

API='/api/vision3d/'
KINDS=('rgb','depth','ir','cloud','depth_info')
TYPES={'rgb':'sensor_msgs/msg/Image','depth':'sensor_msgs/msg/Image','ir':'sensor_msgs/msg/Image',
       'cloud':'sensor_msgs/msg/PointCloud2','depth_info':'sensor_msgs/msg/CameraInfo'}


def read_manifest():
    path=os.environ.get('ATLAS_VISION3D_MANIFEST')
    if not path: return {}
    raw=Path(path).read_bytes()
    if len(raw)>8192: raise ValueError('manifest too large')
    m=json.loads(raw)
    if set(m)-{'topics','modes','usb_verified','identity','deployment_verified'}: raise ValueError('unknown manifest field')
    topics=m.get('topics',{})
    if set(topics)-set(KINDS): raise ValueError('unknown stream')
    for kind, topic in topics.items():
        if not isinstance(topic,str) or not topic.startswith('/') or len(topic)>200 or any(c.isspace() for c in topic):
            raise ValueError('invalid exact topic')
        if topic.startswith(('/cmd','/camera/','/yahboom/','/im10a/','/atlas/')):
            raise ValueError('production namespace forbidden')
    return m


class RosTransport:
    def __init__(self):
        self.node=self.executor=self.context=self.thread=None

    def start(self,topics,callback):
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from sensor_msgs.msg import Image,CameraInfo,PointCloud2
        self.context=Context(); rclpy.init(context=self.context)
        self.node=rclpy.create_node('atlas_vision3d_readonly',context=self.context)
        self.executor=SingleThreadedExecutor(context=self.context); self.executor.add_node(self.node)
        qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.BEST_EFFORT,durability=DurabilityPolicy.VOLATILE)
        # Graph discovery verifies exact type before creating any subscriptions.
        subscribed=set()
        def discover():
            graph=dict(self.node.get_topic_names_and_types())
            for kind,topic in topics.items():
                if kind in subscribed or TYPES[kind] not in graph.get(topic,[]):continue
                typ=CameraInfo if kind=='depth_info' else PointCloud2 if kind=='cloud' else Image
                self.node.create_subscription(typ,topic,lambda msg,k=kind:callback(k,msg),qos)
                subscribed.add(kind)
        discover()
        self.node.create_timer(2.0,discover)  # bounded discovery only while a viewer is active
        self.thread=threading.Thread(target=self.executor.spin,name='vision3d-ros',daemon=True);self.thread.start()

    def stop(self):
        if self.executor: self.executor.shutdown(timeout_sec=2)
        if self.thread: self.thread.join(timeout=2)
        if self.node: self.node.destroy_node()
        if self.context and self.context.ok(): self.context.shutdown()


class VisionService:
    def __init__(self,manifest=None,factory=RosTransport,clock=time.monotonic,wall=time.time):
        self.manifest=manifest
        self.factory,self.clock,self.wall=factory,clock,wall
        self.lock=threading.RLock();self.transport=None;self.messages={};self.received={};self.stats={}
        self.touched=0;self.idle_timer=None;self.error='';self.cache={};self.cache_at={};self.last_accept={};self.retry_after=0

    def touch(self):
        with self.lock:
            self.touched=self.clock()
            if self.manifest is None:
                try:self.manifest=read_manifest()
                except Exception as e:self.error=str(e);return
            if not self.manifest.get('topics') or self.transport or self.clock()<self.retry_after:return
            try:
                t=self.factory();t.start(self.manifest['topics'],self.ingest);self.transport=t
            except Exception as e:
                self.error='ROS unavailable: '+str(e)
                self.retry_after=self.clock()+30
                try:t.stop()
                except Exception:pass
                return
            self.idle_timer=threading.Timer(15,self._idle);self.idle_timer.daemon=True;self.idle_timer.start()

    def _idle(self):
        with self.lock:
            if self.clock()-self.touched<15:
                self.idle_timer=threading.Timer(15,self._idle);self.idle_timer.daemon=True;self.idle_timer.start();return
        self.stop()

    def stop(self):
        with self.lock:
            t,self.transport=self.transport,None
            if self.idle_timer:self.idle_timer.cancel()
            self.messages.clear();self.cache.clear();self.received.clear();self.cache_at.clear();self.last_accept.clear();self.stats.clear()
        if t:t.stop()

    def ingest(self,kind,msg):
        if kind not in KINDS:return
        now=self.clock()
        with self.lock:
            s=self.stats.setdefault(kind,{'received':0,'viewer_throttled':0,'rejected':0,'stamp_regressions':0,'times':deque(maxlen=30),'max_gap_s':0})
            s['received']+=1
            if hasattr(msg,'data') and len(msg.data)>core.MAX_BYTES:
                s['rejected']+=1;self.messages.pop(kind,None);return
            if kind in ('rgb','depth','ir'):
                try:core.image_layout(msg)
                except ValueError as e:
                    s['rejected']+=1;s['error']=str(e);self.messages.pop(kind,None);return
            source=core.stamp(msg)
            if not source>0 or not __import__('math').isfinite(source):s['rejected']+=1;return
            if 'last_stamp' in s and source<=s['last_stamp']:
                s['stamp_regressions']+=1;return
            if s['times']:s['max_gap_s']=max(s['max_gap_s'],now-s['times'][-1])
            s['times'].append(now);s['last_stamp']=source
            # Keep last immutable ROS message only, no conversion in callback.
            if now-self.last_accept.get(kind,-1e9)<.2:
                s['viewer_throttled']+=1;return
            s.pop('error',None)
            self.last_accept[kind]=now;self.messages[kind]=msg;self.received[kind]=now

    def _fresh(self,kind):
        m=self.messages.get(kind)
        if m is None:raise ValueError('stream unavailable')
        if self.clock()-self.received[kind]>2:raise ValueError('STREAM STALE')
        age=self.wall()-core.stamp(m)
        if age<-.25 or age>2:raise ValueError('source timestamp stale or clock mismatch')
        return m

    def status(self):
        with self.lock:
            streams={}
            for k in KINDS[:-1]:
                s=self.stats.get(k,{});m=self.messages.get(k);reason='No validated publication'
                try:self._fresh(k);state='ACTIVE'
                except ValueError as e:state='STALE' if m else 'UNAVAILABLE';reason=str(e)
                if s.get('error'):state='SENSOR ERROR';reason=s['error']
                ts=list(s.get('times',[]));fps=(len(ts)-1)/(ts[-1]-ts[0]) if len(ts)>1 and ts[-1]>ts[0] else None
                streams[k]={'state':state,'reason':reason if state!='ACTIVE' else '',
                            'topic':(self.manifest or {}).get('topics',{}).get(k),'fps_observed':fps,
                            'source_stamp':core.stamp(m) if m else None,'age_s':self.clock()-self.received[k] if m else None,
                            'source_age_s':self.wall()-core.stamp(m) if m else None,
                            'frame':m.header.frame_id if m else None,
                            'width':m.width if m else None,'height':m.height if m else None,
                            'encoding':getattr(m,'encoding','PointCloud2') if m else None,
                            **{a:s.get(a,0) for a in ('received','viewer_throttled','rejected','stamp_regressions','max_gap_s')}}
            return {'read_only':True,'recording':False,'driver_control':False,'error':self.error,
                    'configuration':'configured' if (self.manifest or {}).get('topics') else 'NOT CONFIGURED — live topic approval required',
                    'usb_verified':(self.manifest or {}).get('usb_verified',False),
                    'usb_note':'Inventory only; not a live USB/power monitor',
                    'modes':(self.manifest or {}).get('modes',[]),'mode_control':False,
                    'streams':streams,'depth_stats':self.cache.get('depth_stats'),
                    'dropped_messages':'Transport loss UNKNOWN; ROS2 Image has no sequence counter. Received gaps/throttling shown separately.',
                    'detections':'Existing Pi-camera detections are not registered to Astra; overlay unavailable',
                    'tf':'Camera-frame only. base_link extrinsics unverified; no navigation output.'}

    def frame(self,kind):
        if kind not in ('rgb','depth','ir'):raise ValueError('unknown image kind')
        with self.lock:
            m=self._fresh(kind);key=(kind,core.stamp(m))
            if self.cache.get(kind+'_key')!=key and self.clock()-self.cache_at.get(kind,-1e9)>=.5:
                png,stats=core.preview(m,kind);self.cache[kind]=png;self.cache[kind+'_key']=key
                self.cache[kind+'_message']=m
                self.cache[kind+'_stats']=stats;self.cache_at[kind]=self.clock()
            return self.cache[kind]

    def pixel(self,u,v,displayed_stamp=None):
        with self.lock:
            m=self._fresh('depth');info=self.messages.get('depth_info')
            if displayed_stamp is not None:
                m=self.cache.get('depth_message')
                if m is None or core.stamp(m)!=displayed_stamp:
                    raise ValueError('Displayed depth frame expired; click refreshed image')
                age=self.wall()-core.stamp(m)
                if age<-.25 or age>2:raise ValueError('Displayed depth frame stale')
            return core.measure(m,info,u,v)

    def cloud(self):
        with self.lock:
            m=self._fresh('cloud')
            if self.cache.get('cloud_key')!=core.stamp(m) and self.clock()-self.cache_at.get('cloud',-1e9)>=.5:
                c=core.cloud_points(m);c['shadow_obstacles']=core.obstacle_prototype(c['points'])
                self.cache['cloud']=c;self.cache['cloud_key']=core.stamp(m);self.cache_at['cloud']=self.clock()
            return self.cache['cloud']


SERVICE=VisionService()


def serve(handler,service=None):
    p=urlsplit(handler.path)
    if not p.path.startswith(API):return False
    svc=service or SERVICE
    def send(code,data,ctype='application/json',extra=None):
        body=data if isinstance(data,bytes) else json.dumps(data,allow_nan=False,separators=(',',':')).encode()
        handler.send_response(code);handler.send_header('Content-Type',ctype);handler.send_header('Cache-Control','no-store')
        handler.send_header('X-Content-Type-Options','nosniff');handler.send_header('Content-Length',str(len(body)))
        for k,v in (extra or {}).items():handler.send_header(k,v)
        handler.end_headers();handler.wfile.write(body)
    route=p.path[len(API):];q=parse_qs(p.query)
    if route not in ('status','frame','pixel','cloud'):send(404,{'error':'unknown read-only route'});return True
    try:
        svc.touch()
        if route=='status':send(200,svc.status())
        elif route=='frame':
            kind=q.get('kind',['depth'])[0]
            with svc.lock:
                body=svc.frame(kind)
                send(200,body,'image/png',{'X-Source-Stamp':str(svc.cache[kind+'_key'][1])})
        elif route=='pixel':send(200,svc.pixel(int(q['u'][0]),int(q['v'][0]),float(q['stamp'][0])))
        else:send(200,svc.cloud())
    except (ValueError,KeyError,IndexError) as e:send(409,{'error':str(e)})
    except Exception as e:send(503,{'error':'SENSOR ERROR: '+str(e)})
    return True

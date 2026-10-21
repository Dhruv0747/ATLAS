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
import atlas_vision3d_geometry as geometry

API='/api/vision3d/'
KINDS=('rgb','depth','ir','cloud','depth_info','rgb_info','ir_info')
TYPES={'rgb':'sensor_msgs/msg/Image','depth':'sensor_msgs/msg/Image','ir':'sensor_msgs/msg/Image',
       'cloud':'sensor_msgs/msg/PointCloud2','depth_info':'sensor_msgs/msg/CameraInfo','rgb_info':'sensor_msgs/msg/CameraInfo',
       'ir_info':'sensor_msgs/msg/CameraInfo'}
IR_ENCODINGS=('mono8','mono16','16UC1')   # native IR intensity only; anything else is rejected, never converted
DEPTH_RAW_ENCODINGS=('16UC1','32FC1')     # Stage32: native depth for the browser's UNCALIBRATED diagnostic 3D preview only
MODE_IDS=('depth','concurrent','ir','ir_depth','rgb_ir','depth_cloud')
MODE_STATES=('verified','untested','unsupported','needs_calibration')


def read_manifest():
    path=os.environ.get('ATLAS_VISION3D_MANIFEST')
    if not path:
        default=Path(__file__).resolve().parents[1]/'config/vision3d_live.json'
        if not default.exists():return {}
        path=default
    raw=Path(path).read_bytes()
    if len(raw)>8192: raise ValueError('manifest too large')
    m=json.loads(raw)
    if set(m)-{'topics','modes','usb_verified','identity','deployment_verified','viewer_runtime','mode_support'}: raise ValueError('unknown manifest field')
    support=m.get('mode_support',{})
    if not isinstance(support,dict) or set(support)-set(MODE_IDS): raise ValueError('unknown viewer mode in mode_support')
    for k,v in support.items():
        if not isinstance(v,dict) or v.get('state') not in MODE_STATES or not isinstance(v.get('note',''),str) or len(v.get('note',''))>300:
            raise ValueError('invalid mode_support entry: '+k)
    topics=m.get('topics',{})
    if set(topics)-set(KINDS): raise ValueError('unknown stream')
    for kind, topic in topics.items():
        if not isinstance(topic,str) or not topic.startswith('/') or len(topic)>200 or any(c.isspace() for c in topic):
            raise ValueError('invalid exact topic')
        if topic.startswith(('/cmd','/camera/','/yahboom/','/im10a/','/atlas/')):
            raise ValueError('production namespace forbidden')
    return m


class BridgeTransport:
    """Local existing bridge; subscribe/unsubscribe only, no new DDS participant."""
    def __init__(self):
        self.thread=None;self.ws=None;self.quit=threading.Event();self.error=''

    def start(self,topics,callback):
        import sys,hashlib,struct
        stage=Path('/home/jetson/project-atlas-migration/astra-20261021')
        wheel=stage/'websocket_client-1.9.0-py3-none-any.whl'
        if hashlib.sha256(wheel.read_bytes()).hexdigest()!='af248a825037ef591efbf6ed20cc5faa03d3b47b9e5a2230a529eeee1c1fc3ef':
            raise ValueError('verified private bridge dependency missing')
        if str(wheel) not in sys.path:sys.path.insert(0,str(wheel))
        import websocket
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
        classes={k:get_message(TYPES[k]) for k in topics}
        self.ws=websocket.create_connection('ws://127.0.0.1:8765',
            subprotocols=['foxglove.sdk.v1','foxglove.websocket.v1'],timeout=2,http_proxy_host=None)
        self.ws.settimeout(.25)
        def receive():
            subscriptions={};seen=set()
            try:
                while not self.quit.is_set():
                    try:frame=self.ws.recv()
                    except websocket.WebSocketTimeoutException:continue
                    if isinstance(frame,str):
                        data=json.loads(frame)
                        if data.get('op')!='advertise':continue
                        pending=[]
                        for channel in data.get('channels',[]):
                            for kind,topic in topics.items():
                                if channel.get('topic')!=topic:continue
                                if kind in seen:raise ValueError('duplicate camera channel')
                                if channel.get('encoding')!='cdr' or channel.get('schemaName')!=TYPES[kind]:
                                    raise ValueError('unverified camera channel schema')
                                sid=len(subscriptions)+1;subscriptions[sid]=kind;seen.add(kind)
                                pending.append({'id':sid,'channelId':channel['id']})
                        if pending:self.ws.send(json.dumps({'op':'subscribe','subscriptions':pending}))
                    elif isinstance(frame,bytes):
                        if not 13<=len(frame)<=core.MAX_BYTES+13:raise ValueError('camera wire budget exceeded')
                        opcode,sid,_=struct.unpack_from('<BIQ',frame)
                        if opcode!=1 or sid not in subscriptions:raise ValueError('unexpected bridge operation')
                        kind=subscriptions[sid];callback(kind,deserialize_message(frame[13:],classes[kind]))
                    else:raise ValueError('bridge disconnected')
            except Exception as e:self.error=str(e)
            finally:
                try:
                    if subscriptions:self.ws.send(json.dumps({'op':'unsubscribe','subscriptionIds':list(subscriptions)}))
                except Exception:pass
                self.ws.close()
        self.thread=threading.Thread(target=receive,name='vision3d-local-bridge',daemon=True);self.thread.start()

    def stop(self):
        self.quit.set()
        if self.thread:self.thread.join(timeout=2)
        if self.ws:self.ws.close()


class RosTransport:
    def __init__(self,domain_id=None):
        self.node=self.executor=self.context=self.thread=None;self.domain_id=domain_id

    def start(self,topics,callback):
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from sensor_msgs.msg import Image,CameraInfo,PointCloud2
        self.context=Context()
        if self.domain_id is None:rclpy.init(context=self.context)
        else:rclpy.init(context=self.context,domain_id=self.domain_id)  # private domain: invisible to production nodes
        self.node=rclpy.create_node('atlas_vision3d_readonly',context=self.context)
        self.executor=SingleThreadedExecutor(context=self.context); self.executor.add_node(self.node)
        qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.BEST_EFFORT,durability=DurabilityPolicy.VOLATILE)
        # Graph discovery verifies exact type before creating any subscriptions.
        subscribed=set()
        def discover():
            graph=dict(self.node.get_topic_names_and_types())
            for kind,topic in topics.items():
                if kind in subscribed or TYPES[kind] not in graph.get(topic,[]):continue
                typ=CameraInfo if kind.endswith('_info') else PointCloud2 if kind=='cloud' else Image
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


def viewer_transport():
    """Stage31: receive in the Astra driver's private domain. BridgeTransport is kept for rollback only: it needs the
    driver in the production domain, which is what caused the measured discovery CPU spike."""
    from atlas_vision3d_runtime import ISOLATED_DOMAIN_ID
    return RosTransport(domain_id=ISOLATED_DOMAIN_ID)


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
            if self.manifest.get('viewer_runtime'):
                from atlas_vision3d_runtime import SESSION
                SESSION.touch()
                if SESSION.status()['state']!='ACTIVE':return
            if not self.manifest.get('topics') or self.transport or self.clock()<self.retry_after:return
            try:
                t=viewer_transport() if self.manifest.get('viewer_runtime') else self.factory()
                t.start(self.manifest['topics'],self.ingest);self.transport=t
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
            if kind=='ir' and getattr(msg,'encoding','') not in IR_ENCODINGS:
                s['rejected']+=1;s['error']='IR encoding %s is not native intensity'%getattr(msg,'encoding','?');self.messages.pop(kind,None);return
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

    def _calibration(self):
        return geometry.calibration_state(self.manifest or {})

    def _mode_support(self,cal):
        out={}
        for k,v in (self.manifest or {}).get('mode_support',{}).items():
            v=dict(v)
            if v.get('state')=='needs_calibration':v['state']='untested' if cal['state']=='VALIDATED' else 'unsupported'
            out[k]=v
        return out

    def status(self):
        cal=self._calibration()
        with self.lock:
            streams={}
            for k in ('rgb','depth','ir','cloud'):
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
            runtime=None
            if (self.manifest or {}).get('viewer_runtime'):
                from atlas_vision3d_runtime import SESSION
                runtime=SESSION.status()
            return {'read_only':True,'recording':False,'driver_control':bool(runtime),'error':self.error or getattr(self.transport,'error',''),
                    'runtime':runtime,'calibration':'UNVALIDATED — axial Z reading, not verified accuracy; XYZ/cloud/registration DISABLED',
                    'camera_info':{k:{'frame':m.header.frame_id,'width':m.width,'height':m.height,'source_stamp':core.stamp(m),
                        'note':'Fallback metadata only; NOT admitted to metric geometry'} for k,m in self.messages.items() if k.endswith('_info')},
                    'mode_support':self._mode_support(cal),
                    'calibration_state':{'state':cal['state'],'reason':cal['reason']},
                    'configuration':'configured' if (self.manifest or {}).get('topics') else 'NOT CONFIGURED — live topic approval required',
                    'usb_verified':(self.manifest or {}).get('usb_verified',False),
                    'usb_note':'Inventory only; not a live USB/power monitor',
                    'modes':(self.manifest or {}).get('modes',[]),'mode_control':False,
                    'streams':streams,'depth_stats':self.cache.get('depth_stats'),
                    'dropped_messages':'Transport loss UNKNOWN; ROS2 Image has no sequence counter. Received gaps/throttling shown separately.',
                    'detections':'Existing Pi-camera detections are not registered to Astra; overlay unavailable',
                    'tf':'Camera-frame only. base_link extrinsics unverified; no navigation output.'}

    def summary(self):
        """Stage31 Home card: viewer state WITHOUT touching the viewer lease or starting a transport."""
        runtime=None
        try:
            if self.manifest is None:self.manifest=read_manifest()
            if (self.manifest or {}).get('viewer_runtime'):
                from atlas_vision3d_runtime import SESSION
                runtime=SESSION.status()
        except Exception as e:runtime={'state':'OFF','reason':'Vision Lab unavailable: '+str(e)}
        runtime=runtime or {'state':'OFF','reason':'viewer runtime not installed'}
        failed=runtime.get('failed_resources') or {}
        lim=runtime.get('limits') or {'cpu_percent':75,'ram_percent':80,'temperature_c':70}
        def fps(kind):
            with self.lock:
                ts=list(self.stats.get(kind,{}).get('times',[]))
            return (len(ts)-1)/(ts[-1]-ts[0]) if len(ts)>1 and ts[-1]>ts[0] and self.clock()-ts[-1]<2 else None
        cpu=failed.get('cpu')
        return {'state':str(runtime.get('state','OFF')),'reason':str(runtime.get('reason',''))[:300],
                'blocked_cpu_percent':cpu if isinstance(cpu,(int,float)) and cpu==cpu else None,
                'cpu_limit_percent':lim.get('cpu_percent'),'ram_limit_percent':lim.get('ram_percent'),
                'temperature_limit_c':lim.get('temperature_c'),'driver_stopped':bool(runtime.get('driver_stopped')),
                'mode':runtime.get('mode'),'depth_fps':fps('depth'),'rgb_fps':fps('rgb'),'ir_fps':fps('ir'),'cloud_fps':fps('cloud'),
                'calibration':'UNVALIDATED','read_only':True}

    def frame(self,kind):
        if kind not in ('rgb','depth','ir'):raise ValueError('unknown image kind')
        with self.lock:
            m=self._fresh(kind);key=(kind,core.stamp(m))
            if self.cache.get(kind+'_key')!=key and self.clock()-self.cache_at.get(kind,-1e9)>=.5:
                png,stats=core.preview(m,kind);self.cache[kind]=png;self.cache[kind+'_key']=key
                self.cache[kind+'_message']=m
                self.cache[kind+'_stats']=stats;self.cache_at[kind]=self.clock()
            return self.cache[kind]

    def raw(self,kind):
        """Stage32: native bytes, no server conversion. IR: browser-side display scaling. Depth: ONLY for the browser's
        UNCALIBRATED diagnostic 3D preview (nominal field of view). No metric XYZ, PointCloud2 or ROS output is produced
        here; calibrated geometry stays behind geometry.calibration_state (cloud(), pixel() xyz)."""
        if kind not in ('ir','depth'):raise ValueError('raw transfer is only offered for IR and depth')
        with self.lock:
            m=self._fresh(kind)
            if m.encoding not in (IR_ENCODINGS if kind=='ir' else DEPTH_RAW_ENCODINGS):
                raise ValueError('IR encoding not native intensity' if kind=='ir' else 'depth encoding not native (16UC1/32FC1)')
            headers={'X-Width':str(m.width),'X-Height':str(m.height),'X-Encoding':m.encoding,
                     'X-Step':str(m.step),'X-Bigendian':str(int(bool(m.is_bigendian))),
                     'X-Source-Stamp':str(core.stamp(m)),'X-Frame':m.header.frame_id}
            if kind=='depth':headers['X-Calibration']='UNCALIBRATED-DIAGNOSTIC-ONLY'
            return bytes(m.data),headers

    def pixel(self,u,v,displayed_stamp=None):
        with self.lock:
            m=self._fresh('depth');info=self.messages.get('depth_info')
            if (self.manifest or {}).get('viewer_runtime'):info=None
            if displayed_stamp is not None:
                m=self.cache.get('depth_message')
                if m is None or core.stamp(m)!=displayed_stamp:
                    raise ValueError('Displayed depth frame expired; click refreshed image')
                age=self.wall()-core.stamp(m)
                if age<-.25 or age>2:raise ValueError('Displayed depth frame stale')
            result=core.measure(m,info,u,v)
            cal=self._calibration()
            if cal['state']=='VALIDATED' and result['valid'] and (m.width,m.height,m.header.frame_id)==(cal['calibration']['width'],cal['calibration']['height'],cal['calibration']['frame_id']):
                c=cal['calibration'];x,y=geometry.undistort(u,v,c['k'],c['d']);z=result['depth_z_m']
                result.update(xyz_m=[x*z,y*z,z],range_m=(x*x*z*z+y*y*z*z+z*z)**.5,accuracy='Calibrated (validated file); see calibration report for measured error')
            else:
                result['accuracy']='UNVALIDATED — sensor axial Z, not calibrated physical accuracy'
                if result['valid']:result['xyz_unavailable_reason']='CALIBRATION BLOCKED: '+cal['reason']
            return result

    def cloud(self):
        with self.lock:
            cal=self._calibration()
            if cal['state']!='VALIDATED':raise ValueError('CALIBRATION BLOCKED: '+cal['reason'])
            m=self._fresh('cloud')
            if m.header.frame_id!=cal['calibration']['frame_id']:raise ValueError('cloud frame does not match the validated calibration')
            if self.cache.get('cloud_key')!=core.stamp(m) and self.clock()-self.cache_at.get('cloud',-1e9)>=.5:
                c=core.cloud_points(m);c['shadow_obstacles']=core.obstacle_prototype(c['points'])
                self.cache['cloud']=c;self.cache['cloud_key']=core.stamp(m);self.cache_at['cloud']=self.clock()
            return self.cache['cloud']


SERVICE=VisionService()


def serve(handler,service=None,post=False):
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
    if post:
        origin=urlsplit(handler.headers.get('Origin',''))
        if origin.scheme not in ('http','https') or origin.netloc!=handler.headers.get('Host') or handler.headers.get('X-Atlas-Vision3D')!='1':
            send(403,{'error':'same-origin viewer request required'});return True
        if route!='viewer':send(404,{'error':'unknown viewer route'});return True
        try:
            length=int(handler.headers.get('Content-Length','0'))
            if not 0<length<=256 or handler.headers.get_content_type()!='application/json':raise ValueError('invalid viewer request')
            payload=json.loads(handler.rfile.read(length))
            if svc.manifest is None:svc.manifest=read_manifest()
            if not svc.manifest.get('viewer_runtime'):raise ValueError('viewer runtime not installed')
            from atlas_vision3d_runtime import SESSION
            if payload=={'action':'stop'}:SESSION.stop();svc.stop()
            elif set(payload)=={'action','mode'} and payload['action']=='start':
                svc.stop();SESSION.start(payload['mode'])
            else:raise ValueError('only bounded viewer start/stop supported')
            send(202,SESSION.status())
        except (ValueError,KeyError) as e:send(409,{'error':str(e)})
        return True
    if route=='summary':   # Stage31: Home status card; never touches the viewer lease
        try:send(200,svc.summary())
        except Exception as e:send(503,{'error':'SENSOR ERROR: '+str(e)})
        return True
    if route not in ('status','frame','pixel','cloud','raw'):send(404,{'error':'unknown read-only route'});return True
    try:
        svc.touch()
        if route=='status':send(200,svc.status())
        elif route=='frame':
            kind=q.get('kind',['depth'])[0]
            with svc.lock:
                body=svc.frame(kind)
                send(200,body,'image/png',{'X-Source-Stamp':str(svc.cache[kind+'_key'][1])})
        elif route=='raw':
            body,headers=svc.raw(q.get('kind',['ir'])[0])
            send(200,body,'application/octet-stream',headers)
        elif route=='pixel':send(200,svc.pixel(int(q['u'][0]),int(q['v'][0]),float(q['stamp'][0])))
        else:send(200,svc.cloud())
    except (ValueError,KeyError,IndexError) as e:send(409,{'error':str(e)})
    except Exception as e:send(503,{'error':'SENSOR ERROR: '+str(e)})
    return True

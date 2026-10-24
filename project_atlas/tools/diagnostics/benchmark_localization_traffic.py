"""PC-only paced saved traffic + exact captured sensor callbacks, private domain.

This is dispatch/resource testing, not AMCL replay or localization qualification.
The input Stage19 bag is replay-derived. Missing command/policy traffic is synthetic.
"""
import argparse
import ast
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import threading
import time
import types
import benchmark_executor_counts as B
import benchmark_localization_executor as L

TOPICS = ('/scan', '/odom', '/amcl_pose', '/im10a/imu/bias_corrected_candidate', '/tf')


def window(path, offset, duration):
    if not 0 <= offset <= 240 or not 2 <= duration <= 15:
        raise ValueError('bounded window required')
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as c:
        start = c.execute('select min(timestamp) from messages').fetchone()[0]+int(offset*1e9)
        rows = c.execute('select t.name,t.type,m.timestamp,m.data from messages m '
                         'join topics t on m.topic_id=t.id where m.timestamp>=? and m.timestamp<? '
                         'order by m.timestamp,m.id', (start,start+int(duration*1e9))).fetchall()
        static = c.execute("select m.data from messages m join topics t on t.id=m.topic_id "
                           "where t.name='/tf_static' order by m.timestamp,m.id").fetchall()
    events = [((stamp-start)/1e9,topic,typ,bytes(raw)) for topic,typ,stamp,raw in rows if topic in TOPICS]
    if set(t for _,t,_,_ in events) != set(TOPICS):
        raise ValueError('missing recorded topic')
    return events, [bytes(row[0]) for row in static]


def callbacks(monitor, manual):
    if hashlib.sha256(monitor).hexdigest() != L.MONITOR_SHA or hashlib.sha256(manual).hexdigest() != L.MANUAL_SHA:
        raise ValueError('captured source hash mismatch')
    # Extract only the three exact callback methods: never construct production node.
    tree = ast.parse(monitor)
    cls = next(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and n.name=='Monitor')
    selected = [n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('on_scan','on_odom','on_amcl')]
    scripts=Path(__file__).resolve().parents[2]/'scripts'
    if (scripts/'atlas_localization_monitor.py').read_text()!=monitor.decode().replace('\r\n','\n'):
        raise ValueError('local monitor logic differs from captured source')
    sys.path.insert(0, str(scripts))
    import atlas_localization_monitor as logic
    env = dict(time=time, math=math, SCAN_WINDOW_S=logic.SCAN_WINDOW_S,
               PARKED_MPS=logic.PARKED_MPS, PARKED_RADPS=logic.PARKED_RADPS,
               yaw_of=lambda q: math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z)))
    exec(compile(ast.Module(body=selected,type_ignores=[]),'<captured-callbacks>','exec'),env)
    obj = types.SimpleNamespace(data_lock=threading.Lock(), scans=[], logic=logic.MonitorLogic())
    for name in ('on_scan','on_odom','on_amcl'): setattr(obj,name,types.MethodType(env[name],obj))
    scope = {}; exec(compile(manual,'<captured-manual>','exec'),scope)
    manual_obj = scope['ManualLocationCheck'].__new__(scope['ManualLocationCheck'])
    manual_obj.lock=threading.RLock();manual_obj.values={};manual_obj.motion_epoch=0;manual_obj.last_motion=0
    return obj,manual_obj


def run(module, events, static, duration, monitor, manual):
    import rclpy
    from rclpy.context import Context
    from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
    from rclpy.serialization import serialize_message,deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from tf2_ros import Buffer,TransformListener
    from tf2_msgs.msg import TFMessage
    from std_msgs.msg import String
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import OccupancyGrid
    from nav2_msgs.srv import SetInitialPose
    from std_srvs.srv import Trigger
    obj, manual_obj = callbacks(monitor,manual)
    ctx=Context();rclpy.init(context=ctx)
    node=rclpy.create_node('offline_localization_paced',context=ctx)
    publisher=rclpy.create_node('offline_localization_source',context=ctx)
    ex=module.SingleThreadedExecutor(context=ctx);ex.add_node(node)
    buffer=Buffer(node=node);listener=TransformListener(buffer,node)
    node.create_client(SetInitialPose,'/offline/set_initial_pose')
    node.create_publisher(String,'/offline/check',10)
    for label in ('start','cancel'):node.create_service(Trigger,'/offline/'+label,lambda req,resp:resp)
    node.create_subscription(OccupancyGrid,'/offline/map',lambda msg:None,
        QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
    expected=collections.Counter();seen=collections.Counter(); sent_at={};latency=[];errors=[];pubs={}
    all_events=list(events)
    # These two channels were absent from the saved bag; explicitly synthetic 10Hz.
    for i in range(int(duration*10)):
        all_events.extend([(i/10,'/atlas/control_policy','std_msgs/msg/String',serialize_message(String(data='{"stop_latched":true,"source":"STOPPED"}'))),
                           (i/10,'/cmd_vel','geometry_msgs/msg/Twist',serialize_message(Twist()))])
    all_events.sort(key=lambda e:e[0])
    sequence={}; received_seq=collections.Counter(); sent_seq=collections.Counter()
    for _,topic,typ,raw in all_events:
        # CDR padding is not a semantic field and may change on reserialization.
        sequence.setdefault(topic,[]).append(deserialize_message(raw,get_message(typ)))
    def receive(topic, channel, fn, msg):
        i=received_seq[channel];received_seq[channel]+=1
        if i>=len(sequence[topic]) or msg!=sequence[topic][i]:
            errors.append('payload/order mismatch '+channel)
        stamp=sent_at.get((topic,i))
        if stamp is None:errors.append('unpublished callback '+channel)
        else:latency.append((time.monotonic()-stamp)*1000)
        seen[channel]+=1
        if fn:fn(msg)
    for topic,typ in sorted({(t,typ) for _,t,typ,_ in all_events}):
        qos=qos_profile_sensor_data if topic in ('/scan','/im10a/imu/bias_corrected_candidate') else 10
        cls=get_message(typ);pubs[topic]=publisher.create_publisher(cls,topic,qos)
        fns={'/scan':[obj.on_scan],'/odom':[obj.on_odom,lambda msg:manual_obj.receive('odom',msg)],
             '/amcl_pose':[obj.on_amcl],'/im10a/imu/bias_corrected_candidate':[lambda msg:manual_obj.receive('imu',msg)],
             '/atlas/control_policy':[lambda msg:manual_obj.receive('policy',msg)],
             '/cmd_vel':[lambda msg:manual_obj.receive('cmd',msg)],'/tf':[None]}[topic]
        for j,fn in enumerate(fns):
            channel=topic+':'+str(j);expected[channel]=len(sequence[topic])
            node.create_subscription(cls,topic,lambda msg,t=topic,c=channel,f=fn:receive(t,c,f,msg),qos)
    static_pub=publisher.create_publisher(TFMessage,'/tf_static',QoSProfile(depth=100,durability=DurabilityPolicy.TRANSIENT_LOCAL))
    ticks=[0,0,0]; timer_delays=[[],[],[]]; timer_last=[time.monotonic()]*3
    for i,period in enumerate((.25,1.,.25)):
        def tick(i=i,period=period):
            now=time.monotonic();timer_delays[i].append(max(0,now-timer_last[i]-period)*1000);timer_last[i]=now;ticks[i]+=1
        node.create_timer(period,tick)
    thread=None;stop=threading.Event();publish_late=[]
    try:
        deadline=time.monotonic()+5
        while any(p.get_subscription_count()<(2 if t in ('/odom','/tf') else 1) for t,p in pubs.items()):
            if time.monotonic()>deadline:raise RuntimeError('discovery failed')
            ex.spin_once(timeout_sec=.01)
        for raw in static:static_pub.publish(raw)
        for _ in range(20):ex.spin_once(timeout_sec=.001)
        start=time.monotonic(); cpu=time.process_time();tcpu=time.thread_time()
        def send():
            try:
                for offset,topic,typ,raw in all_events:
                    if stop.wait(max(0,start+offset-time.monotonic())):return
                    i=sent_seq[topic];sent_seq[topic]+=1
                    sent_at[topic,i]=time.monotonic();publish_late.append(max(0,sent_at[topic,i]-start-offset)*1000)
                    pubs[topic].publish(raw)
            except Exception as exc:errors.append(repr(exc))
        thread=threading.Thread(target=send);thread.start()
        while time.monotonic()<start+duration or thread.is_alive() or seen!=expected:
            if time.monotonic()>start+duration+2:raise RuntimeError('delivery deadline '+str(seen-expected)+' '+str(expected-seen))
            if errors:raise RuntimeError(str(errors[:3]))
            # Match production rclpy.spin's blocking wait; do not invent a 200Hz poll.
            # Existing .25s timers ensure bounded wake-up after the sender finishes.
            ex.spin_once(timeout_sec=None)
        elapsed=time.monotonic()-start;cpu=time.process_time()-cpu;tcpu=time.thread_time()-tcpu
        # Verify actual TF listener ingestion at each dynamic edge's last recorded stamp.
        latest={}
        for _,topic,_,raw in events:
            if topic=='/tf':
                for tf in deserialize_message(raw,TFMessage).transforms:latest[tf.header.frame_id,tf.child_frame_id]=tf
        from rclpy.time import Time
        tf_ok=all(buffer.can_transform(a,b,Time.from_msg(tf.header.stamp)) for (a,b),tf in latest.items())
        if not tf_ok:raise RuntimeError('TF buffer did not retain latest transforms')
        return dict(cpu_s=cpu,executor_thread_cpu_s=tcpu,wall_s=elapsed,received=dict(seen),expected=dict(expected),
                    tf_edges_verified=len(latest),latency_p95_ms=sorted(latency)[int(.95*(len(latency)-1))],
                    latency_max_ms=max(latency),publish_lateness_max_ms=max(publish_late),timer_counts=ticks,
                    timer_lateness_max_ms=max([v for values in timer_delays for v in values],default=0),errors=errors)
    finally:
        stop.set()
        if thread:thread.join(timeout=2)
        assert not thread or not thread.is_alive()
        assert ex.shutdown(timeout_sec=1)
        listener.unregister();node.destroy_node();publisher.destroy_node();ctx.shutdown()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('bag','monitor','manual','executor'):p.add_argument(name,type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--offset',type=float,default=10)
    p.add_argument('--duration',type=float,default=6);p.add_argument('--pairs',type=int,default=4)
    a=p.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY')!='1' or os.environ.get('ROS_DOMAIN_ID')!='213':raise RuntimeError('PC localhost domain213 required')
    if not 2<=a.pairs<=8:raise ValueError('bounded pairs required')
    events,static=window(a.bag,a.offset,a.duration);raw=a.executor.read_bytes();B.candidate(raw)
    modules={'original':B.load_executor(raw.decode(),'paced_original'),
             'candidate':B.load_executor(B.cancellation_candidate(raw,True),'paced_candidate')}
    rows=[];savings=[];thread_savings=[]
    for pair in range(a.pairs):
        for name in (('original','candidate') if pair%2==0 else ('candidate','original')):
            row=dict(pair=pair,variant=name,**run(modules[name],events,static,a.duration,a.monitor.read_bytes(),a.manual.read_bytes()))
            rows.append(row);print(json.dumps(row),flush=True)
        q={r['variant']:r for r in rows if r['pair']==pair}
        savings.append(100*(1-q['candidate']['cpu_s']/q['original']['cpu_s']))
        thread_savings.append(100*(1-q['candidate']['executor_thread_cpu_s']/q['original']['executor_thread_cpu_s']))
    result=dict(rows=rows,paired_savings_percent=savings,median_savings_percent=statistics.median(savings),
                paired_thread_savings_percent=thread_savings,median_thread_savings_percent=statistics.median(thread_savings),
                source_bag_sha256=hashlib.sha256(a.bag.read_bytes()).hexdigest(),offset=a.offset,duration=a.duration,
                recorded_counts=dict(collections.Counter(t for _,t,_,_ in events)),
                installed=False,scope='PC paced dispatch; no search/disk status writing/AMCL qualification')
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='rows'}))


if __name__=='__main__':main()

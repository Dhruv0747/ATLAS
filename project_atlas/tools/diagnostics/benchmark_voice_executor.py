"""PC localhost-only native ROS workload from hash-verified voice declarations.

Exercises the actual entity types/QoS/timer periods, not audio hardware or AI.
Never imports/constructs AtlasVoice or connects to ATLAS.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
import benchmark_executor_counts as B

VOICE_SHA='37f275ddb5e259466b909b0da2654fdaaf8a06b06cf02d969813c8affc0c2f72'

def inventory(raw):
    if hashlib.sha256(raw).hexdigest()!=VOICE_SHA:
        raise ValueError('exact live voice source required')
    cls=next(x for x in ast.parse(raw).body if isinstance(x,ast.ClassDef) and x.name=='AtlasVoice')
    init=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='__init__')
    names={'create_publisher','create_subscription','create_timer'}
    selected=[s for s in init.body if any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute)
              and x.func.attr in names for x in ast.walk(s))]
    class Collector:
        def __init__(self): self._subs=[];self._pubs=[];self._timers=[];self.rover={}
        def __getattr__(self,name): return lambda *args:None
        def create_subscription(self,typ,topic,cb,qos,**kw): self._subs.append((typ,topic,qos,kw.get('raw',False)))
        def create_publisher(self,typ,topic,qos): self._pubs.append((typ,topic,qos))
        def create_timer(self,period,cb): self._timers.append(period)
    c=Collector()
    env={k:k for k in ('Bool','Empty','Float32','Int32','String','Twist','NavSatFix','LaserScan','Imu')}
    env.update(self=c,qos_profile_sensor_data='sensor')
    exec(compile(ast.Module(body=selected,type_ignores=[]),'<offline-voice-declarations>','exec'),env)
    return {'subscriptions':c._subs,'publishers':c._pubs,'timers':c._timers}

def patch_voice(raw):
    inventory(raw)
    source=raw.decode()
    old='        rclpy.spin(node)'
    if source.count(old)!=1 or source.count('import rclpy\n')!=1:
        raise ValueError('ambiguous spin/import')
    patched=source.replace('import rclpy\n','import rclpy\nfrom atlas_dashboard_executor import spin as _atlas_voice_spin\n').replace(old,'        _atlas_voice_spin(node)')
    compile(patched,'<offline-voice-candidate>','exec')
    return patched.encode()

def prepare(raw,output):
    patched=patch_voice(raw)
    output.mkdir(exist_ok=False)
    (output/'atlas_voice_companion.py').write_bytes(patched)
    (output/'atlas_voice_companion.original').write_bytes(raw)
    manifest={'installed':False,'baseline_sha256':VOICE_SHA,
        'candidate_sha256':hashlib.sha256(patched).hexdigest(),
        'required_existing_files':{
          'atlas_dashboard_executor.py':'2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab',
          'atlas_dashboard_executor_impl.py':'543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1'},
        'approval_required':'No deployment/restart authorized; later voice-only restart needs explicit approval.'}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

def run(module,inv,rounds):
    import rclpy
    from rclpy.context import Context
    from rclpy.qos import qos_profile_sensor_data
    from std_msgs import msg as std
    from sensor_msgs import msg as sensor
    from geometry_msgs import msg as geom
    types={k:getattr(m,k) for m,ks in [(std,['Bool','Empty','Float32','Int32','String']),
        (sensor,['NavSatFix','LaserScan','Imu']),(geom,['Twist'])] for k in ks}
    ctx=Context();rclpy.init(context=ctx)
    node=rclpy.create_node('offline_voice_entities',context=ctx)
    ex=module.SingleThreadedExecutor(context=ctx);ex.add_node(node)
    pending={};seen=[];latency=[];timers=[0]*len(inv['timers']);errors=[]
    def receive(i,raw,msg):
        if raw and not isinstance(msg,bytes):errors.append('raw payload type changed')
        if i not in pending:errors.append('duplicate/unexpected');return
        latency.append((time.monotonic_ns()-pending.pop(i))/1e6);seen.append(i)
    try:
        # Outbound voice publishers retained as entities but never command anything.
        for i,(typ,topic,qos) in enumerate(inv['publishers']):node.create_publisher(types[typ],'/offline/out_'+str(i),qos)
        pubs=[];messages=[]
        for i,(typ,topic,qos,raw) in enumerate(inv['subscriptions']):
            q=qos_profile_sensor_data if qos=='sensor' else qos
            node.create_subscription(types[typ],'/offline/in_'+str(i),lambda m,i=i,r=raw:receive(i,r,m),q,raw=raw)
            pubs.append(node.create_publisher(types[typ],'/offline/in_'+str(i),q))
            m=types[typ]()
            if typ=='String':m.data=json.dumps({'state':'READY','stop_latched':True})
            if typ=='LaserScan':m.ranges=[1.0]*360
            messages.append(m)
        for i,period in enumerate(inv['timers']):
            node.create_timer(period,lambda i=i:timers.__setitem__(i,timers[i]+1))
        deadline=time.monotonic()+5
        while not all(p.get_subscription_count()==1 for p in pubs):
            if time.monotonic()>deadline:raise RuntimeError('discovery timeout')
            ex.spin_once(timeout_sec=.01)
        start=time.process_time();wall=time.monotonic()
        for _ in range(rounds):
            for i,(pub,m) in enumerate(zip(pubs,messages)):
                pending[i]=time.monotonic_ns();pub.publish(m)
            end=time.monotonic()+2
            while pending:
                if time.monotonic()>end:raise RuntimeError('missing message')
                ex.spin_once(timeout_sec=.01)
        cpu=time.process_time()-start;elapsed=time.monotonic()-wall
        ordered=sorted(latency)
        return dict(cpu_s=cpu,wall_s=elapsed,sent=rounds*len(pubs),received=len(seen),errors=errors,
            raw_channels=sum(x[3] for x in inv['subscriptions']),timers=timers,
            latency_max_ms=max(latency),latency_p95_ms=ordered[int(.95*(len(ordered)-1))])
    finally:
        assert ex.shutdown(timeout_sec=1)
        node.destroy_node();ctx.shutdown()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('voice',type=Path);p.add_argument('executor',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--pairs',type=int,default=10);p.add_argument('--rounds',type=int,default=1000)
    p.add_argument('--prepare-only',action='store_true')
    a=p.parse_args()
    if a.prepare_only:
        print(json.dumps(prepare(a.voice.read_bytes(),a.output),indent=2));return
    if os.environ.get('ROS_LOCALHOST_ONLY')!='1' or os.environ.get('ROS_DOMAIN_ID')!='213':raise RuntimeError('isolated PC domain213 required')
    if not 2<=a.pairs<=10 or not 10<=a.rounds<=2000:raise ValueError('bounded workload required')
    inv=inventory(a.voice.read_bytes());raw=a.executor.read_bytes()
    B.candidate(raw) # verify baseline hash
    modules={'original':B.load_executor(raw.decode(),'voice_original'),
             'candidate':B.load_executor(B.cancellation_candidate(raw,True),'voice_candidate')}
    rows=[];savings=[]
    for pair in range(a.pairs):
        for name in (['original','candidate'] if pair%2==0 else ['candidate','original']):
            row=dict(pair=pair,variant=name,**run(modules[name],inv,a.rounds));rows.append(row);print(json.dumps(row),flush=True)
        q={r['variant']:r for r in rows if r['pair']==pair}
        savings.append(100*(1-q['candidate']['cpu_s']/q['original']['cpu_s']))
    result=dict(inventory=inv,rows=rows,paired_savings_percent=savings,median_saving_percent=statistics.median(savings))
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'savings':savings,'median':statistics.median(savings)}))

if __name__=='__main__':main()

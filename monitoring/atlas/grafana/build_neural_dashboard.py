"""Separate, read-only dashboard. No ROS subscriptions or exporter changes."""
import json
from pathlib import Path
from build_dashboard import panel, row

from neural_queries import guarded, nodes_query, edges_query, TOPOLOGY
DS={'type':'prometheus','uid':'atlas-prom'}

def graph():
    return {'id':900,'type':'nodeGraph','title':'ATLAS LIVE NEURAL DATA FLOW','datasource':DS,
      'description':'Select a node or connection for evidence and history. Green means fresh measured cache traffic, not actuator permission. Grey edges are unverified or unavailable. No synthetic packet animation. Zoom out twice for overview; pan/zoom to inspect. Full source evidence is in the topology notes below.',
      'gridPos':{'x':0,'y':5,'w':24,'h':18},
      'targets':[{'refId':ref,'expr':expr,'format':'table','instant':True,'range':False,'datasource':DS} for ref,expr in [('nodes',nodes_query()),('edges',edges_query())]],
      'transformations':[{'id':'organize','filter':{'id':'byRefId','options':ref},'options':{'excludeByName':{'Time':True},'renameByName':{'Value':'mainstat'}}} for ref in ('nodes','edges')],
      'fieldConfig':{'defaults':{'noValue':'UNAVAILABLE'},'overrides':[{'matcher':{'id':'byName','options':'id'},'properties':[{'id':'links','value':[{'title':'Topic diagnostics and history','url':'/d/atlas-live-neural-data-flow/atlas-live-neural-data-flow?var-topic=${__data.fields.detail__topic}&from=${__from}&to=${__to}&viewPanel=2','targetBlank':True},{'title':'ATLAS Health Monitor','url':'/d/atlas-health-monitor/atlas-health-monitor?from=${__from}&to=${__to}','targetBlank':True}]}]},
        {'matcher':{'id':'byName','options':'detail__evidence'},'properties':[{'id':'displayName','value':'Evidence'}]},
        *[{'matcher':{'id':'byName','options':field},'properties':[{'id':'displayName','value':name}]} for field,name in [('detail__topic','Topic'),('subtitle','Scope'),('secondarystat','State')]]]},
      'options':{'nodes':{'mainStatUnit':'short'},'edges':{'mainStatUnit':'hertz'}}}

def build():
    panels=[{'id':1000,'type':'text','title':'Evidence and topology','gridPos':{'x':0,'y':0,'w':24,'h':5},'options':{'mode':'markdown','content':'Read-only observation, not robot control. Topic rates are cached receiver observations, not proof of each connection. Graph colors reflect measured freshness; unmeasured connections remain grey. Missing metrics mean UNAVAILABLE. Windows is optional; all robot operation remains on Jetson.'}}]
    groups=[('Jetson CPU/GPU',['atlas_cpu_utilization_percent','atlas_gpu_load_percent']),('Observed ROS topic traffic',['atlas_topic_rate_hz{topic=~"$topic"}']),('Topic freshness',['atlas_topic_age_seconds{topic=~"$topic"}']),('Topic stale flags',['atlas_topic_stale']),('Source availability',['atlas_source_available']),('Service state',['atlas_service_active']),('FlySky / Xbox',['atlas_flysky_frame_age_seconds','atlas_control_selected']),('MCU encoder faults',['atlas_encoder_faults'])]
    for i,(title,exprs) in enumerate(groups):
        p=panel('timeseries',title,[guarded(e) for e in exprs],(i%2)*12,23+(i//2)*7,12,7,legend=exprs)
        p['id']=i+1;p['fieldConfig']['defaults']['links']=[{'title':'ATLAS health history','url':'/d/atlas-health-monitor/atlas-health-monitor?from=${__from}&to=${__to}','targetBlank':True}]
        panels.append(p)
    panels.append({'id':1001,'type':'text','title':'Connections pending verification','gridPos':{'x':0,'y':51,'w':24,'h':7},'options':{'mode':'markdown','content':'Topology candidate: Astra RGB/depth → AI detection / RGB-D mapping; CSI → camera preview; LiDAR + IMU + STM32 wheel odometry → EKF / SLAM / AMCL / Nav2; ultrasonic + radar + UNO R4 → sensor diagnostics; FlySky / Xbox → command arbitration. Only the eight explicitly evidenced cache-receipt edges can show measured traffic. Other relationships remain UNVERIFIED; receipt at the cache does not prove delivery to downstream consumers. No raw camera subscriptions, actuator commands or fabricated zero-rate edges. Calibrated mapping remains unverified.\n\n'+ '\n'.join('- **'+e['id']+'**: '+e['evidence'] for e in TOPOLOGY['edges'])}})
    panels.insert(1,graph())
    return {'templating':{'list':[{'name':'topic','type':'custom','query':','.join(['unmeasured']+[e['topic'] for e in TOPOLOGY['edges'] if e['topic']]),'current':{'text':'All','value':'$__all'},'includeAll':True,'allValue':'.*','multi':False}]},'uid':'atlas-live-neural-data-flow','title':'ATLAS LIVE NEURAL DATA FLOW','schemaVersion':41,'version':1,'refresh':'30s','time':{'from':'now-15m','to':'now'},'panels':panels,'tags':['atlas','read-only','cached-traffic']}
if __name__=='__main__':
    (Path(__file__).parent/'dashboards/atlas-neural.json').write_text(json.dumps(build(),indent=2)+'\n')

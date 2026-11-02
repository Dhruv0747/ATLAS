"""Pure PromQL generation: cached observations only, no new runtime process."""
import json
from pathlib import Path
TOPOLOGY=json.loads(Path(__file__).with_name('neural_topology.json').read_text())
S='job="atlas-jetson",instance="192.168.1.16:9118"'
def metric(name,topic=None):
    return name+'{'+S+(' ,topic='+json.dumps(topic) if topic else '')+'}'
OBS=metric('atlas_exporter_observed_timestamp_seconds')
FRESH='(('+metric('up')+' == 1) and on(job,instance) ((time() - '+OBS+' >= 0) and (time() - '+OBS+' < 30)))'
def guarded(expr):return '('+expr+') and on(job,instance) '+FRESH

def labels(expr,values):
    for name,value in values.items():
        expr='label_replace(('+expr+'),'+json.dumps(name)+','+json.dumps(value)+',"__name__",".*")'
    return expr

def edge_query(e):
    common={k:e[k] for k in ('id','source','target')}
    common.update(detail__topic=e['topic'] or 'unmeasured',detail__evidence='Audited receipt' if e['verified'] else 'Unverified link')
    def state(expr,status,color):return labels(expr,dict(common,secondarystat=status,color=color))
    if not e['verified']:return state('vector(0/0)','UNVERIFIED','#8e8e93')
    topic=e['topic'];rate=metric('atlas_topic_rate_hz',topic);age=metric('atlas_topic_age_seconds',topic)
    # Age advances since collection: stale data cannot remain green in Prometheus lookback.
    effective='('+age+' + on(job,instance) group_left() (time() - '+OBS+'))'
    present='('+metric('atlas_topic_available',topic)+' == 1)'
    known=guarded('('+rate+' >= 0) and on(job,instance,topic) '+present)
    fresh='('+known+') and on(job,instance,topic) ('+effective+' <= '+str(e['limit'])+') and on(job,instance,topic) ('+age+' >= 0)'
    traffic='('+fresh+') > 0'
    idle='('+fresh+') == 0'
    stale='('+known+') and on(job,instance,topic) ('+effective+' > '+str(e['limit'])+')'
    available='('+traffic+') or ('+idle+') or ('+stale+')'
    unavailable='vector(0/0) unless on() ('+available+')'
    return ' or '.join([state(traffic,'FRESH OBSERVED','#32c48d'),state(idle,'IDLE','#5794f2'),state(stale,'STALE','#ffb357'),state(unavailable,'UNAVAILABLE','#8e8e93')])

def nodes_query():
    return ' or '.join(labels('vector(0/0)',dict(id=n['id'],title=n['title'],subtitle='Component — inspect edges',color='#5794f2',detail__topic='unmeasured',detail__evidence='Topology only')) for n in TOPOLOGY['nodes'])
def edges_query():return ' or '.join('('+edge_query(e)+')' for e in TOPOLOGY['edges'])

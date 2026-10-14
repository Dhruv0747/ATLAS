"""Installer-only, fail-closed resource evidence; public collector is unchanged."""
import json
import math
import urllib.request
from stage20_public_preflight import validate
from stage20_resource_probe import sample_window,utc

LIMITS={'cpu_percent':75.0,'ram_percent':80.0,'temperature_c':70.0,'free_disk_bytes':2*1024**3}


class AdmissionRefused(ValueError):
    def __init__(self,decision):
        self.decision=decision
        super().__init__('resource/safety admission refused: '+ '; '.join(decision['reasons']))


def decide(measured,status,phase,installation_begun):
    reasons=[]
    def number(value):
        try:
            value=float(value)
            return value if math.isfinite(value) else None
        except (TypeError,ValueError):return None
    samples=measured.get('cpu_samples',[])
    if len(samples)!=5:reasons.append('five consecutive CPU intervals required')
    for i,sample in enumerate(samples):
        cpu=number(sample.get('utilization_percent',{}).get('cpu'))
        duration=number(sample.get('duration_s'))
        if duration is None or not 0.9<=duration<=2.0:
            reasons.append('CPU interval %s has invalid/delayed duration %s'%(i,duration))
        if cpu is None or not 0<=cpu<=100:reasons.append('CPU interval %s unavailable/invalid'%i)
        elif cpu>LIMITS['cpu_percent']:
            reasons.append('CPU interval %s: %.6f%% > 75%%'%(i,cpu))
    for key in ('ram_percent','temperature_c','free_disk_bytes'):
        value=number(measured.get(key));limit=LIMITS[key]
        invalid=value is None or value<0 or (key=='ram_percent' and value>100)
        if invalid:reasons.append(key+' unavailable/invalid')
        elif (value<limit if key=='free_disk_bytes' else value>limit):
            reasons.append('%s: %s %s %s'%(key,value,'<' if key=='free_disk_bytes' else '>',limit))
    system=status.get('system',{})
    dashboard={'cpu_percent':system.get('cpu_percent'),'ram_percent':system.get('ram_percent'),
               'temp':system.get('temp'),'method':'existing dashboard cached /proc delta; sample duration not exposed'}
    # Preserve original safety and resource guard as an additional check, never replace it
    # with an averaged lower CPU value. Dashboard high readings remain refusals too.
    for key in ('cpu_percent','ram_percent'):
        value=number(system.get(key))
        if value is not None and value>LIMITS[key]:reasons.append('dashboard %s: %s > %s'%(key,value,LIMITS[key]))
    try:validate(status)
    except (KeyError,TypeError,ValueError,OverflowError) as exc:reasons.append('existing dashboard/safety guard: '+str(exc))
    return {'timestamp':utc(),'phase':phase,'installation_begun':installation_begun,
            'rollback_required':bool(installation_begun and reasons),
            'allowed':not reasons,'reasons':reasons,'thresholds':dict(LIMITS),
            'policy':'all five 1s intervals AND existing dashboard guard must pass; no retry or spike dismissal',
            'measured':measured,'dashboard':dashboard,
            'safety':{name:status.get('ros',{}).get(name) for name in ('control_policy','cmd_vel')}}


def check(root,phase,installation_begun,emit,*,sampler=sample_window,fetch=None):
    measured={};status={}
    try:
        measured=sampler(root,seconds=5)
        if fetch is not None:status=fetch()
        else:
            with urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=2) as response:
                raw=response.read(2*1024*1024+1)
                if len(raw)>2*1024*1024:raise ValueError('oversized status response')
            status=json.loads(raw)
        if not isinstance(status,dict):raise ValueError('status response is not an object')
        decision=decide(measured,status,phase,installation_begun)
    except Exception as exc:
        decision={'timestamp':utc(),'phase':phase,'installation_begun':installation_begun,
                  'rollback_required':bool(installation_begun),'allowed':False,'thresholds':dict(LIMITS),
                  'reasons':['measurement failed: '+type(exc).__name__+': '+str(exc)],
                  'measured':measured,'dashboard':status.get('system',{}) if isinstance(status,dict) else {'invalid_type':type(status).__name__}}
    emit('resource_decision',decision=decision) # Persist rejected values BEFORE raising.
    if not decision['allowed']:raise AdmissionRefused(decision)
    return decision

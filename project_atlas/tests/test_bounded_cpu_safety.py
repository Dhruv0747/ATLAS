import copy,json,time
import pytest
from test_bounded_process_cpu import safe
import bounded_process_cpu as p

class Clock:
 def __init__(self):self.t=0.
 def now(self):return self.t
 def sleep(self,n):self.t+=n

def simulate(tmp_path,monkeypatch,fail=None,resource=None):
 clock=Clock();monkeypatch.setattr(p.time,'monotonic',clock.now);monkeypatch.setattr(p.time,'sleep',clock.sleep)
 count=[0];polls=[]
 def collect():
  count[0]+=1;i=count[0]
  return {'cpu':[60*i,0,0,40*i,0,0,0,0],'cpu_started':clock.t,'errors':[],'processes':{},'groups':{}}
 def safety():
  polls.append(clock.t)
  if clock.t>=5 and fail:return fail()
  return safe()
 monkeypatch.setattr(p,'read',lambda _: 'MemTotal: 100 kB\nMemAvailable: 90 kB\n')
 path=tmp_path/'capture.jsonl'
 def run():
  return p.run(path,15,collect=collect,safety_reader=safety,thermal_reader=lambda:{'thermal_zones_c':{'cpu':resource if resource is not None and clock.t>=5 else 50}})
 return run,path,count,polls,clock

def modified(field,value):
 d=safe()
 if field=='estop':d['ros']['control_policy']['value']['stop_latched']=value
 elif field=='command':d['ros']['cmd_vel']['value']['ang']=value
 elif field=='telemetry':d['ros']['encoder_health']['value']['packet_age_s']=value
 elif field=='missing':d={}
 elif field=='mode':d['ros']['control_policy']['value']['manual_only']=value
 elif field=='link':d['ros']['encoder_health']['value']['link_state']=value
 return d

@pytest.mark.parametrize('field,value',[('estop',False),('command',0.1),('telemetry',1.1),('missing',None),('mode',False),('link','STALE')])
def test_midcapture_failure_stops_before_more_collection(tmp_path,monkeypatch,field,value):
 run,path,count,polls,clock=simulate(tmp_path,monkeypatch,lambda:modified(field,value))
 with pytest.raises(ValueError,match='safety'):run()
 rows=[json.loads(l) for l in path.read_text().splitlines()]
 assert count[0]==5 and clock.t==5
 assert rows[-1]['kind']=='aborted'
 assert any(r['kind']=='safety' and r['observation']['failed_predicates'] for r in rows)
 assert not any(r['kind']=='complete' for r in rows)

@pytest.mark.parametrize('error',[TimeoutError, json.JSONDecodeError])
def test_api_failure_during_capture(tmp_path,monkeypatch,error):
 def fail():
  if error is json.JSONDecodeError:raise error('malformed','',0)
  raise error('private exception text')
 run,path,count,polls,clock=simulate(tmp_path,monkeypatch,fail)
 with pytest.raises(ValueError):run()
 assert count[0]==5 and 'private exception' not in path.read_text()
 assert 'safety_error' in path.read_text()

@pytest.mark.parametrize('temp',[70,70.01])
def test_temperature_boundary_during_capture(tmp_path,monkeypatch,temp):
 run,path,count,polls,clock=simulate(tmp_path,monkeypatch,resource=temp)
 with pytest.raises(ValueError,match='resource'):run()
 assert '"failed": ["temperature"]' in path.read_text() and clock.t==5

def test_full_15_seconds(tmp_path,monkeypatch):
 run,path,count,polls,clock=simulate(tmp_path,monkeypatch)
 digest=run();rows=[json.loads(l) for l in path.read_text().splitlines()]
 assert len(digest)==64 and clock.t==15
 assert count[0]==16 and len(polls)==32
 assert max(b-a for a,b in zip(polls,polls[1:]))<=1
 assert len([r for r in rows if r['kind']=='resources'])==15
 assert rows[-1]['kind']=='complete'

def test_effective_age_accounts_for_response_delay():
 d=safe();d['ros']['encoder_health']['age']=0.9
 assert 'encoder_health.effective_freshness' in p.safety_check(d,0.2)['failed_predicates']

def test_watchdog_interrupts_blocked_request():
 started=time.monotonic()
 with pytest.raises(TimeoutError):
  with p.bounded_cycle():time.sleep(2)
 assert time.monotonic()-started<1.25

def test_bounded_fetch_timeout_and_size(monkeypatch):
 class Response:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def read(self,n):return b'x'*n
 class Opener:
  def open(self,url,timeout):
   assert url=='http://127.0.0.1:8088/api/status' and timeout==0.25
   return Response()
 monkeypatch.setattr(p.urllib.request,'build_opener',lambda *a:Opener())
 with pytest.raises(ValueError,match='size'):p.fetch_safety()

@pytest.mark.parametrize('kind',['cpu','ram'])
def test_cpu_ram_rejection_during_capture(tmp_path,monkeypatch,kind):
 run,path,count,polls,clock=simulate(tmp_path,monkeypatch)
 original=p.resource_check
 def resource(cpu,mem,thermal):
  if clock.t>=5:
   if kind=='cpu':cpu=75.001
   else:mem={'MemTotal':100,'MemAvailable':19}
  return original(cpu,mem,thermal)
 monkeypatch.setattr(p,'resource_check',resource)
 with pytest.raises(ValueError,match='resource'):run()
 assert clock.t==5
 rows=[json.loads(l) for l in path.read_text().splitlines()]
 assert rows[-1]['kind']=='aborted'
 assert next(r for r in reversed(rows) if r['kind']=='resources')['observation']['failed']==[kind]

@pytest.mark.parametrize('bad',[None,True,'0',float('nan'),-1])
def test_invalid_telemetry_age_denied(bad):
 d=safe();d['ros']['encoder_health']['value']['packet_age_s']=bad
 assert p.safety_check(d,0)['failed_predicates']

def test_body_timeout_clean_abort(tmp_path):
 def stalled():time.sleep(2)
 started=time.monotonic()
 with pytest.raises(ValueError,match='safety request'):
  p.run(tmp_path/'out',15,safety_reader=stalled,thermal_reader=lambda:{})
 assert time.monotonic()-started<1.25
 rows=[json.loads(l) for l in (tmp_path/'out').read_text().splitlines()]
 assert rows[-1]['kind']=='aborted'
 assert any(r['kind']=='safety_error' and r['error_type']=='TimeoutError' for r in rows)
 assert not any(r['kind']=='baseline' for r in rows)

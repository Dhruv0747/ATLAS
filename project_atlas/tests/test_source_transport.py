import sys,json,struct
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/vision3d'),str(ROOT/'tests')]
from local_bridge_observer import SafetyTransport
from existing_safety_snapshot import Consumer
from test_source_provenance import evidence

def frame(sid,payload,bridge=999999999999999999):
 raw=json.dumps(payload).encode()+b'\0'
 return struct.pack('<BIQ',1,sid,bridge)+b'\0\1\0\0'+struct.pack('<I',len(raw))+raw

def ready(tmp_path):
 t=SafetyTransport(tmp_path/'state.json','b',{'policy':('b',1,2),'encoders':('b',3,4)})
 channels=[dict(topic=n,id=i,encoding='cdr',schemaName='std_msgs/msg/String') for i,n in enumerate(['/atlas/control_policy','/atlas/encoder_health','/astra/depth/image_raw'],1)]
 request=json.loads(t.text(json.dumps(dict(op='advertise',channels=channels))))
 assert len(request['subscriptions'])==2
 return t

def test_source_times_survive_to_existing_supervisor_consumer(tmp_path):
 t=ready(tmp_path);p,e=evidence();t.binary(frame(1,p),10.1);t.binary(frame(2,e),10.1);t.emit(10.2)
 raw=json.loads(t.path.read_text());assert raw['observations']['policy'][1]==10
 assert raw['observations']['policy'][0]['source_provenance']==p['source_provenance']
 assert raw['observations']['command']==[p['published_command']['values'],10]
 assert Consumer(t.path,'b').check(10.3)['safe']
 t.close();assert not t.path.exists()
 with pytest.raises(ValueError):t.consumer.check(10.3,10.2)

@pytest.mark.parametrize('case',['buffered','future','wrongboot','nonzero','badcdr','unknown','duplicate'])
def test_transport_rejects_bad_evidence(tmp_path,case):
 t=ready(tmp_path);p,e=evidence()
 if case=='buffered':p['source_provenance']['observed_mono']=8
 if case=='future':p['source_provenance']['observed_mono']=11
 if case=='wrongboot':p['source_provenance']['boot_id']='old'
 if case=='nonzero':p['published_command']['values'][4]=1
 with pytest.raises(ValueError):
  if case=='badcdr':t.binary(frame(1,p)[:-1],10.1)
  elif case=='unknown':t.binary(frame(9,p),10.1)
  else:
   t.binary(frame(1,p),10.1);t.binary(frame(2,e),10.1)
   if case=='duplicate':t.binary(frame(1,p),10.1)
   t.emit(10.1)
 t.close();assert not t.path.exists()

def test_missing_and_expired_output_fail_closed(tmp_path):
 t=ready(tmp_path)
 with pytest.raises(ValueError):t.emit(10)
 assert not t.path.exists()
 t=ready(tmp_path);p,e=evidence();t.binary(frame(1,p),10);t.binary(frame(2,e),10);t.emit(10)
 with pytest.raises(ValueError):Consumer(t.path,'b').check(10.751)
 with pytest.raises(ValueError):t.emit(11.01)
 t.close()

def test_unadvertise_rejects(tmp_path):
 t=ready(tmp_path)
 with pytest.raises(ValueError):t.text(json.dumps(dict(op='unadvertise',channelIds=[1])))
 t.close()


def test_final_consumer_enforces_unrounded_packet_age(tmp_path):
 t=ready(tmp_path);p,e=evidence();e['encoder_packet_monotonic']=9.8996;e['packet_age_s']=.100
 t.binary(frame(1,p),10);t.binary(frame(2,e),10);t.emit(10.8)
 with pytest.raises(ValueError,match='raw encoder packet expired'):Consumer(t.path,'b').check(10.8998)
 t.close()


@pytest.mark.parametrize('end',['disconnect','timeout','duration'])
def test_session_closes_owned_socket_and_output(tmp_path,monkeypatch,end):
 import types,local_bridge_observer as module
 class Timeout(Exception):pass
 clock=[10.]
 p,e=evidence()
 messages=[json.dumps(dict(op='advertise',channels=[dict(topic=n,id=i,encoding='cdr',schemaName='std_msgs/msg/String') for i,n in enumerate(['/atlas/control_policy','/atlas/encoder_health'],1)])),frame(1,p),frame(2,e)]
 class Socket:
  closed=False
  def settimeout(self,n):assert n==.1
  def send(self,data):assert json.loads(data)['op']=='subscribe'
  def recv(self):
   clock[0]+=.1
   if messages:return messages.pop(0)
   if end=='disconnect':return ''
   raise Timeout()
  def close(self):self.closed=True
 sock=Socket();monkeypatch.setitem(sys.modules,'websocket',types.SimpleNamespace(WebSocketTimeoutException=Timeout))
 monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
 args=(tmp_path/'state.json','b',{'policy':('b',1,2),'encoders':('b',3,4)})
 if end=='duration':module.observe_safety(*args,duration=.5,socket_factory=lambda *a,**k:sock)
 else:
  with pytest.raises(ValueError):module.observe_safety(*args,duration=2,socket_factory=lambda *a,**k:sock)
 assert sock.closed and not args[0].exists()


def test_untrusted_websocket_dependency_rejects_before_connect(tmp_path,monkeypatch):
 import local_bridge_observer as module
 monkeypatch.setattr(module,'STAGE',tmp_path)
 (tmp_path/'websocket_client-1.9.0-py3-none-any.whl').write_bytes(b'changed')
 with pytest.raises(ValueError,match='dependency hash mismatch'):
  module.observe_safety(tmp_path/'state.json','b',{},duration=1)
 assert not (tmp_path/'state.json').exists()

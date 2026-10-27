import copy, hashlib, io, json, sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'tools/diagnostics/stm32_readback'))
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import deploy_maintenance_once as d
import safety_evidence as e
from atlas_b1_interlock import Interlock

def good():
 return {'ros':{'control_policy':{'age':0.1,'sample_time':1234,'value':{'stop_latched':True,'manual_only':True,'commission_armed':False,'source':'STOPPED'}},'cmd_vel':{'age':0.1,'sample_time':1234,'value':{'lin':0.,'ang':0.}},'encoder_health':{}}}

@pytest.mark.parametrize('field,value,failed', [('stop_latched',False,'stop_latched'),('manual_only',False,'manual_only'),('commission_armed',True,'commission_armed'),('source','NAV2','source')])
def test_policy(field,value,failed):
 x=good();x['ros']['control_policy']['value'][field]=value
 assert failed in e.evaluate(x)['failed_predicates'];assert not Interlock.safe(x)

@pytest.mark.parametrize('age',[None,-1,1.01,float('nan'),True,'0'])
def test_freshness(age):
 x=good();x['ros']['cmd_vel']['age']=age
 assert 'cmd_vel.fresh' in e.evaluate(x)['failed_predicates'];assert not Interlock.safe(x)

@pytest.mark.parametrize('value',[1,-0.01,True,None,'0',float('inf')])
def test_commands(value):
 x=good();x['ros']['cmd_vel']['value']['lin']=value
 assert 'command.lin' in e.evaluate(x)['failed_predicates'];assert not Interlock.safe(x)

@pytest.mark.parametrize('x',[None,{}, {'ros':None},{'ros':{'control_policy':{'value':'broken'}}}])
def test_missing(x):assert e.evaluate(x)['failed_predicates'] and not Interlock.safe(x)

def arrange(tmp_path,monkeypatch,body=None,error=None):
 monkeypatch.setattr(d,'ROOT',tmp_path);monkeypatch.setattr(d,'result',{});monkeypatch.setattr(d,'modified',True)
 monkeypatch.setattr(d,'gate',Interlock(),raising=False);monkeypatch.setattr(d,'gate_module',SimpleNamespace(packet_counter=lambda x:1),raising=False)
 def fetch(*a,**kw):
  if error:raise error
  return io.StringIO(json.dumps(good()) if body is None else body)
 monkeypatch.setattr(d.urllib.request,'urlopen',fetch)

@pytest.mark.parametrize('body,error',[(None,TimeoutError('secret password')),('not JSON secret',None),(json.dumps({'ros':{}}),None)])
def test_api_evidence(tmp_path,monkeypatch,body,error):
 arrange(tmp_path,monkeypatch,body,error)
 with pytest.raises(RuntimeError):d.safety()
 saved=json.loads((tmp_path/'safety-001.json').read_text())
 assert saved['payload']['failed_predicates']
 assert 'secret' not in (tmp_path/'safety-001.json').read_text()
 assert saved['sha256']==hashlib.sha256(json.dumps(saved['payload'],sort_keys=True,allow_nan=False).encode()).hexdigest()

def test_success_and_multiple(tmp_path,monkeypatch):
 arrange(tmp_path,monkeypatch);assert d.safety()['packet_count']==1
 x=good();x['ros']['control_policy']['value']['stop_latched']=False;x['ros']['cmd_vel']['value']['ang']=2
 arrange(tmp_path,monkeypatch,json.dumps(x))
 with pytest.raises(RuntimeError,match='stop_latched'):d.safety()
 payload=json.loads((tmp_path/'safety-001.json').read_text())['payload']
 assert {'stop_latched','command.ang'}<=set(payload['failed_predicates'])
 assert payload['snapshot']['ros']['cmd_vel']['sample_time']==1234

@pytest.mark.parametrize('operation',['replace','fsync'])
def test_write_failure(tmp_path,monkeypatch,capsys,operation):
 arrange(tmp_path,monkeypatch)
 monkeypatch.setattr(e.os,operation,lambda *a:(_ for _ in ()).throw(OSError('secret disk error')))
 with pytest.raises(RuntimeError,match='persistence'):d.safety()
 assert d.result['safety_evidence'][0]['fallback_evidence']['original_gate_pass']
 assert 'secret disk' not in capsys.readouterr().err
 assert not list(tmp_path.glob('.safety-*'))

def test_redaction(tmp_path):
 x=good();x['password']='secret';x['ros']['control_policy']['value']=json.dumps(dict(x['ros']['control_policy']['value'],token='secret'))
 p=tmp_path/'e.json';e.save(p,e.evaluate(x));assert 'secret' not in p.read_text()


def test_integrity_failure_denies_admission(tmp_path,monkeypatch):
 arrange(tmp_path,monkeypatch)
 original=Path.read_bytes
 def corrupt(path):
  if path.name=='safety-001.json':return b'{"sha256":"wrong","payload":{}}'
  return original(path)
 monkeypatch.setattr(Path,'read_bytes',corrupt)
 with pytest.raises(RuntimeError,match='persistence'):d.safety()
 assert d.result['safety_evidence'][0]['write_error_type']=='OSError'

def test_exact_freshness_boundary():
 x=good()
 for item in x['ros'].values():
  item['age']=1.0
 assert not e.evaluate(x)['failed_predicates'] and Interlock.safe(x)

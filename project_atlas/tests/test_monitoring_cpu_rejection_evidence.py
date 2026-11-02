"""Offline rejection evidence only; no services, network or live proc reads."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import math
import pytest
ROOT=Path(__file__).resolve().parents[2]/'monitoring/atlas/persistent'
def load(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
A=load('activate_timestamp_retry_once')
R=load('recover_once')

def require(value, reason):
    if not value: raise RuntimeError(reason)
def finite(v): return type(v) in (float,int) and math.isfinite(v)
def scalar(v): return v if finite(v) else None

@pytest.fixture
def setup(monkeypatch):
    g=SimpleNamespace(EVIDENCE={'cpu':1,'old':True},require=require,finite=finite,
                      evidence_scalar=scalar,cpu_counter=lambda:(11.,200,100),
                      read_thermal=lambda:([60],[]))
    def validate(ros,cpu,ram,temps,counts):
        require(finite(cpu) and 0<=cpu<=75,'CPU limit'); return counts
    g.validate=validate
    response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
    response.read.return_value=b'{"ros":{}}'
    monkeypatch.setattr(A.urllib.request,'urlopen',lambda *a,**k:response)
    monkeypatch.setattr(A.time,'sleep',lambda _:None)
    monkeypatch.setattr(A.time,'monotonic',lambda:11.02)
    monkeypatch.setattr(A.signal,'setitimer',lambda *a:None)
    monkeypatch.setattr(A.Path,'read_text',lambda *a,**k:'MemTotal: 100\nMemAvailable: 50\n')
    return g

@pytest.mark.parametrize('cpu',[76.,99.,-1.,float('nan'),float('inf')])
def test_rejected_cpu_is_preserved_json_safely(setup,cpu):
    g=setup;g.cpu_counter=lambda:(11.,200,100-cpu)
    with pytest.raises(RuntimeError,match='CPU limit'): A.sample(g,(10.,100,0),None,False)
    e=json.loads(json.dumps(g.EVIDENCE,allow_nan=False))
    assert e['cpu']==(pytest.approx(cpu) if finite(cpu) else None)
    assert e['cpu_sample_monotonic']==11 and e['cpu_sample_age']==pytest.approx(.02)
    assert e['cpu_threshold']==75 and e['stage']=='admission_validate'
    assert 'old' not in e

def test_missing_counter_cannot_reuse_old_value(setup):
    def missing(): raise RuntimeError('CPU counters missing')
    setup.cpu_counter=missing
    with pytest.raises(RuntimeError,match='CPU counters missing'): A.sample(setup,(10,100,0),None,False)
    assert setup.EVIDENCE['cpu'] is None
    assert setup.EVIDENCE['cpu_sample_monotonic'] is None

def test_invalid_interval_rejects_before_calculation(setup):
    setup.cpu_counter=lambda:(9,200,20)
    with pytest.raises(RuntimeError,match='CPU sampling interval'): A.sample(setup,(10,100,0),None,False)
    assert setup.EVIDENCE['cpu'] is None
    assert setup.EVIDENCE['stage']=='admission_CPU_sample'

@pytest.mark.parametrize('cpu',[75.,74.9])
def test_transaction_strict_boundary_retains_evidence(setup,monkeypatch,tmp_path,cpu):
    setup.cpu_counter=lambda:(11.,200,100-cpu)
    monkeypatch.setattr(R,'G',setup);monkeypatch.setattr(R,'A',A)
    monkeypatch.setattr(R,'previous',(10.,100,0));monkeypatch.setattr(R,'counts',None)
    monkeypatch.setattr(R,'protected',False);monkeypatch.setattr(R,'E',tmp_path)
    if cpu==75:
        with pytest.raises(Exception,match='resource limit'): R.sample()
        assert not (tmp_path/'samples.jsonl').exists()
    else: assert R.sample()['cpu']==pytest.approx(cpu)
    assert setup.EVIDENCE['cpu']==pytest.approx(cpu)
    assert setup.EVIDENCE['stage']=='transaction_resource_limit'

def test_sampler_pin_matches_source():
    import hashlib
    assert R.SAMPLER_SHA==hashlib.sha256((ROOT/'activate_timestamp_retry_once.py').read_bytes()).hexdigest()


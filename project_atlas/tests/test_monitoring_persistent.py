"""Persistent monitoring guards: simulated inputs only, no real service/firewall calls."""
import copy
import importlib.util
import json
from pathlib import Path
from unittest import mock

import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('guard',ROOT/'monitoring/atlas/persistent/guard.py')
G=importlib.util.module_from_spec(spec); spec.loader.exec_module(G)

def ros():
    data={k:{'age':0.1,'value':0} for k in G.LIMITS}
    data['control_policy']['value']=json.dumps(dict(stop_latched=True,manual_only=True,commission_armed=False))
    data['encoder_health']['value']=json.dumps(dict(link_state='LIVE',packet_fresh=True))
    data['cmd_vel']['value']={'lin':0.,'ang':0.}
    return data

def test_safe_and_exact_limits():
    assert G.validate(ros(),75,80,[69.999],[0]*4)==[0]*4

@pytest.mark.parametrize('cpu,ram,temps',[(75.01,50,[60]),(50,80.01,[60]),(50,50,[70]),
    (50,50,[]),(float('nan'),50,[60]),(50,True,[60]),(50,50,[float('nan')])])
def test_resource_fail_closed(cpu,ram,temps):
    with pytest.raises(G.Rejected): G.validate(ros(),cpu,ram,temps,[0]*4)

@pytest.mark.parametrize('age',[None,True,-1,1.01,float('nan'),float('inf'),'0'])
def test_age_fail_closed(age):
    data=ros(); data['control_policy']['age']=age
    with pytest.raises(G.Rejected): G.validate(data,60,60,[60],[0]*4)

@pytest.mark.parametrize('field,value',[('stop_latched',False),('manual_only',False),('commission_armed',True),('stop_latched',None)])
def test_policy_failure(field,value):
    data=ros(); policy=json.loads(data['control_policy']['value']); policy[field]=value
    data['control_policy']['value']=json.dumps(policy)
    with pytest.raises(G.Rejected): G.validate(data,60,60,[60],[0]*4)

def test_movement_and_missing_data():
    with pytest.raises(G.Rejected): G.validate(ros(),60,60,[60],[1]*4)
    data=ros();data['cmd_vel']['value']['lin']=0.01
    with pytest.raises(G.Rejected): G.validate(data,60,60,[60],[0]*4)
    data=ros();del data['encoder_health']
    with pytest.raises(KeyError): G.validate(data,60,60,[60],[0]*4)

def test_firewall_exact_semantics():
    baseline={'nftables':[{'metainfo':{'version':'1'}},*G.expected_rules()]}
    assert G.canonical(baseline)==G.expected_rules()
    for transform in ('source','priority','extra','order','ipv6'):
        data=copy.deepcopy(baseline)
        if transform=='source': data['nftables'][3]['rule']['expr'][2]['match']['right']='192.168.1.0/24'
        if transform=='priority': data['nftables'][2]['chain']['prio']=10
        if transform=='extra': data['nftables'].append(copy.deepcopy(data['nftables'][-1]))
        if transform=='order': data['nftables'][3:]=reversed(data['nftables'][3:])
        if transform=='ipv6': data['nftables'][1]['table']['family']='ip'
        with mock.patch.object(G,'command',return_value=json.dumps(data)),pytest.raises(G.Rejected): G.verify_firewall()

def test_thermal_cv_unavailable_and_no_trustworthy(tmp_path):
    z=tmp_path/'thermal_zone0';z.mkdir();(z/'type').write_text('cv0-thermal')
    with pytest.raises(G.Rejected): G.read_thermal(tmp_path)
    c=tmp_path/'thermal_zone1';c.mkdir();(c/'type').write_text('cpu-thermal');(c/'temp').write_text('62000')
    assert G.read_thermal(tmp_path)==([62],['cv0-thermal'])
    (c/'temp').write_text('bad')
    with pytest.raises(G.Rejected): G.read_thermal(tmp_path)

def test_durable_fault_latch(tmp_path,monkeypatch):
    monkeypatch.setattr(G,'STATE',tmp_path);G.latch('CPU limit')
    assert json.loads((tmp_path/'FAULT.json').read_text())['reason']=='CPU limit'
    with pytest.raises(G.Rejected):G.no_fault()

def test_write_failure_not_silently_accepted(tmp_path,monkeypatch):
    monkeypatch.setattr(G,'STATE',tmp_path)
    with mock.patch.object(G.os,'fsync',side_effect=OSError('disk full')),pytest.raises(OSError):G.latch('fault')

def test_api_timeout_and_absolute_deadline(monkeypatch):
    with mock.patch.object(G,'verify_firewall'),mock.patch.object(G,'no_fault'),mock.patch.object(G.signal,'setitimer'),mock.patch.object(G.urllib.request,'urlopen',side_effect=TimeoutError),pytest.raises(TimeoutError):
        G.observe((1,100,50),[0]*4)
    with pytest.raises(G.Rejected):G.deadline(None,None)

def test_rollback_stops_before_delete(tmp_path,monkeypatch):
    monkeypatch.setattr(G,'STATE',tmp_path);(tmp_path/'firewall-owned.json').write_text('{}');calls=[]
    def cmd(*args):
        calls.append(args)
        return '0\n' if 'MainPID' in args else ''
    with mock.patch.object(G,'command',side_effect=cmd),mock.patch.object(G,'listeners',return_value=''),mock.patch.object(G,'firewall_present',side_effect=[True,False]),mock.patch.object(G,'verify_firewall'):
        G.rollback()
    delete=next(i for i,c in enumerate(calls) if 'delete' in c)
    assert calls[0]==('/usr/bin/systemctl','disable','--now',G.UNIT)
    assert any('MainPID' in c for c in calls[:delete])

def test_rollback_retains_protection_if_listener_exists():
    with mock.patch.object(G,'command',return_value='0\n') as cmd,mock.patch.object(G,'listeners',return_value='LISTEN'),pytest.raises(G.Rejected):G.rollback()
    assert not any('delete' in c.args for c in cmd.call_args_list)

def test_watchdog_stop_request_nonblocking():
    with mock.patch.object(G,'command') as cmd:G.stop_exporter()
    cmd.assert_called_once_with('/usr/bin/systemctl','--no-block','stop',G.UNIT)

def test_units_preserve_ordering_and_limits():
    directory=ROOT/'monitoring/atlas/persistent'
    text=(directory/'atlas-monitoring-exporter.service.in').read_text()
    for clause in ('BindsTo=atlas-monitoring-watchdog.service','ExecCondition=+',
                   'CPUQuota=10%','MemoryMax=64M','StartLimitBurst=3','RestartSec=30','KillMode=control-group'):
        assert clause in text
    watch=(directory/'atlas-monitoring-watchdog.service').read_text()
    assert 'Type=notify' in watch and 'Restart=no' in watch and 'WatchdogSec=5' in watch
    assert 'ExecStop=' not in (directory/'atlas-monitoring-firewall.service').read_text()

def test_unclean_watchdog_marker_refuses_restart(tmp_path,monkeypatch):
    monkeypatch.setattr(G,'STATE',tmp_path);(tmp_path/'observer-active.json').write_text('{}')
    with mock.patch.object(G,'two_samples') as sample,pytest.raises(G.Rejected): G.watchdog()
    sample.assert_not_called()

def test_integrity_rejects_wrong_exporter(tmp_path,monkeypatch):
    target=tmp_path/'exporter';target.write_text('wrong');monkeypatch.setattr(G,'EXPORTER',target)
    with mock.patch.object(G,'trusted'),pytest.raises(G.Rejected): G.integrity()

def test_missing_firewall_rejects_before_api():
    with mock.patch.object(G,'no_fault'),mock.patch.object(G.signal,'setitimer'),mock.patch.object(G,'verify_firewall',side_effect=G.Rejected('absent')),mock.patch.object(G.urllib.request,'urlopen') as api,pytest.raises(G.Rejected):
        G.observe((1,100,50),[0]*4)
    api.assert_not_called()

def test_every_watchdog_sample_must_pass(tmp_path,monkeypatch):
    monkeypatch.setattr(G,'STATE',tmp_path)
    with mock.patch.object(G,'two_samples',return_value=((0,100,50),[0]*4,{'cpu':50})),mock.patch.object(G,'notify') as notify,mock.patch.object(G.time,'sleep'),mock.patch.object(G,'observe',side_effect=G.Rejected('stop released')),pytest.raises(G.Rejected):
        G.watchdog()
    assert notify.call_count==1
    assert (tmp_path/'observer-active.json').exists()

def test_package_is_exact_and_refuses_overwrite(tmp_path):
    import importlib.util
    path=ROOT/'monitoring/atlas/persistent/prepare_package.py'
    spec=importlib.util.spec_from_file_location('package',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    out=tmp_path/'package';module.prepare(out,1234)
    import hashlib
    original=(ROOT/'project_atlas/scripts/atlas_health_exporter.py').read_bytes()
    assert hashlib.sha256((out/'atlas_health_exporter.py').read_bytes()).hexdigest()==module.SHA
    assert module.trial_bytes(original.replace(b'\r\n',b'\n'))==(out/'atlas_health_exporter.py').read_bytes()
    with pytest.raises(ValueError):module.trial_bytes(original+b'# changed')
    assert '/run/user/1234' in (out/'atlas-monitoring-exporter.service').read_text()
    with pytest.raises(FileExistsError):module.prepare(out,1234)
    with pytest.raises(ValueError):module.prepare(tmp_path/'bad',0)


def test_first_fault_survives_repeated_refusals_and_reboot(tmp_path,monkeypatch):
    monkeypatch.setattr(G,'STATE',tmp_path)
    monkeypatch.setattr(G,'EVIDENCE',{'cpu':81.2,'stage':'validate'})
    monkeypatch.setattr(G,'ACTION','watchdog')
    G.latch('CPU limit'); original=(tmp_path/'FAULT.json').read_bytes()
    first=json.loads(original)
    assert first['boot_id'] and first['time'] and first['evidence']['cpu']==81.2
    # Fresh module simulates a new process/boot with only disk state retained.
    spec2=importlib.util.spec_from_file_location('guard_reboot',ROOT/'monitoring/atlas/persistent/guard.py')
    new=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(new);new.STATE=tmp_path
    new.ACTION='firewall'
    for _ in range(20):
        with pytest.raises(new.Rejected):new.no_fault()
        new.latch('fault latched; owner review required')
    assert (tmp_path/'FAULT.json').read_bytes()==original
    events=json.loads((tmp_path/'fault-events.json').read_text())
    assert len(events)==16 and events[-1]['action']=='firewall'
    assert events[-1]['evidence']=={} and (tmp_path/'fault-events.json').stat().st_size<=65536

@pytest.mark.parametrize('content',[b'',b'{broken',b'null'])
def test_corrupt_first_fault_preserved_and_blocks(tmp_path,monkeypatch,content):
    monkeypatch.setattr(G,'STATE',tmp_path);(tmp_path/'FAULT.json').write_bytes(content)
    with pytest.raises(G.Rejected):G.no_fault()
    G.latch('fault latched; owner review required')
    assert (tmp_path/'FAULT.json').read_bytes()==content

def test_broken_latch_symlink_blocks(tmp_path,monkeypatch):
    monkeypatch.setattr(G,'STATE',tmp_path);(tmp_path/'FAULT.json').symlink_to(tmp_path/'absent')
    with pytest.raises(G.Rejected):G.no_fault()
    G.latch('fault latched; owner review required')
    assert (tmp_path/'FAULT.json').is_symlink() and not (tmp_path/'absent').exists()

def test_corrupt_event_history_is_not_overwritten(tmp_path,monkeypatch):
    monkeypatch.setattr(G,'STATE',tmp_path);G.latch('first')
    (tmp_path/'fault-events.json').write_text('{broken')
    with pytest.raises(ValueError):G.latch('second')
    assert (tmp_path/'fault-events.json').read_text()=='{broken'
    assert json.loads((tmp_path/'FAULT.json').read_text())['reason']=='first'

def test_subsequent_atomic_failure_preserves_both_records(tmp_path,monkeypatch):
    monkeypatch.setattr(G,'STATE',tmp_path);G.latch('first');G.latch('second')
    before=[(tmp_path/n).read_bytes() for n in ('FAULT.json','fault-events.json')]
    with mock.patch.object(G.os,'replace',side_effect=OSError('disk failure')),pytest.raises(OSError):G.latch('third')
    assert before==[(tmp_path/n).read_bytes() for n in ('FAULT.json','fault-events.json')]

def test_safety_evidence_redacts_and_keeps_invalid_unknown():
    data={'control_policy':{'age':0.1,'value':json.dumps({'stop_latched':False,'manual_only':True,'commission_armed':False,'secret':'password'})},'cmd_vel':{'value':{'lin':0.2,'ang':float('nan'),'secret':'password'}}}
    evidence=G.safety_evidence(data)
    assert evidence['control_policy']['stop_latched'] is False
    assert evidence['command']=={'lin':0.2,'ang':None}
    assert evidence['encoders']==[None]*4 and 'password' not in json.dumps(evidence)

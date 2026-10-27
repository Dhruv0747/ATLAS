import errno
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'tools/diagnostics'))
sys.path.insert(0,str(ROOT/'tools/diagnostics/stm32_readback'))
import offboard_bridge_preflight as probe
import deploy_maintenance_once as deploy


def thermal_fixture(tmp_path, monkeypatch, unavailable=(), malformed=None, model='NVIDIA Jetson Orin Nano Developer Kit'):
    root=tmp_path/'thermal';root.mkdir()
    for i,name in enumerate(sorted(probe.NANO_REQUIRED_THERMAL|probe.NANO_EXPECTED_UNAVAILABLE)):
        z=root/('thermal_zone'+str(i));z.mkdir();(z/'type').write_text(name)
        (z/'temp').write_text((malformed or {}).get(name,'59000'))
    original=probe.read_sysfs_text
    def read(path,limit=256):
        if path.name=='temp' and (path.parent/'type').read_text() in unavailable:
            raise BlockingIOError(errno.EAGAIN,'unavailable')
        return original(path,limit)
    monkeypatch.setattr(probe,'read_sysfs_text',read)
    return probe.read_thermal(root,model)


def test_uses_existing_implementation():
    assert deploy.read_thermal is probe.read_thermal


def test_cv_unavailable_is_none_not_zero(tmp_path,monkeypatch):
    t=thermal_fixture(tmp_path,monkeypatch,probe.NANO_EXPECTED_UNAVAILABLE)
    assert deploy.validate_resources(75,80,t)==59
    assert len(t['thermal_not_applicable'])==3
    assert all(x['temperature_c'] is None for x in t['thermal_measurements'] if x['status']=='not_applicable')


@pytest.mark.parametrize('name',sorted(probe.NANO_REQUIRED_THERMAL))
def test_missing_required_sensor_blocks(tmp_path,monkeypatch,name):
    t=thermal_fixture(tmp_path,monkeypatch,{name})
    with pytest.raises(ValueError):deploy.validate_resources(20,20,t)


@pytest.mark.parametrize('value',['','nonsense','NaN','71000','125000'])
def test_malformed_and_hot_block(tmp_path,monkeypatch,value):
    t=thermal_fixture(tmp_path,monkeypatch,malformed={'cpu-thermal':value})
    with pytest.raises(ValueError):deploy.validate_resources(20,20,t)


def test_all_readings_missing_blocks(tmp_path,monkeypatch):
    t=thermal_fixture(tmp_path,monkeypatch,probe.NANO_REQUIRED_THERMAL|probe.NANO_EXPECTED_UNAVAILABLE)
    with pytest.raises(ValueError):deploy.validate_resources(20,20,t)


@pytest.mark.parametrize('cpu,ram,temp',[(75,80,70),(75.01,80,70),(75,80.01,70),(75,80,70.001)])
def test_exact_limits(cpu,ram,temp):
    t={'thermal_zones_c':{'cpu':temp},'thermal_read_errors':[]}
    if (cpu,ram,temp)==(75,80,70):assert deploy.validate_resources(cpu,ram,t)==70
    else:
        with pytest.raises(ValueError):deploy.validate_resources(cpu,ram,t)


def test_unknown_model_cannot_exempt_cv(tmp_path,monkeypatch):
    t=thermal_fixture(tmp_path,monkeypatch,probe.NANO_EXPECTED_UNAVAILABLE,model='unknown')
    with pytest.raises(ValueError):deploy.validate_resources(20,20,t)


@pytest.mark.parametrize('fail_at',['preflight1','preflight2','first_write','recovery_write','condition_write','postflight','safety_reject','evidence_failure','none'])
def test_transaction_with_fake_files_and_services(tmp_path,monkeypatch,fail_at):
    stage=tmp_path/'stage';stage.mkdir();scripts=tmp_path/'scripts';scripts.mkdir();units=tmp_path/'units';units.mkdir()
    dropdir=units/'rover-base-telemetry.service.d';dropdir.mkdir()
    (dropdir/'priority.conf').write_bytes(b'original priority')
    recovery=scripts/'atlas_sensor_recovery.py';recovery.write_bytes(b'original recovery')
    base=units/'rover-base-telemetry.service';base.write_bytes(b'original base')
    state=tmp_path/'state'
    before={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in [recovery,base,dropdir/'priority.conf']}
    for key,value in {'ROOT':stage,'S':scripts,'U':units,'STATE':state,'DROP':dropdir/'98-b1-maintenance.conf','BACK':stage/'rollback','C':stage/'candidate','EXPECTED':before,'modified':False,'trace':[],'result':{'status':'PREFLIGHT'}}.items():monkeypatch.setattr(deploy,key,value)
    content={'atlas_b1_interlock.py':b'fake module','atlas_sensor_recovery.py':b'candidate recovery','b1-maintenance.conf':b'candidate condition'}
    content['SHA256.json']=json.dumps({n:hashlib.sha256(b).hexdigest() for n,b in content.items()}).encode()
    with tarfile.open(stage/'candidate.tar','w') as t:
        for n,b in content.items():
            info=tarfile.TarInfo(n);info.size=len(b);t.addfile(info,io.BytesIO(b))
    (stage/'baseline-backup.tar').write_bytes(b'fake baseline archive')
    realsha=deploy.sha
    monkeypatch.setattr(deploy,'sha',lambda p: {'candidate.tar':'a28c5ea60de2b9276a2a275d1c2bb0bd303d959a61821b7f0217dc05a428a756','baseline-backup.tar':'6f583eb097236eb675986d472b7ece3c74722a051f1867a58e0b98fed2bda87a'}.get(Path(p).name) or realsha(p))
    class Gate:
        def safe(self,d):return False
        def initialize(self):state.mkdir();(state/'state.json').write_text('{"version":1,"phase":"IDLE"}')
        def start_gate(self):return True
        def load(self):return json.loads((state/'state.json').read_text())
    fake=SimpleNamespace(Interlock=Gate,no_base_jobs=lambda:True)
    monkeypatch.setattr(deploy.importlib.util,'spec_from_file_location',lambda *a:SimpleNamespace(loader=SimpleNamespace(exec_module=lambda m:None)))
    monkeypatch.setattr(deploy.importlib.util,'module_from_spec',lambda s:fake)
    calls=[];restarts=[0]
    def cmd(*a):
        calls.append(a)
        if 'restart' in a:
            assert a==('systemctl','--user','restart','atlas-sensor-recovery.service')
            restarts[0]+=1
        if 'ExecCondition' in a:return str(scripts/'atlas_b1_interlock.py')
        return 'READY: full bounded fault recovery armed'
    monkeypatch.setattr(deploy,'cmd',cmd)
    def stats():
        return {n:{'Id':n,'ActiveState':'active','MainPID':str(100+restarts[0] if n=='atlas-sensor-recovery.service' else 20),'NRestarts':'0'} for n in deploy.UNITS}
    monkeypatch.setattr(deploy,'stats',stats)
    packets=[0]
    actual_safety=deploy.safety
    def safety():
        packets[0]+=1
        if fail_at in ('safety_reject','evidence_failure') and packets[0]==3:
            monkeypatch.setattr(deploy.urllib.request,'urlopen',lambda *a,**kw:io.StringIO('{"ros":{}}'))
            if fail_at=='evidence_failure':
                monkeypatch.setattr(deploy.safety_evidence,'save',lambda *a:(_ for _ in ()).throw(OSError('disk failed')))
            return actual_safety()
        return {'packet_count':packets[0]}
    monkeypatch.setattr(deploy,'safety',safety)
    samples=[0]
    def resource():
        samples[0]+=1
        if fail_at=='preflight'+str(samples[0]) or (fail_at=='postflight' and samples[0]==3):raise ValueError('injected temperature failure')
        row={'cpu_pct':30,'ram_pct':40,'temp_c':59};deploy.trace.append(row);return row
    monkeypatch.setattr(deploy,'resource',resource)
    monkeypatch.setattr(deploy.time,'sleep',lambda _:None)
    actual=deploy.atomic;writes=[0]
    def atomic(src,dst):
        actual(src,dst);writes[0]+=1
        if (fail_at,writes[0]) in [('first_write',1),('recovery_write',2),('condition_write',3)]:raise OSError('injected write failure')
    monkeypatch.setattr(deploy,'atomic',atomic)
    result=deploy.deploy()
    assert not any('rover-base-telemetry.service' in c and 'restart' in c for c in calls)
    if fail_at=='none':
        assert result['status']=='DEPLOYED_AND_VERIFIED' and restarts[0]==1
    else:
        assert result['status'] in ('ABORTED_BEFORE_INSTALL','ROLLED_BACK'),result
        for name,digest in before.items():assert realsha(name)==digest
        assert not deploy.DROP.exists() and not state.exists() and not (scripts/'atlas_b1_interlock.py').exists()
        if fail_at.startswith('preflight'):assert writes[0]==0 and restarts[0]==0
        if fail_at in ('safety_reject','evidence_failure'):
            assert result['status']=='ROLLED_BACK'
            assert result['safety_evidence'][0]['failed_predicates']
            if fail_at=='safety_reject':
                assert json.loads((stage/'safety-001.json').read_text())['payload']['stage']=='post-install'
            else:
                assert result['safety_evidence'][0]['fallback_evidence']['failed_predicates']


@pytest.mark.parametrize('broken',[False,True])
def test_resource_function_reuses_reader_and_preserves_failure_evidence(tmp_path,monkeypatch,broken):
    monkeypatch.setattr(deploy,'ROOT',tmp_path);monkeypatch.setattr(deploy,'trace',[])
    ticks=iter([(100,50),(200,90)])
    monkeypatch.setattr(deploy,'cpu',lambda:next(ticks))
    monkeypatch.setattr(deploy.time,'sleep',lambda _:None)
    realread=Path.read_text
    monkeypatch.setattr(Path,'read_text',lambda p,*a,**kw:'MemTotal: 1000 kB\nMemAvailable: 500 kB\n' if str(p)=='/proc/meminfo' else realread(p,*a,**kw))
    report={'thermal_zones_c':{'cpu':60},'thermal_read_errors':[{'error':'missing required zone'}] if broken else [],'thermal_measurements':[{'type':'cv0-thermal','temperature_c':None,'status':'not_applicable'}]}
    calls=[]
    def read():calls.append(1);return report
    monkeypatch.setattr(deploy,'read_thermal',read)
    if broken:
        with pytest.raises(ValueError):deploy.resource()
    else:
        row=deploy.resource();assert row['temp_c']==60 and row['cpu_pct']==60
    assert calls==[1]
    saved=json.loads((tmp_path/'resources.json').read_text())
    assert saved[0]['thermal']['thermal_measurements'][0]['temperature_c'] is None


def test_cli_without_approval_never_calls_deploy(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,'argv',['deploy','--staging',str(tmp_path)])
    monkeypatch.setattr(deploy,'deploy',lambda:pytest.fail('deployment executed'))
    with pytest.raises(SystemExit):deploy.main()


def test_cli_refuses_previous_attempt_directory(tmp_path,monkeypatch):
    (tmp_path/'result.json').write_text('{}')
    monkeypatch.setattr(sys,'argv',['deploy','--staging',str(tmp_path),'--approve-maintenance-install'])
    monkeypatch.setattr(deploy,'deploy',lambda:pytest.fail('deployment executed'))
    with pytest.raises(SystemExit):deploy.main()


def test_partial_atomic_copy_does_not_change_original(tmp_path,monkeypatch):
    source=tmp_path/'source';source.write_bytes(b'new')
    target=tmp_path/'target';target.write_bytes(b'original')
    def fail_copy(src,dst):
        Path(dst).write_bytes(b'partial');raise OSError('disk error')
    monkeypatch.setattr(deploy.shutil,'copy2',fail_copy)
    with pytest.raises(OSError):deploy.atomic(source,target)
    assert target.read_bytes()==b'original'
    assert sorted(p.name for p in tmp_path.iterdir())==['source','target']

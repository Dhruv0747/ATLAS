"""Activation orchestration tests: fake services and temporary paths only."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

SOURCE=Path(__file__).resolve().parents[2]/'monitoring/atlas/persistent/activate_once.py'

@pytest.mark.parametrize('script',['activate_once.py','activate_timestamp_retry_once.py'])
@pytest.mark.parametrize('failure',[None,'baseline','active','services','prior_clean','prior_fault'])
def test_activation_transaction(tmp_path,monkeypatch,failure,script):
    spec=importlib.util.spec_from_file_location('activation_test',SOURCE.with_name(script))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    monkeypatch.setattr(m,'EVIDENCE',tmp_path/'evidence');monkeypatch.setattr(m,'BASE',tmp_path)
    (tmp_path/'SHA256SUMS').write_text('fixture')
    files={k:str(tmp_path/'installed'/Path(v).name) for k,v in m.FILES.items()}
    monkeypatch.setattr(m,'FILES',files)
    package={k:b'fixture' for k in files};monkeypatch.setattr(m,'verify_package',lambda:package)
    state={'firewall':False,'active':False,'samples':0};calls=[]
    g=SimpleNamespace(STATE=tmp_path/'state',TABLE='atlas_monitor',UNIT='atlas-monitoring-exporter.service',WATCHDOG='atlas-monitoring-watchdog.service',FIREWALL='atlas-monitoring-firewall.service',deadline=lambda *a:None,cpu_counter=lambda:(0,0,0),listeners=lambda:'',firewall_present=lambda:state['firewall'],verify_firewall=lambda:None)
    if failure in ('prior_clean','prior_fault'):
        g.STATE.mkdir();(g.STATE/('FAULT.json' if failure=='prior_fault' else 'last-health.json')).write_text('{}')
    monkeypatch.setattr(m.importlib.util,'module_from_spec',lambda s:g)
    monkeypatch.setattr(m.importlib.util,'spec_from_file_location',lambda *a:SimpleNamespace(loader=SimpleNamespace(exec_module=lambda x:None)))
    monkeypatch.setattr(m.os,'geteuid',lambda:0);monkeypatch.setattr(m.os,'umask',lambda x:None)
    monkeypatch.setattr(m.signal,'signal',lambda *a:None)
    ticks=iter(range(0,10000,60));monkeypatch.setattr(m.time,'monotonic',lambda:next(ticks))
    def sample(*args):
        state['samples']+=1
        if failure=='baseline' or (failure=='active' and state['active']):raise RuntimeError('safety rejected')
        return (0,0,0),[0]*4,{'cpu':60,'ram':60,'temp':60}
    monkeypatch.setattr(m,'sample',sample)
    monkeypatch.setattr(m,'services',lambda:'changed' if failure=='services' and state['active'] else 'original')
    def run(*args):
        calls.append(args)
        if args==('iptables','--version'):return 'legacy'
        if args[:2]==('systemctl','start'):
            if args[2]==g.FIREWALL:
                state['firewall']=True;g.STATE.mkdir();(g.STATE/'firewall-owned.json').write_text('{}')
            if args[2]==g.UNIT:state['active']=True
        if args[:2]==('systemctl','is-active'):return 'active'
        if args[:2]==('systemctl','show'):
            return '0' if 'MainPID' in args and '--value' in args else 'ActiveState=active\nNRestarts=0\n'
        if args[:3]==('systemctl','disable','--now'):state['active']=False
        if args[:2]==('nft','delete'):state['firewall']=False
        return 'baseline'
    monkeypatch.setattr(m,'run',run)
    code=m.main()
    success=failure is None or (failure=='prior_clean' and script=='activate_timestamp_retry_once.py')
    assert code==(0 if success else 1)
    if success:
        assert ('systemctl','enable',g.UNIT) in calls
        assert all(Path(p).exists() for p in files.values())
        if failure=='prior_clean':assert (m.EVIDENCE/'previous-monitoring-state/last-health.json').exists()
    else:
        assert ('systemctl','enable',g.UNIT) not in calls
        assert not any(Path(p).exists() for p in files.values())
        assert not state['firewall']
    assert (m.EVIDENCE/'result.json').exists() and (m.EVIDENCE/'SHA256SUMS').exists()
    assert not any('restart' in x for x in calls)
    with pytest.raises(FileExistsError):m.main()

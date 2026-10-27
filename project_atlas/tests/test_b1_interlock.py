"""Linux-only simulated services: no ROS, serial or systemctl calls."""
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from atlas_b1_interlock import Interlock, Denied


def safe():
    return {'ros': {'control_policy': {'age': 0, 'value': {'stop_latched': True,
        'manual_only': True, 'commission_armed': False, 'source': 'STOPPED'}},
        'cmd_vel': {'age': 0, 'value': {'lin': 0, 'ang': 0}}}}

@pytest.fixture
def g(tmp_path):
    now = [10.]
    gate = Interlock(tmp_path / 'state', clock=lambda: now[0], boot='test')
    gate.initialize()
    gate.now = now
    return gate


def test_inflight_recovery_blocks_admission(g):
    with g.recovery_dispatch():
        with ThreadPoolExecutor() as ex:
            f = ex.submit(g.arm, safe(), lambda: True)
            with pytest.raises(BlockingIOError): f.result(timeout=2)
    assert g.load()['phase'] == 'IDLE'


def test_pending_systemd_job_blocks_admission(g):
    with pytest.raises(Denied): g.arm(safe(), lambda: False)


def test_restart_on_failure_and_queued_recovery_denied(g):
    s = g.arm(safe(), lambda: True)
    for _ in range(5): assert not g.start_gate()
    with pytest.raises(Denied):
        with g.recovery_dispatch(): pytest.fail('restart dispatched')
    g.heartbeat(s, safe()); g.begin_read(s)
    assert not g.start_gate()
    with pytest.raises(Denied): g.heartbeat(s, safe()); g.begin_read(s)


def test_crashed_monitor_timeout_never_releases(g):
    s = g.arm(safe(), lambda: True); g.heartbeat(s, safe()); g.begin_read(s)
    g.now[0] += 3
    with pytest.raises(Denied): g.check_read(s)
    assert not g.start_gate()
    g.now[0] += 1000
    with pytest.raises(Denied): g.heartbeat(s, safe())
    assert g.load()['phase'] == 'ABORTED' and not g.start_gate()


def test_explicit_recovery_and_one_start_only(g):
    s = g.arm(safe(), lambda: True); g.heartbeat(s, safe()); g.begin_read(s); g.abort(s)
    with pytest.raises(Denied): g.resume(s, safe(), True, lambda: False)
    with pytest.raises(Denied): g.resume(s, safe(), False, lambda: True)
    g.resume(s, safe(), True, lambda: True)
    assert g.start_gate() and not g.start_gate()
    with pytest.raises(Denied): g.release(s, safe(), lambda: False, True)
    g.release(s, safe(), lambda: True, True)
    assert g.start_gate()
    with g.recovery_dispatch(): pass


def test_expired_session_requires_explicit_reconciliation(g):
    s = g.arm(safe(), lambda: True); g.now[0] += 1000
    with pytest.raises(Denied): g.resume(s, safe(), True, lambda: True)
    g.reconcile(s, safe(), True, lambda: True)
    with pytest.raises(Denied): g.heartbeat(s, safe()); g.begin_read(s)
    g.resume(s, safe(), True, lambda: True)
    assert g.start_gate()


@pytest.mark.parametrize('bad', ['missing', 'corrupt', 'wrongboot'])
def test_ambiguous_state_denied(g, bad):
    s = g.arm(safe(), lambda: True)
    p = g.root / 'state.json'
    if bad == 'missing': p.unlink()
    elif bad == 'corrupt': p.write_text('{')
    else: g.boot = 'different'
    with pytest.raises(Denied): g.check_read(s)
    if bad != 'wrongboot':
        with pytest.raises(Denied): g.start_gate()
    else: assert not g.start_gate()


def test_safety_failure_latches_abort(g):
    s = g.arm(safe(), lambda: True)
    status = safe(); status['ros']['cmd_vel']['value']['lin'] = 1
    with pytest.raises(Denied): g.heartbeat(s, status)
    assert not g.start_gate()


def test_start_gate_does_not_deadlock_recovery_dispatch(g):
    with g.recovery_dispatch(): assert g.start_gate()


def test_missing_installation_denies_not_creates(tmp_path):
    g=Interlock(tmp_path/'absent',boot='x')
    with pytest.raises(OSError): g.start_gate()
    assert not g.root.exists()

def test_rollback_bytes_preserved(tmp_path):
    import hashlib
    live=tmp_path/'live'; backup=tmp_path/'backup'
    original=b'original service file\n'
    live.write_bytes(original); backup.write_bytes(live.read_bytes())
    expected=hashlib.sha256(original).hexdigest()
    live.write_bytes(b'candidate')
    assert hashlib.sha256(backup.read_bytes()).hexdigest()==expected
    live.write_bytes(backup.read_bytes())
    assert live.read_bytes()==original


def test_reader_token_is_single_use(g):
    s=g.arm(safe(),lambda:True);g.heartbeat(s,safe());g.begin_read(s)
    with g.reader(s):
        g.check_read(s)
        with pytest.raises(BlockingIOError): g.resume(s,safe(),True,lambda:True)
    with pytest.raises(Denied):
        with g.reader(s): pytest.fail('second reader admitted')


def test_expired_heartbeat_cannot_be_revived(g):
    s=g.arm(safe(),lambda:True);g.heartbeat(s,safe());g.begin_read(s)
    g.now[0]+=3
    with pytest.raises(Denied):g.heartbeat(s,safe())
    assert g.load()['phase']=='ABORTED'
    with pytest.raises(Denied):g.check_read(s)


def test_monitor_must_have_started_before_read(g):
    s=g.arm(safe(),lambda:True)
    with pytest.raises(Denied):g.begin_read(s)


def test_read_budget_expiry_is_durable(g):
    s=g.arm(safe(),lambda:True);g.heartbeat(s,safe());g.begin_read(s)
    d=g.load();d['read_deadline']=g.now[0];g.save(d)
    with pytest.raises(Denied):g.check_read(s)
    g.heartbeat(s,safe())
    with pytest.raises(Denied):g.check_read(s)
    assert g.load()['phase']=='ABORTED'


def test_restoration_requires_fresh_increasing_packets():
    from atlas_b1_interlock import verify_restored
    count=[10]
    def status():
        count[0]+=1
        s=safe();s['ros']['encoder_health']={'age':0,'value':{'packet_age_s':0,'packet_fresh':True,'serial_encoder_packets':count[0]}}
        return s
    state=lambda:{'ActiveState':'active','MainPID':'42','NRestarts':'0'}
    assert verify_restored(status,state,lambda _:None)
    cached=status()
    with pytest.raises(Denied):verify_restored(lambda:cached,state,lambda _:None)
    cached['ros']['encoder_health']['age']=2
    with pytest.raises(Denied):verify_restored(lambda:cached,state,lambda _:None)


def test_restoration_rejects_pid_change():
    from atlas_b1_interlock import verify_restored
    count=[0]
    def status():
        count[0]+=1
        s=safe();s['ros']['encoder_health']={'age':0,'value':{'packet_age_s':0,'packet_fresh':True,'serial_encoder_packets':count[0]}}
        return s
    states=iter([{'ActiveState':'active','MainPID':'1','NRestarts':'0'}, {'ActiveState':'active','MainPID':'2','NRestarts':'1'}])
    with pytest.raises(Denied):verify_restored(status,lambda:next(states),lambda _:None)


def test_port_query_timeout_never_retries(monkeypatch):
    import atlas_b1_interlock as module
    from types import SimpleNamespace
    import subprocess
    monkeypatch.setitem(sys.modules,'serial',SimpleNamespace())
    monkeypatch.setitem(sys.modules,'serial.tools',SimpleNamespace(list_ports=SimpleNamespace(comports=lambda:[SimpleNamespace(device='/dev/fake',vid=0x1a86,pid=0x7523,location='1-2.2.3')])))
    calls=[]
    def run(*a,**kw):
        calls.append(a);raise subprocess.TimeoutExpired('fuser',2)
    monkeypatch.setattr(module.subprocess,'run',run)
    with pytest.raises(subprocess.TimeoutExpired): module.verified_port_free('/dev/fake')
    assert len(calls)==1


def test_ambiguous_idle_cannot_bypass_latch(g):
    s=g.arm(safe(),lambda:True)
    d=g.load();d['phase']='IDLE';g.save(d)
    with pytest.raises(Denied):g.start_gate()


def test_nonfinite_lease_denied(g):
    g.arm(safe(),lambda:True)
    d=g.load();d['deadline']=float('nan');g.save(d)
    with pytest.raises(Denied):g.start_gate()

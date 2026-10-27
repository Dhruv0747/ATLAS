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
    g.begin_read(s)
    assert not g.start_gate()
    with pytest.raises(Denied): g.begin_read(s)


def test_crashed_monitor_timeout_never_releases(g):
    s = g.arm(safe(), lambda: True); g.begin_read(s)
    g.now[0] += 3
    with pytest.raises(Denied): g.check_read(s)
    assert not g.start_gate()
    g.now[0] += 1000
    with pytest.raises(Denied): g.heartbeat(s, safe())
    assert g.load()['phase'] == 'ABORTED' and not g.start_gate()


def test_explicit_recovery_and_one_start_only(g):
    s = g.arm(safe(), lambda: True); g.begin_read(s); g.abort(s)
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
    with pytest.raises(Denied): g.begin_read(s)
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

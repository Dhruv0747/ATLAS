"""Offline only: temporary state and simulated systemd/firewall operations."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('recovery_transaction', ROOT/'monitoring/atlas/persistent/recover_once.py')
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


@pytest.fixture
def state(tmp_path, monkeypatch):
    live = tmp_path/'state'; live.mkdir()
    evidence = tmp_path/'attempt'; evidence.mkdir()
    (live/'FAULT.json').write_text('{"reason":"legacy unknown","time":1}')
    (live/'observer-active.json').write_text('{"pid":123,"time":1}')
    (live/'last-health.json').write_text('{"time":1}')
    (live/'operations.lock').write_bytes(b'')
    monkeypatch.setattr(R, 'E', evidence)
    monkeypatch.setattr(R, 'EXPECTED_FAULT', R.digest(live/'FAULT.json'))
    monkeypatch.setattr(R, 'EXPECTED_STATE', {p.name:R.digest(p) for p in live.iterdir()})
    monkeypatch.setattr(R, 'G', SimpleNamespace(STATE=live))
    monkeypatch.setattr(R, 'cancel_expiry', Mock())
    monkeypatch.setattr(R, 'verify_lineage', lambda: None)   # lineage has its own regression test below
    return live, evidence


def test_archive_is_complete_durable_and_reset_is_single_use(state):
    live, evidence = state
    R.archive_state()
    manifest = json.loads((evidence/'state-manifest.json').read_text())
    assert set(manifest) == {p.name for p in live.iterdir()}
    metadata=json.loads((evidence/'state-metadata.json').read_text())
    assert metadata['FAULT.json']['mtime_ns']==(live/'FAULT.json').stat().st_mtime_ns
    assert all((evidence/'original-state'/n).read_bytes() == (live/n).read_bytes() for n in manifest)
    R.rearm()
    assert not (live/'FAULT.json').exists()
    assert not (live/'observer-active.json').exists()
    assert (live/'last-health.json').exists()
    with pytest.raises(Exception): R.rearm()


@pytest.mark.parametrize('damage', ['corrupt', 'changed', 'symlink', 'oversize', 'unexpected'])
def test_invalid_evidence_never_resets(state, damage):
    live, _ = state
    if damage == 'corrupt': (live/'FAULT.json').write_text('not json')
    elif damage == 'changed': (live/'FAULT.json').write_text('{"reason":"changed"}')
    elif damage == 'symlink': (live/'extra').symlink_to(live/'FAULT.json')
    elif damage == 'oversize': (live/'last-health.json').write_text('x'*1048577)
    else: (live/'unexpected').write_text('x')
    with pytest.raises(Exception): R.archive_state()
    assert (live/'FAULT.json').exists()


def test_archive_write_failure_leaves_latch(state, monkeypatch):
    live, _ = state
    monkeypatch.setattr(R, 'write', Mock(side_effect=OSError('disk full')))
    with pytest.raises(OSError): R.archive_state()
    assert (live/'FAULT.json').exists()


def test_changed_state_after_archive_rejected(state):
    live, _ = state
    R.archive_state()
    (live/'last-health.json').write_text('{}')
    with pytest.raises(Exception): R.rearm()
    assert (live/'FAULT.json').exists()


def test_corrupt_archive_rejected_before_reset(state):
    live, evidence = state
    R.archive_state()
    (evidence/'original-state'/'FAULT.json').write_text('{}')
    with pytest.raises(Exception): R.rearm()
    assert (live/'FAULT.json').exists()


@pytest.mark.parametrize('new_fault', [False, True])
def test_restore_retains_new_fault_or_exact_old_bytes(state, new_fault):
    live, evidence = state
    R.archive_state(); R.rearm()
    if new_fault: (live/'FAULT.json').write_text('{"reason":"new failure"}')
    R.restore_latch()
    if new_fault: assert json.loads((live/'FAULT.json').read_text())['reason'] == 'new failure'
    else: assert (live/'FAULT.json').read_bytes() == (evidence/'original-state'/'FAULT.json').read_bytes()


def test_second_archive_refused(state):
    R.archive_state()
    with pytest.raises(FileExistsError): R.archive_state()


def test_systemd_has_independent_cleanup_no_restart_and_hard_timeout():
    args = R.transient_command()
    text = ' '.join(args)
    assert 'RuntimeMaxSec=330' in text
    assert 'Restart=no' in text
    assert 'ExecStopPost=' in text and ' cleanup' in text
    assert 'TimeoutStopSec=30' in text
    assert 'KillMode=control-group' in text


def test_cleanup_failure_keeps_override_and_reports_fail(state, monkeypatch):
    _, evidence = state
    R.archive_state()
    R.write(evidence/'before.json', {'enabled':'enabled'})
    R.write(evidence/'mutation-intent.json', {})
    R.G.rollback = Mock(side_effect=RuntimeError('listener remains'))
    restore = Mock(); monkeypatch.setattr(R, 'restore_configuration', restore)
    monkeypatch.setattr(R, 'verify_cleanup', Mock())
    with pytest.raises(RuntimeError): R.cleanup()
    restore.assert_not_called()
    assert json.loads((evidence/'result.json').read_text())['cleanup'] == 'FAILED'


def test_cleanup_restores_latch_before_configuration(state, monkeypatch):
    live, evidence = state
    R.archive_state(); R.rearm()
    R.write(evidence/'before.json', {'enabled':'enabled'})
    R.write(evidence/'mutation-intent.json', {})
    events=[]
    R.G.rollback = lambda: events.append('rollback')
    monkeypatch.setattr(R, 'verify_cleanup', lambda: events.append('verified'))
    def restore():
        assert (live/'FAULT.json').exists()
        events.append('restore')
    monkeypatch.setattr(R, 'restore_configuration', restore)
    R.cleanup()
    assert events == ['rollback','verified','restore']
    assert json.loads((evidence/'result.json').read_text())['cleanup'] == 'VERIFIED'


def test_preflight_failure_does_not_invoke_cleanup_mutations(state, monkeypatch):
    R.G.rollback=Mock()
    monkeypatch.setattr(R, 'restore_configuration', Mock())
    R.cleanup()
    R.G.rollback.assert_not_called()


def test_false_success_or_kill_cannot_skip_cleanup(state, monkeypatch):
    _, evidence=state
    R.archive_state(); R.rearm()
    R.write(evidence/'before.json', {'enabled':'enabled'})
    R.write(evidence/'mutation-intent.json', {})
    R.write(evidence/'candidate-pass.json', {})
    monkeypatch.setattr(R, 'verify_success', Mock(side_effect=RuntimeError('watchdog dead')))
    monkeypatch.setattr(R, 'verify_cleanup', Mock())
    monkeypatch.setattr(R, 'restore_configuration', Mock())
    R.G.rollback=Mock()
    R.cleanup()
    R.G.rollback.assert_called_once()
    assert json.loads((evidence/'result.json').read_text())['result'] == 'FAIL'


def test_archive_corruption_cannot_prevent_stop(state, monkeypatch):
    _, evidence=state
    R.archive_state(); R.rearm()
    R.write(evidence/'mutation-intent.json', {})
    (evidence/'original-state'/'FAULT.json').write_text('corrupt')
    R.G.rollback=Mock()
    monkeypatch.setattr(R,'verify_cleanup',Mock())
    with pytest.raises(Exception): R.cleanup()
    R.G.rollback.assert_called_once()
    assert json.loads((evidence/'result.json').read_text())['cleanup']=='FAILED'


def test_restore_obeys_fault_writer_lock(state):
    import fcntl
    live, _=state
    R.archive_state(); R.rearm()
    with (live/'evidence.lock').open('w') as other:
        fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError): R.restore_latch()
        (live/'FAULT.json').write_text('{"reason":"new concurrent rejection"}')
    R.restore_latch()
    assert json.loads((live/'FAULT.json').read_text())['reason']=='new concurrent rejection'


def test_pending_start_is_allowed_but_failed_start_is_not(monkeypatch):
    monkeypatch.setattr(R.time,'sleep',lambda _:None)
    p=Mock(side_effect=[{'ActiveState':'inactive'},{'ActiveState':'activating'},{'ActiveState':'active'}])
    monkeypatch.setattr(R,'props',p)
    R.wait_active('fake',1)
    p.side_effect=None; p.return_value={'ActiveState':'failed'}
    with pytest.raises(RuntimeError): R.wait_active('fake',1)


def test_separate_expiry_is_bounded_and_never_starts_exporter():
    text=' '.join(R.expiry_command())
    assert '--on-active=410s' in text and 'TimeoutStartSec=30' in text
    assert text.endswith(' cleanup') and 'Restart=no' in text


def test_missing_client_receipt_aborts_candidate(state, monkeypatch):
    _, evidence=state
    R.archive_state(); R.rearm(); R.write(evidence/'mutation-intent.json',{})
    R.write(evidence/'candidate-pass.json',{})
    monkeypatch.setenv('SERVICE_RESULT','success')
    monkeypatch.setattr(R,'verify_success',Mock())
    monkeypatch.setattr(R,'verify_cleanup',Mock())
    monkeypatch.setattr(R,'restore_configuration',Mock())
    R.G.rollback=Mock()
    R.cleanup()
    R.G.rollback.assert_called_once()


@pytest.mark.parametrize('failure',['cancel','post-rename'])
def test_success_commit_failures_are_not_confused(state, monkeypatch, failure):
    _, evidence=state
    R.archive_state(); R.rearm(); R.write(evidence/'mutation-intent.json',{})
    R.write(evidence/'candidate-pass.json',{})
    monkeypatch.setenv('SERVICE_RESULT','success')
    for name in ('verify_success','verify_client','verify_restored_policy','verify_cleanup','restore_configuration'):
        monkeypatch.setattr(R,name,Mock())
    R.G.two_samples=Mock(); R.G.rollback=Mock()
    if failure=='cancel': monkeypatch.setattr(R,'cancel_expiry',Mock(side_effect=RuntimeError('bus unavailable')))
    else:
        original=R.write
        def write(path,value):
            original(path,value)
            if path.name=='result.json' and value.get('result')=='PASS': raise OSError('fsync failure')
        monkeypatch.setattr(R,'write',write)
    R.cleanup()
    if failure=='cancel':
        R.G.rollback.assert_not_called()
        assert json.loads((evidence/'result.json').read_text())['result']=='PASS'
    else:
        R.G.rollback.assert_called_once()
        assert json.loads((evidence/'result.json').read_text())['result']=='FAIL'


@pytest.mark.parametrize('failure',[None,'firewall','exporter','resource','interruption'])
def test_complete_transaction_with_simulated_services(state, monkeypatch, failure):
    import os
    import stat
    live,evidence=state
    firewall,watchdog,exporter=R.NAMES
    original={u:{'MainPID':'0','NRestarts':'0','ActiveState':'inactive','Restart':
                 'on-failure' if u==exporter else 'no','UnitFileState':'enabled' if u==exporter else 'static'} for u in R.NAMES}
    units={u:dict(p) for u,p in original.items()}; commands=[]; elapsed=[0.0]; sampled=[0]; has_firewall=[False]
    old_stat=Path.lstat
    def lstat(p,*a,**kw):
        if p==live: return SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0)
        return old_stat(p,*a,**kw)
    monkeypatch.setattr(Path,'lstat',lstat)
    old_digest=R.digest
    monkeypatch.setattr(R,'digest',lambda p:R.GUARD_SHA if p==R.GUARD else old_digest(p))
    monkeypatch.setenv('INVOCATION_ID','fake-unit')
    monkeypatch.setattr(R,'configurations',lambda:original)
    monkeypatch.setattr(R,'config_hashes',lambda:{'same':'hash'})
    monkeypatch.setattr(R,'baseline_rules',lambda:{'v4':'same','v6':'same'})
    monkeypatch.setattr(R,'drop',lambda u:evidence/'dropins'/u/R.DROP_NAME)
    (evidence/'dropins').mkdir()
    def props(u):
        p=dict(units[u]); p['Restart']='no' if R.drop(u).exists() else original[u]['Restart']; return p
    monkeypatch.setattr(R,'props',props)
    def run(*args):
        commands.append(args)
        if args[0]=='nft': return '{"nftables":[]}'
        if args[:2]==('systemctl','show'): return str(os.getpid())
        if args[:2]==('systemctl','is-active'): return 'active'
        if args[:2]==('systemctl','disable'): units[exporter]['UnitFileState']='disabled'
        if args[:2]==('systemctl','enable'): units[exporter]['UnitFileState']='enabled'
        if args[:3]==('systemctl','--no-block','start'):
            u=args[-1]
            if failure==('firewall' if u==firewall else 'exporter'): units[u]['ActiveState']='failed'
            else:
                units[u]['ActiveState']='active'; units[u]['MainPID']='0' if u==firewall else '456'
                if u==firewall: has_firewall[0]=True
                else: units[watchdog].update(ActiveState='active',MainPID='123')
        return ''
    monkeypatch.setattr(R,'run',run)
    R.G=SimpleNamespace(STATE=live,UNIT=exporter,WATCHDOG=watchdog,FIREWALL=firewall,
        trusted=Mock(),integrity=Mock(),verify_firewall=Mock(),no_fault=Mock(),two_samples=Mock(),
        cpu_counter=lambda:(0,0,0),firewall_present=lambda:has_firewall[0],
        listeners=lambda:units[exporter]['ActiveState']=='active')
    R.A=SimpleNamespace(services=lambda:'protected unchanged')
    monkeypatch.setattr(R.time,'monotonic',lambda:elapsed[0])
    monkeypatch.setattr(R.time,'sleep',lambda dt:elapsed.__setitem__(0,elapsed[0]+dt))
    def sample(admission=False):
        sampled[0]+=1; elapsed[0]+=1
        if sampled[0]>15 and failure in ('resource','interruption'):
            raise RuntimeError('CPU limit' if failure=='resource' else 'transaction interrupted')
    monkeypatch.setattr(R,'sample',sample)
    def supervised(action, seconds=10):
        sample(); result=action(); sample(); return result
    monkeypatch.setattr(R,'supervised',supervised)
    monkeypatch.setattr(R,'verify_client',Mock())
    def rollback():
        for p in units.values(): p.update(ActiveState='inactive',MainPID='0')
        units[exporter]['UnitFileState']='disabled'; has_firewall[0]=False
    R.G.rollback=rollback
    if failure:
        with pytest.raises(RuntimeError): R.worker()
        monkeypatch.setenv('SERVICE_RESULT','exit-code')
    else:
        R.worker(); monkeypatch.setenv('SERVICE_RESULT','success')
    R.cleanup()
    result=json.loads((evidence/'result.json').read_text())
    assert result['result']==('FAIL' if failure else 'PASS')
    starts=[c[-1] for c in commands if c[:3]==('systemctl','--no-block','start')]
    assert starts.count(firewall)==1 and starts.count(exporter)<=1
    assert set(starts)<=set(R.NAMES)
    assert all(not R.drop(u).exists() for u in R.NAMES)
    assert units[exporter]['UnitFileState']=='enabled'
    if failure:
        assert (live/'FAULT.json').read_bytes()==(evidence/'original-state'/'FAULT.json').read_bytes()
        assert all(p['MainPID']=='0' for p in units.values())


# ---- 2026-10-31 attempt 1 failure: exporter start deadline and redundant launcher stop
MEASURED_EXPORTER_STARTS_S = (3.629, 3.623, 3.598)       # systemd Starting->Started, Jetson journal


def _timed_unit(monkeypatch, active_after):
    clock = [0.0]
    monkeypatch.setattr(R.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(R.time, 'sleep', lambda dt: clock.__setitem__(0, clock[0] + dt))
    state = lambda: 'active' if active_after is not None and clock[0] >= active_after else 'activating'
    monkeypatch.setattr(R, 'props', lambda u: {'ActiveState': state()})
    return clock


def test_measured_exporter_start_fails_old_deadline_and_passes_new(monkeypatch):
    slowest = max(MEASURED_EXPORTER_STARTS_S)
    _timed_unit(monkeypatch, slowest)
    with pytest.raises(RuntimeError, match='startup deadline'):
        R.wait_active('exporter', 3)                         # reproduces attempt 1
    _timed_unit(monkeypatch, slowest)
    R.wait_active('exporter', R.EXPORTER_START_S)            # corrected deadline


def test_exporter_that_never_starts_still_fails_within_the_bound(monkeypatch):
    clock = _timed_unit(monkeypatch, None)
    with pytest.raises(RuntimeError, match='startup deadline'):
        R.wait_active('exporter', R.EXPORTER_START_S)
    assert clock[0] <= R.EXPORTER_START_S + 0.2               # finite: no open-ended wait


def test_deadline_margin_is_finite_and_step_bound_unchanged():
    assert 3 * max(MEASURED_EXPORTER_STARTS_S) <= R.EXPORTER_START_S <= 15
    assert R.START_STEP_S == 25 and R.WATCHDOG_START_S == 20  # outer hard cap unchanged
    src = (ROOT/'monitoring/atlas/persistent/recover_once.py').read_text()
    assert 'wait_active(G.UNIT,3)' not in src and 'wait_active(G.UNIT,EXPORTER_START_S)' in src


def test_new_attempt_never_reuses_attempt_one_identity():
    assert R.E != Path('/var/lib/atlas-monitoring-recovery-20261031')
    assert R.TX != 'atlas-monitoring-recovery-once-20261031'
    assert R.E not in (R.ATTEMPT1, R.ATTEMPT2, R.ATTEMPT3) and R.TX.endswith('-20261031-4')


@pytest.mark.parametrize('show,expect,stopped', [
    ('LoadState=not-found\nActiveState=inactive\n', 'already-finished', False),   # attempt 1: collected unit
    ('LoadState=loaded\nActiveState=failed\n', 'already-finished', False),
    ('LoadState=loaded\nActiveState=active\n', 'stop-requested', True)])
def test_launcher_stop_is_idempotent(monkeypatch, show, expect, stopped):
    calls = []
    def run(args, **kw):
        calls.append(args)
        return SimpleNamespace(stdout=show if args[1] == 'show' else '', returncode=0)
    monkeypatch.setattr(R.subprocess, 'run', run)
    assert R.stop_if_running() == expect
    assert any(a[:3] == ['systemctl', '--no-block', 'stop'] for a in calls) == stopped


def test_launcher_stop_never_raises_or_masks_the_original_error(monkeypatch):
    monkeypatch.setattr(R.subprocess, 'run', Mock(side_effect=OSError('bus down')))
    assert R.stop_if_running() == 'unknown'
    src = (ROOT/'monitoring/atlas/persistent/recover_once.py').read_text()
    start = src.split("if action=='start':")[1].split("elif action=='confirm-client'")[0]
    assert 'stop_if_running()' in start and "run('systemctl','--no-block','stop'" not in start


def _attempt1_lineage(tmp_path, monkeypatch, original, fault):
    """Retained attempt-1/attempt-2 evidence directories exactly as the real transaction leaves them."""
    a1, a2 = tmp_path/'a1', tmp_path/'a2'
    (a1/'original-state').mkdir(parents=True); a2.mkdir()
    (a1/'state-manifest.json').write_text(json.dumps(dict(original, **{'evidence.lock': R.EMPTY_SHA})))
    (a1/'original-state'/'FAULT.json').write_bytes(fault)
    (a1/'result.json').write_text('{"cleanup": "VERIFIED", "original_cause": "UNKNOWN", "result": "FAIL"}')
    (a2/'result.json').write_text('{"cleanup": "NO_MUTATION", "result": "FAIL"}')
    monkeypatch.setattr(R, 'ATTEMPT1', a1); monkeypatch.setattr(R, 'ATTEMPT2', a2)
    a3 = tmp_path/'a3'; (a3/'original-state').mkdir(parents=True)
    (a3/'state-manifest.json').write_text(json.dumps(R.STATE_BEFORE_ATTEMPT3))
    (a3/'original-state'/'FAULT.json').write_bytes(fault)
    (a3/'result.json').write_text('{"cleanup": "VERIFIED", "original_cause": "UNKNOWN", "result": "FAIL"}')
    monkeypatch.setattr(R, 'ATTEMPT3', a3); monkeypatch.setattr(R, 'ATTEMPT3_RESULT_SHA', R.digest(a3/'result.json'))
    monkeypatch.setattr(R, 'ATTEMPT1_RESULT_SHA', R.digest(a1/'result.json'))
    monkeypatch.setattr(R, 'ATTEMPT2_RESULT_SHA', R.digest(a2/'result.json'))
    return a1, a2


@pytest.mark.parametrize('tamper', [None, 'last-health', 'fault', 'extra', 'a1-manifest', 'a2-mutated', 'unverified', 'a3-manifest', 'a3-result'])
def test_attempt2_refusal_reproduced_and_only_verified_post_attempt1_state_accepted(tmp_path, monkeypatch, tamper):
    """2026-10-31 12:57 attempt 2: attempt 1 legitimately changed the state, so the pre-attempt-1 expectation refused."""
    live = tmp_path/'state'; live.mkdir(); evidence = tmp_path/'attempt'; evidence.mkdir()
    fault = b'{"reason":"original watchdog rejection","time":1}'
    files = {'FAULT.json': fault, 'observer-active.json': b'{"pid":1,"time":1}',
             'firewall-owned.json': b'{"table":"atlas_monitor","time":1}', 'last-health.json': b'{"time":1}',
             'operations.lock': b''}
    for n, b in files.items(): (live/n).write_bytes(b)
    original = {n: R.digest(live/n) for n in files}
    # What attempt 1 legitimately left behind (firewall + watchdog start, clean stop, rollback, latch restored).
    (live/'firewall-owned.json').write_bytes(b'{"table":"atlas_monitor","time":2}')
    (live/'last-health.json').write_bytes(b'{"time":2}')
    (live/'observer-active.json').unlink()
    (live/'rollback.json').write_bytes(b'{"result":"PASS","time":2}')
    (live/'evidence.lock').write_bytes(b'')
    verified = {p.name: R.digest(p) for p in live.iterdir()}
    monkeypatch.setattr(R, 'E', evidence); monkeypatch.setattr(R, 'G', SimpleNamespace(STATE=live))
    monkeypatch.setattr(R, 'EXPECTED_FAULT', R.digest(live/'FAULT.json')); monkeypatch.setattr(R, 'ORIGINAL_STATE', original)
    a1, a2 = _attempt1_lineage(tmp_path, monkeypatch, original, fault)

    # The exact attempt-2 failure: the stale pre-attempt-1 expectation.
    monkeypatch.setattr(R, 'EXPECTED_STATE', {k: v for k, v in original.items() if k != 'evidence.lock'})
    with pytest.raises(RuntimeError, match='retained evidence changed'): R.archive_state()

    monkeypatch.setattr(R, 'EXPECTED_STATE', verified)
    if tamper == 'last-health': (live/'last-health.json').write_bytes(b'{"time":3}')
    if tamper == 'fault': (live/'FAULT.json').write_bytes(b'{"reason":"replaced"}')
    if tamper == 'extra': (live/'unexpected.json').write_bytes(b'{}')
    if tamper == 'a1-manifest': (a1/'state-manifest.json').write_text('{}')
    if tamper == 'a2-mutated': (a2/'mutation-intent.json').write_text('{}')
    if tamper == 'unverified': monkeypatch.setattr(R, 'EXPECTED_STATE', {})
    if tamper == 'a3-manifest': (tmp_path/'a3'/'state-manifest.json').write_text('{}')
    if tamper == 'a3-result': (tmp_path/'a3'/'result.json').write_text('{"result": "PASS"}')
    if tamper:
        with pytest.raises(RuntimeError): R.archive_state()
        assert (live/'FAULT.json').exists() and not (evidence/'reset-intent.json').exists()   # latch kept
        return
    R.archive_state(); R.rearm()                     # absent observer-active.json must not crash the reset
    assert not (live/'FAULT.json').exists() and (evidence/'original-state'/'FAULT.json').read_bytes() == fault
    R.restore_latch()
    assert (live/'FAULT.json').read_bytes() == fault


def test_attempt3_constants_are_the_owner_verified_jetson_state():
    """Pinned values from the owner's 13:15 sudo read (the state attempt 3 archived); the latch hash is the original one."""
    assert R.STATE_BEFORE_ATTEMPT3['FAULT.json'] == R.EXPECTED_FAULT == '3715b150b880ed06d9e21f25006b81a699693328bb77a80155cf148dcdb1ae97'
    assert set(R.STATE_BEFORE_ATTEMPT3) == {'FAULT.json','evidence.lock','firewall-owned.json','last-health.json','operations.lock','rollback.json'}
    assert R.ORIGINAL_STATE['FAULT.json'] == R.EXPECTED_FAULT and 'observer-active.json' in R.ORIGINAL_STATE
    a1 = b'{"cleanup": "VERIFIED", "original_cause": "UNKNOWN", "result": "FAIL"}'; a2 = b'{"cleanup": "NO_MUTATION", "result": "FAIL"}'
    assert R.ATTEMPT1_RESULT_SHA == R.hashlib.sha256(a1).hexdigest() and R.ATTEMPT2_RESULT_SHA == R.hashlib.sha256(a2).hexdigest()

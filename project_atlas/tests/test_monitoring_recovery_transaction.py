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
    def restore(*a, **k):
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


@pytest.mark.parametrize('failure',[None,'firewall','exporter','resource','interruption','midinstall'])
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
    monkeypatch.setattr(R,'digest',lambda p:R.PREVIOUS_GUARD_SHA if p==R.GUARD else old_digest(p))
    # 2026-11-04 permanent transaction: install targets are temporary copies of the exact previous files.
    monkeypatch.setattr(R,'pwd',SimpleNamespace(getpwnam=lambda n:SimpleNamespace(pw_uid=1000)))
    cfg=evidence.parent/'live-config'; cfg.mkdir()
    install=[]
    for key,_,old,new in R.INSTALL:
        target=cfg/key; target.write_bytes(R.rendered(old)); target.chmod(0o644); install.append((key,target,old,new))
    monkeypatch.setattr(R,'INSTALL',tuple(install))
    unit_files={exporter:cfg/'exporter-unit',watchdog:cfg/'watchdog-unit'}
    monkeypatch.setenv('INVOCATION_ID','fake-unit')
    monkeypatch.setattr(R,'configurations',lambda:original)
    # Real hashes over the temporary install targets plus one unrelated file (review defect 3).
    (cfg/'atlas-monitor.nft').write_bytes(b'table inet atlas {}\n')
    hashed=[p for _,p,_,_ in install]+[cfg/'atlas-monitor.nft']
    monkeypatch.setattr(R,'config_hashes',lambda:{str(p):R.digest(p) for p in hashed})
    if failure=='midinstall':                         # review defect 1: worker dies after the first replace
        real_replace=R.replace; calls=[0]
        def flaky(path,data,m):
            calls[0]+=1
            if calls[0]==2: raise RuntimeError('CPU limit')
            real_replace(path,data,m)
        monkeypatch.setattr(R,'replace',flaky)
    monkeypatch.setattr(R,'baseline_rules',lambda:{'v4':'same','v6':'same'})
    monkeypatch.setattr(R,'drop',lambda u:evidence/'dropins'/u/R.DROP_NAME)
    (evidence/'dropins').mkdir()
    def props(u):
        p=dict(units[u])
        on_disk=R.unit_restart(unit_files[u].read_bytes()) if u in unit_files else original[u]['Restart']
        p['Restart']='no' if R.drop(u).exists() else on_disk; return p
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
    assert starts.count(firewall)==(0 if failure=='midinstall' else 1) and starts.count(exporter)<=1
    assert set(starts)<=set(R.NAMES)
    assert all(not R.drop(u).exists() for u in R.NAMES)
    assert units[exporter]['UnitFileState']=='enabled'
    if failure:
        assert (live/'FAULT.json').read_bytes()==(evidence/'original-state'/'FAULT.json').read_bytes()
        assert all(p['MainPID']=='0' for p in units.values())
    # 2026-11-04: PASS keeps the reviewed guard/units; FAIL restores the exact previous bytes.
    for key,target,old,new in R.INSTALL:
        assert target.read_bytes()==R.rendered(old if failure else new), key
        if (evidence/'config-metadata.json').exists():
            assert (evidence/'original-config'/key).read_bytes()==R.rendered(old)
    if failure in (None,'firewall','exporter','midinstall'): assert (evidence/'config-metadata.json').exists()
    if failure: assert result.get('cleanup')=='VERIFIED' and result.get('config')=='PREVIOUS_RESTORED', result
    # 2026-11-02 m2-permissions: CPU rejection inside prepare_override (disable + daemon-reload = two
    # PID-1 reloads under the strict sampler). Every enable/disable must skip its implicit reload, and
    # each configuration step reloads exactly once.
    toggles=[c for c in commands if c[:2] in (('systemctl','enable'),('systemctl','disable'))]
    assert toggles and all('--no-reload' in c for c in toggles)
    reloads=[c for c in commands if c==('systemctl','daemon-reload')]
    if not failure:
        assert len(reloads)==2                  # one in prepare_override, one in restore_configuration
    assert len(reloads)<=2


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
    old = [Path('/var/lib/atlas-monitoring-recovery-20261031'+suffix) for suffix in ('','-2','-3','-4','-5')]
    assert R.E not in old and R.E != Path('/var/lib/atlas-monitoring-recovery-m2-20261102')
    assert R.TX != 'atlas-monitoring-recovery-once-m2-20261102'
    assert R.TX != 'atlas-monitoring-recovery-once-m2-cpuevidence-20261102'


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


def test_current_incident_binding():
    # Owner's sudo state read 2026-11-04 13:51 IST: eight present files, observer-active.json PRESENT.
    assert R.EXPECTED_FAULT == '4f04831f22623fad52fa28676348153989291f37ca4b1e4f05069e26e79a7dc5'
    assert len(R.EXPECTED_STATE) == 8 and R.EXPECTED_ABSENT == ()
    assert R.EXPECTED_STATE['observer-active.json'] == '3da97cb57e24c8d881e384ab440fa2baf9f5cf25371691eeee658e92a37c3249'
    assert R.EXPECTED_STATE['rollback.json'] == '1f188cc96e99b4557a1f62503ad33a3fdc3b4cffc495c483d339576409803527'
    assert R.EXPECTED_STATE['fault-events.json'] == 'f23ce63f51d0f795272cc878790a36d44c88322d7944bbab87ec9c627947391f'
    assert R.EXPECTED_STATE['firewall-owned.json'] == '2212fe537ee251d867d8d7093effd941ddf5b969b299e3266cf3782358a727e4'
    assert R.EXPECTED_STATE['last-health.json'] == '35bd5fc4a5fe613a1f636d3f466a4aad3f5244489c9e429c86c65f2a2b91a36a'
    assert R.E.name == 'atlas-monitoring-recovery-m2-permanent-20261104'
    assert R.TX == 'atlas-monitoring-recovery-once-m2-permanent-20261104'
    assert R.GUARD_SHA.startswith('188d53db') and R.PREVIOUS_GUARD_SHA.startswith('27d4caca')
    R.verify_lineage()


@pytest.mark.parametrize('tamper', ['missing', 'fault', 'hash'])
def test_current_binding_rejects_incomplete_identity(monkeypatch, tamper):
    state = dict(R.EXPECTED_STATE)
    if tamper == 'missing': state.pop('fault-events.json')
    if tamper == 'fault': state['FAULT.json'] = '0'*64
    if tamper == 'hash': state['last-health.json'] = ''
    monkeypatch.setattr(R, 'EXPECTED_STATE', state)
    with pytest.raises(RuntimeError): R.verify_lineage()


def test_confirm_by_is_well_before_the_window_and_bounds_are_unchanged():
    """Attempt 3: confirm-client at start+~341 s missed the ~305 s check. The operator target is start+240 s."""
    msg = R.deadline_message(1793433014.8)                      # attempt 3's actual start time
    at = lambda d: R.time.strftime('%H:%M:%S', R.time.localtime(1793433014.8 + d))   # 13:25:19 / 13:24:14 IST
    assert at(305) in msg and at(240) in msg and at(120) in msg and 'Never confirm after' in msg
    assert R.CONFIRM_TARGET_S == 120 < R.CONFIRM_BY_S
    assert R.CONFIRM_BY_S + 60 <= 305
    src = (ROOT/'monitoring/atlas/persistent/recover_once.py').read_text()
    assert 'while time.monotonic()-start < 300:' in src and "'--on-active=410s'" in src and "'--property=RuntimeMaxSec=330'" in src
    assert "observation['cpu'] < 75 and observation['ram'] < 80" in src
    assert src.index('print(deadline_message(') < src.index('run(*expiry_command())')


@pytest.mark.parametrize('events', [[], [{'reason': 'fault latched; owner review required', 'time': 40.4}]])
def test_event_list_archive_and_exact_rollback(state, monkeypatch, events):
    live, evidence = state
    data = json.dumps(events).encode()
    (live/'fault-events.json').write_bytes(data)
    monkeypatch.setattr(R, 'EXPECTED_STATE', R.state_hashes())
    R.archive_state(); R.rearm(); R.restore_latch()
    assert (live/'fault-events.json').read_bytes() == data
    assert (evidence/'original-state'/'fault-events.json').read_bytes() == data
    assert R.verify_archive()['fault-events.json'] == R.digest(live/'fault-events.json')
    (evidence/'original-state'/'fault-events.json').write_bytes(b'[] changed')
    with pytest.raises(RuntimeError): R.verify_archive()


@pytest.mark.parametrize('name,value', [('fault-events.json', {}), ('fault-events.json', [None]),
    ('fault-events.json', [{}]*17), ('last-health.json', [])])
def test_invalid_event_shape_keeps_latch(state, monkeypatch, name, value):
    live, evidence = state
    (live/name).write_text(json.dumps(value))
    monkeypatch.setattr(R, 'EXPECTED_STATE', R.state_hashes())
    with pytest.raises(RuntimeError, match='invalid retained evidence'): R.archive_state()
    assert (live/'FAULT.json').exists()
    assert not (evidence/'reset-intent.json').exists()


@pytest.mark.parametrize('cpu,ram,ok', [(74.99,79.99,True),(75,60,False),(60,80,False)])
def test_incident_continuous_strict_limits(state, monkeypatch, cpu, ram, ok):
    R.G.EVIDENCE={}
    R.G.evidence_scalar=lambda value:value
    monkeypatch.setattr(R,'A',SimpleNamespace(sample=lambda *args:((R.time.monotonic(),100,50),None,{'cpu':cpu,'ram':ram})))
    if ok: R.sample(admission=False)
    else:
        with pytest.raises(RuntimeError,match='resource limit'): R.sample(admission=False)


def test_current_eight_file_archive_reset_restore(tmp_path, monkeypatch):
    live=tmp_path/'live';live.mkdir();evidence=tmp_path/'archive';evidence.mkdir()
    for name in R.EXPECTED_STATE:
        data = b'' if name.endswith('.lock') else b'[]' if name=='fault-events.json' else b'{"reason":"encoder movement"}'
        (live/name).write_bytes(data)
    original={p.name:p.read_bytes() for p in live.iterdir()}
    monkeypatch.setattr(R,'E',evidence)
    monkeypatch.setattr(R,'G',SimpleNamespace(STATE=live))
    monkeypatch.setattr(R,'EXPECTED_FAULT',R.digest(live/'FAULT.json'))
    monkeypatch.setattr(R,'EXPECTED_STATE',{p.name:R.digest(p) for p in live.iterdir()})
    R.archive_state();R.rearm();R.restore_latch()
    assert (live/'FAULT.json').read_bytes()==original['FAULT.json']
    assert (live/'fault-events.json').read_bytes()==original['fault-events.json']
    assert {p.name:p.read_bytes() for p in (evidence/'original-state').iterdir()}==original
    assert len(R.verify_archive())==8


# ---- 2026-11-04 permanent transaction: reviewed guard/unit installation and exact-byte rollback
EXPECTED_PACKAGE = {
    'guard.py': '188d53db127ceb49e4c1c36fed61caacd05b3ab4f70e190f08f83c3b6fba802a',
    'previous-guard.py': '27d4cacae47044a1675cf911aad60a69fc78dd5b85de14bdb6d5480288a560e1'}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(R,'pwd',SimpleNamespace(getpwnam=lambda n:SimpleNamespace(pw_uid=1000)))
    e=tmp_path/'attempt'; e.mkdir(); live=tmp_path/'live'; live.mkdir()
    install=[]
    for key,_,old,new in R.INSTALL:
        p=live/key; p.write_bytes(R.rendered(old)); p.chmod(0o644); install.append((key,p,old,new))
    monkeypatch.setattr(R,'E',e); monkeypatch.setattr(R,'INSTALL',tuple(install))
    monkeypatch.setattr(R,'G',SimpleNamespace(trusted=lambda p:None),raising=False)
    monkeypatch.setattr(R,'config_hashes',lambda:{str(p):R.digest(p) for _,p,_,_ in install})
    return e, install


def test_package_guard_and_unit_hashes_are_the_reviewed_files():
    for name, sha in EXPECTED_PACKAGE.items():
        assert R.digest(R.BASE/name)==sha
    assert R.GUARD_SHA==EXPECTED_PACKAGE['guard.py'] and R.PREVIOUS_GUARD_SHA==EXPECTED_PACKAGE['previous-guard.py']
    assert R.digest(R.BASE/'atlas-monitoring-watchdog.service').startswith('21f8ad39')
    assert R.digest(R.BASE/'atlas-monitoring-exporter.service.in').startswith('74b22487')
    assert {'previous-guard.py','previous-atlas-monitoring-watchdog.service',
            'previous-atlas-monitoring-exporter.service.in'} <= R.PACKAGE_FILES


def test_install_backs_up_exact_previous_bytes_then_installs_reviewed(cfg):
    e,install=cfg; R.install_config()
    meta=json.loads((e/'config-metadata.json').read_text())
    for key,p,old,new in install:
        assert (e/'original-config'/key).read_bytes()==R.rendered(old)
        assert p.read_bytes()==R.rendered(new) and (p.stat().st_mode & 0o777)==0o644
        assert meta[key]['previous_sha256']!=meta[key]['new_sha256']
    assert json.loads((e/'installed-config.json').read_text())=={str(p):R.digest(p) for _,p,_,_ in install}
    with pytest.raises(FileExistsError): R.install_config()          # never twice in one attempt


def test_install_refuses_unreviewed_live_file_and_changes_nothing(cfg):
    e,install=cfg; install[1][1].write_bytes(b'[Unit]\n# local edit\n')
    before={str(p):p.read_bytes() for _,p,_,_ in install}
    with pytest.raises(RuntimeError, match='not the reviewed previous'): R.install_config()
    assert {str(p):p.read_bytes() for _,p,_,_ in install}==before and not (e/'config-metadata.json').exists()


def test_restore_previous_is_exact_and_idempotent(cfg):
    e,install=cfg; R.install_config()
    assert R.restore_previous_config() is True
    for _,p,old,_ in install: assert p.read_bytes()==R.rendered(old) and (p.stat().st_mode & 0o777)==0o644
    assert R.restore_previous_config() is True
    for _,p,old,_ in install: assert p.read_bytes()==R.rendered(old)


def test_restore_without_install_is_a_no_op(cfg):
    assert R.restore_previous_config() is False


@pytest.mark.parametrize('damage',['third_version','corrupt_backup'])
def test_restore_refuses_third_version_or_corrupt_backup(cfg,damage):
    e,install=cfg; R.install_config()
    if damage=='third_version': install[0][1].write_bytes(b'# someone else\n')
    else: (e/'original-config'/'exporter-unit').write_bytes(b'x')
    with pytest.raises(RuntimeError): R.restore_previous_config()
    if damage=='third_version': assert install[0][1].read_bytes()==b'# someone else\n'


def test_expected_policy_comes_from_the_reviewed_unit_files(cfg, monkeypatch):
    e,_=cfg
    (e/'before.json').write_text(json.dumps({'units':{u:{'Restart':'no'} for u in R.NAMES}}))
    new=R.expected_policy(True); old=R.expected_policy(False)
    assert old=={u:'no' for u in R.NAMES}
    assert new['atlas-monitoring-firewall.service']=='no'
    for u,src in (('atlas-monitoring-watchdog.service','atlas-monitoring-watchdog.service'),
                  ('atlas-monitoring-exporter.service','atlas-monitoring-exporter.service.in')):
        assert new[u]==R.unit_restart(R.rendered(src)) and new[u]!='no'


# ---- 2026-11-04 independent review: interrupted install, leftover temp files, real config hash checks
@pytest.fixture
def mix(cfg, monkeypatch, tmp_path):
    e,install=cfg
    other=tmp_path/'atlas-monitor.nft'; other.write_bytes(b'table inet atlas {}\n')
    paths=[p for _,p,_,_ in install]+[other]
    monkeypatch.setattr(R,'config_hashes',lambda:{str(p):R.digest(p) for p in paths})
    (e/'before.json').write_text(json.dumps({'config_hashes':R.config_hashes()}))
    return e,install,other


@pytest.mark.parametrize('stop_after',[0,1,2,3])
def test_interrupted_install_is_accepted_by_cleanup_then_restored_exactly(mix,monkeypatch,stop_after):
    e,install,other=mix; before=json.loads((e/'before.json').read_text())['config_hashes']
    real=R.replace; n=[0]
    def flaky(path,data,m):
        if n[0]==stop_after: raise RuntimeError('CPU limit')          # supervised thread abandoned here
        n[0]+=1; real(path,data,m)
    monkeypatch.setattr(R,'replace',flaky)
    if stop_after<3:
        with pytest.raises(RuntimeError): R.install_config()
    else:
        R.install_config(); (e/'installed-config.json').unlink()        # died before the final write
    monkeypatch.setattr(R,'replace',real)
    assert R.config_reviewed_mix(before)                               # cleanup proceeds, no FAILED
    assert R.restore_previous_config() and R.config_hashes()==before
    assert not any(R.os.path.lexists(R.tmp_path(p)) for _,p,_,_ in install)


def test_cleanup_mix_check_rejects_any_unreviewed_change(mix):
    e,install,other=mix; before=json.loads((e/'before.json').read_text())['config_hashes']
    R.install_config(); assert R.config_reviewed_mix(before)
    other.write_bytes(b'changed\n'); assert not R.config_reviewed_mix(before)
    other.write_bytes(b'table inet atlas {}\n'); install[0][1].write_bytes(b'# third\n')
    assert not R.config_reviewed_mix(before)


def test_mix_without_metadata_requires_previous_exactly(mix):
    e,install,other=mix; before=json.loads((e/'before.json').read_text())['config_hashes']
    assert R.config_reviewed_mix(before)
    install[1][1].write_bytes(R.rendered(install[1][3])); assert not R.config_reviewed_mix(before)


def test_failed_write_leaves_no_temp_file(mix,monkeypatch):
    e,install,_=mix
    monkeypatch.setattr(R.os,'fsync',Mock(side_effect=OSError('EIO')))
    with pytest.raises(OSError): R.replace(install[0][1],b'x',{'uid':0,'gid':0,'mode':0o644})
    assert not R.os.path.lexists(R.tmp_path(install[0][1]))
    assert install[0][1].read_bytes()==R.rendered(install[0][2])


def test_killed_attempt_temp_file_is_removed_by_restore(mix):
    e,install,_=mix; before=json.loads((e/'before.json').read_text())['config_hashes']
    R.install_config(); R.tmp_path(install[0][1]).write_bytes(b'partial')
    assert R.restore_previous_config() and R.config_hashes()==before
    assert not R.os.path.lexists(R.tmp_path(install[0][1]))


def test_restore_refuses_non_regular_temp_entry(mix):
    e,install,_=mix; R.install_config(); R.tmp_path(install[0][1]).symlink_to('/etc/passwd')
    with pytest.raises(RuntimeError, match='unexpected temporary'): R.restore_previous_config()
    assert R.tmp_path(install[0][1]).is_symlink()


def test_install_refuses_pre_existing_temp_file_and_changes_nothing(mix):
    e,install,_=mix; R.tmp_path(install[2][1]).write_bytes(b'someone else')
    with pytest.raises(RuntimeError, match='temporary file exists'): R.install_config()
    assert all(p.read_bytes()==R.rendered(old) for _,p,old,_ in install)
    assert not (e/'config-metadata.json').exists() and R.tmp_path(install[2][1]).read_bytes()==b'someone else'

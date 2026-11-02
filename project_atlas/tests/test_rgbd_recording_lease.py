"""Existing controller only, mocked child; never starts hardware."""
import sys
from pathlib import Path
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_vision3d_runtime as R

@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setattr(R.time,'monotonic',lambda:100.)
    monkeypatch.setattr(R,'driver_args',lambda mode:[])
    monkeypatch.setattr(R,'startup_sample',lambda:{})
    child=Mock();child.poll.return_value=None
    popen=Mock(return_value=child);monkeypatch.setattr(R.subprocess,'Popen',popen)
    return R.ViewerSession(),child,popen

def test_recording_lease_cannot_be_renewed_by_browser(runtime):
    session,child,popen=runtime;owner=object()
    session.start('concurrent',capture_owner=owner,deadline=150.)
    assert popen.call_args.kwargs['env'][R.CAPTURE_DEADLINE]=='150.0'
    child.stdin.write.reset_mock()
    session.touch();child.stdin.write.assert_not_called()
    session.touch(capture_owner=owner);child.stdin.write.assert_called_once()
    with pytest.raises(ValueError):session.release_capture(object())
    with pytest.raises(ValueError):session.release_capture(owner)
    child.poll.return_value=0
    session.release_capture(owner)
    assert session.capture_owner is None

@pytest.mark.parametrize('deadline',[100.,99.,161.,float('nan'),float('inf'),True])
def test_invalid_deadline_never_starts(runtime,deadline):
    session,child,popen=runtime
    with pytest.raises(ValueError):session.start('concurrent',capture_owner=object(),deadline=deadline)
    popen.assert_not_called()

def test_legacy_viewer_keeps_existing_lease(runtime):
    session,child,popen=runtime;session.start('depth')
    assert R.CAPTURE_DEADLINE not in popen.call_args.kwargs['env']
    child.stdin.write.reset_mock();session.touch();child.stdin.write.assert_called_once()

def test_worker_deadline_includes_parent_startup():
    assert R.session_deadline(110.,'150.0')==150.
    assert R.session_deadline(110.,None)==170.
    for value in ('nan','inf','109','171','bad'):
        with pytest.raises(ValueError):R.session_deadline(110.,value)


def test_existing_safety_refresh_and_stale_failure():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
    from rgbd_recording import ExistingSafety
    from test_calibration_capture import observation
    clock=[0.];counter=[(0,0),(100,40),(200,80)]
    def sleep(t):clock[0]+=t
    observe=Mock(side_effect=lambda cpu,w:dict(observation(clock[0]),cpu=cpu,cpu_window_s=w))
    provider=ExistingSafety(observe,clock=lambda:clock[0],sleep=sleep,counters=lambda:counter.pop(0))
    assert provider()['cpu']==60
    clock[0]=1.5;provider();assert observe.call_count==1
    clock[0]=2.;provider();assert observe.call_count==2
    clock[0]=3.2
    with pytest.raises((ValueError,IndexError)):provider()

def test_host_missing_cache_does_not_start():
    from rgbd_recording import host_binding
    with pytest.raises(ValueError,match='disabled'):host_binding(object())


@pytest.mark.parametrize('values',[(75.,60.,60.),(60.,80.,60.),(60.,60.,70.),(float('nan'),60.,60.)])
def test_capture_worker_rejects_exact_limits(values):
    with pytest.raises(ValueError):R.limits(*values,strict=True)

def test_capture_worker_accepts_below_limits():
    R.limits(74.99,79.99,69.99,strict=True)

def test_worker_uses_absolute_capture_deadline(monkeypatch):
    from test_vision3d_stage31b_guard import Sim
    monkeypatch.setenv(R.CAPTURE_DEADLINE,'5008.0')
    alarm=Mock();monkeypatch.setattr(R.signal,'setitimer',alarm)
    s=Sim().run('concurrent')
    assert s.state['driver_stopped'] and s.clock.now()<=5009
    assert s.state['deadline_monotonic_s']==5008
    assert alarm.call_args_list[0].args==(R.signal.ITIMER_REAL,8.)
    assert alarm.call_args_list[-1].args==(R.signal.ITIMER_REAL,0)


def test_native_deadline_interrupts_blocked_worker_read():
    import time,signal
    previous=signal.getsignal(signal.SIGALRM)
    started=time.monotonic()
    try:
        R.arm_capture_deadline(started+.05)
        with pytest.raises(RuntimeError,match='absolute deadline'):
            time.sleep(1)  # represents a blocked local read, no hardware
        assert time.monotonic()-started<.5
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)

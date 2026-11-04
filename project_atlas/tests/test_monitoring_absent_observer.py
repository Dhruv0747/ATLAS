"""Focused absent-observer archive/rollback checks; no services or network."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

@pytest.fixture
def env(tmp_path, monkeypatch):
    spec=importlib.util.spec_from_file_location('absence_recovery',Path(__file__).resolve().parents[2]/'monitoring/atlas/persistent/recover_once.py')
    r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
    live=tmp_path/'live';live.mkdir(); out=tmp_path/'archive';out.mkdir()
    for name in r.EXPECTED_STATE:
        (live/name).write_bytes(b'' if name.endswith('.lock') else b'[]' if name=='fault-events.json' else b'{"evidence":"fixture"}')
        (live/name).chmod(0o600)
    monkeypatch.setattr(r,'E',out);monkeypatch.setattr(r,'G',SimpleNamespace(STATE=live))
    monkeypatch.setattr(r,'EXPECTED_FAULT',r.digest(live/'FAULT.json'))
    monkeypatch.setattr(r,'EXPECTED_STATE',{p.name:r.digest(p) for p in live.iterdir()})
    return r,live,out

def test_seven_files_and_explicit_absence_preserved(env):
    r,live,out=env;r.archive_state()
    assert len(r.verify_archive())==7
    assert json.loads((out/'state-absent.json').read_text())==['observer-active.json']
    assert all((out/'original-state'/n).read_bytes()==(live/n).read_bytes() for n in r.EXPECTED_STATE)
    assert not (out/'original-state'/'observer-active.json').exists()

@pytest.mark.parametrize('kind',['empty','json','dangling_symlink'])
def test_observer_presence_rejected_without_reset(env,kind):
    r,live,out=env;p=live/'observer-active.json'
    if kind=='dangling_symlink':p.symlink_to(live/'missing')
    else:p.write_bytes(b'' if kind=='empty' else b'{}')
    with pytest.raises(RuntimeError):r.archive_state()
    assert (live/'FAULT.json').exists();assert not (out/'reset-intent.json').exists()

@pytest.mark.parametrize('damage',['absence','bytes','added_observer'])
def test_archive_tampering_prevents_reset(env,damage):
    r,live,out=env;r.archive_state()
    if damage=='absence':(out/'state-absent.json').write_text('[]')
    elif damage=='bytes':(out/'original-state'/'FAULT.json').write_text('{}')
    else:(out/'original-state'/'observer-active.json').write_text('{}')
    with pytest.raises(RuntimeError):r.rearm()
    assert (live/'FAULT.json').exists()

@pytest.mark.parametrize('new_fault',[False,True])
def test_rollback_restores_fault_not_observer_and_retains_new_fault(env,new_fault):
    r,live,out=env;r.archive_state();r.rearm()
    if new_fault:(live/'FAULT.json').write_bytes(b'{"reason":"new"}')
    r.restore_latch()
    assert (live/'FAULT.json').read_bytes()==(b'{"reason":"new"}' if new_fault else (out/'original-state'/'FAULT.json').read_bytes())
    assert not (live/'observer-active.json').exists()
    with pytest.raises(Exception):r.rearm()

def test_late_observer_before_reset_rejected(env):
    r,live,out=env;r.archive_state();(live/'observer-active.json').write_text('{}')
    with pytest.raises(RuntimeError):r.rearm()
    assert (live/'FAULT.json').exists()

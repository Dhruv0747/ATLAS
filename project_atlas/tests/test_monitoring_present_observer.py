"""Focused present-observer archive/rollback checks (2026-11-04 permanent transaction); no services or network."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

EVENTS = json.dumps([{'reason': 'fixture', 'n': i} for i in range(11)]).encode()


@pytest.fixture
def env(tmp_path, monkeypatch):
    spec=importlib.util.spec_from_file_location('present_recovery',Path(__file__).resolve().parents[2]/'monitoring/atlas/persistent/recover_once.py')
    r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
    live=tmp_path/'live';live.mkdir(); out=tmp_path/'archive';out.mkdir()
    for name in r.EXPECTED_STATE:
        (live/name).write_bytes(b'' if name.endswith('.lock') else EVENTS if name=='fault-events.json' else b'{"evidence":"'+name.encode()+b'"}')
        (live/name).chmod(0o600)
    monkeypatch.setattr(r,'E',out);monkeypatch.setattr(r,'G',SimpleNamespace(STATE=live))
    monkeypatch.setattr(r,'EXPECTED_FAULT',r.digest(live/'FAULT.json'))
    monkeypatch.setattr(r,'EXPECTED_STATE',{p.name:r.digest(p) for p in live.iterdir()})
    return r,live,out


def test_production_binding_requires_eight_present_files_including_observer():
    spec=importlib.util.spec_from_file_location('binding',Path(__file__).resolve().parents[2]/'monitoring/atlas/persistent/recover_once.py')
    r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
    assert len(r.EXPECTED_STATE)==8 and 'observer-active.json' in r.EXPECTED_STATE and r.EXPECTED_ABSENT==()


def test_eight_files_and_eleven_events_preserved_exactly(env):
    r,live,out=env;r.archive_state()
    assert len(r.verify_archive())==8
    assert json.loads((out/'state-absent.json').read_text())==[]
    assert all((out/'original-state'/n).read_bytes()==(live/n).read_bytes() for n in r.EXPECTED_STATE)
    assert len(json.loads((out/'original-state'/'fault-events.json').read_text()))==11
    meta=json.loads((out/'state-metadata.json').read_text())
    assert set(meta)==set(r.EXPECTED_STATE) and all(m['mode']==0o600 for m in meta.values())


@pytest.mark.parametrize('kind',['missing','empty','other_json','symlink'])
def test_observer_change_rejected_without_reset(env,kind):
    r,live,out=env;p=live/'observer-active.json'
    if kind=='symlink': data=p.read_bytes(); p.unlink(); (live/'copy').write_bytes(data); p.symlink_to(live/'copy')
    elif kind=='missing': p.unlink()
    else: p.write_bytes(b'' if kind=='empty' else b'{}')
    with pytest.raises(RuntimeError):r.archive_state()
    assert (live/'FAULT.json').exists();assert not (out/'reset-intent.json').exists()


def test_changed_event_list_rejected_without_reset(env):
    r,live,out=env;(live/'fault-events.json').write_bytes(json.dumps([{'n':i} for i in range(12)]).encode())
    with pytest.raises(RuntimeError):r.archive_state()
    assert (live/'FAULT.json').exists()


@pytest.mark.parametrize('damage',['absence','bytes','removed_observer','extra_member'])
def test_archive_tampering_prevents_reset(env,damage):
    r,live,out=env;r.archive_state()
    if damage=='absence':(out/'state-absent.json').write_text('["observer-active.json"]')
    elif damage=='bytes':(out/'original-state'/'FAULT.json').write_text('{}')
    elif damage=='removed_observer':(out/'original-state'/'observer-active.json').unlink()
    else:(out/'original-state'/'extra.json').write_text('{}')
    with pytest.raises(RuntimeError):r.rearm()
    assert (live/'FAULT.json').exists() and (live/'observer-active.json').exists()


def test_rearm_removes_only_the_two_reviewed_markers(env):
    r,live,out=env;r.archive_state();r.rearm()
    assert not os.path.lexists(live/'FAULT.json') and not os.path.lexists(live/'observer-active.json')
    assert {p.name for p in live.iterdir()}==set(r.EXPECTED_STATE)-{'FAULT.json','observer-active.json'}
    assert (live/'fault-events.json').read_bytes()==EVENTS


@pytest.mark.parametrize('new_fault',[False,True])
def test_rollback_restores_fault_never_stale_observer_and_retains_new_fault(env,new_fault):
    r,live,out=env;r.archive_state();r.rearm()
    if new_fault:(live/'FAULT.json').write_bytes(b'{"reason":"new"}')
    r.restore_latch()
    assert (live/'FAULT.json').read_bytes()==(b'{"reason":"new"}' if new_fault else (out/'original-state'/'FAULT.json').read_bytes())
    # The archived marker described a listener that is no longer running; it stays only in the archive.
    assert not (live/'observer-active.json').exists() and (out/'original-state'/'observer-active.json').exists()
    with pytest.raises(Exception):r.rearm()


def test_late_observer_change_before_reset_rejected(env):
    r,live,out=env;r.archive_state();(live/'observer-active.json').write_text('{"changed":1}')
    with pytest.raises(RuntimeError):r.rearm()
    assert (live/'FAULT.json').exists()

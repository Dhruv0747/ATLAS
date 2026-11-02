"""Offline binding only: temporary files, no services, ROS or camera."""
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
import web_activation_supervisor as S


def test_missing_snapshot_refuses_before_mutation(tmp_path,monkeypatch):
    monkeypatch.setattr(S,'verify_package',lambda:None)
    monkeypatch.setattr(S,'policy',lambda *_:pytest.fail('policy touched'))
    monkeypatch.setattr(S,'Consumer',lambda *a:SimpleNamespace(check=lambda *_:(_ for _ in ()).throw(FileNotFoundError('no snapshot'))))
    with pytest.raises(FileNotFoundError): S.run(tmp_path)
    assert not (tmp_path/'restart-policy.json').exists()


@pytest.mark.parametrize('damage',[None,'missing','changed'])
def test_frozen_dependency_binding(tmp_path,monkeypatch,damage):
    control=tmp_path/'control';control.mkdir();dep=control/'helper.py';dep.write_bytes(b'pass\n')
    monkeypatch.setattr(S,'CONTROL',control)
    monkeypatch.setattr(S,'DEPENDENCIES',{'helper.py':hashlib.sha256(dep.read_bytes()).hexdigest()})
    monkeypatch.setattr(S,'REVIEW',tmp_path)
    (tmp_path/'payload').write_bytes(b'reviewed')
    manifest=tmp_path/'DEPLOYMENT_SHA256SUMS';manifest.write_text(hashlib.sha256(b'reviewed').hexdigest()+'  payload\n')
    monkeypatch.setattr(S,'EXPECTED',hashlib.sha256(manifest.read_bytes()).hexdigest())
    if damage=='missing':dep.unlink()
    if damage=='changed':dep.write_bytes(b'changed')
    if damage:
        with pytest.raises((OSError,ValueError)): S.verify_package()
    else:S.verify_package()


@pytest.mark.parametrize('cpu,ram,reject',[(74.99,79.99,False),(75,60,True),(60,80,True)])
def test_bound_resource_admission(cpu,ram,reject):
    helper=SimpleNamespace(resource_check=lambda *args:dict(cpu_pct=cpu,ram_pct=ram,temperature_c=60,failed=[]))
    if reject:
        with pytest.raises(ValueError):S.checked_resources(helper,cpu,{}, {})
    else: assert not S.checked_resources(helper,cpu,{}, {})['failed']

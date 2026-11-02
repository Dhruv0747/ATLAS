"""Offline rehearsals against private captured live bytes; no network/hardware.
Set ATLAS_MAPPING_TEST_PACKAGE / ATLAS_MAPPING_TEST_INSPECTION explicitly.
"""
import base64,copy,json,os,shutil,sys,time
from pathlib import Path
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import mapping_install_once as I

def safe():return {"received_mono":time.monotonic()}

@pytest.fixture
def rig(tmp_path):
    package=os.environ.get('ATLAS_MAPPING_TEST_PACKAGE');inspection=os.environ.get('ATLAS_MAPPING_TEST_INSPECTION')
    if not package or not inspection:pytest.skip('explicit private live-byte fixture required')
    pkg=tmp_path/'package';shutil.copytree(package,pkg)
    root=tmp_path/'isolated-live';root.mkdir()
    j=json.loads(Path(inspection).read_text());m=json.loads((pkg/'INSTALL.json').read_text())
    for name,meta in m['existing_dirs'].items():
        p=root/name;p.mkdir(parents=True,exist_ok=True);p.chmod(meta['mode']);os.chown(p,meta['uid'],meta['gid'])
    for name,row in j['files'].items():
        if not row['exists']:continue
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        source=tmp_path/'original';source.write_bytes(base64.b64decode(row['bytes']))
        I.put(source,p,row)
    return root,pkg,m

def test_full_install_and_exact_metadata_rollback(rig):
    root,pkg,m=rig;guard=Mock(side_effect=safe);identity=Mock(return_value='same PIDs and restarts')
    assert I.transact(root,pkg,m,guard,identity)['result']=='PASS'
    assert guard.call_count==len(m['files'])+2
    for row in m['files']:assert I.matches(root/row['path'],row['after'],row['installed'])
    assert I.rollback(root,pkg,m)=='EXACT_BYTES_AND_METADATA_VERIFIED'
    I.verify_baseline(root,m)
    for row in m['files']:
        if row['before'] is not None:
            assert (root/row['path']).stat().st_mtime_ns==row['original']['mtime_ns']

@pytest.mark.parametrize('index',range(1,21))
def test_each_partial_write_rolls_back(rig,index):
    root,pkg,m=rig
    with pytest.raises(RuntimeError,match='injected'):I.transact(root,pkg,m,safe,lambda:'same',fail_after=index)
    I.verify_baseline(root,m)

def test_backup_tamper_prevents_any_install(rig):
    root,pkg,m=rig;row=next(f for f in m['files'] if f['before'])
    (pkg/'rollback'/row['path']).write_bytes(b'bad')
    with pytest.raises(ValueError,match='rollback mismatch'):I.transact(root,pkg,m,safe,lambda:'same')
    I.verify_baseline(root,m)

def test_live_drift_prevents_any_install(rig):
    root,pkg,m=rig;row=next(f for f in m['files'] if f['before'])
    p=root/row['path'];p.write_bytes(b'later owner change')
    with pytest.raises(ValueError,match='baseline drift'):I.transact(root,pkg,m,safe,lambda:'same')
    assert p.read_bytes()==b'later owner change'

def test_guard_failure_and_interruption_restore(rig):
    root,pkg,m=rig;count=[0]
    def guard():
        count[0]+=1
        if count[0]==5:raise KeyboardInterrupt('offline interruption')
        return safe()
    with pytest.raises(KeyboardInterrupt):I.transact(root,pkg,m,guard,lambda:'same')
    I.verify_baseline(root,m)

def test_service_change_restores_without_service_operations(rig):
    root,pkg,m=rig;identity=Mock(side_effect=['before','before','changed'])
    with pytest.raises(ValueError,match='service identity'):I.transact(root,pkg,m,safe,identity)
    I.verify_baseline(root,m)

def test_rollback_refuses_later_owner_edits(rig):
    root,pkg,m=rig;I.transact(root,pkg,m,safe,lambda:'same')
    row=m['files'][0];p=root/row['path'];p.write_bytes(b'new owner change')
    with pytest.raises(ValueError,match='later drift'):I.rollback(root,pkg,m)
    assert p.read_bytes()==b'new owner change'

def test_new_file_collision_and_symlink_rejected(rig,tmp_path):
    root,pkg,m=rig;row=next(f for f in m['files'] if f['before'] is None and (root/f['path']).parent.exists())
    p=root/row['path'];p.symlink_to(tmp_path/'foreign')
    with pytest.raises(ValueError):I.transact(root,pkg,m,safe,lambda:'same')

def test_mode_change_rejected(rig):
    root,pkg,m=rig;row=next(f for f in m['files'] if f['before']);p=root/row['path'];p.chmod(0o600)
    with pytest.raises(ValueError,match='baseline drift'):I.transact(root,pkg,m,safe,lambda:'same')

def test_xattrs_and_permissions_preserved(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'original');os.setxattr(source,'user.atlas_test',b'private metadata')
    meta=I.metadata(source);meta['atime_ns']=source.stat().st_atime_ns;dest=tmp_path/'dest'
    I.put(source,dest,meta)
    assert I.matches(dest,I.sha(source),meta)
    assert os.getxattr(dest,'user.atlas_test')==b'private metadata'

def test_missing_web_patches_and_safety_defaults(rig):
    root,pkg,m=rig
    source=(pkg/'payload/scripts/atlas_status_web.py').read_text()
    assert 'ATLAS_RGBD_EVIDENCE_CACHE' in source and 'atlas_map3d_web.serve(self)' in source
    assert "'map3d': 'map3d.html'" in (pkg/'payload/scripts/atlas_web_v2.py').read_text()
    assert json.loads((pkg/'payload/config/onboard_mapping.json').read_text())['enabled'] is False
    assert all(not f['path'].startswith(('web/v2/index','web/v2/vision3d','web/v2/material','.config/')) for f in m['files'])


def test_stale_guard_prevents_payload_write(rig):
    root,pkg,m=rig
    with pytest.raises(ValueError,match='stale'):I.transact(root,pkg,m,lambda:{'received_mono':time.monotonic()-2},lambda:'same')
    I.verify_baseline(root,m)

def test_final_target_drift_is_failure_not_pass(rig):
    root,pkg,m=rig;count=[0];p=root/m['files'][0]['path']
    def guard():
        count[0]+=1
        if count[0]==len(m['files'])+2:p.write_bytes(b'concurrent edit')
        return safe()
    with pytest.raises(ValueError,match='later drift'):I.transact(root,pkg,m,guard,lambda:'same')
    assert p.read_bytes()==b'concurrent edit'

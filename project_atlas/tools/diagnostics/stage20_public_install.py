"""Explicitly approved optional sidecar installation/activation with rollback.

This module is NOT invoked by the builder or collector. It only manages its own
new unit; never starts/restarts localization, motor or safety services. No enable.
"""
import json
from pathlib import Path
import shutil
import subprocess
from stage20_install_guard import sha
from stage20_package_transaction import install,rollback,atomic_copy
from stage20_public_package import preflight

UNIT='atlas-stage20-public-capture.service'

def deploy(manifest,package,root,user_units,dependencies,*,owner_approved=False,
           activate=False,activation_approved=False,runner=None):
    if not owner_approved:raise ValueError('separate installation approval required')
    if activate and not activation_approved:raise ValueError('separate capture activation approval required')
    root=Path(root).resolve();user_units=Path(user_units).resolve()
    unit=user_units/UNIT
    for name,expected in manifest.get('installer_hashes',{}).items():
        source=(Path(package)/name).resolve()
        if not source.is_relative_to(Path(package).resolve()) or sha(source)!=expected:
            raise ValueError('installer checksum mismatch')
    if unit.exists() or unit.is_symlink():raise ValueError('existing user unit not overwritten')
    preflight(manifest,shutil.disk_usage(root).free,dependencies)
    if runner is None:runner=lambda args:subprocess.run(args,check=True,capture_output=True,text=True)
    # Parse the exact candidate unit before writing any production files.
    runner(['systemd-analyze','--user','verify',str(Path(package)/'tools/stage20_public'/UNIT)])
    result=install(manifest,package,root,owner_approved=True)
    if result['status']=='already_installed':raise ValueError('use saved transaction for explicit activation; do not duplicate')
    backup=Path(result['backup']);source=root/'tools/stage20_public'/UNIT;expected=sha(source)
    try:
        # Create only a previously absent dedicated unit, never a drop-in on another unit.
        user_units.mkdir(parents=True,exist_ok=True)
        atomic_copy(source,unit,expected)
        (backup/'unit_transaction.json').write_text(json.dumps({'unit':str(unit),'sha256':expected,'before':None}))
        capture_root=root/'data/diagnostics/stage20_public'
        if not capture_root.resolve().is_relative_to(root):raise ValueError('capture output path escape')
        capture_root.mkdir(parents=True,exist_ok=True)  # Dedicated metadata/output only, never delete it on rollback.
        runner(['systemctl','--user','daemon-reload'])
        if activate:
            runner(['systemctl','--user','start',UNIT])
            runner(['systemctl','--user','is-active','--quiet',UNIT])
        return dict(result,unit=str(unit),activated=activate,autostart=False)
    except Exception:
        # Stop only our diagnostic child before restoring/removing its own files.
        if activate:
            try:runner(['systemctl','--user','stop',UNIT])
            except Exception:pass
        if unit.is_file() and sha(unit)==expected:unit.unlink()
        elif unit.exists():raise ValueError('rollback refuses unrelated unit drift; owner action required')
        rollback(backup,root)
        runner(['systemctl','--user','daemon-reload'])
        raise

def undo(backup,root,*,owner_approved=False,runner=None):
    if not owner_approved:raise ValueError('explicit rollback approval required')
    if runner is None:runner=lambda args:subprocess.run(args,check=True,capture_output=True,text=True)
    backup=Path(backup).resolve();root=Path(root).resolve()
    if not backup.is_relative_to(root/'data/backups'):raise ValueError('backup outside approved root')
    event=json.loads((backup/'unit_transaction.json').read_text());unit=Path(event['unit'])
    if unit.name!=UNIT or unit.parent!=Path.home()/'.config/systemd/user':
        raise ValueError('unexpected user-unit path')
    if unit.exists() and sha(unit)!=event['sha256']:raise ValueError('later unit drift refused')
    runner(['systemctl','--user','stop',UNIT])
    rollback(backup,root)
    if unit.exists():unit.unlink()
    runner(['systemctl','--user','daemon-reload'])
    return {'restored':True,'other_units_touched':False,'recordings_preserved':True}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path)
    p.add_argument('--root',type=Path,default=Path('/home/jetson/project_atlas'))
    p.add_argument('--install',action='store_true');p.add_argument('--activate',action='store_true')
    p.add_argument('--rollback',type=Path);p.add_argument('--owner-approved-install',action='store_true')
    p.add_argument('--owner-approved-capture',action='store_true');a=p.parse_args()
    if bool(a.install)==bool(a.rollback):p.error('one explicit install or rollback action required')
    if a.rollback:
        print(json.dumps(undo(a.rollback,a.root,owner_approved=a.owner_approved_install)))
    else:
        if not a.package:p.error('exact reviewed package required')
        from stage20_public_preflight import check
        check()  # Fresh parked/headroom proof; never POST a stop/release command.
        manifest=json.loads((a.package/'MANIFEST.json').read_text())
        dependencies=subprocess.check_output(['dpkg-query','-W','-f=${Package}=${Version}\n',
            'ros-humble-rclpy','ros-humble-rosbag2-py','ros-humble-robot-localization','ros-humble-nav2-amcl'],text=True).splitlines()
        print(json.dumps(deploy(manifest,a.package,a.root,Path.home()/'.config/systemd/user',dependencies,
            owner_approved=a.owner_approved_install,activate=a.activate,activation_approved=a.owner_approved_capture)))

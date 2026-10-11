#!/usr/bin/env python3
"""Rehearse an existing stage package and rollback, then explicitly install it.

No service restart or motor command. Never delete the rehearsal evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
from validate_recorder_parked import status


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--direct-ros-stop', action='store_true',
        help='Verify stop via finite read-only ROS subscriber and systemd, not dashboard cache')
    parser.add_argument('--root', choices=('/home/jetson/project_atlas',
        '/home/jetson/project_atlas_ws/src/tortoisebot_bringup'),
        default='/home/jetson/project_atlas')
    args = parser.parse_args()
    def parked():
        if not args.direct_ros_stop:
            return status()
        evidence=Path(tempfile.mkdtemp(prefix='atlas_direct_stop_'))/'result.json'
        subprocess.run([sys.executable,str(Path(__file__).with_name('verify_parked_guard_restart.py')),
            '--output',str(evidence)],check=True,timeout=50)
    live = Path(args.root)
    manifest = (args.package/'MANIFEST').read_text().splitlines()
    files = [line.split()[1] for line in manifest if line.startswith(('ADD ', 'PATCH '))]
    if not files or any(Path(f).is_absolute() or '..' in Path(f).parts for f in files):
        raise ValueError('invalid manifest')
    if args.root.endswith('tortoisebot_bringup') and files != ['config/nav2_params.yaml']:
        raise ValueError('workspace installation restricted to the Nav2 config copy')
    parked()
    scratch = Path(tempfile.mkdtemp(prefix='atlas_stage_rehearsal_'))
    for folder in ('scripts','config','web/v2'):
        (scratch/folder).mkdir(parents=True)
    before = {f:digest(live/f) for f in files}
    for f in files:
        if (live/f).exists():
            (scratch/f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live/f, scratch/f)
    def install(root):
        result = subprocess.run(['bash', str(args.package/'install.sh')],
                                env=dict(os.environ, ATLAS_ROOT=str(root)), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        (scratch/('live_install.log' if root==live else 'rehearsal.log')).write_text(result.stdout)
        print(result.stdout, flush=True)
        result.check_returncode()
        for line in manifest:
            if line.startswith(('ADD ', 'PATCH ')):
                fields = line.split()
                expected = fields[-1].split('result=')[-1]
                assert digest(root/fields[1]) == expected, fields[1]+' hash mismatch'
    install(scratch)
    rollback = next((scratch/'data/backups').glob('*/ROLLBACK.sh'))
    subprocess.run(['bash', str(rollback)], check=True, timeout=30)
    assert {f:digest(scratch/f) for f in files} == before, 'rollback mismatch'
    print('REHEARSAL_AND_ROLLBACK_PASS', scratch, flush=True)
    if args.install:
        parked()
        assert {f:digest(live/f) for f in files} == before, 'live changed during rehearsal'
        install(live)
        parked()
        print('LIVE_INSTALL_HASHES_VERIFIED', json.dumps({f:digest(live/f) for f in files}), flush=True)


if __name__ == '__main__':
    main()

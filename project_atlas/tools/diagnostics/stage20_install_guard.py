"""Strict Stage 20 pre-install identity guard. Does NOT install/restart anything.

Use before the existing stage-package installer. Until readiness is verified,
this guard refuses installation even when individual files match.
"""
import hashlib
from pathlib import Path

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check(manifest, package, live_root):
    if manifest.get('deployment_ready') is not True:raise ValueError('Stage 20 not deployment-ready')
    package=Path(package).resolve();root=Path(live_root).resolve();same=True
    for f in manifest['files']:
        relative=Path(f['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('unsafe manifest path')
        if relative.parts[0] in ('maps','config') or relative.name in ('yahboom_base.py','atlas_cmd_vel_mux.py'):
            raise ValueError('outside diagnostic installation scope')
        source=(package/relative).resolve();dest=(root/relative).resolve()
        if not source.is_relative_to(package) or not dest.is_relative_to(root):raise ValueError('symlink escape')
        if sha(source)!=f['after']:raise ValueError('package hash mismatch')
        current=sha(dest) if dest.is_file() else None
        if current==f['after']:continue
        same=False
        if current!=f['before']:raise ValueError('unexpected live-file drift: '+f['path'])
    return {'status':'already_installed' if same else 'identities_match',
            'services_restarted':[],'files_changed':[],'requires_owner_installation_approval':True}

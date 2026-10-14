"""Read-only ROS opt-in gate. Never creates approval or enables services.

A future approved one-shot boot grant writes only its exclusive usage marker.
No motor, filter, map or service operation exists in this module.
"""
import hashlib
import json
from pathlib import Path
import uuid

IDENTITY_FILES=('config/atlas_ekf.yaml','config/nav2_params.yaml',
                'maps/atlas_latest.yaml','maps/atlas_latest.pgm')
PUBLIC_RUNTIME_FILES=tuple('tools/stage20_public/tools/diagnostics/'+name for name in (
    'stage20_capture.py','stage19_contract.py','stage20_production_gate.py',
    'stage20_capture_integrity.py','stage20_public_preflight.py'))+tuple(
    'tools/stage20_public/scripts/'+name for name in (
    'atlas_motion_recorder.py','atlas_motion_recorder_core.py','atlas_motion_recorder_writer.py'))+(
    'tools/stage20_public/atlas-stage20-public-capture.service',)
def current_boot_id():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

def verify_approval(path,root=Path('/home/jetson/project_atlas')):
    path=Path(path);root=Path(root).resolve()
    if not path.is_absolute() or path.is_symlink():raise ValueError('absolute regular approval file required')
    data=json.loads(path.read_text())
    if data.get('enabled') is not True or data.get('owner_approved') is not True:
        raise ValueError('capture disabled; separate owner approval required')
    if data.get('deployment_ready') is not True:raise ValueError('package qualification incomplete')
    if data.get('mode') not in ('read_only_stationary_startup','read_only_partial_public'):
        raise ValueError('wrong approval scope')
    if not data.get('source_commit'):
        raise ValueError('source and finite session identity required')
    if data['mode']=='read_only_partial_public':
        identity=data.get('runtime_identity',{})
        if set(identity)!=set(PUBLIC_RUNTIME_FILES):raise ValueError('exact partial capsule identity required')
        for name,expected in identity.items():
            item=(root/name).resolve()
            if not item.is_relative_to(root) or hashlib.sha256(item.read_bytes()).hexdigest()!=expected:
                raise ValueError('runtime capsule drift: '+name)
    for relative in IDENTITY_FILES:
        item=(root/relative).resolve()
        if not item.is_relative_to(root):raise ValueError('live identity path escape')
        actual=hashlib.sha256(item.read_bytes()).hexdigest()
        if actual!=data.get('identity',{}).get(relative):raise ValueError('unapproved live identity drift: '+relative)
    boot=current_boot_id()
    if data.get('boot_policy')=='next_normal_boot_once':
        if not data.get('approved_before_boot_id') or data['approved_before_boot_id']==boot:
            raise ValueError('awaiting separately approved future normal startup')
        grant=str(uuid.UUID(data['grant_id']))
        marker_root=(root/'data/diagnostics/stage20_public') if data['mode']=='read_only_partial_public' else path.parent
        marker=marker_root/('checkpoint_grant_'+grant+'.used.json')
        # Never overwrite an earlier grant or restart the rover to exercise it.
        with marker.open('x') as f:json.dump({'grant_id':grant,'boot_id':boot,'scope':'diagnostic_capture_only'},f)
    elif data.get('expires_after_boot_session')!=boot:
        raise ValueError('approval not for this boot session')
    elif data['mode']=='read_only_partial_public':
        grant=str(uuid.UUID(data['grant_id']))
        marker=root/'data/diagnostics/stage20_public'/('checkpoint_grant_'+grant+'.used.json')
        with marker.open('x') as f:json.dump({'grant_id':grant,'boot_id':boot,'scope':'partial_public_capture'},f)
    return {'mode':data['mode'],'source_commit':data['source_commit'],'boot_id':boot,
            'control_authority':'NONE','installation_approval_not_created_by_collector':True,
            'capture_root':str(root/'data/diagnostics/stage20_public') if data['mode']=='read_only_partial_public' else None}

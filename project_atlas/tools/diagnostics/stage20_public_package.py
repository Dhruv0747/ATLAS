"""Build a new, standalone partial-sidecar capsule. No installation/autostart.

Own copies of existing bag sink/worker are frozen, not installed over live files.
Binary overlays, accepted maps, motor and navigation files are never payloads.
Qualification is a separate decision; prepare() always defaults not ready.
"""
import hashlib
import json
from pathlib import Path
import shutil
from stage20_install_guard import sha

DIAGNOSTICS=('stage20_capture.py','stage19_contract.py','stage20_production_gate.py',
             'stage20_capture_integrity.py','stage20_public_preflight.py')
SCRIPTS=('atlas_motion_recorder.py','atlas_motion_recorder_core.py','atlas_motion_recorder_writer.py')
INSTALLER=('stage20_public_install.py','stage20_public_package.py','stage20_install_guard.py',
           'stage20_package_transaction.py','stage20_public_preflight.py')

def prepare(repo,output,inventory,source_commit):
    repo=Path(repo);output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    files=[]
    def add(source,relative):
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        files.append({'path':relative,'before':None,'after':sha(target)})
    for name in DIAGNOSTICS:
        add(repo/'project_atlas/tools/diagnostics'/name,'tools/stage20_public/tools/diagnostics/'+name)
    for name in SCRIPTS:
        add(repo/'project_atlas/scripts'/name,'tools/stage20_public/scripts/'+name)
    add(repo/'project_atlas/tools/diagnostics/stage20_public_capture.service.in',
        'tools/stage20_public/atlas-stage20-public-capture.service')
    installer={}
    for name in INSTALLER:
        target=output/'installer'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(repo/'project_atlas/tools/diagnostics'/name,target)
        installer['installer/'+name]=sha(target)
    manifest={'schema':1,'source_commit':source_commit,'deployment_ready':False,
        'scope':'PARTIAL_PUBLIC_ONLY','default':'OFF','files':files,'installer_hashes':installer,
        'live_preflight_hashes':inventory['identities'],'dependency_pins':inventory['dependencies'],
        'maps_modified':False,'binary_overlays':[], 'control_services_changed':[],
        'initial_ekf_state_available':False,'relative_reference_available':False,
        'full_covariance_available':False,'actual_consumption_available':False,
        'replay_fidelity_verified':False,'maximum_capture_s':120,'quota_mib':500,
        'unit_target':'atlas-stage20-public-capture.service',
        'qualification_required':['native_rate_and_caps','graph','installation_rollback','failure_tests']}
    (output/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    return manifest

def preflight(manifest,free_bytes,dependencies):
    if free_bytes<2*1024**3:raise OSError('2 GiB installation/capture reserve required')
    if sorted(dependencies)!=sorted(manifest['dependency_pins']):raise ValueError('dependency drift')
    for name,expected in manifest['live_preflight_hashes'].items():
        if sha(name)!=expected:raise ValueError('unexpected live-file drift: '+name)
    return {'identities_verified':True,'maps_changed':False}

def qualify(manifest,evidence):
    """Readiness for PUBLIC partial evidence only; never owner approval/fidelity."""
    required=('native_full_duration_rates','kernel_memory_tasks_total_cpu_limits',
              'actual_service_graph','native_production_adapter','cdr_receipt_integrity',
              'scratch_install_activation_rollback','quota_crash_missing_sensor_tests')
    if manifest['scope']!='PARTIAL_PUBLIC_ONLY' or manifest['binary_overlays']:
        raise ValueError('private estimator instrumentation is not qualified by this evidence')
    if evidence.get('scope_reviewed')!='PARTIAL_PUBLIC_ONLY' or any(evidence.get(k) is not True for k in required):
        raise ValueError('mandatory partial-sidecar gates incomplete')
    result=dict(manifest,deployment_ready=True,qualification=evidence,
        owner_installation_approved=False,owner_capture_approved=False,
        full_checkpoint_deployment_ready=False,replay_fidelity_verified=False)
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--inventory',required=True,type=Path)
    p.add_argument('--source-commit',required=True);p.add_argument('--qualification',type=Path);a=p.parse_args()
    result=prepare(a.repo,a.output,json.loads(a.inventory.read_text(encoding='utf-8-sig')),a.source_commit)
    if a.qualification:
        result=qualify(result,json.loads(a.qualification.read_text()))
        (a.output/'MANIFEST.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

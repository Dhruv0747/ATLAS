"""Native scratch rollback driven by a real transient diagnostic exit failure.

The deliberately failing child is /bin/false: no ROS, devices or control calls.
Only its uniquely named transient unit is created; no production unit is restarted.
"""
import json
from pathlib import Path
import subprocess
import uuid
from stage20_public_install import deploy

base=Path('/tmp/atlas-stage20-complete-EW8kVA07')/('actual_rollback_'+uuid.uuid4().hex[:8]);base.mkdir()
package=Path('/tmp/atlas-stage20-complete-EW8kVA07/public_capsule_v3')
manifest=json.loads((package/'MANIFEST.json').read_text());assert not manifest['deployment_ready']
manifest['deployment_ready']=True  # In-memory fixture qualification; never write production approval.
dependencies=subprocess.check_output(['dpkg-query','-W','-f=${Package}=${Version}\n',
    'ros-humble-rclpy','ros-humble-rosbag2-py','ros-humble-robot-localization','ros-humble-nav2-amcl'],text=True).splitlines()
root=base/'live';root.mkdir();old=root/'data/diagnostics/keep';old.mkdir(parents=True)
(old/'important').write_bytes(b'KEEP')
test_unit='atlas-stage20-activation-failure-'+uuid.uuid4().hex[:8]
calls=[]
def runner(command):
    calls.append(command)
    if command[0]=='systemd-analyze':return subprocess.run(command,check=True,capture_output=True,text=True)
    if 'start' in command:
        # Native manager actually reports status=1, which reaches installer's exception rollback.
        return subprocess.run(['systemd-run','--user','--wait','--collect','--pipe','--unit='+test_unit,
            '-p','RuntimeMaxSec=5','-p','MemoryMax=32M','-p','TasksMax=8','/bin/false'],
            check=True,capture_output=True,text=True)
    return None  # No daemon-reload/stop on production bus; test child is already collected.
try:
    deploy(manifest,package,root,base/'user-units',dependencies,owner_approved=True,
        activate=True,activation_approved=True,runner=runner)
    raise AssertionError('deliberately failed activation unexpectedly succeeded')
except subprocess.CalledProcessError as error:
    assert error.returncode!=0
assert (old/'important').read_bytes()==b'KEEP'
assert not (root/'tools/stage20_public/tools/diagnostics/stage20_capture.py').exists()
assert not (base/'user-units/atlas-stage20-public-capture.service').exists()
report={'actual_transient_exit_failure':True,'automatic_scratch_rollback':True,
    'backups_preserved':bool(list((root/'data/backups').glob('*'))),'old_evidence_preserved':True,
    'production_units_changed':False,'scope':'real diagnostic failure; scratch unit path/manager reload mocked'}
(base/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

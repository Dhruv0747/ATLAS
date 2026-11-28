"""Native scratch-file capsule tests, with explicit fake activation failure.

Does not call systemctl; only native systemd-analyze parses the exact unit.
Production control services/files are not installation targets.
"""
import json
from pathlib import Path
import subprocess
import uuid
from stage19_contract import require_isolation
from stage20_public_install import deploy,UNIT

require_isolation()
base=Path('/tmp/replay')/('capsule_rehearsal_'+uuid.uuid4().hex[:8]);base.mkdir()
package=Path('/tmp/replay/public_capsule_v2')
m=json.loads((package/'MANIFEST.json').read_text())
assert m['deployment_ready'] is False
dependencies=subprocess.check_output(['dpkg-query','-W','-f=${Package}=${Version}\n',
    'ros-humble-rclpy','ros-humble-rosbag2-py','ros-humble-robot-localization','ros-humble-nav2-amcl'],text=True).splitlines()
# Fixture qualification is not production approval and is never written to the package.
m['deployment_ready']=True
results=[]
for failed in (False,True):
    root=base/('failure' if failed else 'success');root.mkdir()
    old=root/'data/diagnostics/old';old.mkdir(parents=True);(old/'important').write_bytes(b'PRESERVE')
    units=base/('failed-units' if failed else 'successful-units');calls=[]
    def runner(args):
        calls.append(args)
        if args[0]=='systemd-analyze':return subprocess.run(args,check=True,capture_output=True,text=True)
        if failed and 'is-active' in args:raise RuntimeError('injected activation health failure')
        return None  # Deliberate mocked manager, never contacts the live user bus.
    try:
        r=deploy(m,package,root,units,dependencies,owner_approved=True,
            activate=failed,activation_approved=failed,runner=runner)
        assert not failed and r['activated'] is False
        assert (units/UNIT).is_file()
    except RuntimeError:
        assert failed
        assert not (units/UNIT).exists()
        assert not (root/'tools/stage20_public/tools/diagnostics/stage20_capture.py').exists()
    assert (old/'important').read_bytes()==b'PRESERVE'
    assert list((root/'data/backups').glob('*'))
    assert not any('enable' in args or 'restart' in args for args in calls)
    results.append({'injected_failure':failed,'existing_evidence_preserved':True,
        'native_unit_parser_pass':True,'manager_calls':'mocked; activation failure explicit'})
report={'cases':results,'scope':'native scratch install/rollback; not real production activation',
        'deployment_readiness_asserted':False,'production_changed':False}
(base/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

"""Single-file owner-approved guardian installation; no restart or camera start."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

LIVE=Path('/home/jetson/project_atlas/tools/vision3d')
TARGET=LIVE/'stationary_ros_probe.py'
BEFORE='f6321da4961482064a6d278e368efbb25540d5a3178ee14900255972b269a384'
AFTER='f8a24e2a9fe92f505f52e96572a00691b0ebcfe92b092ba1c98ee052c18ed9dd'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    candidate=Path(__file__).with_name('stationary_ros_probe.py')
    sys.path.insert(0,str(LIVE))
    import stationary_gate as G
    import stationary_ros_probe as old
    def identities():
        result=G.services()
        result['web']=subprocess.check_output(['systemctl','--user','show','rover-status-web',
            '-p','MainPID','-p','NRestarts','-p','ActiveState'],text=True,timeout=3)
        return result
    def check(probe):
        a=G.ticks();time.sleep(1)
        row=G.check(G.cpu_delta(a,G.ticks()),probe.safety_snapshot())
        probe.extra_safety()
        state=json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/vision3d/summary',timeout=3))
        if not (state.get('state')=='OFF' or (state.get('state')=='RESOURCE BLOCKED' and state.get('driver_stopped') is True)):
            raise RuntimeError('Astra not OFF')
        if subprocess.run(['pgrep','-x','astra_camera_no'],stdout=subprocess.DEVNULL,timeout=2).returncode!=1:
            raise RuntimeError('Astra process not absent')
        return row
    backup=Path(tempfile.mkdtemp(prefix='stable-guardian-',dir=str(Path(__file__).parent)))
    report={'result':'ABORTED','backup':str(backup),'camera_started':False,'services_restarted':False}
    installed=False
    try:
        if digest(TARGET)!=BEFORE or digest(candidate)!=AFTER:raise RuntimeError('hash mismatch')
        report['services_before']=identities()
        report['preflight']=[check(old) for _ in range(3)]
        shutil.copy2(TARGET,backup/'stationary_ros_probe.py')
        if digest(backup/'stationary_ros_probe.py')!=BEFORE:raise RuntimeError('backup mismatch')
        spec=importlib.util.spec_from_file_location('astra_stable_candidate',candidate)
        new=importlib.util.module_from_spec(spec);spec.loader.exec_module(new)
        report['resolved_devices']=new.verify_astra_usb_access()
        if identities()!=report['services_before']:raise RuntimeError('service identity changed')
        if digest(TARGET)!=BEFORE:raise RuntimeError('baseline changed')
        fd,name=tempfile.mkstemp(prefix='.stable-guardian-',dir=str(LIVE));os.close(fd)
        try:
            shutil.copyfile(candidate,name);os.chmod(name,TARGET.stat().st_mode & 0o777)
            if digest(Path(name))!=AFTER:raise RuntimeError('staged hash mismatch')
            os.replace(name,TARGET);installed=True
        finally:
            if os.path.exists(name):os.unlink(name)
        report['postflight']=[check(new) for _ in range(3)]
        report['services_after']=identities()
        if report['services_after']!=report['services_before'] or digest(TARGET)!=AFTER:
            raise RuntimeError('post-install identity/hash mismatch')
        report.update(result='INSTALLED_VERIFIED_NO_RESTART',installed_sha256=digest(TARGET))
    except Exception as exc:
        report['error']=repr(exc)
        if installed:
            if digest(TARGET)==AFTER:
                shutil.copy2(backup/'stationary_ros_probe.py',TARGET)
                report['rollback_verified']=digest(TARGET)==BEFORE
            else:report['rollback_blocked']='unexpected concurrent file change'
    finally:
        (backup/'result.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    return 0 if report['result']=='INSTALLED_VERIFIED_NO_RESTART' else 1


if __name__=='__main__':sys.exit(main())

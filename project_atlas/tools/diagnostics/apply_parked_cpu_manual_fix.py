"""Explicit approved parked deployment: manual-only env OR demand-only AI JPEG.

No motion/steering publications, stop resets, essential-service disablement,
calibration changes or recorder activation. Exact live hashes are mandatory.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import py_compile
import shutil
import subprocess
import time
import urllib.request
import uuid

ROOT=Path('/home/jetson/project_atlas')
EXPECTED_MUX='0d95928632f1cac7e8d41f5dfe499eb837cdb014cbf47ac7bebcde6f52ff7dc3'
EXPECTED_AI='485fcd7487feb53f07332cb7df7db8de8c30167c8d79ae695f962abb6cd50515'
EXPECTED_STOP='1a44fb37a532c911612e305fe77cfbeae1ed6f46ae9495a970b60b59bfda803a'
PROTECTED=('scripts/yahboom_base.py','config/steering_calibration.json',
           'scripts/atlas_cmd_vel_mux.py','scripts/atlas_remote_stop.py')
UNITS=('rover-base-telemetry.service','atlas-ekf.service','atlas-localization.service',
       'atlas-lidar.service','atlas-im10a.service','atlas-camera.service',
       'atlas-stage20-public-capture.service')


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unit_state(units):
    raw=subprocess.check_output(['systemctl','--user','show',*units,
        '--property=Id,ActiveState,MainPID,NRestarts'],text=True,timeout=5)
    return {row['Id']:row for row in (dict(line.split('=',1) for line in block.splitlines()
        if '=' in line) for block in raw.strip().split('\n\n'))}


def parked(require_manual):
    with urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=3) as response:
        raw=response.read(2*1024**2+1)
        if len(raw)>2*1024**2:raise ValueError('oversized status')
    data=json.loads(raw);ros=data['ros']
    p=ros['control_policy'];c=ros['cmd_vel']
    if not all(0<=float(x['age'])<=2 for x in (p,c)):raise ValueError('stale stop/command')
    policy=json.loads(p['value']) if isinstance(p['value'],str) else p['value']
    if policy['stop_latched'] is not True or policy['source']!='STOPPED':raise ValueError('latched stop required')
    if policy['commission_armed'] is not False:raise ValueError('commissioning must be disarmed')
    if require_manual and policy['manual_only'] is not True:raise ValueError('manual-only required')
    command=c['value']
    if not all(float(command[k])==0 for k in ('lin','ang')):raise ValueError('zero commands required')
    # CPU75% remains the recording gate; this is the authorized CPU repair,
    # not recording admission. RAM/temp safeguards still apply to this operation.
    system=data['system']
    if not 0<=float(system['ram_percent'])<=80:raise ValueError('RAM headroom unavailable')
    if not 0<=float(str(system['temp']).split()[0])<=70:raise ValueError('thermal headroom unavailable')
    return {'policy':policy,'policy_age_s':p['age'],'command':command,
            'command_age_s':c['age'],'system':{k:system.get(k) for k in ('cpu_percent','ram_percent','temp')},
            'steering_commanded':{k:ros.get(k) for k in ('front_steer','rear_steer')}}


def observe_startup(check,observations,*,clock=time.monotonic,pause=time.sleep,seconds=20):
    """Bounded read-only wait for first fresh stop data after an approved restart.

    Only stale/missing arrivals can settle. An unsafe value or other error fails
    immediately. This never repeats a restart or changes a threshold.
    """
    start=clock()
    while True:
        try:
            sample=check()
            observations.append({'elapsed_s':clock()-start,'state':'fresh'})
            return sample
        except ValueError as exc:
            elapsed=clock()-start
            observations.append({'elapsed_s':elapsed,'error':str(exc)})
            if str(exc)!='stale stop/command' or elapsed>=seconds:raise
            pause(min(.5,seconds-elapsed))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('manual','annotator'),required=True)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--candidate-sha')
    args=parser.parse_args()
    stage=args.stage
    result={'stage':stage,'changed':False,'restarted':False,'result':'PREFLIGHT'}
    backup=None
    try:
        result['before']=parked(require_manual=stage!='manual')
        states=unit_state(UNITS)
        result['units_before']=states
        recorder=states['atlas-stage20-public-capture.service']
        if recorder['ActiveState']!='inactive' or recorder['MainPID']!='0':raise ValueError('recorder must be OFF')
        hashes={p:digest(ROOT/p) for p in PROTECTED}
        result['protected_before']=hashes
        if hashes['scripts/atlas_cmd_vel_mux.py']!=EXPECTED_MUX or hashes['scripts/atlas_remote_stop.py']!=EXPECTED_STOP:
            raise ValueError('stop/mux source differs from reviewed version')
        if stage=='manual':
            target=Path('/home/jetson/.config/systemd/user/atlas-cmd-vel-mux.service.d/40-manual-commissioning.conf')
            original=target.read_bytes()
            old=original.decode()
            if old.count('Environment=ATLAS_MANUAL_ONLY=0')!=1:raise ValueError('unexpected manual override')
            env=Path('/home/jetson/.config/project-atlas/hardware.env')
            if env.exists() and any(x.strip().startswith('ATLAS_MANUAL_ONLY=') for x in env.read_text().splitlines()):
                raise ValueError('hardware env contains a competing manual-only setting')
            replacement=old.replace('Environment=ATLAS_MANUAL_ONLY=0','Environment=ATLAS_MANUAL_ONLY=1').encode()
            unit='atlas-cmd-vel-mux.service'
        else:
            target=ROOT/'scripts/ai_annotator_node.py';original=target.read_bytes()
            if digest(target)!=EXPECTED_AI:raise ValueError('unexpected live AI version')
            if not args.candidate or digest(args.candidate)!=args.candidate_sha:raise ValueError('candidate hash mismatch')
            py_compile.compile(str(args.candidate),doraise=True)
            replacement=args.candidate.read_bytes();unit='atlas-ai-annotator.service'
        result['target']=str(target);result['target_before_sha']=hashlib.sha256(original).hexdigest()
        backup=ROOT/'data/backups'/('20261015_cpu_'+stage+'_'+uuid.uuid4().hex[:8])
        backup.mkdir(parents=True,exist_ok=False)
        shutil.copy2(target,backup/'original')
        result['backup']=str(backup)
        result['rollback']={'restore_from':str(backup/'original'),'restore_to':str(target),'restart_only':unit}
        (backup/'transaction.json').write_text(json.dumps(result,indent=2))
        # Same directory replace preserves the file's existing mode.
        temporary=target.with_name(target.name+'.atlas-'+uuid.uuid4().hex)
        temporary.write_bytes(replacement);shutil.copymode(target,temporary);temporary.replace(target)
        result['changed']=True
        if stage=='manual':subprocess.run(['systemctl','--user','daemon-reload'],check=True,timeout=10)
        subprocess.run(['systemctl','--user','restart',unit],check=True,timeout=15)
        result['restarted']=True
        time.sleep(4)
        result['startup_observations']=[]
        result['after']=observe_startup(lambda:parked(require_manual=True),result['startup_observations'])
        result['units_after']=unit_state(UNITS)
        if states!=result['units_after']:raise ValueError('protected production unit identity/state changed')
        result['protected_after']={p:digest(ROOT/p) for p in PROTECTED}
        if hashes!=result['protected_after']:raise ValueError('protected calibration/base/mux file changed')
        if target.read_bytes()!=replacement:raise ValueError('installed bytes mismatch')
        result['installed_sha']=digest(target)
        result['changed_unit']=unit_state((unit,))[unit]
        if result['changed_unit']['ActiveState']!='active':raise ValueError('changed unit not active')
        result['result']='VERIFIED'
    except Exception as exc:
        result['result']='FAILED';result['error']=type(exc).__name__+': '+str(exc)
        # Preserve the safer manual-only setting if its postflight cannot be read.
        # For a failed AI deployment, restore just its old source and restart it.
        if stage=='annotator' and result['changed'] and backup:
            shutil.copy2(backup/'original',target)
            subprocess.run(['systemctl','--user','restart','atlas-ai-annotator.service'],check=True,timeout=15)
            result['rolled_back']=digest(target)==EXPECTED_AI
    finally:
        result['utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        if backup:(backup/'transaction.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2),flush=True)
    return 0 if result['result']=='VERIFIED' else 2


if __name__=='__main__':raise SystemExit(main())

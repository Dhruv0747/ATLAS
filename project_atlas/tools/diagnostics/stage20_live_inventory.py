"""Read-only systemd graph / package identities. Does not read service secrets."""
import hashlib
import json
from pathlib import Path
import subprocess
from stage20_minimum_contract import verify_unit

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def inventory(unit):
    listing=subprocess.check_output(['systemctl','--user','list-units','--all','--plain','--no-legend'],text=True)
    names=[line.split()[0] for line in listing.splitlines() if line.split()]
    output=subprocess.check_output(['systemctl','--user','show',
        '-p','Id','-p','Requires','-p','Wants','-p','BindsTo','-p','PartOf',
        '-p','Before','-p','After','-p','FragmentPath','-p','DropInPaths','--',*names],text=True)
    graph={};identities={}
    for block in output.strip().split('\n\n'):
        props=dict(line.split('=',1) for line in block.splitlines() if '=' in line)
        if not props.get('Id'):continue
        graph[props['Id']]={k:v.split() for k,v in props.items() if k not in ('Id','FragmentPath','DropInPaths')}
        if props['Id'].startswith(('atlas','rover')):
            for p in (props.get('FragmentPath','')+' '+props.get('DropInPaths','')).split():
                if Path(p).is_file():identities[p]=sha(p)
    result=verify_unit(Path(unit).read_text(),graph)
    if not graph or any(name not in graph for name in ('atlas-ekf.service','atlas-localization.service',
        'atlas-cmd-vel-mux.service','atlas-remote.service','rover-base-telemetry.service')):
        raise ValueError('incomplete actual systemd graph; qualification refused')
    base=Path('/home/jetson/project_atlas')
    for relative in ('config/atlas_ekf.yaml','config/nav2_params.yaml','maps/atlas_latest.yaml',
        'maps/atlas_latest.pgm','scripts/atlas_mission_control.py','scripts/seed_atlas_localization.py',
        'scripts/atlas_motion_recorder.py','scripts/atlas_motion_recorder_core.py','scripts/atlas_motion_recorder_writer.py'):
        identities[str(base/relative)]=sha(base/relative)
    versions=subprocess.check_output(['dpkg-query','-W','-f=${Package}=${Version}\n',
        'ros-humble-rclpy','ros-humble-rosbag2-py','ros-humble-robot-localization','ros-humble-nav2-amcl'],text=True)
    return {'graph':graph,'unit_check':result,'identities':identities,'dependencies':versions.splitlines(),
        'production_changed':False}

if __name__=='__main__':
    import sys
    print(json.dumps(inventory(sys.argv[1]),indent=2))

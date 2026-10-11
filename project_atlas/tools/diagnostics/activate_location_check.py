#!/usr/bin/env python3
"""Activate only the approved Stage A monitor/web files, rollback on failure.

Requires an installed/rehearsed stage and a fresh direct-ROS stop check. Never
changes control units, stop latch, localization mode, pose or motor commands.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rollback',required=True,type=Path)
    p.add_argument('--evidence',required=True,type=Path)
    a=p.parse_args()
    if (a.evidence.exists() or a.rollback.name!='ROLLBACK.sh' or not a.rollback.is_file()
        or a.rollback.resolve().parent.parent!=Path('/home/jetson/project_atlas/data/backups')):
        p.error('new evidence directory and exact live rollback required')
    a.evidence.mkdir()
    def stopped(name):
        subprocess.run([sys.executable,str(Path(__file__).with_name('verify_parked_guard_restart.py')),
            '--output',str(a.evidence/name)],check=True,timeout=50)
    def pid(unit):
        return subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
    units=['atlas-localization-monitor','rover-status-web']
    mode=Path.home()/'.config/project_atlas/relocalize_mode'
    assert mode.read_text().strip()=='suggest','automatic reseeding must remain disabled'
    stopped('before.json')
    preserved={u:pid(u) for u in ['atlas-cmd-vel-mux','atlas-localization','atlas-tight-recovery']}
    try:
        subprocess.run(['systemctl','--user','restart',*units],check=True,timeout=30)
        end=time.monotonic()+30
        while True:
            try:
                with urllib.request.urlopen('http://127.0.0.1:8088/api/location-check',timeout=2) as response:
                    status=json.load(response)
                assert status['state']=='IDLE' and time.time()-status['written_unix']<3
                break
            except Exception:
                if time.monotonic()>end:raise
                time.sleep(.5)
        stopped('after.json')
        assert preserved=={u:pid(u) for u in preserved},'unrelated owner restarted'
        assert mode.read_text().strip()=='suggest'
        report=dict(activated=units,preserved_pids=preserved,status=status,rollback=str(a.rollback))
        (a.evidence/'activation.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    except Exception:
        subprocess.run(['bash',str(a.rollback)],check=True,timeout=30)
        subprocess.run(['systemctl','--user','restart',*units],check=True,timeout=30)
        raise


if __name__=='__main__':main()

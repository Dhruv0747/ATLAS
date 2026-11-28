"""Approved parked trial of read-only localization search CPU budget.

Changes only its cgroup CPUQuota; does not restart/stop any service or alter
localization algorithms, sensor rates, result thresholds or motion authority.
"""
import json
from pathlib import Path
import subprocess
import uuid
from apply_parked_cpu_manual_fix import ROOT, PROTECTED, UNITS, digest, parked, unit_state

UNIT='atlas-localization-monitor.service'


def main():
    result={'stage':'runtime_search_budget','changed':False}
    backup=None
    try:
        result['before']=parked(True)
        mode=Path('/home/jetson/.config/project_atlas/relocalize_mode')
        if mode.exists() and mode.read_text().split()[0]!='suggest':
            raise ValueError('trial limited to suggest-only monitor')
        units=unit_state(UNITS+(UNIT,))
        result['units_before']=units
        recorder=units['atlas-stage20-public-capture.service']
        if recorder['ActiveState']!='inactive' or recorder['MainPID']!='0':raise ValueError('recorder not OFF')
        hashes={p:digest(ROOT/p) for p in PROTECTED}
        quota=subprocess.check_output(['systemctl','--user','show',UNIT,'-p','CPUQuotaPerSecUSec','--value'],text=True).strip()
        if quota!='600ms':raise ValueError('expected original60% budget; got '+quota)
        backup=ROOT/'data/backups'/('20261015_cpu_search_'+uuid.uuid4().hex[:8]);backup.mkdir(parents=True,exist_ok=False)
        result['backup']=str(backup);result['original_quota']='60%'
        result['rollback']=['systemctl','--user','set-property','--runtime',UNIT,'CPUQuota=60%']
        (backup/'original_unit.txt').write_text(subprocess.check_output(['systemctl','--user','cat',UNIT],text=True))
        (backup/'transaction.json').write_text(json.dumps(result,indent=2))
        subprocess.run(['systemctl','--user','set-property','--runtime',UNIT,'CPUQuota=25%'],check=True,timeout=10)
        result['changed']=True
        result['installed_quota']=subprocess.check_output(['systemctl','--user','show',UNIT,'-p','CPUQuotaPerSecUSec','--value'],text=True).strip()
        if result['installed_quota']!='250ms':raise ValueError('quota not applied')
        result['after']=parked(True)
        result['units_after']=unit_state(UNITS+(UNIT,))
        if units!=result['units_after']:raise ValueError('unit identity/state changed')
        if hashes!={p:digest(ROOT/p) for p in PROTECTED}:raise ValueError('protected file changed')
        result['result']='RUNTIME_TRIAL_APPLIED'
    except Exception as exc:
        result['result']='FAILED';result['error']=str(exc)
        if result['changed']:
            subprocess.run(result['rollback'],check=True,timeout=10)
            result['rolled_back']=True
    finally:
        if backup:(backup/'transaction.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2),flush=True)
    return 0 if result['result']=='RUNTIME_TRIAL_APPLIED' else 2


if __name__=='__main__':raise SystemExit(main())

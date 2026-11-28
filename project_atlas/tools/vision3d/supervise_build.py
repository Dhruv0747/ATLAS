"""One explicit resource-bounded isolated build; never starts a camera or controls ATLAS."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import stationary_gate as gate

STAGE=Path('/home/jetson/project-atlas-migration/astra-20261021')
UNIT='atlas-astra-build-20261021.service'


def unit_state():
    raw=subprocess.check_output(['systemctl','--user','show',UNIT,'-p','ActiveState','-p','ExecMainStatus','-p','Result','-p','CPUUsageNSec','-p','MemoryPeak'],text=True)
    return dict(line.split('=',1) for line in raw.splitlines())


def main():
    a=argparse.ArgumentParser();a.add_argument('--approve-isolated-build',action='store_true');a.add_argument('--attempt',type=int,default=1,choices=(1,2,3));args=a.parse_args()
    if not args.approve_isolated_build:raise SystemExit('Explicit opt-in required')
    if not STAGE.is_dir():raise SystemExit('isolated staging directory missing')
    global UNIT
    UNIT='atlas-astra-build-20261021-'+str(args.attempt)+'.service'
    result={'kind':'isolated build only','attempt':args.attempt,'samples':[],'started':False,'failure':None}
    path=STAGE/('build_supervised_result_'+str(args.attempt)+'.json')
    if path.exists():raise SystemExit('existing evidence preserved; no automatic repeat')
    started=False
    try:
        rows,identities=gate.preflight();result.update(preflight=rows,units_before=identities)
        cgroup=Path('/proc/self/cgroup').read_text().strip().split('::',1)[1]
        controllers=(Path('/sys/fs/cgroup'+cgroup)/'cgroup.controllers').read_text().split()
        if 'cpu' not in controllers:
            raise RuntimeError('CPU controller unavailable: requested systemd CPUQuota would not be enforced; build refused')
        state=subprocess.check_output(['systemctl','--user','show',UNIT,'-p','LoadState'],text=True)
        if 'LoadState=not-found' not in state:raise RuntimeError('build unit already exists')
        subprocess.run(['systemd-run','--user','--unit='+UNIT,'--property=CPUQuota=35%',
                        '--property=MemoryMax=800M','--property=RuntimeMaxSec=900','--property=Nice=19',
                        '--working-directory='+str(STAGE/'ws'),'/bin/bash',str(STAGE/'build_isolated.sh')],check=True)
        started=True;result['started']=True;print('ISOLATED BUILD STARTED; CPU quota 0.35 core, RAM cap 800MiB',flush=True)
        start=time.monotonic();last=gate.ticks()
        while time.monotonic()-start<905:
            time.sleep(1);now=gate.ticks();row=gate.check(gate.cpu_delta(last,now));last=now
            row['elapsed_s']=time.monotonic()-start;result['samples'].append(row)
            if len(result['samples'])%10==0:
                if gate.services()!=identities:raise RuntimeError('essential service identity changed')
                print('BUILD progress',round(row['elapsed_s']),round(row['cpu_percent'],2),flush=True)
            state=unit_state()
            if state.get('ActiveState') not in ('active','activating'):
                result['unit_result']=state
                if state.get('ExecMainStatus')!='0' or state.get('Result')!='success':raise RuntimeError('isolated build failed')
                result['result']='PASS';break
        else:raise RuntimeError('build deadline exceeded')
    except Exception as e:
        result['result']='BLOCKED';result['failure']=str(e);print('BUILD BLOCKED',str(e),flush=True)
        if isinstance(e,gate.AdmissionError):result['failed_sample']=e.evidence
    finally:
        if started:
            subprocess.run(['systemctl','--user','stop',UNIT],check=False)
            result['unit_final']=unit_state()
            result['journal']=subprocess.getoutput('journalctl --user -u '+UNIT+' --no-pager -n 100')
        result['units_after']=gate.services()
        path.write_text(json.dumps(result,indent=2))
        print('EVIDENCE',str(path),result['result'],flush=True)


if __name__=='__main__':main()

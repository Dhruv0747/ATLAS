"""Explicit one-shot isolated build; own-child pacing plus independent admission.

No CPU quota claim, no service changes, no camera activation. Logs are build
diagnostics, not sensor recordings. Existing evidence is never overwritten.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from bounded_process import OwnedPacer
import stationary_gate as gate

STAGE=Path('/home/jetson/project-atlas-migration/astra-20261021')


def main():
    p=argparse.ArgumentParser();p.add_argument('--approve-isolated-build',action='store_true')
    a=p.parse_args()
    if not a.approve_isolated_build:raise SystemExit('explicit build approval required')
    evidence=STAGE/'stage28_paced_build.json'
    if evidence.exists():raise SystemExit('preserve existing attempt; no automatic retry')
    result={'result':'BLOCKED','samples':[],'started':False};proc=pacer=None
    try:
        rows,before=gate.preflight();result.update(preflight=rows,units_before=before)
        with (STAGE/'stage28_build_stdout.txt').open('x') as out, (STAGE/'stage28_build_stderr.txt').open('x') as err:
            proc=subprocess.Popen(['/bin/bash',str(STAGE/'build_isolated.sh')],cwd=str(STAGE/'ws'),
                                  stdout=out,stderr=err,start_new_session=True)
            pacer=OwnedPacer(proc,run_s=.01,hold_s=.09).start();result['started']=True
            start=time.monotonic();last=gate.ticks()
            while proc.poll() is None:
                if time.monotonic()-start>600:raise RuntimeError('600-second build deadline')
                if pacer.error:raise RuntimeError('pacer failed: '+pacer.error)
                time.sleep(1);now=gate.ticks()
                result['samples'].append(gate.check(gate.cpu_delta(last,now)));last=now
                if gate.services()!=before:raise RuntimeError('essential identity changed')
                if len(result['samples'])%15==0:print('BUILD',len(result['samples']),'samples',flush=True)
            if proc.returncode:raise RuntimeError('build exited '+str(proc.returncode))
            result['result']='PASS'
    except Exception as e:
        result['failure']=str(e)
        if isinstance(e,gate.AdmissionError):result['failed_sample']=e.evidence
    finally:
        if pacer:pacer.close()
        if proc and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=3)
        result['units_after']=gate.services()
        evidence.write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':main()

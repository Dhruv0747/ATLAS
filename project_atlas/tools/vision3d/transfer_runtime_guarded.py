"""PC-only one-shot rate-limited upload with fresh independent Jetson admission."""
import json
from pathlib import Path
import subprocess
import time

SSH='/mnt/c/Windows/System32/OpenSSH/ssh.exe'
SCP='/mnt/c/Windows/System32/OpenSSH/scp.exe'
KEY='C:/Users/Dhruv/.ssh/atlas_codex_runtime'
HOST='jetson@192.168.1.15'
BASE='/home/jetson/project-atlas-migration/astra-20261021/'
REMOTE="""
import sys,json,time,pathlib
sys.path.insert(0,'/home/jetson/project-atlas-migration/astra-20261021')
import stationary_gate as g
try:
 if pathlib.Path('/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2.tar.gz').exists():raise RuntimeError('existing candidate preserved')
 rows,units=g.preflight()
 print(json.dumps({'ready':True,'preflight':rows,'units':units}),flush=True)
 last=g.ticks()
 for i in range(20):
  time.sleep(1);now=g.ticks();row=g.check(g.cpu_delta(last,now));last=now
  if g.services()!=units:raise RuntimeError('essential service identity changed')
  print(json.dumps({'sample':row}),flush=True)
 print(json.dumps({'done':True,'units':g.services()}),flush=True)
except Exception as e:
 print(json.dumps({'failure':str(e)}),flush=True);sys.exit(2)
"""


def main():
    evidence=Path('/root/atlas-stage29/runtime-upload-result.json')
    if evidence.exists():raise SystemExit('preserve one-shot attempt; no automatic retry')
    result={'result':'BLOCKED','samples':[]};copy=None;monitor=None
    try:
        monitor=subprocess.Popen([SSH,'-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=3','-o','ServerAliveCountMax=2',HOST,'python3 -u -'],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        monitor.stdin.write(REMOTE);monitor.stdin.close()
        first=json.loads(monitor.stdout.readline());result['admission']=first
        if first.get('ready') is not True:raise RuntimeError(str(first))
        source='C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/ATLAS-github/artifacts/astra_stationary_20261021/astra-arm64-stage29-v2.tar.gz'
        copy=subprocess.Popen([SCP,'-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=3','-o','ServerAliveCountMax=2','-l','2048',source,HOST+':'+BASE],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        for line in monitor.stdout:
            row=json.loads(line);result['samples'].append(row)
            if 'failure' in row:raise RuntimeError(row['failure'])
        monitor.wait(timeout=5)
        if monitor.returncode:raise RuntimeError('monitor failed')
        out,err=copy.communicate(timeout=5);result['copy_stderr']=err
        if copy.returncode:raise RuntimeError('copy failed '+str(copy.returncode))
        result['result']='PASS'
    except Exception as e:result['failure']=str(e)
    finally:
        for child in (copy,monitor):
            if child and child.poll() is None:
                child.terminate()
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
        evidence.write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()

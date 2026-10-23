"""Owner-approved static theme only; no ROS participant, restart, camera or motion.

Stage beside material.css and manifest.json (SHA256 supplied as sole argument).
Manifest maps the exact baseline HTML names to their SHA256. Fail closed on drift.
An explicitly owner-authorized --installation-cpu-report-only applies ONLY to
this static-file installation. Never changes production guard files/thresholds.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path('/home/jetson/project_atlas')
WEB=ROOT/'web/v2'
STAGE=Path(__file__).resolve().parent
CSS_SHA='ea6a213b8a7b5aa5f4777af64259a75589799ebd151e39acf4723fc6fb6368d5'
LINK=b'<link rel="stylesheet" href="/v2/material.css">'
NAMES={'camera.html','classic.html','commissioning.html','flysky-testlab.html',
       'index.html','lidar.html','mapping.html','testlab.html','vision3d.html','wifi.html'}


def sha(data):return hashlib.sha256(data).hexdigest()


def resource_check(gate,cpu,observation,report_only=False):
    import math
    if not math.isfinite(cpu) or not 0<=cpu<=100:raise RuntimeError('invalid CPU sample')
    row=gate.check(None if report_only else cpu,observation)
    row['cpu_percent']=cpu
    row['installation_cpu_policy']='OWNER REPORT ONLY' if report_only else 'STOP >75%'
    return row


def patched(data):
    if LINK in data or data.count(b'</head>')!=1:raise RuntimeError('unexpected HTML/theme state')
    out=data.replace(b'</head>',LINK+b'</head>',1)
    if out.replace(LINK,b'')!=data:raise RuntimeError('non-style HTML modification')
    return out


def atomic(path,data,mode=0o644):
    fd,name=tempfile.mkstemp(prefix='.theme-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.chmod(name,mode);os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def main():
    report_only=len(sys.argv)==3 and sys.argv[2]=='--installation-cpu-report-only'
    backup=Path(tempfile.mkdtemp(prefix='white-glass-backup-',dir=STAGE))
    report={'result':'ABORTED','backup':str(backup),'camera_started':False,'services_restarted':False}
    changed=[];original={};installed={}
    sys.path.insert(0,str(ROOT/'tools/vision3d'))
    import stationary_gate as G
    import stationary_ros_probe as P
    def services():
        values=G.services()
        for unit in ('rover-status-web','atlas-network-fallback'):
            args=['systemctl']+(['--user'] if unit=='rover-status-web' else [])
            raw=subprocess.check_output(args+['show',unit,'-p','MainPID','-p','NRestarts','-p','ActiveState'],text=True,timeout=3)
            values[unit]=dict(l.split('=',1) for l in raw.strip().splitlines())
        if any(v['ActiveState']!='active' or v['MainPID']=='0' for v in values.values()):
            raise RuntimeError('protected service not active')
        return values
    def off():
        status=json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/vision3d/summary',timeout=3))
        if not (status.get('state')=='OFF' or (status.get('state')=='RESOURCE BLOCKED' and status.get('driver_stopped') is True)):
            raise RuntimeError('Astra not OFF')
        if subprocess.run(['pgrep','-x','astra_camera_no'],stdout=subprocess.DEVNULL,timeout=2).returncode!=1:
            raise RuntimeError('Astra process present/unknown')
    def samples(pid):
        def pticks():
            fields=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
            return int(fields[11])+int(fields[12])
        rows=[]
        for _ in range(10):
            a=G.ticks();t=time.monotonic();p=pticks();time.sleep(1)
            b=G.ticks();end=time.monotonic();q=pticks()
            row=resource_check(G,G.cpu_delta(a,b),P.safety_snapshot(),report_only)
            P.extra_safety();off()
            row['web_cpu_one_core_percent']=100*(q-p)/os.sysconf('SC_CLK_TCK')/(end-t)
            row['web_rss_kib']=int(next(l.split()[1] for l in Path('/proc',str(pid),'status').read_text().splitlines() if l.startswith('VmRSS:')))
            rows.append(row)
        return rows
    try:
        manifest_bytes=(STAGE/'manifest.json').read_bytes()
        if not (len(sys.argv)==2 or report_only) or sha(manifest_bytes)!=sys.argv[1]:raise RuntimeError('manifest hash/arguments mismatch')
        report['installation_cpu_report_only']=report_only
        manifest=json.loads(manifest_bytes)
        if set(manifest)!=NAMES:raise RuntimeError('unexpected file scope')
        css=(STAGE/'material.css').read_bytes()
        if sha(css)!=CSS_SHA or (WEB/'material.css').exists():raise RuntimeError('CSS mismatch/already present')
        if shutil.disk_usage(WEB).free<100*1024*1024:raise RuntimeError('disk headroom insufficient')
        for name,expected in manifest.items():
            data=(WEB/name).read_bytes()
            if sha(data)!=expected:raise RuntimeError('live baseline mismatch: '+name)
            original[name]=data;installed[name]=patched(data)
        installed['material.css']=css
        protected={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in WEB.rglob('*') if p.is_file() and p.name not in NAMES}
        for name in ('atlas_status_web.py','atlas_web_v2.py'):
            p=ROOT/'scripts'/name;protected[str(p.relative_to(ROOT))]=sha(p.read_bytes())
        for name in ('stationary_gate.py','stationary_ros_probe.py'):
            p=ROOT/'tools/vision3d'/name;protected[str(p.relative_to(ROOT))]=sha(p.read_bytes())
        report['services_before']=services();off()
        report['before']=samples(report['services_before']['rover-status-web']['MainPID'])
        shutil.copytree(WEB,backup/'web')
        for name,data in original.items():
            if sha((backup/'web'/name).read_bytes())!=sha(data):raise RuntimeError('backup verification failed')
        if services()!=report['services_before']:raise RuntimeError('service identity changed')
        report['installed_hashes']={name:sha(data) for name,data in installed.items()}
        for name in ['material.css']+sorted(NAMES):
            path=WEB/name
            if name in original and path.read_bytes()!=original[name]:raise RuntimeError('concurrent change: '+name)
            mode=path.stat().st_mode & 0o777 if path.exists() else 0o644
            atomic(path,installed[name],mode);changed.append(name)
        for rel,digest in protected.items():
            if sha((ROOT/rel).read_bytes())!=digest:raise RuntimeError('protected file changed: '+rel)
        report['http']={}
        for name in ['material.css']+sorted(NAMES):
            with urllib.request.urlopen('http://127.0.0.1:8088/v2/'+name,timeout=3) as r:
                body=r.read();report['http'][name]=r.status
            if name=='material.css':
                if sha(body)!=CSS_SHA:raise RuntimeError('served CSS mismatch')
            elif LINK not in body:raise RuntimeError('served page lacks theme: '+name)
            if sha((WEB/name).read_bytes())!=sha(installed[name]):raise RuntimeError('installed hash mismatch')
        report['after']=samples(report['services_before']['rover-status-web']['MainPID'])
        report['services_after']=services()
        if report['services_after']!=report['services_before']:raise RuntimeError('protected service changed')
        report['result']='DEPLOYED_VERIFIED_NO_RESTART'
    except Exception as exc:
        report['error']=repr(exc);errors=[]
        for name in reversed(changed):
            try:
                path=WEB/name
                if path.read_bytes()!=installed[name]:raise RuntimeError('concurrent file change')
                if name in original:atomic(path,original[name],(backup/'web'/name).stat().st_mode & 0o777)
                else:path.unlink()  # only our new hash-verified CSS, never existing evidence
            except Exception as rollback:errors.append(name+': '+repr(rollback))
        report['rollback_errors']=errors
        report['rollback_verified']=bool(changed) and not errors and all((WEB/n).read_bytes()==b for n,b in original.items())
    finally:
        (backup/'result.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    return 0 if report['result']=='DEPLOYED_VERIFIED_NO_RESTART' else 1


if __name__=='__main__':sys.exit(main())

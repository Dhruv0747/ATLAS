#!/usr/bin/env python3
"""Single approved activation; local sudo only. Runtime candidate is unchanged."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import signal
import subprocess
import sys
import time
import urllib.request

BASE=Path(__file__).resolve().parent
MANIFEST='9161805480525237f4a75f4a9763b997b3c893a57a1641caf4e5f4d0d0937318'
EVIDENCE=Path('/var/lib/atlas-monitoring-activation-20261030')
TIMER='atlas-monitoring-activation-rollback'
FILES={'atlas_health_exporter.py':'/opt/atlas-monitoring-exporter/atlas_health_exporter.py',
       'guard.py':'/usr/local/libexec/atlas-monitoring-guard.py',
       'atlas-monitor.nft':'/etc/atlas-monitoring/atlas-monitor.nft',
       **{f'atlas-monitoring-{x}.service':f'/etc/systemd/system/atlas-monitoring-{x}.service' for x in ('firewall','watchdog','exporter')}}

def run(*args):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=15).stdout

def verify_package():
    manifest=(BASE/'SHA256SUMS').read_bytes()
    assert hashlib.sha256(manifest).hexdigest()==MANIFEST,'manifest mismatch'
    expected={}
    for line in manifest.decode().splitlines():
        digest,name=line.split('  ')
        assert name in {*FILES,'TARGET_UID'},'unexpected package member'
        data=(BASE/name).read_bytes()
        assert hashlib.sha256(data).hexdigest()==digest,'package hash: '+name
        expected[name]=data
    assert set(expected)=={*FILES,'TARGET_UID'},'incomplete package'
    assert int(expected['TARGET_UID'])==pwd.getpwnam('jetson').pw_uid,'UID mismatch'
    return expected

def normalized(text):
    return '\n'.join(re.sub(r'\[\d+:\d+\]','[0:0]',x) for x in text.splitlines() if not x.startswith('#'))

def services():
    uid=str(pwd.getpwnam('jetson').pw_uid)
    return run('runuser','-u','jetson','--','env','XDG_RUNTIME_DIR=/run/user/'+uid,
               'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/'+uid+'/bus','systemctl','--user','show',
               'atlas-*.service','rover-*.service','-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState')

def save(name,value):
    data=value if isinstance(value,str) else json.dumps(value,indent=2,allow_nan=False)
    tmp=EVIDENCE/(name+'.tmp')
    with tmp.open('w') as f:f.write(data);f.flush();os.fsync(f.fileno())
    tmp.replace(EVIDENCE/name)

def sample(g,prev,counts,protected):
    time.sleep(max(0,prev[0]+1-time.monotonic()))
    if protected:return g.observe(prev,counts)
    # Same safety predicate before firewall installation; never a listener here.
    signal.setitimer(signal.ITIMER_REAL,2)
    try:
        with urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=.5) as response:
            body=response.read(1048577)
        g.require(len(body)<=1048576,'API oversized')
        ros=json.loads(body)['ros'];cur=g.cpu_counter()
        g.require(.8<=cur[0]-prev[0]<=1.5 and cur[1]>prev[1],'CPU sampling interval')
        cpu=100*(1-(cur[2]-prev[2])/(cur[1]-prev[1]))
        mem={a:int(b.split()[0]) for a,b in (x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines())}
        ram=100*(1-mem['MemAvailable']/mem['MemTotal']);temps,_=g.read_thermal()
        counts=g.validate(ros,cpu,ram,temps,counts)
        return cur,counts,dict(time=time.time(),cpu=cpu,ram=ram,temp=max(temps),sample_interval=cur[0]-prev[0])
    finally:signal.setitimer(signal.ITIMER_REAL,0)

def main():
    assert os.geteuid()==0,'local sudo required'
    EVIDENCE.mkdir(mode=0o700)  # exclusive: no automatic or accidental repeat
    os.umask(0o077)
    result={'result':'FAIL','source_commit':'852feb9ad8e6443b74981cbe6d8b2e013644e330'}
    installed=[];timer=False;g=None;before=None;samples=[];original=None
    def interrupted(signum,frame):raise RuntimeError('activation interrupted')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:
        package=verify_package()
        spec=importlib.util.spec_from_file_location('reviewed_guard',BASE/'guard.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
        signal.signal(signal.SIGALRM,g.deadline)
        assert not any(Path(p).exists() for p in FILES.values()),'installed path exists'
        assert not g.STATE.exists(),'monitoring state exists'
        assert not g.listeners() and not g.firewall_present(),'listener/table exists'
        original=run('iptables-save');original6=run('ip6tables-save')
        assert 'ATLAS_MONITOR' not in original,'trial firewall remains'
        assert 'legacy' in run('iptables','--version'),'backend changed'
        save('iptables-before.txt',original);save('ip6tables-before.txt',original6)
        save('nft-before.json',run('nft','-j','list','ruleset'))
        before=services();save('services-before.txt',before)
        prev=g.cpu_counter();counts=None
        for _ in range(60):
            prev,counts,s=sample(g,prev,counts,False);s['phase']='baseline';samples.append(s)
        save('samples.json',samples)
        for name,destination in FILES.items():
            target=Path(destination)
            if not target.parent.exists():
                target.parent.mkdir(mode=0o755,parents=True);target.parent.chmod(0o755)
            with target.open('xb') as f:f.write(package[name]);f.flush();os.fsync(f.fileno())
            installed.append(target);target.chmod(0o644)
            assert target.read_bytes()==package[name],'installed hash mismatch'
        save('package-manifest.txt',(BASE/'SHA256SUMS').read_text())
        run('systemd-analyze','verify',*[str(p) for p in installed if p.suffix=='.service'])
        run('systemctl','daemon-reload')
        # Independent expiry protects against supervisor death; cancelled only after acceptance.
        run('systemd-run','--unit='+TIMER,'--on-active=480s','/usr/bin/python3','-I','-B',FILES['guard.py'],'rollback');timer=True
        prev=g.cpu_counter();prev,counts,s=sample(g,prev,counts,False)
        run('systemctl','start',g.FIREWALL);g.verify_firewall()
        save('nft-active.json',run('nft','-j','list','table','inet',g.TABLE))
        run('systemctl','start',g.UNIT)
        assert run('systemctl','is-active',g.UNIT).strip()=='active','exporter startup failed'
        prev=g.cpu_counter();started=time.monotonic()
        while time.monotonic()-started<300:
            prev,counts,s=sample(g,prev,counts,True);s['phase']='active';samples.append(s)
            for unit in (g.UNIT,g.WATCHDOG):
                info=run('systemctl','show',unit,'-p','ActiveState','-p','MainPID','-p','NRestarts','-p','CPUUsageNSec','-p','MemoryCurrent')
                assert 'ActiveState=active' in info and 'NRestarts=0' in info,'monitoring service failure'
                s[unit]=info
            save('samples.json',samples)
        assert before==services(),'protected services changed'
        assert normalized(original)==normalized(run('iptables-save')),'legacy firewall changed'
        assert normalized(original6)==normalized(run('ip6tables-save')),'IPv6 legacy firewall changed'
        g.verify_firewall();run('systemctl','enable',g.UNIT)
        run('systemctl','stop',TIMER+'.timer');timer=False
        save('services-after.txt',services())
        result.update(result='PASS',persistent='ENABLED_ACTIVE',reboot_verified=False,
                      grafana_validation='PENDING PC verification',rollback='installed helper; evidence retained')
    except Exception as exc:
        result['error']=str(exc)[:1000]
        try:
            if installed:
                run('systemctl','disable','--now','atlas-monitoring-exporter.service')
                run('systemctl','stop','atlas-monitoring-watchdog.service')
                assert not g.listeners(),'listener remains; retain firewall'
                run('systemctl','stop','atlas-monitoring-firewall.service')
                if g.firewall_present():
                    assert (g.STATE/'firewall-owned.json').exists(),'unowned firewall'
                    g.verify_firewall();run('nft','delete','table','inet',g.TABLE)
                for target in reversed(installed):
                    name=next(k for k,v in FILES.items() if v==str(target))
                    assert target.read_bytes()==package[name],'changed installed file; retain'
                    target.unlink()
                run('systemctl','daemon-reload')
            if timer:run('systemctl','stop',TIMER+'.timer')
            if before is not None:assert before==services(),'protected service state changed'
            result['rollback']='VERIFIED' if installed else 'NOT NEEDED: no installation'
        except Exception as rollback_error:result['rollback_error']=str(rollback_error)[:1000]
    finally:
        save('samples.json',samples);save('result.json',result)
        save('SHA256SUMS',''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(EVIDENCE.iterdir()) if p.name!='SHA256SUMS'))
        print(json.dumps(result),flush=True)
    return 0 if result['result']=='PASS' else 1

if __name__=='__main__':sys.exit(main())

#!/usr/bin/env python3
"""Native PC systemd fake-unit tests. Never reference production service names."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=15)

def main():
    assert os.geteuid() == 0
    prefix = 'atlas-prep-' + uuid.uuid4().hex[:10]
    units = [prefix+'-'+x+'.service' for x in ('firewall','watchdog','exporter','burst','hardened')]
    paths = [Path('/run/systemd/system')/x for x in units]
    result = {}
    with tempfile.TemporaryDirectory(prefix=prefix, dir='/run') as temp:
        root = Path(temp)
        root.chmod(0o755)
        worker = root/'fake.py'
        worker.write_text('''import os,socket,sys,time
from pathlib import Path
root=Path(sys.argv[1]); mode=sys.argv[2]
if mode=='hardened':
 assert Path('/proc/stat').read_text().startswith('cpu')
 assert 'MemAvailable' in Path('/proc/meminfo').read_text()
 try: Path('/etc/'+root.name).write_text('must fail')
 except OSError: pass
 else: raise RuntimeError('filesystem not protected')
 sys.exit(0)
if mode=='firewall':
 (root/'protected').touch(); sys.exit(0)
if mode=='check':
 sys.exit(0 if (root/'protected').exists() and not (root/'reject').exists() else 78)
if mode=='exporter':
 assert (root/'protected').exists() and (root/'ready').exists()
 (root/'started').touch()
if mode=='watchdog':
 time.sleep(.25); (root/'ready').touch()
 s=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM); s.connect(os.environ['NOTIFY_SOCKET'])
 s.send(b'READY=1\\nWATCHDOG=1')
 while True:
  if not (root/'stall').exists(): s.send(b'WATCHDOG=1')
  time.sleep(.1)
while True: time.sleep(1)
''')
        py = '/usr/bin/python3 '+str(worker)+' '+str(root)+' '
        paths[0].write_text('[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart='+py+'firewall\n')
        paths[1].write_text('[Unit]\nRequires='+units[0]+'\nAfter='+units[0]+'\n[Service]\nType=notify\nRestart=no\nWatchdogSec=1\nTimeoutStopSec=1\nExecStart='+py+'watchdog\n')
        paths[2].write_text('[Unit]\nRequires='+units[0]+'\nBindsTo='+units[1]+'\nAfter='+units[0]+' '+units[1]+'\n[Service]\nExecCondition='+py+'check\nExecStart='+py+'exporter\nRestart=on-failure\nRestartSec=1\nTimeoutStopSec=1\n')
        paths[3].write_text('[Unit]\nStartLimitIntervalSec=10\nStartLimitBurst=3\n[Service]\nExecStart=/bin/false\nRestart=on-failure\nRestartSec=100ms\n')
        paths[4].write_text('[Service]\nType=oneshot\nUser=nobody\nExecStart='+py+'hardened\nCPUQuota=10%\nMemoryMax=64M\nTasksMax=32\nNice=10\nNoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=read-only\nPrivateTmp=yes\nRestrictAddressFamilies=AF_INET AF_UNIX AF_NETLINK\n')
        def state(unit):
            return run('systemctl','show',unit,'-p','ActiveState','--value').stdout.strip()
        def wait_off(unit):
            end=time.monotonic()+5
            while time.monotonic()<end:
                if state(unit) in ('inactive','failed'): return True
                time.sleep(.1)
            return False
        try:
            run('systemctl','daemon-reload')
            run('systemctl','start',units[2])
            end=time.monotonic()+3
            while not (root/'started').exists() and time.monotonic()<end: time.sleep(.05)
            result['ordered_readiness']=(root/'started').exists() and state(units[2])=='active'
            run('systemctl','kill','--signal=KILL',units[1])
            result['guard_crash_stops_exporter']=wait_off(units[2])
            run('systemctl','stop',*units[:3]); run('systemctl','reset-failed',*units[:3],check=False)
            (root/'started').unlink(); (root/'reject').touch()
            run('systemctl','start',units[2],check=False)
            result['condition_rejection_no_listener']=not (root/'started').exists() and state(units[2])!='active'
            run('systemctl','stop',*units[:3]); (root/'reject').unlink()
            run('systemctl','start',units[2]); (root/'stall').touch()
            result['watchdog_stall_stops_exporter']=wait_off(units[2])
            run('systemctl','start',units[3],check=False)
            end=time.monotonic()+5
            while time.monotonic()<end:
                if 'Start request repeated too quickly' in run('journalctl','-u',units[3],'-n','15','--no-pager').stdout: break
                time.sleep(.1)
            count=run('systemctl','show',units[3],'-p','NRestarts','--value').stdout.strip()
            time.sleep(.5)
            result['restart_limit']=(count=='3' and state(units[3])=='failed' and
                run('systemctl','show',units[3],'-p','NRestarts','--value').stdout.strip()==count and
                'Start request repeated too quickly' in run('journalctl','-u',units[3],'-n','15','--no-pager').stdout)
            run('systemctl','start',units[4])
            result['hardened_fake_process']=run('systemctl','show',units[4],'-p','Result','--value').stdout.strip()=='success'
            result['resource_properties']=(run('systemctl','show',units[4],'-p','MemoryMax','--value').stdout.strip()=='67108864' and
                run('systemctl','show',units[4],'-p','CPUQuotaPerSecUSec','--value').stdout.strip()=='100ms')
            run('systemctl','stop',*units)
            result['clean_shutdown']=all(state(x) in ('inactive','failed') for x in units)
            result['firewall_retained_on_stop']=(root/'protected').exists()
            assert all(result.values()), result
            print(json.dumps(result,indent=2))
        finally:
            run('systemctl','stop',*units,check=False)
            run('systemctl','reset-failed',*units,check=False)
            for path in paths: path.unlink(missing_ok=True)
            run('systemctl','daemon-reload')

if __name__=='__main__': main()

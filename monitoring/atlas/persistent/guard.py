#!/usr/bin/env python3
"""Monitoring-only guard. No ROS, serial, controller writes or production restarts.

All paths/addresses are fixed. No environment switch can bypass a safety gate.
Faults retain the dedicated firewall and latch until explicit operator review.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.request

STATE = Path('/var/lib/atlas-monitoring')
CONFIG = Path('/etc/atlas-monitoring')
EXPORTER = Path('/opt/atlas-monitoring-exporter/atlas_health_exporter.py')
SHA = '0248d329dd659f3557b68ae8731cb1a85db763bb7855850e1c5cec0ccd0f3e3d'
TABLE = 'atlas_monitor'
UNIT = 'atlas-monitoring-exporter.service'
WATCHDOG = 'atlas-monitoring-watchdog.service'
FIREWALL = 'atlas-monitoring-firewall.service'
LIMITS = dict(control_policy=1, cmd_vel=1, motor_speed=2, encoder_health=1,
              enc_m1=1, enc_m2=1, enc_m3=1, enc_m4=1, lidar=2, imu_heading=2, odom=1)

class Rejected(RuntimeError):
    pass

def require(ok, reason):
    if not ok:
        raise Rejected(reason)

def command(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=1).stdout

def finite(value):
    return type(value) in (int, float) and math.isfinite(value)

def trusted(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            'untrusted file: '+str(path))

def atomic(name, value):
    target = STATE/name
    temporary = STATE/(name+'.tmp')
    fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output, allow_nan=False); output.flush(); os.fsync(output.fileno())
    os.replace(temporary, target)
    fd = os.open(STATE, os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

EVIDENCE = {}
ACTION = 'unknown'
EVENT_LIMIT = 16

def latch(reason):
    # Serialize independent guard processes; retain even malformed first evidence.
    fd = os.open(STATE/'evidence.lock', os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        except OSError:
            boot = None
        record = dict(time=time.time(), monotonic=time.monotonic(), boot_id=boot,
                      action=ACTION, reason=reason[:160], evidence=dict(EVIDENCE))
        if not os.path.lexists(STATE/'FAULT.json'):
            atomic('FAULT.json', record)
            return
        # Never read/repair/replace the original latch, including corrupt files.
        path = STATE/'fault-events.json'
        events = []
        if os.path.lexists(path):
            require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 65536,
                    'invalid subsequent evidence')
            events = json.loads(path.read_text())
            require(isinstance(events,list) and len(events)<=EVENT_LIMIT and
                    all(isinstance(e,dict) for e in events), 'corrupt subsequent evidence')
        events = (events + [record])[-EVENT_LIMIT:]
        require(len(json.dumps(events,allow_nan=False).encode())<=65536, 'evidence size limit')
        atomic('fault-events.json', events)

def evidence_scalar(value):
    return value if type(value) is bool or (finite(value) and abs(value)<1e15) else None

def safety_evidence(ros):
    # Whitelist numerical/boolean observations; no raw payloads or private strings.
    out = {'ages':{k:evidence_scalar(ros.get(k,{}).get('age')) for k in LIMITS}}
    for key, fields in [('control_policy',('stop_latched','manual_only','commission_armed')),
                        ('encoder_health',('packet_fresh',))]:
        try:
            obj=json.loads(ros.get(key,{}).get('value',''))
            out[key]={k:evidence_scalar(obj.get(k)) for k in fields}
        except (ValueError,TypeError,AttributeError):out[key]=None
    cmd=ros.get('cmd_vel',{}).get('value')
    out['command']={k:evidence_scalar(cmd.get(k)) for k in ('lin','ang')} if isinstance(cmd,dict) else None
    out['encoders']=[evidence_scalar(ros.get('enc_m'+str(i),{}).get('value')) for i in range(1,5)]
    out['motor_speed']=evidence_scalar(ros.get('motor_speed',{}).get('value'))
    return out

def no_fault():
    require(not os.path.lexists(STATE/'FAULT.json'), 'fault latched; owner review required')

def canonical(document):
    entries = []
    for entry in document['nftables']:
        if 'metainfo' in entry:
            continue
        require(len(entry) == 1, 'unexpected nft entry')
        kind, fields = next(iter(entry.items()))
        require(kind in ('table','chain','rule'), 'unexpected nft object')
        entries.append({kind:{k:v for k,v in fields.items() if k != 'handle'}})
    return entries

def expected_rules():
    def match(left, right):
        return {'match':{'op':'==','left':left,'right':right}}
    port = match({'payload':{'protocol':'tcp','field':'dport'}},9118)
    rule = {'family':'inet','table':TABLE,'chain':'input'}
    return [
        {'table':{'family':'inet','name':TABLE}},
        {'chain':{'family':'inet','table':TABLE,'name':'input','type':'filter',
                  'hook':'input','prio':-10,'policy':'accept'}},
        {'rule':dict(rule,expr=[port,match({'meta':{'key':'iifname'}},'wlP1p1s0'),
               match({'payload':{'protocol':'ip','field':'saddr'}},'192.168.1.6'),
               match({'payload':{'protocol':'ip','field':'daddr'}},'192.168.1.16'),{'return':None}])},
        {'rule':dict(rule,expr=[port,{'drop':None}])}]

def firewall_present():
    data = json.loads(command('/usr/sbin/nft','-j','list','tables'))
    return any(e.get('table',{}).get('family')=='inet' and
               e.get('table',{}).get('name')==TABLE for e in data['nftables'])

def verify_firewall():
    actual = json.loads(command('/usr/sbin/nft','-j','list','table','inet',TABLE))
    require(canonical(actual) == expected_rules(), 'firewall missing/changed')

def listeners():
    return command('/usr/bin/ss','-H','-ltn','sport','=',':9118').strip()

def install_firewall():
    no_fault()
    rule = CONFIG/'atlas-monitor.nft'; trusted(rule)
    require(not listeners(), 'port already listening')
    if firewall_present():
        require((STATE/'firewall-owned.json').exists(), 'unowned table; refusing adoption')
        verify_firewall(); return
    # Mark intended ownership before creation; never remove an ambiguous table.
    atomic('firewall-owned.json', {'table':TABLE,'time':time.time()})
    command('/usr/sbin/nft','-c','-f',str(rule))
    command('/usr/sbin/nft','-f',str(rule))  # one atomic transaction, never flush ruleset
    verify_firewall()

def read_thermal(root=Path('/sys/class/thermal')):
    values = []; unavailable = []
    for zone in sorted(root.glob('thermal_zone*')):
        name = (zone/'type').read_text().strip()
        try:
            value = float((zone/'temp').read_text())/1000
        except (OSError,TypeError,ValueError):
            # Jetson CV domains are power-gated; only known CV unavailable zones may be skipped.
            require(name in ('cv0-thermal','cv1-thermal','cv2-thermal'), 'required thermal zone unavailable')
            unavailable.append(name); continue
        require(math.isfinite(value) and -200 < value < 200, 'invalid thermal value')
        values.append(value)
    require(bool(values), 'no trustworthy temperature')
    return values, unavailable

def validate(ros, cpu, ram, temperatures, previous):
    for key, limit in LIMITS.items():
        age = ros[key]['age']
        require(finite(age) and 0 <= age <= limit, 'freshness: '+key)
    policy = json.loads(ros['control_policy']['value'])
    require(policy.get('stop_latched') is True and policy.get('manual_only') is True
            and policy.get('commission_armed') is False, 'stop/manual/commission policy')
    cmd = ros['cmd_vel']['value']; speed = ros['motor_speed']['value']
    require(all(finite(x) and x == 0 for x in (cmd.get('lin'),cmd.get('ang'),speed)), 'command/speed not zero')
    health = json.loads(ros['encoder_health']['value'])
    require(health.get('link_state')=='LIVE' and health.get('packet_fresh') is True, 'MCU not live')
    counts = [ros['enc_m'+str(i)]['value'] for i in range(1,5)]
    require(all(type(x) is int for x in counts), 'invalid encoder counts')
    require(previous is None or counts == previous, 'encoder movement')
    require(finite(cpu) and 0 <= cpu <= 75, 'CPU limit')
    require(finite(ram) and 0 <= ram <= 80, 'RAM limit')
    require(temperatures and all(finite(t) and -200 < t < 70 for t in temperatures), 'temperature limit/missing')
    return counts

def cpu_counter():
    values = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    require(len(values)==8, 'CPU counters missing')
    return time.monotonic(),sum(values),values[3]+values[4]

def deadline(signum, frame):
    raise Rejected('observer deadline exceeded')

def observe(previous, counts):
    EVIDENCE.clear()
    EVIDENCE.update(observation_started=time.time(), stage='firewall')
    no_fault()
    # Absolute deadline also bounds a slow-drip HTTP response, filesystem stalls and nft inspection.
    signal.setitimer(signal.ITIMER_REAL, 2)
    try:
        verify_firewall()
        EVIDENCE['stage']='API'
        started = time.monotonic()
        with urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=0.5) as response:
            payload = response.read(1048577)
        require(len(payload)<=1048576 and time.monotonic()-started<=0.75, 'API size/deadline')
        ros = json.loads(payload)['ros']
        EVIDENCE.update(safety_evidence(ros)); EVIDENCE['stage']='resources'
        cur = cpu_counter(); elapsed = cur[0]-previous[0]
        require(0.8 <= elapsed <= 1.5 and cur[1]>previous[1] and cur[2]>=previous[2], 'CPU sampling interval')
        cpu = 100*(1-(cur[2]-previous[2])/(cur[1]-previous[1]))
        EVIDENCE.update(cpu=evidence_scalar(cpu),sample_interval=evidence_scalar(elapsed))
        mem = {a:int(b.split()[0]) for a,b in (x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines())}
        ram = 100*(1-mem['MemAvailable']/mem['MemTotal'])
        EVIDENCE['ram']=evidence_scalar(ram)
        temps, unavailable = read_thermal()
        EVIDENCE.update(cpu=evidence_scalar(cpu),ram=evidence_scalar(ram),
                        temperatures=[evidence_scalar(t) for t in temps[:16]],
                        sample_interval=evidence_scalar(elapsed),
                        previous_encoders=[evidence_scalar(v) for v in counts] if counts is not None else None,stage='validate')
        counts = validate(ros,cpu,ram,temps,counts)
        return cur,counts,{'time':time.time(),'cpu':cpu,'ram':ram,'temp':max(temps),
                           'sample_interval':elapsed,'unavailable_thermal':unavailable}
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)

def integrity():
    trusted(EXPORTER)
    require(hashlib.sha256(EXPORTER.read_bytes()).hexdigest()==SHA, 'exporter hash mismatch')

def two_samples():
    integrity(); no_fault(); previous=cpu_counter(); counts=None; summary=None
    for _ in range(2):
        time.sleep(max(0, previous[0]+1-time.monotonic()))
        previous,counts,summary=observe(previous,counts)
    return previous,counts,summary

def notify(message):
    address=os.environ.get('NOTIFY_SOCKET')
    require(bool(address), 'missing systemd notify socket')
    if address.startswith('@'):
        address='\0'+address[1:]
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as client:
        client.settimeout(0.5); client.connect(address); client.sendall(message.encode())

def stop_exporter():
    # Nonblocking: exporter has After=watchdog; blocking here would deadlock a stop job.
    command('/usr/bin/systemctl','--no-block','stop',UNIT)

def watchdog():
    no_fault()
    require(not (STATE/'observer-active.json').exists(), 'unclean observer exit; owner review required')
    atomic('observer-active.json',{'pid':os.getpid(),'time':time.time()})
    previous,counts,summary=two_samples()
    atomic('last-health.json',summary)
    notify('READY=1\nWATCHDOG=1')
    last_saved=time.monotonic()
    try:
        while True:
            time.sleep(max(0,previous[0]+1-time.monotonic()))
            previous,counts,summary=observe(previous,counts)
            notify('WATCHDOG=1')
            if time.monotonic()-last_saved>=15:
                atomic('last-health.json',summary); last_saved=time.monotonic()
    finally:
        # Remains on any fault/crash. Only clean systemd SIGTERM path clears it below.
        pass

def rollback():
    command('/usr/bin/systemctl','disable','--now',UNIT)
    command('/usr/bin/systemctl','stop',WATCHDOG)
    require(command('/usr/bin/systemctl','show',UNIT,'-p','MainPID','--value').strip()=='0', 'exporter still running')
    require(not listeners(), 'listener remains; firewall retained')
    command('/usr/bin/systemctl','stop',FIREWALL)
    if firewall_present():
        require((STATE/'firewall-owned.json').exists(), 'unowned table')
        verify_firewall()
        command('/usr/sbin/nft','delete','table','inet',TABLE)
    require(not firewall_present(), 'firewall rollback incomplete')
    atomic('rollback.json',{'time':time.time(),'result':'PASS'})

class CleanStop(BaseException):
    pass

def main():
    global ACTION
    EVIDENCE.clear()
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['firewall','preflight','watchdog','rollback'])
    action=parser.parse_args().action
    ACTION=action
    require(os.geteuid()==0,'root required')
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    require(STATE.lstat().st_uid==0 and stat.S_ISDIR(STATE.lstat().st_mode)
            and not STATE.lstat().st_mode & 0o077,'untrusted state directory')
    signal.signal(signal.SIGALRM,deadline)
    def stopped(signum,frame):
        raise CleanStop()
    signal.signal(signal.SIGTERM,stopped); signal.signal(signal.SIGINT,stopped)
    try:
        if action in ('firewall','rollback'):
            with open(STATE/'operations.lock','a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                (install_firewall if action=='firewall' else rollback)()
        elif action=='preflight':
            two_samples()
        else:
            watchdog()
    except CleanStop:
        if action=='watchdog':
            # systemd ordering stops exporter first on a normal dependency stop.
            if not listeners() and not os.path.lexists(STATE/'FAULT.json'):
                (STATE/'observer-active.json').unlink(missing_ok=True)
            else:
                latch('observer stopped with exporter/fault present')
        return 0
    except Exception as exc:
        try:
            latch(str(exc) if isinstance(exc,Rejected) else type(exc).__name__)
        finally:
            if action in ('watchdog','preflight'):
                try:
                    stop_exporter()
                except Exception:
                    pass  # systemd BindsTo/WatchdogSec also stops the exporter
        print('Monitoring guard rejected; inspect local fault latch',file=sys.stderr)
        return 78
    return 0

if __name__=='__main__':
    sys.exit(main())

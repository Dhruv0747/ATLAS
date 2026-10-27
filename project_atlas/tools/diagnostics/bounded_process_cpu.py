"""Bounded passive CPU evidence. No ROS, subprocess, service or hardware control.
Uses Stage31 aggregate convention; adds PID start identity and cgroup accounting.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import time
import urllib.request
from contextlib import contextmanager

POLL_INTERVAL = 1.0
CYCLE_TIMEOUT = 0.75
API_TIMEOUT = 0.25

@contextmanager
def bounded_cycle():
    """Linux main-thread watchdog covering HTTP, collection and evidence writes."""
    def expired(*_):
        raise TimeoutError('safety cycle deadline')
    old = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, CYCLE_TIMEOUT)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)

def fetch_safety():
    # Fixed loopback endpoint, proxies disabled, no ROS discovery or control calls.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:8088/api/status', timeout=API_TIMEOUT) as response:
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise ValueError('safety response size limit')
    return json.loads(body)

def safety_check(data, elapsed):
    from stm32_readback.safety_evidence import evaluate
    report = evaluate(data)
    ros = data.get('ros', {}) if isinstance(data, dict) else {}
    ros = ros if isinstance(ros, dict) else {}
    failed = report['failed_predicates']
    for name in ('control_policy', 'cmd_vel', 'encoder_health'):
        item = ros.get(name)
        item = item if isinstance(item, dict) else {}
        age = item.get('age')
        if type(age) not in (int, float) or not math.isfinite(age) or age < 0 or age + elapsed > 1:
            failed.append(name + '.effective_freshness')
    item = ros.get('encoder_health', {})
    value = item.get('value') if isinstance(item, dict) else None
    try:
        value = json.loads(value) if isinstance(value, str) else value
        packet_age = value['packet_age_s']
        if value['link_state'] != 'LIVE': failed.append('telemetry.LIVE')
        if (type(packet_age) not in (int, float) or not math.isfinite(packet_age)
                or packet_age < 0 or packet_age + elapsed > 1):
            failed.append('telemetry.packet_freshness')
    except (ValueError, KeyError, TypeError):
        failed.append('telemetry.missing_or_malformed')
    report['request_elapsed_s'] = elapsed
    return report

MAX_PIDS = 4096
MAX_GROUPS = 256
MAX_BYTES = 16 * 1024 * 1024

def read(path, limit=65536):
    with open(path, 'rb') as f:
        value = f.read(limit + 1)
    if len(value) > limit:
        raise ValueError('attribute size limit')
    return value.decode('utf-8', errors='strict')

def process_stat(text):
    end = text.rfind(')')
    fields = text[end + 2:].split()
    return {'name': text[text.index('(')+1:end], 'start_ticks': int(fields[19]),
            'user_ticks': int(fields[11]), 'system_ticks': int(fields[12])}

def memberships(text):
    return [dict(zip(('id','controllers','path'), line.split(':',2)))
            for line in text.splitlines()]

def group_mounts(proc):
    result = []
    for line in read(proc/'self/mountinfo').splitlines():
        left, right = line.split(' - ',1); a,b=left.split(),right.split()
        if b[0]=='cgroup2' or (b[0]=='cgroup' and 'cpuacct' in b[2].split(',')):
            result.append({'version':2 if b[0]=='cgroup2' else 1,
                           'root':a[3], 'mount':a[4]})
    return result

def group_path(m, mounts):
    version=2 if m['controllers']=='' else 1
    if version==1 and 'cpuacct' not in m['controllers'].split(','):return None
    for mount in mounts:
        if mount['version']!=version:continue
        root=Path(mount['root']); path=Path(m['path'])
        try: rel=path.relative_to(root)
        except ValueError:continue
        base=Path(mount['mount']).resolve(); target=(base/rel).resolve()
        if not target.is_relative_to(base):raise ValueError('cgroup path escape')
        return version,target
    return None

def snapshot(proc=Path('/proc')):
    started=time.monotonic(); cpu_started=time.monotonic()
    cpu=[int(v) for v in read(proc/'stat').splitlines()[0].split()[1:9]]
    if len(cpu)!=8:raise ValueError('invalid aggregate counters')
    cpu_finished=time.monotonic()
    mounts=group_mounts(proc); processes={}; groups={}; errors=[]; wanted={}
    pids=sorted(p for p in proc.iterdir() if p.name.isdigit())
    if len(pids)>MAX_PIDS:raise ValueError('process count limit')
    for p in pids:
        t=time.monotonic()
        try:
            stat=process_stat(read(p/'stat')); mem=memberships(read(p/'cgroup'))
            # Verify PID did not get reused during membership read.
            if process_stat(read(p/'stat'))['start_ticks']!=stat['start_ticks']:
                raise ValueError('PID identity changed')
            stat.update(sample_started=t,sample_finished=time.monotonic(),groups=mem)
            processes[p.name]=stat
            for member in mem:
                path=group_path(member,mounts)
                if path:wanted[str(path[1])]=path
        except (OSError,ValueError,IndexError) as exc:
            errors.append({'pid':p.name,'error_type':type(exc).__name__})
    if len(wanted)>MAX_GROUPS:raise ValueError('cgroup count limit')
    for key,(version,path) in wanted.items():
        t=time.monotonic()
        try:
            identity=path.stat()
            if version==2:
                values=dict(line.split() for line in read(path/'cpu.stat').splitlines())
                usage=int(values['usage_usec'])*1000
            else:usage=int(read(path/'cpuacct.usage'))
            if path.stat().st_ino!=identity.st_ino:raise ValueError('cgroup replaced')
            groups[key]={'usage_ns':usage,'inode':identity.st_ino,'device':identity.st_dev,
                         'version':version,'sample_started':t,'sample_finished':time.monotonic()}
        except (OSError,ValueError,KeyError) as exc:
            errors.append({'cgroup':key,'error_type':type(exc).__name__})
    return {'wall':time.time(),'started':started,'finished':time.monotonic(),
            'cpu_started':cpu_started,'cpu_finished':cpu_finished,'cpu':cpu,
            'processes':processes,'groups':groups,'errors':errors}

def differences(before,after,hz):
    delta=[b-a for a,b in zip(before['cpu'],after['cpu'])]
    total=sum(delta)
    if len(delta)!=8 or any(v<0 for v in delta) or total<=0:raise ValueError('invalid CPU delta')
    cpu=100*(total-delta[3]-delta[4])/total
    result={'cpu_delta_ticks':delta,'cpu_pct':cpu,
            'aggregate_interval_s':after['cpu_started']-before['cpu_started'],
            'processes':{},'groups':{},'new_or_reused':[],
            'exited':sorted(set(before['processes'])-set(after['processes']))}
    for pid,b in after['processes'].items():
        a=before['processes'].get(pid)
        if not a or a['start_ticks']!=b['start_ticks']:
            result['new_or_reused'].append(pid);continue
        ticks=b['user_ticks']+b['system_ticks']-a['user_ticks']-a['system_ticks']
        interval=b['sample_started']-a['sample_started']
        if ticks<0 or interval<=0:raise ValueError('invalid process delta')
        result['processes'][pid]={'delta_ticks':ticks,'interval_s':interval,'one_core_pct':100*ticks/hz/interval}
    for key,b in after['groups'].items():
        a=before['groups'].get(key)
        if not a or (a['inode'],a['device'])!=(b['inode'],b['device']):continue
        ns=b['usage_ns']-a['usage_ns'];interval=b['sample_started']-a['sample_started']
        if ns<0 or interval<=0:raise ValueError('invalid cgroup delta')
        result['groups'][key]={'delta_ns':ns,'interval_s':interval,'one_core_pct':100*ns/1e9/interval}
    return result

def resource_check(cpu,mem,thermal):
    if type(cpu) not in (int,float) or not math.isfinite(cpu) or not 0<=cpu<=100:
        raise ValueError('invalid CPU measurement')
    values=list(thermal.get('thermal_zones_c',{}).values())
    if thermal.get('platform_model_error') or thermal.get('thermal_read_errors') or not values:
        raise ValueError('untrustworthy temperature')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):raise ValueError('invalid temperature')
    if not 0<mem['MemTotal'] or not 0<=mem['MemAvailable']<=mem['MemTotal']:raise ValueError('invalid RAM')
    ram=100*(1-mem['MemAvailable']/mem['MemTotal']);temp=max(values)
    return {'cpu_pct':cpu,'ram_pct':ram,'temperature_c':temp,
            'failed':(['cpu'] if cpu>75 else []) + (['ram'] if ram>80 else []) + (['temperature'] if temp>=70 else [])}

def run(output,duration,collect=snapshot,thermal_reader=None,safety_reader=fetch_safety):
    if not 2<=duration<=60:raise ValueError('duration must be 2..60 seconds')
    if thermal_reader is None:
        from offboard_bridge_preflight import read_thermal
        thermal_reader=read_thermal
    hz=os.sysconf('SC_CLK_TCK');start=time.monotonic();own=time.process_time();written=0
    with open(output,'x',encoding='utf-8') as f:
        os.chmod(output,0o600)
        def emit(row):
            nonlocal written
            data=json.dumps(row,allow_nan=False)+'\n';written+=len(data.encode())
            if written>MAX_BYTES:raise ValueError('output byte limit')
            f.write(data);f.flush()
        def guard():
            began=time.monotonic()
            try:
                data=safety_reader()
                report=safety_check(data,time.monotonic()-began)
            except Exception as exc:
                emit({'kind':'safety_error','error_type':type(exc).__name__,
                      'monotonic':time.monotonic()})
                raise ValueError('safety request or evaluation failed') from None
            emit({'kind':'safety','observation':report})
            if report['failed_predicates']:raise ValueError('safety predicates rejected')
        def resources(cpu):
            mem={line.split(':')[0]:int(line.split()[1]) for line in read(Path('/proc/meminfo')).splitlines()}
            thermal=thermal_reader()
            emit({'kind':'resource_inputs','mem':{k:mem[k] for k in ('MemTotal','MemAvailable')},'thermal':thermal})
            measured=resource_check(cpu,mem,thermal)
            emit({'kind':'resources','observation':measured})
            if measured['failed']:raise ValueError('resource limit exceeded')
        try:
            emit({'kind':'metadata','pid':os.getpid(),'hz':hz,'logical_cpus':os.cpu_count(),
                  'limits':{'cpu':75,'ram':80,'temperature':70},
                  'reject_operators':{'cpu':'>','ram':'>','temperature':'>='},
                  'poll_interval_s':POLL_INTERVAL,'cycle_timeout_s':CYCLE_TIMEOUT,
                  'api_timeout_s':API_TIMEOUT,'start_wall':time.time()})
            with bounded_cycle():
                guard()
                previous=collect();emit({'kind':'baseline','snapshot':previous})
                if previous['errors']:raise ValueError('incomplete baseline process/cgroup evidence')
                guard()
            for index in range(1,int(duration)+1):
                due=start+index*POLL_INTERVAL
                time.sleep(max(0,due-time.monotonic()))
                if time.monotonic()-due>CYCLE_TIMEOUT:raise TimeoutError('missed safety polling deadline')
                with bounded_cycle():
                    guard()
                    current=collect();delta=differences(previous,current,hz)
                    emit({'kind':'sample','snapshot':current,'delta':delta,
                          'profiler_cpu_seconds':time.process_time()-own,'elapsed_s':time.monotonic()-start})
                    resources(delta['cpu_pct'])
                    if current['errors']:raise ValueError('incomplete process/cgroup evidence')
                    guard()
                    previous=current
            emit({'kind':'complete','elapsed_s':time.monotonic()-start,'profiler_cpu_seconds':time.process_time()-own})
        except BaseException as exc:
            emit({'kind':'aborted','error_type':type(exc).__name__,
                  'reason':str(exc) if isinstance(exc,ValueError) else 'collection interrupted or unavailable'})
            raise
        finally:os.fsync(f.fileno())
    return hashlib.sha256(Path(output).read_bytes()).hexdigest()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--duration',type=int,default=15);a=p.parse_args()
    def stop(*_):raise InterruptedError('bounded stop')
    for s in (signal.SIGTERM,signal.SIGINT):signal.signal(s,stop)
    signal.signal(signal.SIGALRM,stop)
    print(run(a.output,a.duration))

"""Reuse deployed stationary gates without importing the mapping runtime."""
import json
import math
from pathlib import Path
import sys
import subprocess
import time
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
from stationary_gate import require_cpu,validate_policy,ticks,cpu_delta


def check(cpu,j):
    # Reuse policy/CPU predicates, but bound recorder systemctl instead of the
    # legacy check() helper's unbounded subprocess wait.
    require_cpu(cpu);policy=validate_policy(j['ros'])
    mem={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    ram=max(100*(1-mem['MemAvailable']/mem['MemTotal']),float(j['system']['ram_percent']))
    required={'cpu-thermal','gpu-thermal','soc0-thermal','soc1-thermal','soc2-thermal','tj-thermal'}
    temps={}
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        kind=(zone/'type').read_text().strip()
        if kind in required:temps[kind]=float((zone/'temp').read_text())/1000
    if set(temps)!=required or any(not math.isfinite(x) or not 0<x<70 for x in temps.values()):raise ValueError('thermal source unavailable/over limit')
    if not math.isfinite(ram) or not 0<=ram<=80:raise ValueError('RAM limit failed')
    recorder=subprocess.check_output(['systemctl','--user','show','atlas-stage20-public-capture.service','-p','ActiveState','-p','MainPID'],text=True,timeout=.3)
    if 'ActiveState=inactive' not in recorder or 'MainPID=0\n' not in recorder:raise ValueError('recorder not OFF')
    return dict(cpu_percent=cpu,ram_percent=ram,thermal_c=temps,policy=policy)


def observe(cpu,window):
    if not math.isfinite(window) or not .9<=window<=1.1:raise ValueError('CPU observation window not one second')
    with urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=.5) as response:
        raw=response.read(1_048_577)
        if len(raw)>1_048_576:raise ValueError('oversized safety snapshot')
    j=json.loads(raw)
    r=check(cpu,j)  # existing E-STOP/manual/zero, resources and recorder checks
    temperature=max(r['thermal_c'].values())
    if not 0<temperature<70:raise ValueError('temperature unavailable or >=70')
    for key in ('control_policy','cmd_vel','encoder_health'):
        age=j['ros'][key]['age']
        if type(age) not in (int,float) or not math.isfinite(age) or not 0<=age<=1:raise ValueError(key+' stale/missing')
    e=j['ros']['encoder_health']['value'];e=json.loads(e) if isinstance(e,str) else e
    age=e['packet_age_s'];deltas=e['encoder_interval_delta_m']
    if e['link_state']!='LIVE' or e['packet_fresh'] is not True or type(age) not in (int,float) or not 0<=age<=1:
        raise ValueError('telemetry not LIVE/fresh')
    if len(deltas)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or v!=0 for v in deltas):raise ValueError('encoder motion/unknown')
    return dict(cpu=r['cpu_percent'],ram=r['ram_percent'],temperature=temperature,
                checked_mono=time.monotonic(),policy=r['policy'],commands_zero=True,telemetry_live=True)

"""Read-only stationary/resource admission for isolated Astra work. No ROS control."""
import json
import math
from pathlib import Path
import subprocess
import time
import urllib.request

UNITS=('atlas-camera.service','rover-base-telemetry.service','atlas-cmd-vel-mux.service',
       'atlas-ekf.service','atlas-localization.service','atlas-lidar.service')


class AdmissionError(RuntimeError):
    def __init__(self,message,evidence):
        super().__init__(message)
        self.evidence=evidence


def require_cpu(cpu):
    """Reject an already-failed sample before any blocking dashboard request."""
    if cpu is not None and (not math.isfinite(cpu) or cpu>75):
        evidence={'cpu':cpu if math.isfinite(cpu) else None,'other_resources':'not sampled: CPU already failed'}
        raise AdmissionError('CPU resource limit failed: '+str(evidence),evidence)


def ticks():
    a=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    return sum(a),a[3]+a[4]


def cpu_delta(a,b):
    dt,di=b[0]-a[0],b[1]-a[1]
    if dt<=0 or not 0<=di<=dt:raise RuntimeError('invalid CPU interval')
    return 100*(dt-di)/dt


def services():
    raw=subprocess.check_output(['systemctl','--user','show',*UNITS,'-p','Id','-p','MainPID','-p','NRestarts','-p','ActiveState'],text=True,timeout=2)
    return parse_services(raw)


def parse_services(raw):
    rows={}
    for block in raw.strip().split('\n\n'):
        row=dict(line.split('=',1) for line in block.splitlines())
        unit=row.pop('Id',None)
        if unit not in UNITS or unit in rows or set(row)!={'MainPID','NRestarts','ActiveState'}:
            raise RuntimeError('incomplete/duplicate protected service identity')
        rows[unit]=row
    if set(rows)!=set(UNITS):raise RuntimeError('missing protected service identity')
    return {unit:rows[unit] for unit in UNITS}


def validate_policy(r):
    for k in ('control_policy','cmd_vel'):
        if k not in r or not isinstance(r[k].get('age'),(int,float)) or not 0<=r[k]['age']<=2:
            raise RuntimeError('stale or missing '+k)
    p=r['control_policy']['value'];p=json.loads(p) if isinstance(p,str) else p
    if p.get('stop_latched') is not True or p.get('manual_only') is not True or p.get('commission_armed') is not False or p.get('source')!='STOPPED':
        raise RuntimeError('stationary policy admission failed')
    cmd=r['cmd_vel']['value']
    if any(k not in cmd or not math.isfinite(float(cmd[k])) or float(cmd[k])!=0 for k in ('lin','ang')):
        raise RuntimeError('nonzero/unknown motor command')
    return p


def check(cpu=None,observation=None):
    require_cpu(cpu)
    j=observation if observation is not None else json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=3))
    p=validate_policy(j.get('ros',{}))
    mem={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    ram=max(100*(mem['MemTotal']-mem['MemAvailable'])/mem['MemTotal'],float(j['system']['ram_percent']))
    temps={}
    for z in Path('/sys/class/thermal').glob('thermal_zone*'):
        name=(z/'type').read_text().strip()
        # Orin Nano CV zones are documented unavailable, not silently treated as zero.
        if name in ('cpu-thermal','gpu-thermal','soc0-thermal','soc1-thermal','soc2-thermal','tj-thermal'):
            temps[name]=float((z/'temp').read_text())/1000
    if not all(k in temps for k in ('cpu-thermal','gpu-thermal','soc0-thermal','soc1-thermal','soc2-thermal','tj-thermal')):
        raise RuntimeError('required thermal source missing')
    t=max(temps.values())
    if not math.isfinite(ram) or ram>80 or not all(math.isfinite(x) for x in temps.values()) or t>70 or (cpu is not None and (not math.isfinite(cpu) or cpu>75)):
        evidence={'cpu':cpu,'ram':ram,'temp':t,'thermal_c':temps}
        raise AdmissionError('resource limit failed: '+str(evidence),evidence)
    recorder=subprocess.check_output(['systemctl','--user','show','atlas-stage20-public-capture.service','-p','ActiveState','-p','MainPID'],text=True)
    if 'ActiveState=inactive' not in recorder or 'MainPID=0\n' not in recorder:raise RuntimeError('recorder not OFF')
    return {'cpu_percent':cpu,'ram_percent':ram,'thermal_c':temps,'policy':p,'commands_zero':True,'recorder_off':True}


def preflight():
    rows=[];a=ticks()
    for _ in range(3):
        time.sleep(1);b=ticks();rows.append(check(cpu_delta(a,b)));a=b
    identities=services()
    if any(x.get('ActiveState')!='active' or x.get('MainPID')=='0' for x in identities.values()):
        raise RuntimeError('essential owner not active')
    return rows,identities

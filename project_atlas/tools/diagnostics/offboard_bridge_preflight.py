"""Read-only Jetson admission probe; run once over existing SSH, no ROS node.

Prints evidence before the verdict. No bridge socket, publisher, service changes,
network configuration or retry. This probe only admits the approved stationary
test; it cannot activate recording itself.
"""
import datetime
import json
import math
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request


def ticks():
    fields=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    return sum(fields),fields[3]+fields[4]


def status():
    with urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=2) as response:
        raw=response.read(2*1024**2+1)
        if len(raw)>2*1024**2:raise ValueError('oversized dashboard response')
    data=json.loads(raw)
    ros=data['ros']
    # Whitelist diagnostics only; never save complete dashboard/network credentials.
    names=[k for k in ros if k in ('control_policy','cmd_vel','lidar','imu','imu_status',
        'imu_heading','encoder_update','encoder_health','im10a_status','im10a',
        'im10a_dashboard','im10a_dashboard_json','odom','amcl_pose','safety_status')
        or k.startswith('enc_m')]
    return {'system':{k:data['system'].get(k) for k in
                     ('cpu_percent','ram_percent','temp','resource_age_s')},
            'ros':{k:ros[k] for k in names},'available_diagnostic_keys':[
                k for k in ros if any(x in k for x in ('imu','im10','encoder','lidar','policy','safety'))]}


def main():
    result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'bridge_connected':False,'production_subscriptions_started':False,
            'cpu_samples':[],'decision':'BLOCKED','reasons':[]}
    try:
        previous=ticks();last=time.monotonic()
        for _ in range(5):
            time.sleep(1);current=ticks();now=time.monotonic()
            total=current[0]-previous[0];idle=current[1]-previous[1]
            if total<=0 or not 0<=idle<=total:raise ValueError('invalid CPU delta')
            result['cpu_samples'].append({'duration_s':now-last,'percent':100*(total-idle)/total})
            previous,last=current,now
        mem={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
        result['ram_percent']=100*(1-mem['MemAvailable']/mem['MemTotal'])
        result['thermal_zones_c']={}
        for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
            result['thermal_zones_c'][(zone/'type').read_text().strip()]=float((zone/'temp').read_text())/1000
        result['free_disk_bytes']=shutil.disk_usage('/home/jetson/project_atlas').free
        result['dashboard']=status()
        units=subprocess.run(['systemctl','--user','show','atlas-stage20-public-capture.service',
            'atlas-localization.service','rover-base-telemetry.service','--property=Id,ActiveState,MainPID,NRestarts'],
            capture_output=True,text=True,timeout=3,check=True).stdout
        result['services']=units
        reasons=result['reasons']
        for index,sample in enumerate(result['cpu_samples']):
            if not .9<=sample['duration_s']<=2:reasons.append('CPU interval %s duration invalid'%index)
            if sample['percent']>75:reasons.append('CPU interval %s %.6f%% exceeds75%%'%(index,sample['percent']))
        if result['ram_percent']>80:reasons.append('measured RAM exceeds80%')
        if not result['thermal_zones_c']:reasons.append('temperature unavailable')
        for name,value in result['thermal_zones_c'].items():
            if not math.isfinite(value) or value>70:reasons.append('temperature %s=%s exceeds70C/invalid'%(name,value))
        data=result['dashboard'];system=data['system'];ros=data['ros']
        for field,limit in (('cpu_percent',75),('ram_percent',80)):
            value=float(system[field])
            if not math.isfinite(value) or not 0<=value<=limit:reasons.append('dashboard %s=%s violates%s'%(field,value,limit))
        temp=float(str(system['temp']).split()[0])
        if not math.isfinite(temp) or temp>70:reasons.append('dashboard temperature violates70C')
        def fresh(key):
            record=ros[key];age=float(record['age'])
            if not math.isfinite(age) or not 0<=age<=2:reasons.append('%s evidence age=%s violates2s'%(key,age))
            value=record['value'];return json.loads(value) if isinstance(value,str) else value
        policy=fresh('control_policy');command=fresh('cmd_vel')
        for key,expected in (('stop_latched',True),('commission_armed',False),('manual_only',True),('source','STOPPED')):
            if policy.get(key)!=expected:reasons.append('control_policy.%s=%r; required%r'%(key,policy.get(key),expected))
        for key in ('lin','ang'):
            value=float(command[key])
            if not math.isfinite(value) or abs(value)>1e-9:reasons.append('motor command %s nonzero/invalid'%key)
        # Parse unit-specific service state rather than accepting another unit's PID0.
        blocks=[dict(line.split('=',1) for line in block.splitlines() if '=' in line) for block in units.strip().split('\n\n')]
        recorder=next((x for x in blocks if x.get('Id')=='atlas-stage20-public-capture.service'),{})
        if recorder.get('ActiveState')!='inactive' or recorder.get('MainPID')!='0':reasons.append('Stage20 recorder OFF not verified')
        # Sensor freshness must be verified before a later bridge connection. A
        # blocked resource/safety gate is final; do not create ROS readers to fill gaps.
        result['sensor_evidence']='dashboard diagnostic entries only; inspect required source ages before connection'
        result['decision']='RESOURCE_SAFETY_PASS_SENSOR_ADMISSION_PENDING' if not reasons else 'BLOCKED'
    except Exception as exc:
        result['reasons'].append(type(exc).__name__+': '+str(exc))
    print(json.dumps(result,indent=2,allow_nan=False),flush=True)
    return 0 if result['decision']!='BLOCKED' else 2


if __name__=='__main__':raise SystemExit(main())

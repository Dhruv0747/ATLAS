"""Read-only Jetson admission probe; run once over existing SSH, no ROS node.

Prints evidence before the verdict. No bridge socket, publisher, service changes,
network configuration or retry. This probe only admits the approved stationary
test; it cannot activate recording itself.
"""
import datetime
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import traceback
import urllib.request

THERMAL_ROOT = Path('/sys/class/thermal')


def read_sysfs_text(path, limit=256):
    """One bounded binary read; never feed an unavailable read to TextIOWrapper.

    Sysfs attributes are small ASCII values. An EAGAIN/None/empty read fails this
    attempt; there are no retries, default temperatures or dashboard fallbacks.
    """
    # Linux uses NONBLOCK; Windows offline fixtures require binary mode instead.
    flags = os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(path, flags)
    try:
        raw = os.read(descriptor, limit + 1)
    finally:
        os.close(descriptor)
    if not isinstance(raw, bytes):
        raise OSError('sysfs read returned no bytes object')
    if not raw or len(raw) > limit:
        raise ValueError('sysfs attribute empty or larger than %s bytes' % limit)
    value = raw.decode('ascii').strip()
    if not value:
        raise ValueError('sysfs attribute is blank')
    return value


def read_thermal(root=None):
    """Retain every valid zone and path-specific failure; any failure blocks."""
    root = THERMAL_ROOT if root is None else Path(root)
    result = {'thermal_zones_c': {}, 'thermal_measurements': [],
              'thermal_read_errors': [], 'thermal_read_method':
              'one os.read <=257 bytes per attribute; ASCII; integer millidegrees; no retry'}

    def failure(path, stage, exc):
        result['thermal_read_errors'].append({
            'path': str(path), 'stage': stage, 'exception_type': type(exc).__name__,
            'error': str(exc), 'traceback': traceback.format_exc()})

    try:
        zones = sorted(root.glob('thermal_zone*'))
        if not zones:
            raise ValueError('no thermal zones available')
    except Exception as exc:
        failure(root, 'enumerate', exc)
        return result
    for zone in zones:
        row = {'zone': zone.name, 'type_path': str(zone / 'type'),
               'temp_path': str(zone / 'temp'), 'type': None, 'temperature_c': None}
        for attribute in ('type', 'temp'):
            path = zone / attribute
            try:
                value = read_sysfs_text(path)
                if attribute == 'type':
                    row['type'] = value
                else:
                    if not re.fullmatch(r'[+-]?[0-9]+', value):
                        raise ValueError('temperature must be integer millidegrees Celsius')
                    temperature = int(value) / 1000.0
                    if not math.isfinite(temperature) or temperature < -273.15:
                        raise ValueError('temperature is nonfinite or below absolute zero')
                    row['temperature_c'] = temperature
                    # Stable zone ids preserve different zones with the same type.
                    result['thermal_zones_c'][zone.name] = temperature
            except Exception as exc:
                failure(path, attribute, exc)
        result['thermal_measurements'].append(row)
    return result


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
    phase='cpu'
    try:
        previous=ticks();last=time.monotonic()
        for _ in range(5):
            time.sleep(1);current=ticks();now=time.monotonic()
            total=current[0]-previous[0];idle=current[1]-previous[1]
            if total<=0 or not 0<=idle<=total:raise ValueError('invalid CPU delta')
            result['cpu_samples'].append({'duration_s':now-last,'percent':100*(total-idle)/total})
            previous,last=current,now
        phase='memory'
        mem={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
        result['ram_percent']=100*(1-mem['MemAvailable']/mem['MemTotal'])
        phase='temperature'
        result.update(read_thermal())
        if result['thermal_read_errors']:
            for error in result['thermal_read_errors']:
                result['reasons'].append('temperature %s %s: %s: %s' % (
                    error['stage'],error['path'],error['exception_type'],error['error']))
            raise ValueError('temperature measurement incomplete; admission blocked')
        phase='disk'
        result['free_disk_bytes']=shutil.disk_usage('/home/jetson/project_atlas').free
        phase='dashboard'
        result['dashboard']=status()
        phase='service_inspection'
        units=subprocess.run(['systemctl','--user','show','atlas-stage20-public-capture.service',
            'atlas-localization.service','rover-base-telemetry.service','--property=Id,ActiveState,MainPID,NRestarts'],
            capture_output=True,text=True,timeout=3,check=True).stdout
        result['services']=units
        phase='validation'
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
        result['measurement_error']={'phase':phase,'exception_type':type(exc).__name__,
                                     'error':str(exc),'traceback':traceback.format_exc()}
    print(json.dumps(result,indent=2,allow_nan=False),flush=True)
    return 0 if result['decision']!='BLOCKED' else 2


if __name__=='__main__':raise SystemExit(main())

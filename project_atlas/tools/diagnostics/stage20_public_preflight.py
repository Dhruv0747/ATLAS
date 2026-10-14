"""Read-only fresh parked/headroom gate for the optional stationary capture."""
import json
import math
import urllib.request

def validate(status):
    ros=status['ros'];system=status['system']
    def item(name):
        x=ros[name];age=float(x['age'])
        if not math.isfinite(age) or not 0<=age<=2:raise ValueError('stale safety evidence: '+name)
        value=x['value'];return json.loads(value) if isinstance(value,str) else value
    policy=item('control_policy');command=item('cmd_vel')
    if policy.get('stop_latched') is not True or policy.get('source')!='STOPPED':
        raise ValueError('fresh latched stationary stop required')
    for key in ('lin','ang'):
        value=float(command[key])
        if not math.isfinite(value) or abs(value)>1e-9:raise ValueError('nonzero drive command')
    cpu=float(system['cpu_percent']);ram=float(system['ram_percent'])
    temp=float(str(system['temp']).split()[0])
    if not all(math.isfinite(v) for v in (cpu,ram,temp)):raise ValueError('unknown resource state')
    if cpu>75 or ram>80 or temp>70:raise ValueError('diagnostic headroom unavailable')
    return {'stop_latched':True,'zero_command':True,'cpu_percent':cpu,'ram_percent':ram,'temperature_c':temp}

def check():
    # No POST or control endpoint. A timeout denies the optional recording only.
    with urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=2) as response:
        raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('oversized status response')
    return validate(json.loads(raw))

if __name__=='__main__':print(json.dumps(check()))

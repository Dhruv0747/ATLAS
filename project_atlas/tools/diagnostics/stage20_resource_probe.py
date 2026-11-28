"""Read-only Linux resource evidence. No ROS, control or manager mutation."""
import datetime
import json
import os
from pathlib import Path
import shutil
import time


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def cpu_ticks():
    rows = {}
    for line in Path('/proc/stat').read_text().splitlines():
        parts = line.split()
        if parts and (parts[0] == 'cpu' or parts[0][3:].isdigit() and parts[0].startswith('cpu')):
            # guest/guest_nice are already included in user/nice; do not double count.
            fields = list(map(int, parts[1:9]))
            rows[parts[0]] = (sum(fields), fields[3] + fields[4])
    return rows


def cpu_delta(before, after):
    result = {}
    for name, (total, idle) in after.items():
        if name not in before:
            raise ValueError('CPU topology changed')
        dt, di = total-before[name][0], idle-before[name][1]
        if dt <= 0 or not 0 <= di <= dt:
            raise ValueError('invalid CPU accounting interval')
        result[name] = 100.0 * (dt-di)/dt
    if set(before) != set(after):
        raise ValueError('CPU topology changed')
    return result


def processes():
    result = {}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            text = (p/'stat').read_text()
            left, rest = text.rsplit(')', 1)
            f = rest.split()  # f[0] is field3 state; starttime is field22.
            group = (p/'cgroup').read_text().splitlines()
            units = [x for line in group for x in line.split('/') if x.endswith('.service')]
            result[p.name] = {'name': left.split('(', 1)[1], 'ticks': int(f[11])+int(f[12]),
                             'start_ticks': int(f[19]), 'rss_bytes': int(f[21])*os.sysconf('SC_PAGE_SIZE'),
                             'unit': units[-1] if units else None}
        except (OSError, ValueError, IndexError):
            continue  # Process exit or unreadable process; never interpret as zero CPU.
    return result


def process_delta(before, after, elapsed):
    rows = []
    hz = os.sysconf('SC_CLK_TCK')
    for pid, row in after.items():
        prev = before.get(pid)
        if prev is None or prev['start_ticks'] != row['start_ticks']:
            continue
        ticks = row['ticks']-prev['ticks']
        if ticks < 0:
            continue
        rows.append(dict(pid=int(pid), name=row['name'], unit=row['unit'], rss_bytes=row['rss_bytes'],
                         cpu_percent_one_core=100*ticks/hz/elapsed))
    return sorted(rows, key=lambda x:x['cpu_percent_one_core'], reverse=True)


def pressure(name):
    try:
        return {line.split()[0]: {k: float(v) for k,v in (x.split('=') for x in line.split()[1:])}
                for line in Path('/proc/pressure', name).read_text().splitlines()}
    except (OSError, ValueError):
        return None


def gauges(root):
    mem = {line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()}
    temps = {}; read_errors = []
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        try: temps[(zone/'type').read_text().strip()] = float((zone/'temp').read_text())/1000
        except (OSError, ValueError, TypeError) as exc: read_errors.append({'path':str(zone),'error_type':type(exc).__name__})
    cooling = {}
    for node in Path('/sys/class/thermal').glob('cooling_device*'):
        try: cooling[node.name+':'+(node/'type').read_text().strip()] = int((node/'cur_state').read_text())
        except (OSError, ValueError, TypeError) as exc: read_errors.append({'path':str(node),'error_type':type(exc).__name__})
    throttle = {}
    for path in Path('/sys/devices/system/cpu').glob('cpu*/thermal_throttle/*'):
        if path.is_file():
            try: throttle[str(path)] = path.read_text().strip()
            except (OSError,TypeError): pass
    disks = {}
    for line in Path('/proc/diskstats').read_text().splitlines():
        f = line.split()
        if f[2].startswith(('nvme','mmcblk','sd','dm-')):
            disks[f[2]] = {'sectors_read':int(f[5]),'sectors_written':int(f[9]),'io_ms':int(f[12])}
    load = Path('/proc/loadavg').read_text().split()
    return {'ram_percent':100*(mem['MemTotal']-mem['MemAvailable'])/mem['MemTotal'],
            'memory_bytes':{k:mem[k] for k in ('MemTotal','MemAvailable','SwapTotal','SwapFree','Dirty','Writeback')},
            'temperature_c':float(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000,
            'thermal_zones_c':temps,'thermal_read_errors':read_errors,'cooling_states':cooling,'thermal_throttle_counters':throttle or None,
            'load_average':[float(x) for x in load[:3]],'runnable_total':load[3],
            'pressure':{name:pressure(name) for name in ('cpu','io','memory')},
            'disk_counters':disks,'free_disk_bytes':shutil.disk_usage(root).free}


def sample_window(root, seconds=5):
    start = time.monotonic(); start_utc = utc(); proc_before = processes()
    before = cpu_ticks(); ticks_time = time.monotonic(); samples = []
    for _ in range(seconds):
        time.sleep(1)
        after = cpu_ticks(); now = time.monotonic()
        samples.append({'timestamp':utc(),'duration_s':now-ticks_time,'utilization_percent':cpu_delta(before,after)})
        before, ticks_time = after, now
    proc_after = processes(); end = time.monotonic()
    return {'timestamp':utc(),'started_at':start_utc,'duration_s':end-start,
            'method':'Linux /proc/stat delta; total minus idle+iowait; guest not double counted; each 1s sample retained',
            'cpu_samples':samples,'cpu_percent':max(x['utilization_percent']['cpu'] for x in samples),
            'per_process':process_delta(proc_before,proc_after,end-start),
            'process_method':'/proc/PID/stat delta over window; 100% = one core; matched PID/start time only',
            **gauges(root)}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--duration',type=int,default=600);p.add_argument('--root',type=Path,default=Path('/home/jetson/project_atlas'))
    a=p.parse_args()
    if a.duration<5 or a.duration%5: p.error('duration must be a positive multiple of 5')
    cpu_start=time.process_time();wall_start=time.monotonic()
    with a.output.open('x') as stream:
        print(json.dumps({'started_at':utc(),'duration_requested_s':a.duration,'output':str(a.output)}),flush=True)
        for i in range(a.duration//5):
            row=sample_window(a.root)
            row['window']=i;row['sampler_cpu_seconds']=time.process_time()-cpu_start
            stream.write(json.dumps(row)+'\n');stream.flush()
            if (i+1)%12==0:print(json.dumps({'windows':i+1,'elapsed_s':time.monotonic()-wall_start,'last_cpu_max':row['cpu_percent']}),flush=True)
    print(json.dumps({'complete':True,'elapsed_s':time.monotonic()-wall_start,'sampler_cpu_seconds':time.process_time()-cpu_start}),flush=True)

"""Passive all-PID stat + explicitly selected cgroup counters. No ROS/control.
Approval required before Jetson use; paired independent safety supervisor required.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import resource
import time

MAX_PIDS=4096
MAX_GROUPS=16
MAX_BYTES=16*1024*1024


def read(path):
    with path.open('rb') as stream:data=stream.read(65537)
    if len(data)>65536:raise ValueError('attribute too large')
    return data.decode()


def stat(text):
    end=text.rfind(')');fields=text[end+2:].split()
    return {'name':text[text.index('(')+1:end],'start_ticks':int(fields[19]),
            'user_ticks':int(fields[11]),'system_ticks':int(fields[12]),'rss_pages':int(fields[21])}


def snapshot(proc=Path('/proc'),groups=(),budget=.15,priority_pids=()):
    if not 0<budget<=.15:raise ValueError('invalid scan budget')
    start=time.monotonic();cpu=read(proc/'stat').splitlines()[0].split()[1:9]
    result={'mono':start,'wall':time.time(),'cpu':list(map(int,cpu)),
            'cpu_read_finished':time.monotonic(),'hz':os.sysconf('SC_CLK_TCK'),'online_cpus':os.cpu_count(),
            'processes':{},'groups':{},'gaps':[],'complete':True}
    if len(cpu)!=8:raise ValueError('invalid aggregate')
    paths=[p for p in proc.iterdir() if p.name.isdigit()]
    if len(paths)>MAX_PIDS or len(groups)>MAX_GROUPS:raise ValueError('inventory bound')
    priorities={str(pid) for pid in priority_pids}
    paths.sort(key=lambda p:(p.name not in priorities,int(p.name)))
    def finish(reason=None):
        result['finished']=time.monotonic()
        result['complete']=reason is None
        result['collection_issue']=reason
        result['unread_pids']=[p.name for p in paths if p.name not in result['processes'] and not any(g.get('pid')==p.name for g in result['gaps'])]
        result['unread_groups']=[name for name,_,_ in groups if name not in result['groups'] and not any(g.get('group')==name for g in result['gaps'])]
        return result
    for name,path,version in groups:
        if time.monotonic()-start>budget:return finish('scan_budget_exhausted')
        path=Path(path)
        if version not in (1,2):raise ValueError('unsupported cgroup version')
        try:
            identity=path.stat();stamp=time.monotonic()
            if version==2:
                values=dict(line.split() for line in read(path/'cpu.stat').splitlines())
                usage=int(values['usage_usec'])*1000
            else:usage=int(read(path/'cpuacct.usage'))
            after=path.stat()
            if (identity.st_ino,identity.st_dev)!=(after.st_ino,after.st_dev):raise ValueError('cgroup changed during read')
            result['groups'][name]={'mono':stamp,'path':str(path),'inode':identity.st_ino,'device':identity.st_dev,'usage_ns':usage,'version':version,'read_finished':time.monotonic()}
        except FileNotFoundError:result['gaps'].append({'group':name,'reason':'absent'})
    for p in paths:
        if time.monotonic()-start>budget:return finish('scan_budget_exhausted')
        try:
            stamp=time.monotonic();value=stat(read(p/'stat'));value['mono']=stamp;value['read_finished']=time.monotonic()
            result['processes'][p.name]=value
        except (FileNotFoundError,ProcessLookupError):result['gaps'].append({'pid':p.name,'reason':'exited during scan'})
        except PermissionError:result['gaps'].append({'pid':p.name,'reason':'permission denied'})
    result['finished']=time.monotonic()
    return finish('scan_budget_exhausted' if result['finished']-start>budget else None)


def differences(a,b):
    delta=[y-x for x,y in zip(a['cpu'],b['cpu'])];elapsed=b['mono']-a['mono']
    if a['hz']!=b['hz'] or len(delta)!=8 or min(delta)<0 or sum(delta)<=0 or elapsed<=0:raise ValueError('invalid aggregate interval')
    out={'interval':elapsed,'cpu_pct':100*(sum(delta)-delta[3]-delta[4])/sum(delta),
         'irq_ticks':delta[5],'softirq_ticks':delta[6],'processes':{},'new_or_reused':{},
         'exited':list(a['processes'].keys()-b['processes'].keys()) if b.get('complete',True) else [],
         'not_observed':list(a['processes'].keys()-b['processes'].keys()) if not b.get('complete',True) else [],'groups':{},
         'warning':'Sequential endpoints; do not sum nested cgroups or call residual exact kernel CPU.'}
    for pid,current in b['processes'].items():
        old=a['processes'].get(pid)
        if not old or old['start_ticks']!=current['start_ticks']:
            out['new_or_reused'][pid]={'lifetime_ticks':current['user_ticks']+current['system_ticks'],'start_ticks':current['start_ticks']}
            continue
        ticks=current['user_ticks']+current['system_ticks']-old['user_ticks']-old['system_ticks'];dt=current['mono']-old['mono']
        if ticks<0 or dt<=0:raise ValueError('invalid PID counter interval')
        out['processes'][pid]={'one_core_pct':100*ticks/a['hz']/dt,'delta_ticks':ticks,'interval':dt,'name':current['name']}
    for key,current in b['groups'].items():
        old=a['groups'].get(key)
        if not old or (old['path'],old['inode'],old['device'])!=(current['path'],current['inode'],current['device']):continue
        dt=current['mono']-old['mono'];used=current['usage_ns']-old['usage_ns']
        if used<0 or dt<=0:raise ValueError('invalid cgroup counter interval')
        out['groups'][key]={'one_core_pct':100*used/1e9/dt,'interval':dt,'usage_ns':used}
    return out


def persist(directory,index,row):
    raw=json.dumps(row,allow_nan=False,separators=(',',':')).encode()
    if sum(p.stat().st_size for p in directory.iterdir() if p.is_file())+len(raw)>MAX_BYTES:raise ValueError('evidence quota')
    temporary=directory/(str(index)+'.tmp');final=directory/('%03d.json'%index)
    if final.exists():raise ValueError('evidence overwrite forbidden')
    with temporary.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temporary,final)
    fd=os.open(directory,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    return hashlib.sha256(raw).hexdigest()


def run(output,groups=(),duration=30):
    if not 1<=duration<=30:raise ValueError('duration bound')
    output=Path(output);output.mkdir(mode=0o700)
    old=None;start=time.monotonic();index=0;total_cpu=time.process_time()
    try:
        while time.monotonic()-start<duration:
            stamp=start+index
            time.sleep(max(0,stamp-time.monotonic()))
            if time.monotonic()-start>=duration:break
            if (output/'STOP').exists():break
            current=snapshot(groups=groups)
            row={'snapshot':current,'collector_cpu_s':time.process_time()-total_cpu,'collector_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'collector_pid':os.getpid()}
            if old:row['delta']=differences(old,current)
            digest=persist(output,index,row)
            # A durable baseline exists before a future supervisor may permit start.
            if index==0:(output/'READY').write_text(json.dumps({'baseline_sha256':digest,'pid':os.getpid(),'mono':current['mono'],'warning':'Not a safety approval; verify process identity and fresh numbered samples'}))
            old=current;index+=1
            if (output/'STOP').exists():break
        return index
    except BaseException as exc:
        # Already committed samples remain valid even if this final write fails.
        persist(output,index,{'error_type':type(exc).__name__,'mono':time.monotonic(),'wall':time.time(),'decision':'ABORT; no restart authorization'})
        raise
    finally:
        (output/'READY').unlink(missing_ok=True)
        # Prior atomic numbered files survive SIGKILL even without final manifest.

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--groups',required=True);a=p.parse_args()
    config=json.loads(Path(a.groups).read_text())
    if not isinstance(config,list) or len(config)>MAX_GROUPS:raise ValueError('invalid group configuration')
    if len({item[0] for item in config})!=len(config):raise ValueError('duplicate group labels')
    for name,path,version in config:
        if not Path(path).resolve().is_relative_to(Path('/sys/fs/cgroup')):raise ValueError('cgroup path outside kernel tree')
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt('stop')))
    run(a.output,config)

"""Single guarded isolated ARM64 comparison. Never installs or restarts production."""
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import urllib.request

LIVE=Path('/home/jetson/project_atlas')
GUARDS={'stationary_gate.py':'0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9',
        'stationary_ros_probe.py':'f8a24e2a9fe92f505f52e96572a00691b0ebcfe92b092ba1c98ee052c18ed9dd'}


def verify(root, entries):
    for name, expected in entries.items():
        path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()):raise RuntimeError('manifest escapes root')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise RuntimeError('Hash mismatch: '+name)


def check_cpu(value, report_only=False):
    if not isinstance(value,(float,int)) or not math.isfinite(value) or not 0<=value<=100:
        raise RuntimeError('Invalid CPU measurement: '+str(value))
    if not report_only and value>75:
        raise RuntimeError('CPU guard failed: '+str(value))
    return None if report_only else value


def options(args):
    if args not in ([],['--diagnostic-cpu-report-only']):
        raise ValueError('Only explicit owner-approved diagnostic CPU reporting option accepted')
    return bool(args)


def stop_owned(proc):
    if proc is None or proc.poll() is not None:return
    try:os.killpg(proc.pid,signal.SIGINT)
    except ProcessLookupError:return
    try:proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        proc.wait(timeout=2)


def main():
    report_only=options(sys.argv[1:])
    root=Path(__file__).resolve().parent
    result={'status':'ABORTED','production_changed':False,'camera_started':False,'services_restarted':False}
    result['cpu_policy']='OWNER ONE-TEST REPORT ONLY' if report_only else 'STOP >75%'
    proc=None;before=None;log=None;G=None
    # Exclusive creation prevents accidental reuse/retry of this directory.
    trace=(root/'guard-trace.jsonl').open('x',buffering=1)
    def emit(row):trace.write(json.dumps(row,allow_nan=False)+'\n');trace.flush();os.fsync(trace.fileno())
    try:
        manifest=json.loads((root/'manifest.json').read_text())
        verify(root,manifest['package']);verify(LIVE,manifest['production'])
        verify(LIVE/'tools/vision3d',GUARDS)
        if __import__('shutil').disk_usage(root).free<512*1024*1024:raise RuntimeError('Disk headroom failed')
        sys.path.insert(0,str(LIVE/'tools/vision3d'))
        import stationary_gate as G
        import stationary_ros_probe as P
        G.UNITS+=('rover-status-web.service','atlas-voice-companion.service','atlas-safety-status.service','atlas-localization-monitor.service')
        before=G.services();result['services_before']=before
        if any(v['ActiveState']!='active' or int(v['MainPID'])<=1 for v in before.values()):raise RuntimeError('Protected service unhealthy')
        previous=G.ticks();last=time.monotonic();started=last
        def sample(phase):
            nonlocal previous,last
            time.sleep(max(0,last+1-time.monotonic()))
            now=time.monotonic();ticks=G.ticks();cpu=G.cpu_delta(previous,ticks);dt=now-last
            previous=ticks;last=now
            emit({'phase':phase,'cpu':cpu,'interval_s':dt,'monotonic':now})
            admitted_cpu=check_cpu(cpu,report_only)
            if dt>1.5:raise RuntimeError('Resource sampling deadline failed')
            snap=P.safety_snapshot();health=G.check(admitted_cpu,snap);extra=P.extra_safety(snap['ros'])
            health['cpu_percent']=cpu;health['diagnostic_cpu_report_only']=report_only
            with urllib.request.urlopen('http://127.0.0.1:8088/api/vision3d/summary',timeout=2) as r:camera=json.load(r)
            if not (camera.get('state')=='OFF' or camera.get('state')=='RESOURCE BLOCKED' and camera.get('driver_stopped') is True):raise RuntimeError('Astra not OFF')
            if subprocess.run(['pgrep','-x','astra_camera_no'],stdout=subprocess.DEVNULL,timeout=2).returncode!=1:raise RuntimeError('Astra process present/query failed')
            emit({'phase':phase,'health':health,'extra':extra,'monotonic':time.monotonic()})
            if time.monotonic()-now>1.5:raise RuntimeError('Safety sampling deadline failed')
        for _ in range(3):sample('baseline')
        if G.services()!=before:raise RuntimeError('Service changed during admission')
        args=['/usr/bin/python3','-B',str(root/'project_atlas/tools/diagnostics/benchmark_localization_traffic.py'),
              str(root/'input.db3'),str(root/'monitor.py'),str(root/'manual.py'),str(root/'executors.py'),
              '--pairs','2','--duration','6','--output',str(root/'benchmark-result.json')]
        env=dict(os.environ,ROS_LOCALHOST_ONLY='1',ROS_DOMAIN_ID='213',RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
        for key in ('ROS_DISCOVERY_SERVER','FASTRTPS_DEFAULT_PROFILES_FILE','CYCLONEDDS_URI'):env.pop(key,None)
        log=(root/'benchmark.log').open('x')
        proc=subprocess.Popen(['/bin/bash','-c','source /opt/ros/humble/setup.bash && exec '+shlex.join(args)],
            env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        result['isolated_pid']=proc.pid
        while proc.poll() is None:
            if time.monotonic()-started>60:raise RuntimeError('Overall deadline failed')
            sample('benchmark')
        result['returncode']=proc.returncode
        if proc.returncode:raise RuntimeError('Benchmark failed; see retained log')
        sample('postflight');verify(LIVE,manifest['production'])
        result['benchmark']=json.loads((root/'benchmark-result.json').read_text())
        result['status']='COMPLETE'
    except Exception as exc:result['error']=str(exc)
    finally:
        stop_owned(proc)
        if log:log.close()
        result['isolated_process_stopped']=proc is None or proc.poll() is not None
        if G:
            try:
                result['services_after']=G.services()
                result['protected_unchanged']=before==result['services_after']
                if not result['protected_unchanged']:result['status']='ABORTED'
            except Exception as exc:result['postflight_error']=str(exc);result['status']='ABORTED'
        trace.close()
        (root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()

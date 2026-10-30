"""Bounded Jetson-only mapping supervisor; never starts a camera or robot service.

Run only under the reviewed optional systemd unit after deployment approval.
Systemd watchdog/RuntimeMaxSec/KillMode provide independent process-death cleanup.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import fcntl
from onboard_adapter import configuration
from onboard_store import atomic,budget,new_session,recover,finalize
from calibration_capture import safety
from stationary_gate import ticks,cpu_delta,services

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'diagnostics'))
from offboard_bridge_preflight import read_thermal


def notify(text):
    address=os.environ.get('NOTIFY_SOCKET')
    if not address:raise RuntimeError('independent systemd watchdog required')
    if address.startswith('@'):address='\0'+address[1:]
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as s:s.sendto(text.encode(),address)


def read_json(url):
    with urllib.request.urlopen(url,timeout=.25) as r:
        raw=r.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('oversized local snapshot')
        return json.loads(raw)


def observe(cpu,window):
    j=read_json('http://127.0.0.1:8088/api/status');r=j['ros']
    def value(k):
        row=r[k]
        if type(row['age']) not in (int,float) or not 0<=row['age']<=1:raise ValueError(k+' stale')
        return json.loads(row['value']) if isinstance(row['value'],str) else row['value']
    policy=value('control_policy');cmd=value('cmd_vel');enc=value('encoder_health')
    thermal=read_thermal()
    if thermal['thermal_read_errors'] or not thermal['thermal_zones_c']:raise ValueError('trustworthy thermal data unavailable')
    mem={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    recorder=subprocess.check_output(['systemctl','--user','show','atlas-stage20-public-capture.service','-p','ActiveState','-p','MainPID'],text=True,timeout=.3)
    o=dict(received_mono=time.monotonic(),cpu_window_s=window,cpu=cpu,
           ram=100*(1-mem['MemAvailable']/mem['MemTotal']),temperature=max(thermal['thermal_zones_c'].values()),
           estop=policy['stop_latched'],manual_only=policy['manual_only'],commissioning=policy['commission_armed'],
           recorder_off=('ActiveState=inactive' in recorder and 'MainPID=0\n' in recorder),
           telemetry_live=enc['link_state']=='LIVE' and enc['packet_fresh'] is True,
           telemetry_age=enc['packet_age_s'],linear=cmd['lin'],angular=cmd['ang'],encoder_deltas=enc['encoder_interval_delta_m'])
    safety(o,time.monotonic());return o


def adapter_health(a,now,started):
    if not 0<=now-a['observed_mono']<=1:raise ValueError('adapter heartbeat stale')
    if a['error']:raise ValueError(a['error'])
    for key in ('last_bundle','last_odom','last_scan'):
        v=a[key]
        if v is None:
            if now-started>=10:raise ValueError(key+' startup timeout')
        elif not 0<=now-v<=1:raise ValueError(key+' stale')


def stop_camera(c):
    receipt=Path(c['storage'])/'camera-owner.json'
    if not receipt.exists():return
    owned=json.loads(receipt.read_text())
    current=read_json('http://127.0.0.1:8088/api/vision3d/status')['runtime']
    if current.get('driver_stopped') is True or current.get('state')=='OFF':
        receipt.unlink();return
    if current.get('driver_pid')!=owned['driver_pid'] or current.get('startup_guard_baseline_monotonic_s')!=owned['startup']:
        raise ValueError('different camera session; refusing stop')
    req=urllib.request.Request('http://127.0.0.1:8088/api/vision3d/viewer',
        data=b'{"action":"stop"}',headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8088','X-Atlas-Vision3D':'1'})
    with urllib.request.urlopen(req,timeout=.5) as r:r.read(65536)
    s=read_json('http://127.0.0.1:8088/api/vision3d/status')['runtime']
    if s.get('state')!='OFF' and s.get('driver_stopped') is not True:raise ValueError('camera shutdown not yet verified')
    receipt.unlink()


def main():
    p=argparse.ArgumentParser();p.add_argument('config');p.add_argument('--cleanup-camera',action='store_true');a=p.parse_args()
    c=json.loads(Path(a.config).read_text())
    if a.cleanup_camera:stop_camera(c);return
    configuration(c)
    if int(os.environ.get('WATCHDOG_USEC','0'))>3000000 or not os.environ.get('WATCHDOG_USEC'):
        raise RuntimeError('bounded systemd watchdog missing')
    root=Path(c['storage']);root.mkdir(parents=True,exist_ok=True)
    lock=(root/'owner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    recover(root);session=new_session(root);children=[];reason='duration complete'
    def interrupted(*args):raise KeyboardInterrupt('supervisor interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    notify('READY=1');started=time.monotonic();last=started;prev=ticks()
    try:
        # Fresh one-second CPU interval before child startup.
        time.sleep(1);now=time.monotonic();cur=ticks();observe(cpu_delta(prev,cur),now-last)
        prev=cur;last=now;baseline=services()
        if any(v['ActiveState']!='active' or int(v['MainPID'])<=0 for v in baseline.values()):
            raise ValueError('protected service not active')
        notify('WATCHDOG=1')
        camera=read_json('http://127.0.0.1:8088/api/vision3d/status')['runtime']
        if camera.get('state') not in ('RUNNING','ACTIVE') or camera.get('driver_stopped') is True:
            raise ValueError('approved existing camera session not running; supervisor will not start it')
        if not camera.get('driver_pid') or not camera.get('startup_guard_baseline_monotonic_s'):
            raise ValueError('camera session identity incomplete')
        atomic(root/'camera-owner.json',dict(driver_pid=camera['driver_pid'],startup=camera['startup_guard_baseline_monotonic_s']))
        env=dict(os.environ,ROS_DOMAIN_ID=str(c['mapping_domain']),ROS_LOCALHOST_ONLY='1',
                 OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',RMW_IMPLEMENTATION='rmw_fastrtps_cpp',SKIP_DEFAULT_XML='1')
        for k in ('ROS_DISCOVERY_SERVER','FASTRTPS_DEFAULT_PROFILES_FILE','FASTDDS_DEFAULT_PROFILES_FILE','CYCLONEDDS_URI'):env.pop(k,None)
        args=[['/usr/bin/python3',str(HERE/'onboard_adapter.py'),a.config,str(session)],
              ['/opt/ros/humble/lib/rtabmap_slam/rtabmap','--ros-args','--params-file',str(HERE/'onboard_mapping.yaml'),
               '-r','__ns:=/atlas_mapping','-p','database_path:='+str(session/'map.db'),
               '-r','rgb/image:=input/rgb','-r','depth/image:=input/depth',
               '-r','rgb/camera_info:=input/camera_info','-r','odom:=input/odom','-r','scan:=input/scan']]
        for i,cmd in enumerate(args):
            log=(session/('child'+str(i)+'.log')).open('wb')
            try:children.append(subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT))
            finally:log.close()
        while time.monotonic()-started<c['duration_s']:
            delay=1-(time.monotonic()-last)
            if delay>0:time.sleep(delay)
            now=time.monotonic();cur=ticks();obs=observe(cpu_delta(prev,cur),now-last);prev=cur;last=now
            budget(session,c['max_session_bytes'],c['free_reserve_bytes'])
            if any(p.poll() is not None for p in children):raise RuntimeError('mapping child exited')
            # Existing status route renews the existing four-second runtime lease.
            # This local guarded client, not a PC browser, owns it during the test.
            current=read_json('http://127.0.0.1:8088/api/vision3d/status')['runtime']
            if (current.get('driver_pid')!=camera['driver_pid'] or current.get('driver_stopped') is True
                or current.get('startup_guard_baseline_monotonic_s')!=camera['startup_guard_baseline_monotonic_s']):
                raise ValueError('camera session changed/stopped')
            ap=session/'adapter.json'
            if ap.exists():adapter_health(json.loads(ap.read_text()),time.monotonic(),started)
            elif now-started>=10:raise ValueError('adapter startup timeout')
            atomic(session/'status.json',dict(state='RUNNING',observed=time.time(),resources=obs,label='PROVISIONAL — PHYSICAL ACCURACY NOT VERIFIED'))
            notify('WATCHDOG=1')
    except BaseException as e:reason=str(e)
    finally:
        for p in children:
            if p.poll() is None:p.send_signal(signal.SIGINT)
        for p in children:
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=1)
        try:stop_camera(c)
        except Exception as e:reason+='; camera cleanup: '+str(e)
        result=finalize(session,reason)
        result['mapping_completed']=reason=='duration complete' and result.get('nodes',0)>0
        try:
            result['protected_services_unchanged']=services()==baseline
        except Exception:result['protected_services_unchanged']=False
        atomic(session/'status.json',result)
        print(json.dumps(result))
    return 0 if result['mapping_completed'] and result['protected_services_unchanged'] else 1


if __name__=='__main__':sys.exit(main())

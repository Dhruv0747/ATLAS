"""Bounded isolated local camera test using existing-bridge direct health evidence.

Requires explicit owner CPU-report-only approval. Never changes production CPU
policy. Status-page timeouts are NOT treated as permission to ignore controls:
fresh direct policy, commands, wheel outputs and required sensors replace them.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import stationary_gate as G
from local_bridge_observer import REQUIRED

STAGE=Path('/home/jetson/project-atlas-migration/astra-20261021');RUNTIME=STAGE/'astra-arm64-stage29-v2'


def resources():
    mem={l.split(':')[0]:int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines()}
    ram=100*(mem['MemTotal']-mem['MemAvailable'])/mem['MemTotal'];temps={}
    names=('cpu-thermal','gpu-thermal','soc0-thermal','soc1-thermal','soc2-thermal','tj-thermal')
    for z in Path('/sys/class/thermal').glob('thermal_zone*'):
        name=(z/'type').read_text().strip()
        if name in names:temps[name]=float((z/'temp').read_text())/1000
    if set(temps)!=set(names) or not math.isfinite(ram) or ram>80 or any(not math.isfinite(t) or t>70 for t in temps.values()):
        raise RuntimeError('RAM/thermal safety failed')
    return {'ram_percent':ram,'thermal_c':temps}


def direct_safety(data,now):
    if not 0<=now-data['updated_monotonic']<=1:raise RuntimeError('observer status stale')
    for topic in REQUIRED:
        age=now-data['last_receive_monotonic'].get(topic,-1e9)
        if not 0<=age<=2:raise RuntimeError('direct topic stale '+topic)
    v=data['values'];ages={k:now-data['last_receive_monotonic'][k] for k in REQUIRED}
    G.validate_policy({'control_policy':{'age':ages['/atlas/control_policy'],'value':v['/atlas/control_policy']},
                       'cmd_vel':{'age':ages['/cmd_vel'],'value':v['/cmd_vel']}})
    wheels=v['/atlas/drive_pid/diagnostics'].get('wheels',[])
    if len(wheels)!=4 or any(w.get('output')!=0 or w.get('target_mps')!=0 for w in wheels):raise RuntimeError('nonzero/unknown wheel outputs')
    if v['/atlas/mission_status']!='READY' or data['errors']:raise RuntimeError('mission or observer fault')
    return {'direct_policy_and_cmd_fresh':True,'outputs_zero':True,'required_sensor_ages':ages}


def main():
    p=argparse.ArgumentParser();p.add_argument('--approve-stationary',action='store_true');p.add_argument('--cpu-report-only-owner-approved',action='store_true');p.add_argument('--mode',choices=('depth','rgb','concurrent','cloud'),required=True);p.add_argument('--evidence-tag',choices=('','-origin-fixed','-sdk-protocol','-steady-window'),default='');a=p.parse_args()
    if not(a.approve_stationary and a.cpu_report_only_owner_approved):raise SystemExit('explicit stationary and CPU exception approval required')
    label=a.mode+a.evidence_tag
    target=STAGE/('stage29-bridge-'+label+'.json');snapshot=STAGE/('stage29-bridge-'+label+'-scalar.json')
    if target.exists() or snapshot.exists():raise SystemExit('existing evidence preserved; no automatic retry')
    result={'result':'BLOCKED','samples':[],'cpu_policy':'owner-approved report-only; production safeguard unchanged','recording':False};children=[];handles=[]
    try:
        import stationary_ros_probe as P
        pre=[];last=G.ticks()
        for _ in range(3):
            time.sleep(1);now=G.ticks();row=P.resource_sample(G.cpu_delta(last,now),True);last=now;pre.append(row)
        result['preflight']=pre;result['extra_safety']=P.extra_safety();units=G.services();result['units_before']=units
        env=dict(os.environ);env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        env['LD_LIBRARY_PATH']=str(RUNTIME/'lib')+':/opt/ros/humble/lib:'+env.get('LD_LIBRARY_PATH','')
        env['AMENT_PREFIX_PATH']=str(RUNTIME)+':/opt/ros/humble'
        out=(STAGE/('stage29-bridge-'+label+'-observer-out.txt')).open('x');err=(STAGE/('stage29-bridge-'+label+'-observer-err.txt')).open('x');handles.extend([out,err])
        observer=subprocess.Popen([sys.executable,str(STAGE/'local_bridge_observer.py'),'--snapshot',str(snapshot)],env=env,stdout=out,stderr=err,start_new_session=True);children.append(observer)
        start=time.monotonic();driver=None;start_driver=None;first_data=None;process_last={}
        while time.monotonic()-start<40:
            time.sleep(.5);nowticks=G.ticks();row=resources();row['cpu_percent']=G.cpu_delta(last,nowticks);last=nowticks
            if G.services()!=units:raise RuntimeError('essential service identity changed')
            if observer.poll() is not None:raise RuntimeError('bridge observer exited')
            recorder=subprocess.check_output(['systemctl','--user','show','atlas-stage20-public-capture.service','-p','ActiveState','-p','MainPID'],text=True)
            if 'ActiveState=inactive' not in recorder or 'MainPID=0' not in recorder:raise RuntimeError('recorder activated')
            if snapshot.exists():
                data=json.loads(snapshot.read_text())
                if all(topic in data['values'] or topic in data['counts'] for topic in REQUIRED):
                    row['safety']=direct_safety(data,time.monotonic())
                    if driver is None:
                        args=[str(RUNTIME/'lib/astra_camera/astra_camera_node'),'--ros-args','-r','__ns:=/astra']
                        values={'camera_name':'astra','use_uvc_camera':str(a.mode in ('rgb','concurrent')).lower(),
                                'enable_color':str(a.mode in ('rgb','concurrent')).lower(),'enable_depth':str(a.mode!='rgb').lower(),
                                'enable_ir':'false','enable_point_cloud':str(a.mode=='cloud').lower(),'enable_colored_point_cloud':'false',
                                'publish_tf':'false','depth_registration':'false','enable_publish_extrinsic':'false',
                                'depth_width':'160','depth_height':'120','depth_fps':'30','depth_scale':'1',
                                'color_width':'320','color_height':'240','color_fps':'15','uvc_vendor_id':'0x2bc5',
                                'uvc_product_id':'0x0501','uvc_camera_format':'mjpeg','uvc_retry_count':'0',
                                'oni_log_to_file':'false','oni_log_to_console':'false'}
                        if a.mode=='cloud':raise RuntimeError('cloud launch requires independently verified intrinsics first')
                        for k,v in values.items():args+=['-p',k+':='+v]
                        stdout=(STAGE/('stage29-bridge-'+label+'-driver-out.txt')).open('x');stderr=(STAGE/('stage29-bridge-'+label+'-driver-err.txt')).open('x');handles.extend([stdout,stderr])
                        driver=subprocess.Popen(args,env=env,stdout=stdout,stderr=stderr,start_new_session=True,cwd=str(RUNTIME));children.append(driver);start_driver=time.monotonic()
                elif time.monotonic()-start>5:raise RuntimeError('required direct subscriptions unavailable')
            elif time.monotonic()-start>5:raise RuntimeError('bridge scalar status unavailable')
            row['processes']=[]
            for child in children:
                try:
                    stat=(Path('/proc')/str(child.pid)/'stat').read_text().rsplit(')',1)[1].split();ticks=int(stat[11])+int(stat[12]);stamp=time.monotonic()
                    rss=next(int(l.split()[1]) for l in (Path('/proc')/str(child.pid)/'status').read_text().splitlines() if l.startswith('VmRSS:'))
                    prior=process_last.get(child.pid);process_last[child.pid]=(ticks,stamp)
                    row['processes'].append({'role':'Astra driver' if child is driver else 'local bridge observer','rss_kib':rss,
                        'cpu_one_core_percent':100*(ticks-prior[0])/os.sysconf('SC_CLK_TCK')/(stamp-prior[1]) if prior else None})
                except (OSError,StopIteration):pass
            gpu=Path('/sys/devices/platform/17000000.gpu/load');row['gpu_percent']=float(gpu.read_text())/10 if gpu.exists() else None
            result['samples'].append(row)
            if driver is not None and driver.poll() is not None:raise RuntimeError('driver exited '+str(driver.returncode))
            if start_driver is not None:
                expected=('/astra/depth/image_raw','/astra/depth/camera_info') if a.mode=='depth' else ('/astra/color/image_raw','/astra/color/camera_info')
                if a.mode=='concurrent':expected+=('/astra/depth/image_raw','/astra/depth/camera_info')
                if all(data['counts'].get(k,0)>=1 for k in expected):
                    if first_data is None:first_data=time.monotonic()
                    if time.monotonic()-first_data>=8:break
                elif time.monotonic()-start_driver>25:raise RuntimeError('Astra startup produced no required data within 25 seconds')
        else:raise RuntimeError('bounded test deadline')
        data=json.loads(snapshot.read_text());direct_safety(data,time.monotonic());result['observed']=data
        required=('/astra/depth/image_raw','/astra/depth/camera_info') if a.mode=='depth' else ('/astra/color/image_raw','/astra/color/camera_info')
        if a.mode=='concurrent':required+=('/astra/depth/image_raw','/astra/depth/camera_info')
        if any(data['counts'].get(k,0)<5 or time.monotonic()-data['last_receive_monotonic'].get(k,-1e9)>1 for k in required):
            raise RuntimeError('required Astra stream missing/stale')
        result['result']='PASS (bounded streams; CPU exception, not production endurance)'
    except Exception as e:result['failure']=str(e)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGINT)
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=3)
        for h in handles:h.close()
        result['units_after']=G.services();target.write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()

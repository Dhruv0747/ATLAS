"""Opt-in bounded Astra ROS depth validation. Scalar metadata only; no recordings.

Guardian never imports ROS. Only its newly owned observer/driver are terminated.
No publishers, control APIs, production services, external TF or autostart.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import stationary_gate as gate

STAGE=Path('/home/jetson/project-atlas-migration/astra-20261021')
RUNTIME=STAGE/'astra-arm64-stage29-v2'


def resource_sample(cpu,report_only=False):
    row=gate.check(None if report_only else cpu)
    row['cpu_percent']=cpu
    return row


def safety_snapshot():
    """Same fresh ROS snapshot without unrelated network/system dashboard work."""
    import urllib.request
    data=json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/commissioning',timeout=3))
    mem={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    return {'ros':data['ros'],'system':{'ram_percent':100*(mem['MemTotal']-mem['MemAvailable'])/mem['MemTotal']}}


def _astra_ports():
    """25 Oct 2026: port-independent identity (scripts/atlas_astra_usb.py). Exactly one Astra Pro on the Jetson
    controller: depth on .2 and RGB on .1 of the camera's own Genesys hub, on any port. Two cameras, a lone half or
    a non-sibling pair are refused exactly like the earlier fixed-port check."""
    scripts=str(Path(__file__).resolve().parents[2]/'scripts')
    if scripts not in sys.path:sys.path.insert(0,scripts)
    import atlas_astra_usb as A
    try:return A.find_astra()
    except A.AstraUsbError as e:
        raise RuntimeError('Astra USB physical identity missing/ambiguous: '+str(e)) from e


def verify_astra_usb_access():
    """Resolve verified physical ports afresh, never cache BUSNUM/DEVNUM.

    Sysfs supports already-connected devices before the new udev aliases exist.
    An existing alias must agree with sysfs. No stream, permission changes or
    substitution by another same-model device on a different port is allowed.
    """
    verified=[]
    try:
        found=_astra_ports()
        for port,identity,alias in (
                (found['depth_port'],'2bc5:0403','atlas-astra-depth-usb'),
                (found['rgb_port'],'2bc5:0501','atlas-astra-rgb-usb')):
            matches=[p for p in Path('/sys/bus/usb/devices').glob('*-'+port)
                     if '3610000.usb' in p.resolve(strict=True).parts]
            if len(matches)!=1:
                raise RuntimeError('Astra USB physical identity missing/ambiguous: '+port)
            sysdev=matches[0]
            def attributes():
                return tuple((sysdev/name).read_text().strip() for name in
                             ('idVendor','idProduct','devpath','busnum','devnum','dev'))
            before=attributes()
            if ':'.join(before[:2])!=identity or before[2]!=port:
                raise RuntimeError('Astra USB identity missing/mismatch: '+port)
            bus,num=int(before[3]),int(before[4])
            if not 1<=bus<=999 or not 1<=num<=127:
                raise RuntimeError('Astra USB invalid bus/device number')
            device=Path('/dev/bus/usb')/f'{bus:03d}'/f'{num:03d}'
            stable=Path('/dev')/alias
            if os.path.lexists(stable) and stable.resolve(strict=True)!=device:
                raise RuntimeError('Astra USB stable alias mismatch: '+str(stable))
            node=device.stat()
            if (not stat.S_ISCHR(node.st_mode) or
                    f'{os.major(node.st_rdev)}:{os.minor(node.st_rdev)}'!=before[5]):
                raise RuntimeError('Astra USB device-node identity mismatch: '+str(device))
            if not os.access(device,os.R_OK|os.W_OK,effective_ids=True):
                raise RuntimeError('Astra USB read/write access denied: '+str(device))
            if attributes()!=before or device.stat()!=node:
                raise RuntimeError('Astra USB identity/access changed during check')
            verified.append({'path':str(device),'vid_pid':identity,'physical_port':port,
                             'stable_alias':str(stable),'read_write_access':True})
    except (OSError,ValueError) as exc:
        raise RuntimeError('Astra USB identity/access query failed: '+str(exc)) from exc
    return verified


def extra_safety(ros=None):
    import urllib.request
    if ros is None:ros=json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=3))['ros']
    for key in ('lidar','imu_full','enc_m1','enc_m2','enc_m3','enc_m4','camera_info','drive_pid','mission_status','motor_speed'):
        value=ros.get(key,{})
        if not isinstance(value.get('age'),(float,int)) or not 0<=value['age']<=2:raise RuntimeError('stale required '+key)
    pid=ros['drive_pid']['value'];pid=json.loads(pid) if isinstance(pid,str) else pid
    if len(pid.get('wheels',[]))!=4 or any(w.get('output')!=0 or w.get('target_mps')!=0 for w in pid['wheels']):
        raise RuntimeError('nonzero/unknown wheel output command')
    if ros['mission_status']['value']!='READY' or ros['motor_speed']['value']!=0:
        raise RuntimeError('mission or measured motor state not idle')
    info=ros['camera_info']['value']
    if info.get('publisher_count',1)<1:raise RuntimeError('Pi camera publisher missing')
    verify_astra_usb_access()
    return {'required_fresh':True,'wheel_output_commands_zero':True,'mission':'READY','motor_speed':0}


def observe(phase):
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image,CameraInfo,CompressedImage,Imu,LaserScan
    from std_msgs.msg import String
    rclpy.init();node=Node('atlas_astra_stationary_observer',enable_rosout=False,start_parameter_services=False)
    counts={};metadata={};last={};first={};gaps={};errors=[];subs=[]
    def receive(key,msg):
        now=time.monotonic();counts[key]=counts.get(key,0)+1;first.setdefault(key,now)
        if key in last:gaps[key]=max(gaps.get(key,0),now-last[key])
        last[key]=now
        if key=='depth':
            if (msg.width,msg.height,msg.encoding)!=(160,120,'16UC1') or msg.step<320 or len(msg.data)!=msg.step*msg.height:
                errors.append('malformed or unexpected depth mode');return
            raw=memoryview(msg.data);values=[int.from_bytes(raw[y*msg.step+x*2:y*msg.step+x*2+2],'big' if msg.is_bigendian else 'little')
                 for y in range(0,120,8) for x in range(0,160,8)]
            valid=[v for v in values if v not in (0,65535)]
            metadata[key]={'width':msg.width,'height':msg.height,'encoding':msg.encoding,'frame':msg.header.frame_id,
                'stamp_sec':msg.header.stamp.sec,'stamp_nanosec':msg.header.stamp.nanosec,
                'ros_receipt_minus_header_s':node.get_clock().now().nanoseconds/1e9-(msg.header.stamp.sec+msg.header.stamp.nanosec/1e9),
                'sampled_valid':len(valid),'sampled_pixels':len(values),'min_z_m':min(valid)/1000 if valid else None,
                'header_provenance':'vendor uses ROS node now at processing, not hardware capture timestamp'}
        elif key=='depth_info':
            metadata[key]={'width':msg.width,'height':msg.height,'frame':msg.header.frame_id,
                          'k':list(msg.k),'p':list(msg.p),'d':list(msg.d),'distortion_model':msg.distortion_model,
                          'calibration_provenance':'NOT independently validated'}
            if not all(math.isfinite(x) for x in msg.k) or msg.k[0]<=0 or msg.k[4]<=0:errors.append('invalid depth intrinsics')
        elif key=='pi_rgb':metadata[key]={'format':msg.format,'bytes':len(msg.data),'frame':msg.header.frame_id}
    for topic,kind,key in [('/scan',LaserScan,'scan'),('/im10a/imu/unvalidated',Imu,'imu'),
                           ('/atlas/encoder_update',String,'encoder'),('/camera/image_raw/compressed',CompressedImage,'pi_rgb'),
                           ('/astra/depth/image_raw',Image,'depth'),('/astra/depth/camera_info',CameraInfo,'depth_info')]:
        subs.append(node.create_subscription(kind,topic,lambda msg,k=key:receive(k,msg),qos_profile_sensor_data))
    start=time.monotonic();ready=False
    try:
        try:
            while time.monotonic()-start<12 and not errors:
                rclpy.spin_once(node,timeout_sec=.05)
                if not ready and all(counts.get(k,0)>=3 for k in ('scan','imu','encoder','pi_rgb')):
                    print(json.dumps({'observer_ready':True}),flush=True);ready=True
        except KeyboardInterrupt:errors.append('observer stopped by guardian/operator')
        endpoints={topic:[{'node':e.node_name,'namespace':e.node_namespace,'reliability':str(e.qos_profile.reliability)}
                    for e in node.get_publishers_info_by_topic(topic)]
                   for topic in ('/astra/depth/image_raw','/astra/depth/camera_info','/camera/image_raw/compressed')}
        hz={k:(counts[k]-1)/(last[k]-first[k]) if counts[k]>1 else 0 for k in counts}
        result={'counts':counts,'observed_hz':hz,'largest_receive_gap_s':gaps,'metadata':metadata,'errors':errors,'publishers':endpoints}
        required=('scan','imu','encoder','pi_rgb')+(('depth','depth_info') if phase=='depth' else ())
        if any(counts.get(k,0)<3 for k in required):errors.append('missing/insufficient required stream')
        print(json.dumps(result),flush=True)
    finally:
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()


def main():
    p=argparse.ArgumentParser();p.add_argument('--approve-stationary',action='store_true');p.add_argument('--phase',choices=('baseline','depth'),required=True);p.add_argument('--observer',action='store_true');p.add_argument('--cpu-report-only-owner-approved',action='store_true');p.add_argument('--stagger-start',action='store_true');a=p.parse_args()
    if a.observer:return observe(a.phase)
    if not a.approve_stationary:raise SystemExit('explicit stationary approval required')
    suffix='-cpu-owner-approved' if a.cpu_report_only_owner_approved else ''
    if a.stagger_start:suffix+='-staggered'
    target=STAGE/('stage29-ros-'+a.phase+suffix+'.json')
    if target.exists():raise SystemExit('preserve existing evidence; no automatic retry')
    result={'result':'BLOCKED','samples':[],'recording':False,'cpu_policy':'REPORT ONLY: explicit owner approval' if a.cpu_report_only_owner_approved else 'STOP >75%'};children=[];handles=[];units=None
    try:
        if a.cpu_report_only_owner_approved:
            rows=[];last=gate.ticks()
            for _ in range(3):
                time.sleep(1);now=gate.ticks();row=resource_sample(gate.cpu_delta(last,now),True);last=now;rows.append(row)
            units=gate.services()
            if any(v.get('ActiveState')!='active' or v.get('MainPID')=='0' for v in units.values()):raise RuntimeError('essential owner not active')
        else:rows,units=gate.preflight()
        result.update(preflight=rows,units_before=units,extra_safety=extra_safety())
        env=dict(os.environ);env['LD_LIBRARY_PATH']=str(RUNTIME/'lib')+':/opt/ros/humble/lib:'+env.get('LD_LIBRARY_PATH','')
        env['AMENT_PREFIX_PATH']=str(RUNTIME)+':/opt/ros/humble'
        env['OPENBLAS_NUM_THREADS']='1';env['OMP_NUM_THREADS']='1'
        obsout=(STAGE/('stage29-'+a.phase+suffix+'-observer.json')).open('x');obserr=(STAGE/('stage29-'+a.phase+suffix+'-observer-stderr.txt')).open('x');handles.extend([obsout,obserr])
        observer=subprocess.Popen([sys.executable,__file__,'--observer','--phase',a.phase],env=env,stdout=obsout,stderr=obserr,start_new_session=True);children.append(observer)
        def launch_driver():
            stdout=(STAGE/('stage29-depth'+suffix+'-driver-stdout.txt')).open('x');stderr=(STAGE/('stage29-depth'+suffix+'-driver-stderr.txt')).open('x');handles.extend([stdout,stderr])
            args=[str(RUNTIME/'lib/astra_camera/astra_camera_node'),'--ros-args','-r','__ns:=/astra']
            for key,value in {'camera_name':'astra','use_uvc_camera':'false','enable_color':'false','enable_depth':'true',
                              'enable_ir':'false','enable_point_cloud':'false','enable_colored_point_cloud':'false','publish_tf':'false',
                              'depth_registration':'false','enable_publish_extrinsic':'false','depth_width':'160','depth_height':'120',
                              'depth_fps':'30','depth_scale':'1','oni_log_to_file':'false','oni_log_to_console':'false'}.items():args+=['-p',key+':='+value]
            child=subprocess.Popen(args,env=env,stdout=stdout,stderr=stderr,start_new_session=True,cwd=str(RUNTIME));children.append(child);return child
        driver=launch_driver() if a.phase=='depth' and not a.stagger_start else None
        start=time.monotonic();last=gate.ticks();process_previous={}
        while observer.poll() is None:
            if time.monotonic()-start>20:raise RuntimeError('bounded test timeout')
            time.sleep(.5);now=gate.ticks();cpu=gate.cpu_delta(last,now);row=resource_sample(cpu,a.cpu_report_only_owner_approved);last=now
            row['processes']=[]
            for child in children:
                try:
                    fields=(Path('/proc')/str(child.pid)/'stat').read_text().rsplit(')',1)[1].split()
                    ticks=int(fields[11])+int(fields[12]);stamp=time.monotonic()
                    rss=next(int(s.split()[1]) for s in (Path('/proc')/str(child.pid)/'status').read_text().splitlines() if s.startswith('VmRSS:'))
                    prior=process_previous.get(child.pid);process_previous[child.pid]=(ticks,stamp)
                    row['processes'].append({'role':'observer' if child is observer else 'Astra driver','pid':child.pid,'rss_kib':rss,
                        'cpu_one_core_percent':100*(ticks-prior[0])/os.sysconf('SC_CLK_TCK')/(stamp-prior[1]) if prior else None})
                except (OSError,StopIteration):pass
            gpu=Path('/sys/devices/platform/17000000.gpu/load')
            row['gpu_percent']=float(gpu.read_text())/10 if gpu.exists() else None
            row['extra_safety']=extra_safety();result['samples'].append(row)
            if units!=gate.services():raise RuntimeError('production identity changed')
            if a.phase=='depth' and driver is None:
                progress=(STAGE/('stage29-'+a.phase+suffix+'-observer.json')).read_text()
                if '"observer_ready": true' in progress:driver=launch_driver()
            if driver is not None and driver.poll() is not None:raise RuntimeError('driver exited '+str(driver.returncode))
        if observer.returncode:raise RuntimeError('observer exited '+str(observer.returncode))
        obsout.flush();observed=json.loads((STAGE/('stage29-'+a.phase+suffix+'-observer.json')).read_text().splitlines()[-1]);result['observed']=observed
        if observed['errors']:raise RuntimeError('stream validation failed: '+str(observed['errors']))
        result['result']='PASS'
    except Exception as e:
        result['failure']=str(e)
        if isinstance(e,gate.AdmissionError):result['failed_sample']=e.evidence
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGINT)
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=3)
        for h in handles:h.close()
        result['units_after']=gate.services();target.write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':main()

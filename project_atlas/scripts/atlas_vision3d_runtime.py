"""Owner-approved, leased, bounded Astra VIEWING only. No control ROS interfaces.

Worker owns only a new isolated camera child; production services are never
changed. No camera frames/logs are persisted. Scalar runtime health is ephemeral.
"""
import atexit
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path('/home/jetson/project-atlas-migration/astra-20261021')
RUNTIME = STAGE/'astra-arm64-stage29-v2'
STATE = Path(os.environ.get('ATLAS_VISION3D_STATE_PATH') or
             str(Path('/run/user')/str(os.getuid())/'atlas-vision3d-viewer.json'))
MAX_SECONDS = 60


def process_metrics(pid, previous=None):
    """Read only this process; retain attribution even when a guard rejects CPU."""
    try:
        root=Path('/proc')/str(pid)
        fields=(root/'stat').read_text().rsplit(')',1)[1].split()
        ticks=int(fields[11])+int(fields[12]);now=time.monotonic()
        rss=next(int(s.split()[1]) for s in (root/'status').read_text().splitlines() if s.startswith('VmRSS:'))
        row={'pid':pid,'rss_kib':rss,'cpu_one_core_percent':None}
        if previous and now>previous[1]:
            row['cpu_one_core_percent']=100*(ticks-previous[0])/os.sysconf('SC_CLK_TCK')/(now-previous[1])
        return row,(ticks,now)
    except (OSError,StopIteration,ValueError,IndexError):return {'pid':pid,'state':'unavailable'},None


def limits(cpu, ram, hottest):
    import math
    if not all(math.isfinite(x) for x in (cpu, ram, hottest)):
        raise ValueError('RESOURCE BLOCKED: unknown measurement')
    if cpu > 75 or ram > 80 or hottest > 70:
        raise ValueError('RESOURCE BLOCKED: CPU75% / RAM80% / temperature70C limit')


def driver_args(mode):
    if mode not in ('depth', 'concurrent'):
        raise ValueError('unsupported viewer mode')
    values = {'camera_name':'astra','use_uvc_camera':str(mode=='concurrent').lower(),
              'enable_color':str(mode=='concurrent').lower(),'enable_depth':'true',
              'enable_ir':'false','enable_point_cloud':'false','enable_colored_point_cloud':'false',
              'publish_tf':'false','depth_registration':'false','enable_publish_extrinsic':'false',
              'depth_width':'160','depth_height':'120','depth_fps':'30','depth_scale':'1',
              'color_width':'320','color_height':'240','color_fps':'15',
              'uvc_vendor_id':'0x2bc5','uvc_product_id':'0x0501','uvc_camera_format':'mjpeg',
              'uvc_retry_count':'0','oni_log_to_file':'false','oni_log_to_console':'false'}
    args=[str(RUNTIME/'lib/astra_camera/astra_camera_node'),'--ros-args','-r','__ns:=/astra']
    for k,v in values.items():args+=['-p', k+':='+v]
    return args


class ViewerSession:
    def __init__(self):
        self.lock=threading.RLock(); self.child=None; self.error=''; self.generation=0

    def start(self, mode):
        driver_args(mode)
        with self.lock:
            if self.child and self.child.poll() is None:
                raise ValueError('viewer already running; pause before changing mode')
            self.generation+=1
            command=['/bin/bash','-lc','source /opt/ros/humble/setup.bash; exec /usr/bin/python3 '
                     +str(Path(__file__).resolve())+' --worker '+mode]
            self.child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL,start_new_session=True)
            self.error=''; self.touch()

    def touch(self):
        with self.lock:
            if self.child and self.child.poll() is None:
                try:self.child.stdin.write(b'1\n');self.child.stdin.flush()
                except (OSError,ValueError):pass

    def status(self):
        with self.lock:
            if self.child is None:return {'state':'OFF','reason':self.error}
            try:
                data=json.loads(STATE.read_text())
                if data.get('worker_pid')!=self.child.pid:raise ValueError('different session')
            except (OSError,ValueError):data={'state':'CHECKING','reason':'Fresh safety/resource admission'}
            if self.child.poll() is not None and data.get('state') in ('ACTIVE','CHECKING'):
                data={'state':'OFF','reason':'Viewer process ended'}
            return data

    def stop(self):
        with self.lock:
            child=self.child
            if child and child.poll() is None:
                child.stdin.close()  # EOF revokes the viewing lease, not any motor stop.
                try:child.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    try:child.wait(timeout=3)
                    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=2)


SESSION=ViewerSession()
atexit.register(SESSION.stop)


def worker(mode):
    import select
    sys.path.insert(0,str(ROOT/'tools/vision3d'))
    import stationary_gate as G
    import stationary_ros_probe as P
    child=None; rows=[]; started=time.monotonic(); last_lease=started; process_last=None;worker_last=None
    parent=os.getppid(); state={'state':'CHECKING','worker_pid':os.getpid(),'mode':mode,
                              'limits':{'cpu_percent':75,'ram_percent':80,'temperature_c':70},
                              'recording':False,'calibration':'UNVALIDATED; axial Z only'}
    def write():
        temporary=STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps(state,allow_nan=False));os.replace(temporary,STATE)
    def interrupted(*_):raise RuntimeError('viewer cancelled')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    def sample():
        nonlocal last_ticks,process_last,worker_last
        ticks=G.ticks();cpu=G.cpu_delta(last_ticks,ticks);last_ticks=ticks
        state['worker_process'],worker_last=process_metrics(os.getpid(),worker_last)
        if child:state['astra_process'],process_last=process_metrics(child.pid,process_last)
        state['elapsed_s']=time.monotonic()-started
        try:
            G.require_cpu(cpu)
            observation=P.safety_snapshot()
            row=G.check(cpu,observation=observation)
        except G.AdmissionError as e:
            state['failed_resources']=e.evidence
            raise ValueError('RESOURCE BLOCKED: '+str(e)) from e
        limits(cpu,row['ram_percent'],max(row['thermal_c'].values()))
        P.extra_safety(ros=observation['ros']);rows.append(row)
        state.update(resources=row,remaining_s=max(0,MAX_SECONDS-(time.monotonic()-started)))
    try:
        write()
        # Integrity check is local and read-only, before opening camera hardware.
        manifest=json.loads((RUNTIME/'manifest.json').read_text())
        if len(manifest['files'])!=458:raise ValueError('runtime manifest count mismatch')
        for f in manifest['files']:
            p=(RUNTIME/f['path']).resolve()
            if not p.is_relative_to(RUNTIME) or hashlib.sha256(p.read_bytes()).hexdigest()!=f['sha256']:
                raise ValueError('isolated runtime integrity failure')
        units=G.services();last_ticks=G.ticks()
        for _ in range(3):time.sleep(1);sample();write()
        if subprocess.run(['pgrep','-x','astra_camera_no'],stdout=subprocess.DEVNULL).returncode==0:
            raise ValueError('existing Astra process; refusing second owner')
        # Linux prctl in this single-threaded worker: camera dies if guardian dies.
        def parent_death():
            import ctypes
            if ctypes.CDLL(None).prctl(1,signal.SIGKILL,0,0,0)!=0:os._exit(127)
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        env['LD_LIBRARY_PATH']=str(RUNTIME/'lib')+':/opt/ros/humble/lib:'+env.get('LD_LIBRARY_PATH','')
        env['AMENT_PREFIX_PATH']=str(RUNTIME)+':/opt/ros/humble'
        child=subprocess.Popen(driver_args(mode),env=env,cwd=RUNTIME,stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,start_new_session=True,preexec_fn=parent_death)
        state['driver_launch_elapsed_s']=time.monotonic()-started
        state['astra_process'],process_last=process_metrics(child.pid)
        state.update(state='ACTIVE',reason='Bounded stationary viewing; accuracy NOT verified',driver_pid=child.pid)
        while time.monotonic()-started<MAX_SECONDS:
            if os.getppid()!=parent:raise RuntimeError('dashboard owner ended')
            if select.select([sys.stdin.buffer],[],[],1)[0]:
                lease=os.read(sys.stdin.fileno(),4096)
                if not lease:raise RuntimeError('viewer paused or closed')
                last_lease=time.monotonic()
            if time.monotonic()-last_lease>4:raise RuntimeError('viewer lease expired')
            # Sample at >=1 second, never accept an effectively zero CPU window.
            time.sleep(.5)
            sample()
            if G.services()!=units:raise RuntimeError('essential service identity changed')
            if child.poll() is not None:raise RuntimeError('isolated camera exited')
            metrics=state['astra_process']
            if metrics.get('state')=='unavailable':raise RuntimeError('camera process unavailable')
            state['astra_rss_kib']=metrics['rss_kib']
            state['astra_cpu_one_core_percent']=metrics['cpu_one_core_percent']
            write()
        state.update(state='OFF',reason='60-second session complete; explicit Start required')
    except Exception as e:
        reason=str(e)
        state.update(state='RESOURCE BLOCKED' if 'CPU' in reason or 'RAM' in reason or 'thermal' in reason or 'RESOURCE' in reason else 'OFF',reason=reason)
    finally:
        if child and child.poll() is None:
            os.killpg(child.pid,signal.SIGINT)
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=2)
        state.update(driver_stopped=True,sample_count=len(rows))
        write()


if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--worker':raise SystemExit('explicit viewer worker only')
    worker(sys.argv[2])

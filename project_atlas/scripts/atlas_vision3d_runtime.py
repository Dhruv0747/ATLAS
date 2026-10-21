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
# Stage31: the Astra driver joins a PRIVATE ROS domain. Measured on the Jetson (21 Oct): a participant joining the
# production domain wakes ~34 existing nodes for ~3 s (65% -> 92% CPU); the same join in a private domain cost only the
# joiner itself.  Only the Vision Lab receiver joins this domain, so no production node sees the camera graph.
ISOLATED_DOMAIN_ID = 77


def domain_in_use(domain_id, proc=Path('/proc')):
    """True if any readable process already declares this ROS_DOMAIN_ID (read-only /proc scan)."""
    want=('ROS_DOMAIN_ID=%d' % domain_id).encode()
    for entry in proc.iterdir():
        if not entry.name.isdigit():continue
        try:
            if want in (entry/'environ').read_bytes().split(b'\0'):return True
        except OSError:continue
    return False


# Stage31b candidate: every CPU guard sample covers at least MIN_CPU_WINDOW_S. Each sample is still a single
# fail-closed decision against the unchanged 75% limit. A window longer than MAX_CPU_WINDOW_S (stalled guardian,
# slow safety snapshot) fails closed, so a long average can never hide a sustained spike. Measured 21 Oct: a ~0.5 s
# window caught the Astra start-up burst (76.0%) while every 1-s sample over 191 s stayed <=73.8%.
MIN_CPU_WINDOW_S = 1.0
MAX_CPU_WINDOW_S = 2.0
LEASE_POLL_S = 0.25
STARTUP_SEED = 'ATLAS_VISION3D_STARTUP_SAMPLE'


def startup_sample():
    # Captured in the existing web process BEFORE shell/Python startup.
    stamp = time.monotonic()
    fields = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    return [stamp, sum(fields), fields[3] + fields[4]]


def validate_startup_sample(value, now):
    import math
    if (not isinstance(value, list) or len(value) != 3 or
            any(not isinstance(x, (float, int)) or not math.isfinite(x) for x in value) or
            not 0 <= now-value[0] <= MAX_CPU_WINDOW_S or
            not 0 <= value[2] <= value[1]):
        raise ValueError('RESOURCE BLOCKED: missing, stale or invalid startup CPU sample')
    return value[0], (value[1], value[2])


def verify_runtime(runtime, checkpoint, chunk_size=128*1024):
    """Hash every byte, bounded memory; cancellation/resource checks between chunks.

    No cache or skipped verification. Cooperative yielding reduces burstiness,
    not total SHA work; native CPU benefit requires a separately approved test.
    """
    checkpoint()
    manifest=json.loads((runtime/'manifest.json').read_text())
    if len(manifest['files']) != 458:raise ValueError('runtime manifest count mismatch')
    seen=set();resolved_root=runtime.resolve()
    for entry in manifest['files']:
        checkpoint()
        p=(runtime/entry['path']).resolve()
        if not p.is_relative_to(resolved_root) or p in seen:
            raise ValueError('isolated runtime unsafe/duplicate path')
        seen.add(p)
        digest=hashlib.sha256()
        with p.open('rb') as stream:
            while True:
                checkpoint()
                block=stream.read(chunk_size)
                if not block:break
                digest.update(block)
                if len(block)==chunk_size:time.sleep(0.002)
        if digest.hexdigest()!=entry['sha256']:
            raise ValueError('isolated runtime integrity failure')
    checkpoint()


class CpuWindow:
    """Times the CPU guard. due(): a full window has elapsed. close(): returns the window length or fails closed."""
    def __init__(self, now):
        self.start = now

    def due(self, now):
        return now - self.start >= MIN_CPU_WINDOW_S

    def wait(self, now):
        return max(0.02, min(LEASE_POLL_S, MIN_CPU_WINDOW_S - (now - self.start)))

    def close(self, now):
        width = now - self.start
        if width < MIN_CPU_WINDOW_S - 1e-6:
            raise RuntimeError('guard CPU window %.3f s shorter than %.1f s' % (width, MIN_CPU_WINDOW_S))
        if width > MAX_CPU_WINDOW_S:
            raise RuntimeError('RESOURCE BLOCKED: guard sampling interval %.2f s exceeded %.1f s; failing closed' % (width, MAX_CPU_WINDOW_S))
        self.start = now
        return width


def driver_env(base):
    env=dict(base,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    env['ROS_DOMAIN_ID']=str(ISOLATED_DOMAIN_ID)
    return env


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


# Stage32: explicit stream combinations. Each is a bounded viewer mode, not a capability claim: whether the camera
# actually delivers a stream is decided by the driver's OpenNI mode negotiation and recorded from its log.
# Astra Pro: depth and IR come from the same OpenNI (2bc5:0403) sensor; RGB is the separate UVC camera (2bc5:0501).
VIEW_MODES = {
    'depth':      {'depth': True,  'ir': False, 'rgb': False},
    'concurrent': {'depth': True,  'ir': False, 'rgb': True},    # RGB + depth (historical name kept)
    'ir':         {'depth': False, 'ir': True,  'rgb': False},
    'ir_depth':   {'depth': True,  'ir': True,  'rgb': False},
    'rgb_ir':     {'depth': False, 'ir': True,  'rgb': True},
    # Stage32 addendum: depth + XYZ PointCloud2 from a separate private-domain node; refused unless calibration VALIDATED
    'depth_cloud': {'depth': True, 'ir': False, 'rgb': False, 'cloud': True},
}
CLOUD_NODE = ROOT / 'scripts/atlas_vision3d_cloud_node.py'


def cloud_admission(mode):
    """Refuse a cloud mode before any camera hardware is opened unless the calibration gate passes."""
    if not VIEW_MODES[mode].get('cloud'):
        return None
    import atlas_vision3d_geometry as Geo
    manifest = json.loads((ROOT / 'config/vision3d_live.json').read_text())
    st = Geo.calibration_state(manifest)
    if st['state'] != 'VALIDATED':
        raise ValueError('CALIBRATION BLOCKED: ' + st['reason'])
    return st
def driver_log():
    return STATE.with_name('atlas-vision3d-driver.log')   # next to the state file on tmpfs; capped; no frames


DRIVER_LOG_MAX = 2 * 1024 * 1024
NEGOTIATION = ('video mode', 'Supported video modes', 'is started', 'not supported', 'disabled', 'Failed', 'ERROR',
               'Error', 'Infrared', 'PixelFormat', 'fps', 'resolution', 'signal_handler(')


def lifecycle_event(state, event, **details):
    """Bounded scalar evidence; no frames, subscriptions or ROS discovery."""
    state.setdefault('lifecycle',[]).append(dict(event=event,monotonic_s=time.monotonic(),
                                               unix_s=time.time(),**details))
    state['lifecycle']=state['lifecycle'][-32:]


def shutdown_owned_process(child,state,role):
    """Reap only the session-owned process; tolerate exit between poll and signal."""
    if child is None:return True
    if child.poll() is not None:
        lifecycle_event(state,'already_exited',role=role,returncode=child.returncode)
        return True
    lifecycle_event(state,'signal_send',role=role,pid=child.pid,signal='SIGINT')
    try:os.killpg(child.pid,signal.SIGINT)
    except ProcessLookupError:pass
    try:child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        lifecycle_event(state,'signal_send',role=role,pid=child.pid,signal='SIGKILL')
        try:os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        child.wait(timeout=2)
    lifecycle_event(state,'process_reaped',role=role,returncode=child.returncode)
    return child.poll() is not None


def driver_error_order(text):
    """Describe observed log ordering, never suppress exceptions or infer CPU cause."""
    import re
    signal_stamp=None;context_stamp=None
    for line in text.splitlines():
        stamp=re.search(r'\[(\d+\.\d+)\]',line)
        if stamp is None:continue
        if 'signal_handler(SIGINT/SIGTERM)' in line and signal_stamp is None:
            signal_stamp=float(stamp.group(1))
        if "context is invalid" in line and context_stamp is None:
            context_stamp=float(stamp.group(1))
    ordered=signal_stamp is not None and context_stamp is not None and signal_stamp<=context_stamp
    return {'signal_log_unix_s':signal_stamp,'invalid_context_log_unix_s':context_stamp,
            'signal_precedes_invalid_context':ordered,
            'context_after_signal_ms':round((context_stamp-signal_stamp)*1000,3) if ordered else None,
            'interpretation':'invalid context reported after signal; shutdown race supported' if ordered
                else 'ordering unproven; preserve and investigate driver error'}


def driver_args(mode):
    if mode not in VIEW_MODES:
        raise ValueError('unsupported viewer mode')
    m = VIEW_MODES[mode]
    on = lambda b: str(bool(b)).lower()
    values = {'camera_name':'astra','use_uvc_camera':on(m['rgb']),
              'enable_color':on(m['rgb']),'enable_depth':on(m['depth']),
              'enable_ir':on(m['ir']),'enable_point_cloud':'false','enable_colored_point_cloud':'false',
              'publish_tf':'false','depth_registration':'false','enable_publish_extrinsic':'false',
              'depth_width':'160','depth_height':'120','depth_fps':'30','depth_scale':'1',
              'color_width':'320','color_height':'240','color_fps':'15',
              'uvc_vendor_id':'0x2bc5','uvc_product_id':'0x0501','uvc_camera_format':'mjpeg',
              'uvc_retry_count':'0','oni_log_to_file':'false','oni_log_to_console':'false'}
    if m['ir']:   # IR parameters only when IR is requested, so depth / RGB+depth launches stay byte-identical
        values.update(ir_width='640',ir_height='480',ir_fps='30')
    args=[str(RUNTIME/'lib/astra_camera/astra_camera_node'),'--ros-args','-r','__ns:=/astra']
    for k,v in values.items():args+=['-p', k+':='+v]
    return args


def negotiation_lines(text, limit=40):
    """Driver start-up lines about stream/mode negotiation only (no frame data)."""
    out=[]
    for line in text.splitlines():
        if any(k in line for k in NEGOTIATION):
            out.append(line.strip()[-240:])
            if len(out)>=limit:break
    return out


class ViewerSession:
    def __init__(self):
        self.lock=threading.RLock(); self.child=None; self.error=''; self.generation=0

    def start(self, mode):
        driver_args(mode)
        with self.lock:
            if self.child and self.child.poll() is None:
                raise ValueError('viewer already running; pause before changing mode')
            self.generation+=1
            # Web service already sources Humble and its overlay. Re-sourcing in
            # a login shell repeats setup subprocesses before the first sample.
            # Inherit that environment; never move this work outside the guard.
            command=['/usr/bin/python3',str(Path(__file__).resolve()),'--worker',mode]
            self.child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL,start_new_session=True,
                                        env=dict(os.environ, **{STARTUP_SEED:json.dumps(startup_sample())}))
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


def worker(mode, startup=None):
    import select
    sys.path.insert(0,str(ROOT/'tools/vision3d'))
    import stationary_gate as G
    import stationary_ros_probe as P
    child=None; cloud_child=None; rows=[]; started=time.monotonic(); last_lease=started; process_last=None;worker_last=None
    parent=os.getppid(); state={'state':'CHECKING','worker_pid':os.getpid(),'mode':mode,
                              'limits':{'cpu_percent':75,'ram_percent':80,'temperature_c':70},
                              'recording':False,'calibration':'UNVALIDATED; axial Z only'}
    lifecycle_event(state,'worker_started')
    def write():
        temporary=STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps(state,allow_nan=False));os.replace(temporary,STATE)
    def interrupted(*_):
        lifecycle_event(state,'cancellation_received')
        raise RuntimeError('viewer cancelled')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    def sample():
        nonlocal last_ticks,process_last,worker_last
        now=time.monotonic()
        if not window.due(now):time.sleep(MIN_CPU_WINDOW_S-(now-window.start))   # never sample a short window
        width=window.close(time.monotonic())
        ticks=G.ticks();cpu=G.cpu_delta(last_ticks,ticks);last_ticks=ticks
        state['cpu_window_s']=round(width,3)
        state['worker_process'],worker_last=process_metrics(os.getpid(),worker_last)
        if child:state['astra_process'],process_last=process_metrics(child.pid,process_last)
        state['elapsed_s']=time.monotonic()-started
        try:
            G.require_cpu(cpu)
            observation=P.safety_snapshot()
            row=G.check(cpu,observation=observation)
        except G.AdmissionError as e:
            state['failed_resources']=e.evidence
            lifecycle_event(state,'resource_guard_failed',evidence=e.evidence)
            raise ValueError('RESOURCE BLOCKED: '+str(e)) from e
        limits(cpu,row['ram_percent'],max(row['thermal_c'].values()))
        P.extra_safety(ros=observation['ros']);rows.append(row)
        state.update(resources=row,remaining_s=max(0,MAX_SECONDS-(time.monotonic()-started)))
    def checkpoint():
        nonlocal last_lease
        if os.getppid()!=parent:raise RuntimeError('dashboard owner ended')
        if select.select([sys.stdin.buffer],[],[],0)[0]:
            if not os.read(sys.stdin.fileno(),4096):raise RuntimeError('viewer paused or closed')
            last_lease=time.monotonic()
        if time.monotonic()-last_lease>4:raise RuntimeError('viewer lease expired')
        if time.monotonic()-started>=MAX_SECONDS:raise RuntimeError('startup session deadline exceeded')
        if window.due(time.monotonic()):sample();write()
    try:
        write()
        seed_time,last_ticks=validate_startup_sample(startup if startup is not None else startup_sample(),time.monotonic())
        state['startup_guard_baseline_monotonic_s']=seed_time
        window=CpuWindow(seed_time)
        # Includes shell/Python startup, imports and all later integrity work.
        sample();write()
        units=G.services()
        verify_runtime(RUNTIME,checkpoint)
        cloud_admission(mode)
        while len(rows)<3:checkpoint();time.sleep(window.wait(time.monotonic()))
        if subprocess.run(['pgrep','-x','astra_camera_no'],stdout=subprocess.DEVNULL).returncode==0:
            raise ValueError('existing Astra process; refusing second owner')
        if domain_in_use(ISOLATED_DOMAIN_ID):
            raise ValueError('private Vision Lab ROS domain %d already in use; refusing' % ISOLATED_DOMAIN_ID)
        checkpoint()
        if G.services()!=units:raise RuntimeError('essential service identity changed during startup')
        state['ros_domain_id']=ISOLATED_DOMAIN_ID
        # Linux prctl in this single-threaded worker: camera dies if guardian dies.
        def parent_death():
            import ctypes
            if ctypes.CDLL(None).prctl(1,signal.SIGKILL,0,0,0)!=0:os._exit(127)
        env=driver_env(os.environ)
        env['LD_LIBRARY_PATH']=str(RUNTIME/'lib')+':/opt/ros/humble/lib:'+env.get('LD_LIBRARY_PATH','')
        env['AMENT_PREFIX_PATH']=str(RUNTIME)+':/opt/ros/humble'
        log=open(driver_log(),'wb')
        child=subprocess.Popen(driver_args(mode),env=env,cwd=RUNTIME,stdout=log,
                               stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=parent_death)
        lifecycle_event(state,'driver_spawned',pid=child.pid)
        log.close()
        if VIEW_MODES[mode].get('cloud'):
            cloud_admission(mode)   # re-check immediately before launching the cloud node
            cloud_child=subprocess.Popen([sys.executable,str(CLOUD_NODE)],env=env,cwd=ROOT,stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL,start_new_session=True,preexec_fn=parent_death)
            state['cloud_pid']=cloud_child.pid
        state['driver_launch_elapsed_s']=time.monotonic()-started
        state['astra_process'],process_last=process_metrics(child.pid)
        state.update(state='ACTIVE',reason='Bounded stationary viewing; accuracy NOT verified',driver_pid=child.pid)
        while time.monotonic()-started<MAX_SECONDS:
            if os.getppid()!=parent:raise RuntimeError('dashboard owner ended')
            if select.select([sys.stdin.buffer],[],[],window.wait(time.monotonic()))[0]:
                lease=os.read(sys.stdin.fileno(),4096)
                if not lease:raise RuntimeError('viewer paused or closed')
                last_lease=time.monotonic()
            if time.monotonic()-last_lease>4:raise RuntimeError('viewer lease expired')
            # Lease is checked every <=0.25 s; the CPU/RAM/thermal/policy guard runs once per full >=1 s window.
            if not window.due(time.monotonic()):continue
            sample()
            if G.services()!=units:raise RuntimeError('essential service identity changed')
            if child.poll() is not None:raise RuntimeError('isolated camera exited')
            if cloud_child is not None and cloud_child.poll() is not None:raise RuntimeError('point cloud node exited')
            metrics=state['astra_process']
            if metrics.get('state')=='unavailable':raise RuntimeError('camera process unavailable')
            try:
                if driver_log().stat().st_size>DRIVER_LOG_MAX:os.truncate(driver_log(),0)   # bound tmpfs use
            except OSError:pass
            state['astra_rss_kib']=metrics['rss_kib']
            state['astra_cpu_one_core_percent']=metrics['cpu_one_core_percent']
            write()
        state.update(state='OFF',reason='60-second session complete; explicit Start required')
    except Exception as e:
        reason=str(e)
        lifecycle_event(state,'session_stopping',reason=reason)
        state.update(state='RESOURCE BLOCKED' if 'CPU' in reason or 'RAM' in reason or 'thermal' in reason or 'RESOURCE' in reason else 'OFF',reason=reason)
    finally:
        # Cleanup of one child must not prevent cleanup of the other.
        stopped={}
        for role,owned in (('cloud',cloud_child),('driver',child)):
            try:stopped[role]=shutdown_owned_process(owned,state,role)
            except Exception as e:
                stopped[role]=False
                lifecycle_event(state,'cleanup_failed',role=role,error=str(e))
        state.update(driver_stopped=stopped['driver'],cloud_stopped=stopped['cloud'],sample_count=len(rows))
        if child:
            try:
                with open(driver_log(),'rb') as f:text=f.read(65536).decode('utf-8','replace')
                state['driver_negotiation']=negotiation_lines(text)
                state['driver_error_order']=driver_error_order(text)
                os.truncate(driver_log(),min(len(text.encode()),65536))
            except OSError:state['driver_negotiation']=['driver log unavailable']
        write()


if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--worker':raise SystemExit('explicit viewer worker only')
    # Old web owners cannot silently launch this candidate without coverage.
    worker(sys.argv[2], startup=json.loads(os.environ.get(STARTUP_SEED,'null')) or [])

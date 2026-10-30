"""Optional single-session feature lab. Disabled until reviewed deployment.

No camera starts/lease renewal, new ROS subscribers, TF or actuator publications.
All JSON evidence is local; image pixels are IPC-only and never written to disk.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

NAMES={'face':'Face Recognition','gesture':'Gesture Recognition','body':'Human Body Tracking',
       'target':'Target Tracking','object':'Object Detection','mapping':'RGB-D 3D Mapping'}
BLOCKERS={'face':'Identity model, opt-in enrollment and deletion backend not installed',
          'gesture':'Hand landmarks and gesture model not installed',
          'mapping':'Calibration/registration/TF and onboard mapping activation not verified'}
ROOT=Path(__file__).resolve().parents[1]


class Lab:
    def __init__(self,root=None,config=None):
        self.root=Path(root or Path.home()/'.local/share/atlas/vision-tests')
        self.config=config or ROOT/'config/vision_feature_lab.json'
        self.lock=threading.RLock();self.active=None;self.reports={};self.thread=None
        self.stop_event=threading.Event();self.process=None;self.latest=None
        if self.root.exists() and not self.root.is_symlink():
            for path in sorted(self.root.glob('*.json'),key=lambda p:p.stat().st_mtime)[-100:]:
                try:
                    if path.is_symlink() or path.stat().st_size>131072:continue
                    raw=path.read_bytes();r=json.loads(raw);key=r['feature']
                    if key not in NAMES or r['id']!=path.stem:continue
                    if r['state']=='RUNNING':r.update(state='FAILED',reason='Interrupted session; no automatic resume')
                    r['evidence_sha256']=hashlib.sha256(raw).hexdigest()
                    self.reports[key]=r
                except (ValueError,KeyError,OSError):continue

    def settings(self):
        c=json.loads(Path(self.config).read_text())
        if c.get('enabled') is not True:raise ValueError('Feature execution disabled; reviewed deployment required')
        if c.get('model_sha256')!='97cd66586901c75707164e912e609253d1e71705055248b9c83430c3421721df':
            raise ValueError('unreviewed model hash')
        return c

    def status(self):
        with self.lock:
            try:self.settings();enabled=True
            except (ValueError,OSError):enabled=False
            rows=[]
            for key,name in NAMES.items():
                r=self.reports.get(key)
                reason=BLOCKERS.get(key,'Read-only adapter prepared; live Astra validation pending')
                state='NOT INSTALLED' if key in ('face','gesture') else 'UNAVAILABLE'
                if enabled and key in ('object','body','target'):reason='Start requires active approved RGB viewer and fresh safety admission'
                if r:state=r['state'];reason=r['reason']
                rows.append(dict(id=key,name=name,state=state,reason=reason,
                                 start_available=enabled and key not in BLOCKERS and self.active is None,
                                 report=copy.deepcopy(r),metrics=copy.deepcopy(r.get('resources')) if r else None))
            return dict(features=rows,active=self.active,latest=copy.deepcopy(self.latest),
                        pan_tilt_allowed=False,face_enrollment_available=False,
                        evidence='Local metadata only; no images saved',max_duration_s=30)

    def save(self,r):
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.root.is_symlink():raise ValueError('symlink evidence root forbidden')
        files=list(self.root.glob('*.json'))
        path=self.root/(r['id']+'.json')
        if sum(p.stat().st_size for p in files)>8*1024*1024-131072 or (len(files)>=100 and not path.exists()):
            raise ValueError('evidence quota reached; export/review before another test')
        raw=json.dumps({k:v for k,v in r.items() if k!='evidence_sha256'},allow_nan=False,sort_keys=True).encode()
        if len(raw)>131072:raise ValueError('report size limit')
        temp=path.with_suffix('.tmp')
        with open(temp,'wb') as f:
            os.chmod(temp,0o600);f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
        return hashlib.sha256(raw).hexdigest()

    def download(self,feature):
        with self.lock:
            r=self.reports.get(feature)
            if not r:raise ValueError('no session evidence')
            ident=r['id']
            if len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):raise ValueError('invalid report identity')
            path=self.root/(ident+'.json')
            if path.is_symlink() or path.stat().st_size>131072:raise ValueError('invalid report file')
            raw=path.read_bytes()
            return raw,hashlib.sha256(raw).hexdigest()

    def verdict(self,feature,value):
        with self.lock:
            if value not in ('PASS','FAIL'):raise ValueError('invalid manual verdict')
            r=self.reports.get(feature)
            if not r or self.active:raise ValueError('completed test evidence required')
            if value=='PASS' and (r['state']!='READY' or r['frames']<2 or r.get('detections_seen',0)<1):
                raise ValueError('PASS requires completed real frame processing without safety failure')
            r=dict(r,manual_verdict=value,reviewed_at=time.time())
            r['state']='PHYSICALLY VERIFIED' if value=='PASS' else 'FAILED'
            r['reason']='Operator observation recorded; not calibrated geometry or identity accuracy certification'
            r['evidence_sha256']=self.save(r);self.reports[feature]=r
            return r

    def stop(self):
        self.stop_event.set()
        with self.lock:
            p=self.process
        if p and p.poll() is None:p.kill()

    def start(self,feature,viewer):
        with self.lock:
            if feature not in NAMES:raise ValueError('unknown feature')
            if self.active is not None:raise ValueError('one test at a time')
            if feature in BLOCKERS:raise ValueError(BLOCKERS[feature])
            c=self.settings()
            r=dict(id=uuid.uuid4().hex,feature=feature,state='RUNNING',reason='Fresh admission in progress',
                   started_at=time.time(),frames=0,detections_seen=0,manual_verdict=None,events=[],resources=None,
                   model_sha256=c['model_sha256'],interpretation='2D person boxes, not skeletal pose' if feature=='body' else '2D boxes; no metric geometry')
            self.save(r)  # prove writable bounded evidence before optional work
            self.active=feature;self.reports[feature]=r;self.latest=None;self.stop_event.clear()
            self.thread=threading.Thread(target=self.run,args=(feature,c,viewer,r),daemon=True,name='astra-feature-guard')
            self.thread.start()
            return r

    def run(self,feature,c,viewer,r):
        p=None;io=None;error=None;completed=False;io_error=[];last_result=[time.monotonic()];last_stamp=[None]
        try:
            sys.path.insert(0,str(ROOT/'tools/vision3d'))
            from onboard_supervisor import observe
            from stationary_gate import ticks,cpu_delta
            from atlas_vision3d_runtime import SESSION
            from atlas_vision_features import rgb_array
            camera=SESSION.status()
            if camera.get('state')!='ACTIVE':raise ValueError('Start existing approved RGB camera session first')
            identity=(camera.get('driver_pid'),camera.get('startup_guard_baseline_monotonic_s'))
            if not all(identity):raise ValueError('camera identity unavailable')
            def check_camera():
                current=SESSION.status()
                if current.get('state')!='ACTIVE' or identity!=(current.get('driver_pid'),current.get('startup_guard_baseline_monotonic_s')):
                    raise ValueError('camera session changed or stopped')
                with viewer.lock:
                    message=viewer._fresh('rgb')
                    if viewer.clock()-viewer.received['rgb']>.5:raise ValueError('RGB reception stale')
                    return rgb_array(message,time.time_ns())
            before=ticks();t=time.monotonic()
            if self.stop_event.wait(1):raise ValueError('operator stopped before admission')
            now=time.monotonic();cur=ticks();r['resources']=observe(cpu_delta(before,cur),now-t)
            check_camera()
            if self.stop_event.is_set():raise ValueError('operator stopped before worker launch')
            env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
            p=subprocess.Popen([sys.executable,str(ROOT/'scripts/atlas_vision_feature_worker.py'),feature,c['model_path'],c['model_sha256']],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env)
            with self.lock:self.process=p
            started=time.monotonic();last_result[0]=started
            def exchange():
                try:
                    while not self.stop_event.is_set():
                        image,stamp=check_camera()
                        if stamp==last_stamp[0]:self.stop_event.wait(.05);continue
                        request=dict(width=image.shape[1],height=image.shape[0],stamp_ns=stamp,
                                     rgb=base64.b64encode(image.tobytes()).decode())
                        p.stdin.write((json.dumps(request)+'\n').encode());p.stdin.flush()
                        raw=p.stdout.readline(65537)
                        if not raw or len(raw)>65536:raise ValueError('worker output unavailable/oversized')
                        result=json.loads(raw)
                        if result.get('error'):raise ValueError(result['error'])
                        if result['stamp_ns']!=stamp or not 0<=time.time_ns()-stamp<=1_000_000_000:
                            raise ValueError('inference frame stale/mismatched')
                        last_stamp[0]=stamp;last_result[0]=time.monotonic()
                        with self.lock:
                            r['frames']+=1;r['fps']=r['frames']/(time.monotonic()-started)
                            r['detections_seen']+=len(result['detections'])
                            self.latest=dict(result,feature=feature,received_at=time.time())
                            r['last_result']=result
                        self.stop_event.wait(.5)  # at most 2 Hz; no duplicate raw subscribers
                except Exception as e:io_error.append(str(e))
            io=threading.Thread(target=exchange,daemon=True,name='astra-feature-ipc');io.start()
            while time.monotonic()-started<30 and not self.stop_event.is_set():
                if self.stop_event.wait(max(0,1-(time.monotonic()-now))):break
                prev=cur;t=now;now=time.monotonic();cur=ticks()
                obs=observe(cpu_delta(prev,cur),now-t);check_camera()
                if io_error:raise ValueError(io_error[0])
                if p.poll() is not None:raise ValueError('optional inference worker exited')
                if now-last_result[0]>5:raise ValueError('model startup/inference timeout')
                with self.lock:
                    r['resources']=obs;r['events'].append(dict(at=time.time(),cpu=obs['cpu'],ram=obs['ram'],temperature=obs['temperature']))
                    r['events']=r['events'][-64:]
            completed=not self.stop_event.is_set() and r['frames']>=2
        except Exception as e:error=str(e)
        finally:
            self.stop_event.set()
            if p:
                if p.poll() is None:p.kill()
                p.wait(timeout=2)
            if io:io.join(timeout=2)
            with self.lock:
                r.update(state='READY' if completed else 'FAILED',ended_at=time.time(),
                         reason='Bounded test complete; manual verification required' if completed else error or 'Operator stopped; incomplete test')
                try:r['evidence_sha256']=self.save(r)
                except Exception as e:r.update(state='FAILED',reason='Evidence save failed: '+str(e))
                self.process=None;self.active=None


LAB=Lab()

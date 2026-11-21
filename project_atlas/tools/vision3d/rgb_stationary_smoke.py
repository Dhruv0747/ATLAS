"""Bounded Astra RGB V4L2 smoke test. No image/rosbag saving or ROS publishing.

Explicit stationary opt-in; child owns only freshly checked Astra /dev/video1.
Parent monitors unchanged admission limits and kills only its own child on failure.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import stationary_gate as gate
from bounded_process import OwnedPacer

STAGE=Path('/home/jetson/project-atlas-migration/astra-20261021')


def camera_identity():
    p=Path('/sys/class/video4linux/video1')
    if 'Astra Pro' not in (p/'name').read_text():raise RuntimeError('video1 is not verified Astra RGB')
    d=(p/'device').resolve()
    for a in d.parents:
        if (a/'idVendor').exists() and (a/'idProduct').exists():
            if ((a/'idVendor').read_text().strip(),(a/'idProduct').read_text().strip())!=('2bc5','0501'):
                raise RuntimeError('Astra RGB USB identity mismatch')
            return str(d)
    raise RuntimeError('RGB USB identity missing')


def child():
    identity=camera_identity()
    import cv2  # child only; no dependency/import cost in the safety supervisor
    cap=cv2.VideoCapture('/dev/video1',cv2.CAP_V4L2)
    try:
        if not cap.isOpened():raise RuntimeError('Astra RGB open failed')
        requested={'width':320,'height':240,'fps':15,'fourcc':'MJPG'}
        accepted={'fourcc':cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG')),
                  'width':cap.set(cv2.CAP_PROP_FRAME_WIDTH,320),'height':cap.set(cv2.CAP_PROP_FRAME_HEIGHT,240),
                  'fps':cap.set(cv2.CAP_PROP_FPS,15)}
        cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
        reported={k:cap.get(v) for k,v in [('width',cv2.CAP_PROP_FRAME_WIDTH),('height',cv2.CAP_PROP_FRAME_HEIGHT),('fps',cv2.CAP_PROP_FPS)]}
        print(json.dumps({'phase':'mode configured before read','accepted':accepted,'reported':reported}),file=sys.stderr,flush=True)
        if not all(accepted.values()) or any(abs(reported[k]-requested[k])>.01 for k in ('width','height','fps')):
            raise RuntimeError('Astra RGB mode negotiation did not match approved advertised mode')
        frames=[];times=[]
        for i in range(15):
            ok,frame=cap.read();t=time.monotonic()
            if not ok or frame is None:raise RuntimeError('RGB frame read failed')
            if frame.shape[:2]!=(240,320):raise RuntimeError('unexpected RGB dimensions')
            times.append(t);frames.append({'index':i,'width':frame.shape[1],'height':frame.shape[0],
                                         'encoding':'OpenCV decoded bgr8','min':int(frame.min()),'max':int(frame.max())})
        print(json.dumps({'kind':'REAL ASTRA RGB, no saved frames','identity':identity,'requested':requested,
                          'settings_accepted':accepted,'device_reported':reported,'frames':frames,
                          'observed_receive_hz':(len(times)-1)/(times[-1]-times[0]),
                          'largest_receive_gap_s':max(b-a for a,b in zip(times,times[1:])),
                          'source_timestamp':'UNKNOWN — OpenCV receive times are not sensor capture timestamps'}),flush=True)
    finally:cap.release()


def main():
    p=argparse.ArgumentParser();p.add_argument('--approve-stationary-rgb',action='store_true');p.add_argument('--child',action='store_true');p.add_argument('--paced',action='store_true');p.add_argument('--supported-mode',action='store_true');a=p.parse_args()
    if a.child:return child()
    if not a.approve_stationary_rgb:raise SystemExit('Explicit stationary opt-in required')
    target=STAGE/('rgb_stationary_supported_mode_result.json' if a.supported_mode else 'rgb_stationary_paced_result.json' if a.paced else 'rgb_stationary_result.json')
    if target.exists():raise SystemExit('Prior evidence preserved; no automatic repeat')
    result={'result':'BLOCKED','samples':[],'recording':False,'paced':a.paced};proc=None;pacer=None
    try:
        camera_identity();rows,before=gate.preflight();result.update(preflight=rows,units_before=before)
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        proc=subprocess.Popen([sys.executable,__file__,'--child'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,start_new_session=True)
        if a.paced:pacer=OwnedPacer(proc).start()
        start=time.monotonic();last=gate.ticks()
        while proc.poll() is None:
            if time.monotonic()-start>20:raise RuntimeError('20-second RGB deadline')
            if pacer and pacer.error:raise RuntimeError('test pacer failed: '+pacer.error)
            time.sleep(.5);now=gate.ticks();result['samples'].append(gate.check(gate.cpu_delta(last,now)));last=now
            if gate.services()!=before:raise RuntimeError('essential identity changed')
        stdout,stderr=proc.communicate(timeout=1);result['stderr']=stderr.decode(errors='replace')
        if proc.returncode!=0:raise RuntimeError('RGB child failed: '+result['stderr'][-800:])
        result['camera']=json.loads(stdout);result['result']='PASS'
    except Exception as e:
        result['failure']=str(e)
        if isinstance(e,gate.AdmissionError):result['failed_sample']=e.evidence
    finally:
        if pacer:pacer.close()
        if proc and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=2)
        if proc:
            stdout,stderr=proc.communicate(timeout=1)
            result['child_stdout']=stdout.decode(errors='replace')[-12000:];result['child_stderr']=stderr.decode(errors='replace')[-3000:]
        result['units_after']=gate.services();target.write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':main()

"""Single bounded passive SBUS session. No serial writes, ROS or actuator APIs."""
import sys,time,json,os,hashlib
from pathlib import Path
import serial
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from passive_evidence import Evidence
from atlas_yahboom_rc_report import parse_payload
from atlas_flysky_core import decode_sbus
import argparse
a=argparse.ArgumentParser(description=__doc__)
a.add_argument('--run-approved-session', action='store_true')
a.add_argument('--evidence-dir', type=Path, required=True)
args=a.parse_args()
if not args.run_approved_session: a.error('explicit separately approved session required')
d=args.evidence_dir
d.mkdir(parents=True, exist_ok=True)
evidence=Evidence(d)
with (d/'attempt-used').open('x') as f: f.write(str(time.time()))
p=serial.Serial(); p.port='COM26'; p.baudrate=115200; p.timeout=.1; p.dtr=False; p.rts=False
start=time.monotonic(); last_rc=start; last_save=0; buf=bytearray(); count=0; rc_count=0; rawhash=hashlib.sha256()
state={'status':'STARTING','writes':0,'rc_reports':0}; result='TIME_LIMIT'
try:
 p.open()
 print('LISTENING COM26; transmitter must remain OFF until instructed',flush=True)
 with (d/'raw.bin').open('wb') as raw,(d/'reports.jsonl').open('w') as log:
  while time.monotonic()-start<900:
   if (d/'stop.request').exists(): result='OPERATOR_STOP'; break
   b=p.read(min(max(p.in_waiting,1),4096)); now=time.monotonic()
   if b: raw.write(b);raw.flush();rawhash.update(b);buf.extend(b)
   while len(buf)>=4:
    if buf[:2]!=b'\xff\xfb':
     if count: raise RuntimeError('Unexpected unframed data or firmware restart')
     del buf[0];continue
    n=buf[2]+2
    if not 5<=n<=100: raise RuntimeError('Invalid packet length')
    if len(buf)<n: break
    f=bytes(buf[:n]);del buf[:n]
    if sum(f[2:-1])&255!=f[-1]: raise RuntimeError('Packet checksum failure')
    count+=1
    if f[3]==10 and any(f[4:10]): raise RuntimeError('Nonzero motion telemetry')
    if f[3]==225:
     r=parse_payload(f[4:-1]);rc_count+=1;last_rc=now
     decoded=decode_sbus(r.sbus_frame) if r.sbus_frame else None
     row=dict(monotonic=now,wall=time.time(),seq=r.seq,ever=r.ever,fresh=r.fresh,frame_lost=r.frame_lost,failsafe=r.failsafe,drive_disabled=r.drive_disabled,age_ms=r.age_ms,channels=list(decoded.raw[:10]) if decoded else None)
     log.write(json.dumps(row)+'\n');log.flush()
     state.update(row,status='MONITORING',rc_reports=rc_count)
   if now-last_rc>2: raise RuntimeError('RC report stream stale >2 seconds')
   if now-last_save>.5:
    state.update(packets=count,elapsed=now-start)
    evidence.save(state);last_save=now
except Exception as e:
 result='ABORTED';state['error']=str(e)
finally:
 p.close();state.update(status=result,port_closed=True,elapsed=time.monotonic()-start,rc_reports=rc_count,packets=count,raw_sha256=rawhash.hexdigest())
 try:
  evidence.save(state)
 except Exception as final_error:
  state['final_evidence_error']=str(final_error)
  print(json.dumps(state),flush=True)
  raise
 print(json.dumps(state),flush=True)

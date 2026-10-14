"""Private production-adapter test against a namespace-bound fake project root.

HTTP response and map/config identities are fixtures, never live safety approval.
Requires actual PID/network isolation and explicit fake-root marker.
"""
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from stage19_contract import require_isolation
from stage20_capture_integrity import inspect
from stage20_production_gate import IDENTITY_FILES,current_boot_id,PUBLIC_RUNTIME_FILES

require_isolation()
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--capsule',default='/tmp/replay/public_capsule_v3')
args=parser.parse_args()
root=Path('/home/jetson/project_atlas')
assert (root/'STAGE20_FAKE_ROOT').is_file(),'production root must never be used by fixture'
identity={}
for name in IDENTITY_FILES:
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'PRIVATE_FIXTURE_ONLY')
    identity[name]=hashlib.sha256(p.read_bytes()).hexdigest()
capture_root=root/'data/diagnostics/stage20_public';capture_root.mkdir(parents=True)
status={'ros':{'control_policy':{'age':.1,'value':{'source':'STOPPED','stop_latched':True}},
    'cmd_vel':{'age':.1,'value':{'lin':0.,'ang':0.}}},
    'system':{'cpu_percent':50,'ram_percent':60,'temp':'50 C'}}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data=json.dumps(status).encode();self.send_response(200);self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass
server=HTTPServer(('127.0.0.1',8088),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
approval=root/'fixture_approval.json'
runtime={}
for name in PUBLIC_RUNTIME_FILES:
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
    # Frozen fixture payload identities; no production source is altered.
    source=Path(args.capsule)/name
    __import__('shutil').copyfile(source,target)
    runtime[name]=hashlib.sha256(target.read_bytes()).hexdigest()
grant={'enabled':True,'owner_approved':True,'deployment_ready':True,'source_commit':'PRIVATE_FIXTURE',
    'mode':'read_only_partial_public','expires_after_boot_session':current_boot_id(),
    'grant_id':str(uuid.uuid4()),'identity':identity,'runtime_identity':runtime}
approval.write_text(json.dumps(grant));ready=root/'ready.json'
args=[sys.executable,str(root/'tools/stage20_public/tools/diagnostics/stage20_capture.py'),'--record','--public-only',
    '--root',str(capture_root),'--duration','120','--quota-mib','500',
    '--approval-config',str(approval),'--ready-file',str(ready)]
child=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:
    deadline=time.monotonic()+15
    while not ready.exists() and time.monotonic()<deadline:
        if child.poll() is not None:raise RuntimeError(child.communicate())
        time.sleep(.05)
    assert ready.exists();child.terminate();out,error=child.communicate(timeout=25)
    assert child.returncode==0,error
    result=json.loads(out.strip().splitlines()[-1]);e=json.loads((Path(result['path'])/'stage20_evidence.json').read_text())
    assert e['initial_state_history']=='NOT_CAPTURED' and e['missing_topics']
    assert inspect(result['path'])['complete']
    repeat=subprocess.run(args,capture_output=True,text=True,timeout=10)
    assert repeat.returncode!=0 and 'FileExistsError' in repeat.stderr
    assert len(list(capture_root.glob('capture_*')))==1
    report={'native_production_adapter':True,'namespace_fake_root':True,
        'grant_single_use':True,'graceful_operator_termination':True,
        'missing_topics_explicit':True,'private_state_unavailable_explicit':True,
        'production_approval_created':False,'production_changed':False}
    (root/'adapter_result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if child.poll() is None:child.kill();child.wait()
    server.shutdown()

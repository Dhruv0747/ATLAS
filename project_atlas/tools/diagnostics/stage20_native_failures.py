"""Private-namespace recorder failure tests. No source/control publishers."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
from stage19_contract import require_isolation
from stage20_capture_integrity import inspect

require_isolation()
root=Path('/tmp/replay')/('failures_'+uuid.uuid4().hex[:8]);root.mkdir()
script=Path('/tmp/replay/tools/diagnostics/stage20_capture.py')
def run(directory,duration=5,extra=()):
    return subprocess.run([sys.executable,str(script),'--record','--root',str(directory),
        '--duration',str(duration),*extra],capture_output=True,text=True,timeout=30)

# Missing sensors: finalization is possible but checkpoint remains explicitly incomplete.
r=run(root/'missing');assert r.returncode==0,r.stderr
result=json.loads(r.stdout.strip().splitlines()[-1])
e=json.loads((Path(result['path'])/'stage20_evidence.json').read_text())
assert e['complete_restorable_checkpoint'] is False and e['missing_topics']

# Existing logical quota is never deleted to make room, even when evidence is incomplete.
old=root/'quota'/'capture_keep';old.mkdir(parents=True)
p=old/'retained_evidence.bin'
with p.open('xb') as f:f.write(b'KEEP');f.truncate(70*1024*1024)
before=(p.stat().st_size,p.open('rb').read(4))
r=run(root/'quota',extra=('--quota-mib','64'))
assert r.returncode!=0 and 'quota' in r.stderr
assert (p.stat().st_size,p.open('rb').read(4))==before

# Kill only our own diagnostic child, detect incomplete evidence, restart uniquely.
ready=root/'crash_ready.json';directory=root/'crash'
child=subprocess.Popen([sys.executable,str(script),'--record','--root',str(directory),
    '--duration','60','--ready-file',str(ready)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    deadline=time.monotonic()+15
    while not ready.exists() and time.monotonic()<deadline:time.sleep(.1)
    assert ready.exists()
    child.kill();child.wait(timeout=10)
finally:
    if child.poll() is None:child.kill();child.wait()
previous=list(directory.glob('capture_*'));assert len(previous)==1
assert inspect(previous[0])['complete'] is False
saved={p.name:p.stat().st_size for p in previous[0].iterdir() if p.is_file()}
r=run(directory);assert r.returncode==0,r.stderr
assert len(list(directory.glob('capture_*')))==2
assert saved=={p.name:p.stat().st_size for p in previous[0].iterdir() if p.is_file()}
report={'missing_sensor_checkpoint_rejected':True,'quota_stop_preserves_evidence':True,
    'killed_capture_incomplete':True,'restart_preserves_crashed_capture':True,
    'production_changed':False,'scope':'diagnostic-only private namespace; no physical disk-full injection'}
(root/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

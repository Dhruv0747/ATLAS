"""New 30-second-mode failure cases in existing private namespace infrastructure."""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
from stage19_contract import require_isolation
from stage20_capture_integrity import inspect

require_isolation()
root=Path('/tmp/replay')/('stationary_failures_'+uuid.uuid4().hex[:8]);root.mkdir()
script=Path('/tmp/replay/tools/diagnostics/stage20_capture.py')
def command(folder,ready):
    return [sys.executable,str(script),'--record','--public-only','--stationary-30',
            '--duration','30','--root',str(folder),'--ready-file',str(ready)]
def wait_ready(child,path):
    deadline=time.monotonic()+12
    while not path.exists() and time.monotonic()<deadline:
        if child.poll() is not None:raise AssertionError(child.communicate())
        time.sleep(.05)
    assert path.exists()
results={}
start=time.monotonic()
missing=subprocess.run(command(root/'missing',root/'missing_ready.json'),capture_output=True,text=True,timeout=30)
assert missing.returncode==2,missing.stderr
bag=Path(json.loads(missing.stdout.strip().splitlines()[-1])['path'])
e=json.loads((bag/'stage20_evidence.json').read_text())
assert e['end_reason']=='sensor_preflight_failed' and not e['public_topic_window_complete'] and not e['counts']
assert not inspect(bag)['complete'] and inspect(bag)['finalization_integrity_verified']
results['missing_sensor']={'rejected':True,'wall_s':time.monotonic()-start,'zero_recorded_samples':True}
for mode in ('cancel','forced_timeout'):
    folder=root/mode;ready=root/(mode+'_ready.json')
    child=subprocess.Popen(command(folder,ready),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        wait_ready(child,ready)
        if mode=='cancel':child.terminate()
        else:child.kill() # Only this fixture child; simulate outer deadline escalation.
        stdout,stderr=child.communicate(timeout=15)
        assert child.poll() is not None
        if mode=='cancel':
            assert child.returncode==2,stderr
            bag=Path(json.loads(stdout.strip().splitlines()[-1])['path'])
            e=json.loads((bag/'stage20_evidence.json').read_text())
            assert e['end_reason']=='sigterm' and not e['public_topic_window_complete']
            assert not e['writer']['alive'] and not e['writer']['busy']
            results[mode]={'incomplete_reported':True,'writer_stopped':True,'flush_s':e['flush_elapsed_s']}
        else:
            bags=list(folder.glob('capture_*'))
            assert all(not inspect(b)['complete'] for b in bags)
            results[mode]={'process_reaped':True,'no_finalization_claim':True,'bags_preserved':len(bags)}
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=5)
(root/'result.json').write_text(json.dumps(results,indent=2))
print(json.dumps({'path':str(root),'tests':results,'production_changed':False}))

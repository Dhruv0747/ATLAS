"""Offline exact-live patch builder. Never writes production paths or runs services."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

BASELINE='5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a'

def apply_changes(live, changes, reverse=False):
    for old,new in (reversed(changes) if reverse else changes):
        if reverse:old,new=new,old
        if live.count(old)!=1:raise ValueError('ambiguous patch context')
        live=live.replace(old,new,1)
    return live

def prepare(source, output):
    raw=Path(source).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BASELINE:raise ValueError('live baseline drift')
    root=Path(__file__).resolve().parents[3]
    name='project_atlas/scripts/atlas_sensor_recovery.py'
    old=subprocess.check_output(['git','show','80f7c8a:'+name],cwd=root).decode().splitlines(True)
    new=subprocess.check_output(['git','show','2625327:'+name],cwd=root).decode().splitlines(True)
    changes=[]
    for tag,a,b,c,d in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
        if tag=='equal':continue
        # Common context from the old file; zero-width additions stay unambiguous.
        prefix=''.join(old[max(0,a-2):a]);suffix=''.join(old[b:b+2])
        changes.append((prefix+''.join(old[a:b])+suffix,prefix+''.join(new[c:d])+suffix))
    text=raw.decode();candidate=apply_changes(text,changes)
    if apply_changes(candidate,changes,True).encode()!=raw:raise ValueError('rollback mismatch')
    compile(candidate,'candidate','exec')
    output=Path(output);output.mkdir(mode=0o700)
    (output/'atlas_sensor_recovery.py').write_bytes(candidate.encode())
    (output/'snapshot.patch').write_text(''.join(difflib.unified_diff(text.splitlines(True),candidate.splitlines(True),fromfile='live/atlas_sensor_recovery.py',tofile='candidate/atlas_sensor_recovery.py')))
    for helper in ('existing_safety_snapshot.py','restart_safety_observer.py'):
        shutil.copyfile(Path(__file__).with_name(helper),output/helper)
    (output/'plan.json').write_text(json.dumps({'original_sha256':BASELINE,'output_disabled_by_default':True,'restart_authorized':False,'changes':changes},indent=2))
    (output/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(output.iterdir())))
    return candidate,changes

if __name__=='__main__':prepare(sys.argv[1],sys.argv[2])

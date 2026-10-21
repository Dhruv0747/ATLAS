"""Build a reviewable ZIP + SHA256 manifest locally. Does NOT install or contact Jetson."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[3]
FILES=['project_atlas/scripts/'+s for s in ('atlas_vision3d_core.py','atlas_vision3d_web.py','atlas_status_web.py','atlas_web_v2.py')]+[
    'project_atlas/web/v2/'+s for s in ('index.html','vision3d.html','vision3d.css','vision3d.js')]

def main():
    a=argparse.ArgumentParser();a.add_argument('--output',required=True);args=a.parse_args()
    out=Path(args.output).resolve()
    if out.exists():raise SystemExit('Refusing to overwrite existing package')
    out.parent.mkdir(parents=True,exist_ok=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    manifest={'source_commit':commit,'deployment_authorized':False,'recording':False,'topics':{},
              'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FILES}}
    with zipfile.ZipFile(out,'x',zipfile.ZIP_DEFLATED) as z:
        for n in FILES:z.writestr(n,(ROOT/n).read_bytes())
        z.writestr('manifest.json',json.dumps(manifest,indent=2))
    print(json.dumps({'package':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'manifest':manifest},indent=2))

if __name__=='__main__':main()

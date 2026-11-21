"""Prepare ONLY the reviewed three-file observer cleanup; never install/run it."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[3]
BASELINE={
 'scripts/atlas_vision3d_runtime.py':'1803eb363d3dcc95a607dd363248e58c8e3833b7be3abd7f3242d39ec0a20bcf',
 'tools/vision3d/stationary_gate.py':'880297606b92acfbbca982f5e4ea70e75cf1529f1f321ea9c97cda4b8ea4824f',
 'tools/vision3d/stationary_ros_probe.py':'6fd59f325b97e90df3b6e1902713f0a20155fb4a37581cc136357092bfea7262'}


def prepare(out):
    if out.exists():raise ValueError('preserve existing proposal')
    files={p:(ROOT/'project_atlas'/p).read_bytes() for p in BASELINE}
    for p,data in files.items():compile(data,p,'exec')
    if b'OwnedPacer' in files['scripts/atlas_vision3d_runtime.py']:
        raise ValueError('rejected startup pacing must not enter proposal')
    manifest={'scope':'observer/guard cleanup ONLY; camera reliability NOT passed',
              'production_approval_required':True,'restart_required':False,
              'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'expected_live_sha256':BASELINE,
              'candidate_sha256':{p:hashlib.sha256(data).hexdigest() for p,data in files.items()},
              'limits':{'cpu_percent':75,'ram_percent':80,'temperature_c':70},
              'recording':False,'autostart':False}
    payload={**files,'stage30-proposal-manifest.json':json.dumps(manifest,indent=2).encode()}
    with tarfile.open(out,'w:gz') as tar:
        for p,data in payload.items():
            info=tarfile.TarInfo(p);info.size=len(data);info.mode=0o644
            tar.addfile(info,io.BytesIO(data))
    print(json.dumps({'archive':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),**manifest},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();prepare(a.out)

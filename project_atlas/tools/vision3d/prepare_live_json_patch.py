"""Prepare an exact-live, whitespace-only JSON optimization OFFLINE."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import tarfile

BASE_SHA='98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79'
OLD=b'    body = json.dumps(clean_json(payload), indent=2, allow_nan=False).encode()'
NEW=b'    body = json.dumps(clean_json(payload), separators=(",", ":"), allow_nan=False).encode()'
def sha(b):return hashlib.sha256(b).hexdigest()
def prepare(b):
    if sha(b)!=BASE_SHA:raise ValueError('live baseline mismatch')
    if b.count(OLD)!=1:raise ValueError('unexpected response implementation')
    result=b.replace(OLD,NEW,1)
    assert result.replace(NEW,OLD,1)==b
    a,c=ast.parse(b),ast.parse(result)
    # Verify only the response implementation can differ; exact reverse bytes
    # above further constrain that difference to this one serialization call.
    for tree in (a,c):
        tree.body=[n for n in tree.body if not(isinstance(n,ast.FunctionDef) and n.name=='json_response')]
    assert ast.dump(a)==ast.dump(c)
    compile(result,'atlas_status_web.py','exec')
    return result
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('baseline',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=prepare(a.baseline.read_bytes());a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'atlas_status_web.py').write_bytes(result)
    package=a.output/'json-live.tar'
    with tarfile.open(package,'w',format=tarfile.USTAR_FORMAT) as t:
        info=tarfile.TarInfo('scripts/atlas_status_web.py');info.size=len(result);info.mode=0o644;info.mtime=0
        t.addfile(info,io.BytesIO(result))
    manifest={'baseline_sha256':BASE_SHA,'candidate_sha256':sha(result),'package_sha256':sha(package.read_bytes()),'deployed':False}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()

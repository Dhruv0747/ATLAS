"""Offline package builder only. No SSH, services, ROS or deployment operations."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import tarfile

BASE_SHA = 'fa62787f94c63b0103c666855cef0175b2c86e40022bf700beebe77e44adbd12'
REPLACEMENTS = (
    (b'            samples = self.update_times.setdefault(key, deque(maxlen=128))\n',
     b'            samples = self.update_times.get(key)\n'
     b'            if samples is None:\n'
     b'                samples = self.update_times[key] = deque(maxlen=128)\n'),
    (b'                samples = [stamp for stamp in times if now_mono - stamp < 10]\n',
     b'                # Monotonic timestamps are ordered under this same lock.\n'
     b'                # Expired prefixes can never become fresh again.\n'
     b'                while times and now_mono - times[0] >= 10:\n'
     b'                    times.popleft()\n'
     b'                samples = times\n'))


def sha(data): return hashlib.sha256(data).hexdigest()


def unrelated_ast(data):
    tree = ast.parse(data)
    for cls in tree.body:
        if isinstance(cls, ast.ClassDef) and cls.name == 'AtlasRosNode':
            cls.body = [n for n in cls.body if not
                        (isinstance(n, ast.FunctionDef) and n.name in ('snapshot','_set'))]
    return ast.dump(tree, include_attributes=False)


def prepare(original):
    if sha(original) != BASE_SHA:
        raise ValueError('Exact live baseline hash mismatch; do not patch')
    candidate = original
    for old, new in REPLACEMENTS:
        if candidate.count(old) != 1:
            raise ValueError('Expected exactly one edit site')
        candidate = candidate.replace(old, new, 1)
    if unrelated_ast(original) != unrelated_ast(candidate):
        raise ValueError('Unrelated AST changed')
    restored = candidate
    for old, new in reversed(REPLACEMENTS):
        restored = restored.replace(new, old, 1)
    if restored != original:
        raise ValueError('Byte-exact reverse patch failed')
    compile(candidate, 'atlas_status_web.py', 'exec')
    return candidate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    candidate=prepare(args.baseline.read_bytes())
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'atlas_status_web.py').write_bytes(candidate)
    package=args.output/'snapshot-live.tar'
    with tarfile.open(package,'w',format=tarfile.USTAR_FORMAT) as archive:
        info=tarfile.TarInfo('scripts/atlas_status_web.py')
        info.size=len(candidate);info.mode=0o644;info.mtime=0
        archive.addfile(info,io.BytesIO(candidate))
    manifest=dict(baseline_sha256=BASE_SHA,candidate_sha256=sha(candidate),
                  package_sha256=sha(package.read_bytes()),runtime_files=['scripts/atlas_status_web.py'],
                  deployed=False)
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__': main()

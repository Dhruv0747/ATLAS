"""Relocate hard-coded exported target paths in PRIVATE copied CMake configs."""
import hashlib
import json
from pathlib import Path
ROOT=Path('/root/atlas-stage29');TARGET=ROOT/'target'


def main():
    changes=[]
    for f in list((TARGET/'opt/ros/humble/share').rglob('*.cmake'))+list((TARGET/'usr/lib').rglob('*.cmake'))+list((TARGET/'usr/share').rglob('*.cmake')):
        before=f.read_text();after=before
        for prefix in ('/usr/lib/aarch64-linux-gnu/','/usr/include/','/usr/share/'):
            # Idempotent: do not relocate an already private absolute path twice.
            import re
            after=re.sub(r'(?<![A-Za-z0-9_/.-])'+re.escape(prefix),str(TARGET)+prefix,after)
        if after!=before:
            f.write_text(after);changes.append({'path':str(f.relative_to(TARGET)),
                'before_sha256':hashlib.sha256(before.encode()).hexdigest(),
                'after_sha256':hashlib.sha256(after.encode()).hexdigest()})
    evidence=ROOT/'cross-cmake-relocations.json'
    old=json.loads(evidence.read_text()) if evidence.exists() else []
    evidence.write_text(json.dumps(old+changes,indent=2));print('private CMake path relocations',len(changes))


if __name__=='__main__':main()

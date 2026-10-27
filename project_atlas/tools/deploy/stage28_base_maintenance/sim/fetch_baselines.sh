#!/usr/bin/env bash
# SIMULATION ONLY: materialise the exact live baselines (from git blobs + the committed fixture) into $1.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); OUT=$1; mkdir -p "$OUT"
python3 - "$HERE" "$OUT" <<'PY'
import json, subprocess, sys, shutil, pathlib
here, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
spec = json.loads((here / 'baselines.json').read_text())
for name, blob in spec['git_blobs'].items():
    (out / name).write_bytes(subprocess.check_output(['git', '-C', str(here), 'cat-file', 'blob', blob]))
for name, rel in spec['fixture'].items():
    shutil.copy(here / rel, out / name)
man = json.loads((here.parent / 'MANIFEST.json').read_text())
import hashlib
want = {**{k: v['baseline_sha256'] for k, v in man['modified'].items()}, **man['must_remain']}
for name, digest in want.items():
    got = hashlib.sha256((out / name).read_bytes()).hexdigest()
    assert got == digest, (name, got)
print('baselines verified:', ', '.join(sorted(want)))
PY

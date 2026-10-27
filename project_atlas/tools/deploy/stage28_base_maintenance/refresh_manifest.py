#!/usr/bin/env python3
"""Offline: recompute MANIFEST.json hashes from the repository files and the git/fixture baselines.

Baselines come from sim/fetch_baselines.sh (git blobs + committed yahboom_base fixture), so the candidate hashes are
reproducible without access to the Jetson. On the Jetson the deployer rebuilds the candidates from the LIVE files
and refuses unless they match these hashes exactly.
"""
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / 'scripts'
INSERTS = {'insert_recovery_base_hold.py': HERE, 'insert_rc_hooks.py': HERE.parent / 'stage28_yahboom_rc',
           'insert_rosmaster_rc.py': HERE.parent / 'stage28_yahboom_rc'}
h = lambda b: hashlib.sha256(b).hexdigest()
m = json.loads((HERE / 'MANIFEST.json').read_text())
with tempfile.TemporaryDirectory() as d:
    subprocess.run([str(HERE / 'sim/fetch_baselines.sh'), d], check=True, capture_output=True)
    for name, spec in m['modified'].items():
        p = Path(d) / name
        assert h(p.read_bytes()) == spec['baseline_sha256'], name
        subprocess.run([sys.executable, '-I', str(INSERTS[spec['insert']] / spec['insert']), str(p)], check=True,
                       capture_output=True)
        spec['candidate_sha256'] = h(p.read_bytes())
for name, spec in m['added'].items():
    spec['sha256'] = h((SCRIPTS / name).read_bytes())
(HERE / 'MANIFEST.json').write_text(json.dumps(m, indent=1) + '\n')
print(json.dumps({k: v['candidate_sha256'][:12] for k, v in m['modified'].items()} |
                 {k: v['sha256'][:12] for k, v in m['added'].items()}))

#!/usr/bin/env python3
"""Rehearse staged packages against a copy of the deployed baseline tree (never the Jetson).

For each install order: export project_atlas/ at the baseline commit into a temp ROOT, run each
stage's install.sh, check the combined result equals the expected file at --expect, then run every
ROLLBACK.sh in reverse and check the tree is byte-identical to the baseline again.
Usage: check_packages.py <pkg-dir> <baseline-commit> <expect-commit> <stage> [<stage> ...]
"""
import filecmp, hashlib, itertools, os, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(root.rglob('*')):
        if p.is_file() and 'data/backups' not in str(p.relative_to(root)) and '__pycache__' not in str(p):
            h.update(str(p.relative_to(root)).encode()); h.update(p.read_bytes())
    return h.hexdigest()


def export(commit, dest):
    data = subprocess.run(['git', '-C', str(REPO), 'archive', commit, 'project_atlas/scripts', 'project_atlas/config'],
                          check=True, capture_output=True).stdout
    subprocess.run(['tar', '-x', '--strip-components=1', '-C', str(dest)], input=data, check=True)


def main():
    pkg, base, expect, stages = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4:]
    ok = True
    for order in itertools.permutations(stages):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'project_atlas'; root.mkdir(); export(base, root); (root / 'data/backups').mkdir(parents=True)
            before = tree_hash(root)
            env = {**os.environ, 'ATLAS_ROOT': str(root)}
            for st in order:
                r = subprocess.run(['bash', str(pkg / st / 'install.sh')], env=env, capture_output=True, text=True)
                if r.returncode:
                    print('FAIL install', order, st, r.stdout[-400:], r.stderr[-400:]); ok = False; break
            else:
                with tempfile.TemporaryDirectory() as e:
                    exp = Path(e); export(expect, exp)
                    for rel in ('scripts/atlas_status_web.py', 'scripts/atlas_visual_cloud_agent.py',
                                'scripts/atlas_visual_cloud_server.py', 'scripts/atlas_visual_cloud_core.py', 'config/atlas_visual_cloud.json'):
                        changed = any((pkg / st / 'MANIFEST').read_text().find(' ' + rel + ' ') >= 0 for st in order)
                        if changed and not filecmp.cmp(root / rel, exp / rel, shallow=False):
                            print('FAIL result', order, rel); ok = False
                for bk in sorted((root / 'data/backups').iterdir(), reverse=True):   # newest first (ns timestamps)
                    r = subprocess.run(['bash', str(bk / 'ROLLBACK.sh')], env=env, capture_output=True, text=True)
                    if r.returncode:
                        print('FAIL rollback', bk.name, r.stderr[-300:]); ok = False
                after = tree_hash(root)
                print(('PASS' if after == before else 'FAIL rollback-identity'), ' -> '.join(order))
                ok = ok and after == before
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()

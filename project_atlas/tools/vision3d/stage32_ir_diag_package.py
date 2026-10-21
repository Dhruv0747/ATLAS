"""Stage32 takeover: build the NO-RESTART IR diagnostic package (offline; never installs).

Why this package differs from the rolled-back three-file candidate (1e6704ad...):
  * It ships ONLY the instrumented driver library, which is loaded by the per-session driver process. Nothing that runs
    inside rover-status-web changes, so no rover-status-web restart is needed (the restart transient, not the candidate,
    is what the 95.64% post-restart sample measured; see ATLAS_STAGE32_ASTRA_INFRARED_INTEGRATION.md section 20).
  * It also ships the isolated runtime's manifest.json with the ONE libastra_camera.so entry updated (sha256, size).
    The Vision Lab worker hash-checks all 458 runtime files before opening the camera; the earlier candidate replaced the
    library without updating that entry, so every session (Depth included) would have been refused with
    "isolated runtime integrity failure" even if the install had been accepted.
Receiver/API/canvas boundaries are observed with the already-deployed web (streams.ir received/rejected counters) and the
session script (raw fetch + canvas read), so the candidate web.py/vision3d.js are intentionally NOT included.

usage: python3 stage32_ir_diag_package.py CANDIDATE_TAR(1e6704ad...) LIVE_RUNTIME_MANIFEST(c1a6d1c0...) OUT_DIR
"""
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

CANDIDATE_TAR_SHA = '1e6704adb163747328b1a9f37dfd0053e713fb8d16aa09afbb1ae7744e5a3473'
LIB = 'lib/libastra_camera.so'
LIB_BASE = ('6ae876010c824be97d2545996f897e40e07e0c97fa7a45694f96f342cf6e22a6', 2825416)
LIB_CAND = ('8609f2641d181fb6fccda60e84f83d4c5d399b673dc65b27b723490a8b24cab9', 2835096)
RT_MANIFEST = 'manifest.json'
RT_MANIFEST_BASE = 'c1a6d1c02f1620850cd160022eb0d10dd269a1152f91c5436a0ada82e4e17dfb'
RUNTIME_FILES = 458


def sha(b):
    return hashlib.sha256(b).hexdigest()


def edit_manifest(text):
    """Change exactly the libastra_camera.so entry; every other byte stays identical."""
    old = '"path": "lib/libastra_camera.so",\n      "sha256": "%s",\n      "size": %d\n' % LIB_BASE
    new = '"path": "lib/libastra_camera.so",\n      "sha256": "%s",\n      "size": %d\n' % LIB_CAND
    if text.count(old) != 1:
        raise ValueError('runtime manifest entry for libastra_camera.so not found exactly once')
    out = text.replace(old, new)
    doc = json.loads(out)
    if len(doc['files']) != RUNTIME_FILES:
        raise ValueError('runtime manifest file count changed')
    entries = [f for f in doc['files'] if f['path'] == LIB]
    if entries != [{'path': LIB, 'sha256': LIB_CAND[0], 'size': LIB_CAND[1]}]:
        raise ValueError('edited entry wrong')
    before = json.loads(text)
    diff = [(a, b) for a, b in zip(before['files'], doc['files']) if a != b]
    if len(diff) != 1 or {k: v for k, v in before.items() if k != 'files'} != {k: v for k, v in doc.items() if k != 'files'}:
        raise ValueError('more than one manifest entry would change')
    return out


def build(candidate_tar, live_manifest, out_dir):
    tar_bytes = Path(candidate_tar).read_bytes()
    if sha(tar_bytes) != CANDIDATE_TAR_SHA:
        raise ValueError('candidate archive hash mismatch')
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as t:
        lib = t.extractfile('payload/' + LIB).read()
    if (sha(lib), len(lib)) != LIB_CAND:
        raise ValueError('candidate library hash/size mismatch')
    text = Path(live_manifest).read_text()
    if sha(text.encode()) != RT_MANIFEST_BASE:
        raise ValueError('live runtime manifest is not the verified baseline')
    new_manifest = edit_manifest(text).encode()
    out = Path(out_dir)
    (out / 'payload/lib').mkdir(parents=True, exist_ok=False)
    (out / 'payload' / LIB).write_bytes(lib)
    (out / 'payload' / RT_MANIFEST).write_bytes(new_manifest)
    meta = {'purpose': 'IR zero-frame diagnostic driver counters; NO rover-status-web restart',
            'source_candidate_archive': CANDIDATE_TAR_SHA, 'vendor_pin': 'f7e71d9ce806e788cb48d8580aac2c778fba4214',
            'vendor_diff_sha256': '973eb10f839856406d03ce0c95d884b86f0f71cf7a9d41159a4613c5f11064f5',
            'runtime_root': '/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2',
            'files': {LIB: {'baseline': LIB_BASE[0], 'candidate': LIB_CAND[0], 'bytes': LIB_CAND[1]},
                      RT_MANIFEST: {'baseline': RT_MANIFEST_BASE, 'candidate': sha(new_manifest), 'bytes': len(new_manifest)}},
            'restart_required': False, 'production_process_files_changed': [],
            'deployment_authorized': False, 'activation_authorized': False}
    (out / 'package.json').write_text(json.dumps(meta, indent=2) + '\n')
    return meta


if __name__ == '__main__':
    print(json.dumps(build(*sys.argv[1:4]), indent=2))

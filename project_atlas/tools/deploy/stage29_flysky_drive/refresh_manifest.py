#!/usr/bin/env python3
"""Rebuild MANIFEST.json for Stage 29 Stage A from the committed live baselines and repo sources (deterministic)."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import insert_flysky_mux          # noqa: E402
import insert_status_web_hooks    # noqa: E402
import insert_controller_input_hooks   # noqa: E402

h = lambda b: hashlib.sha256(b).hexdigest()
BASE_MUX = HERE / 'baseline/atlas_cmd_vel_mux.py.live-0d959286'
BASE_WEB = HERE / 'baseline/atlas_status_web.py.live-4ab16214'
# Live copies (hashes read on the rover 2026-10-29; equal to repo commits a97178c / 615b846).
BASE_WEB_V2 = HERE / 'baseline/atlas_web_v2.py.live-4893d1f6'
BASE_CSS = HERE / 'baseline/flysky.css.live-34d3e404'
LIVE_WEB_V2 = h(BASE_WEB_V2.read_bytes())
LIVE_FLYSKY_CSS = h(BASE_CSS.read_bytes())
assert LIVE_WEB_V2.startswith('4893d1f65fb3') and LIVE_FLYSKY_CSS.startswith('34d3e40423c9')


def src(rel):
    return {'source': rel, 'candidate_sha256': h((REPO / rel).read_bytes())}


# A3 (web step) page files exactly as deployed 2026-10-29; the 'view' step replaces them. Pinned so the web step keeps
# describing what A3 installed even after the repo moves on.
A3 = {'web/v2/flysky-drive.html': 'baseline/flysky-drive.html.a3-89f017a9', 'web/v2/flysky-drive.js': 'baseline/flysky-drive.js.a3-b2d0c83f',
      'web/v2/flysky.css': 'baseline/flysky.css.a3-e5852855'}
A3_STATUS_WEB = insert_status_web_hooks.apply(BASE_WEB.read_text())


def pinned(rel):
    path = HERE / A3[rel]
    return {'source': str(path.relative_to(REPO)), 'candidate_sha256': h(path.read_bytes())}


def build():
    return {
        'stage': '29 Stage A: FlySky driving integration deployed with the gate OFF (+ view: dual-controller dashboard)',
        'gate': 'ATLAS_FLYSKY_DRIVE_ENABLED must be absent or 0 everywhere; config reviewed_by_owner false',
        'order': ['mux', 'teleop', 'web', 'view'],
        'required_for_driving': ['mux', 'teleop', 'web'],
        'steps': {
            'mux': {'unit': 'atlas-cmd-vel-mux.service', 'files': {
                'scripts/atlas_cmd_vel_mux.py': {'kind': 'patch', 'patcher': 'insert_flysky_mux.py',
                                                 'baseline_sha256': h(BASE_MUX.read_bytes()),
                                                 'candidate_sha256': h(insert_flysky_mux.apply(BASE_MUX.read_text()).encode())}}},
            'teleop': {'unit': 'atlas-flysky-teleop.service', 'files': {
                'scripts/atlas_flysky_drive_core.py': {'kind': 'new', **src('scripts/atlas_flysky_drive_core.py')},
                'scripts/atlas_flysky_teleop.py': {'kind': 'new', **src('scripts/atlas_flysky_teleop.py')},
                'config/atlas_flysky_drive.json': {'kind': 'new', **src('config/atlas_flysky_drive.json')},
                'systemd/atlas-flysky-teleop.service': {'kind': 'unit', **src('systemd/atlas-flysky-teleop.service')}}},
            'web': {'unit': 'rover-status-web.service', 'files': {
                'scripts/atlas_status_web.py': {'kind': 'patch', 'patcher': 'insert_status_web_hooks.py',
                                                'baseline_sha256': h(BASE_WEB.read_bytes()),
                                                'candidate_sha256': h(insert_status_web_hooks.apply(BASE_WEB.read_text()).encode())},
                'scripts/atlas_web_v2.py': {'kind': 'replace', 'baseline_sha256': LIVE_WEB_V2, **src('scripts/atlas_web_v2.py')},
                'web/v2/flysky.css': {'kind': 'replace', 'baseline_sha256': LIVE_FLYSKY_CSS, **pinned('web/v2/flysky.css')},
                'scripts/atlas_manual_controller_web.py': {'kind': 'new', **src('scripts/atlas_manual_controller_web.py')},
                'web/v2/flysky-drive.html': {'kind': 'new', **pinned('web/v2/flysky-drive.html')},
                'web/v2/flysky-drive.js': {'kind': 'new', **pinned('web/v2/flysky-drive.js')}}},
            # Dual-controller dashboard (UI only): read-only live Xbox input + controller visualisation. Chained on A3:
            # every baseline below is the A3 candidate. Not required for driving; it cannot enable or select anything.
            'view': {'unit': 'rover-status-web.service', 'supersedes': 'web', 'files': {
                'scripts/atlas_status_web.py': {'kind': 'patch', 'patcher': 'insert_controller_input_hooks.py',
                                                'baseline_sha256': h(A3_STATUS_WEB.encode()),
                                                'candidate_sha256': h(insert_controller_input_hooks.apply(A3_STATUS_WEB).encode())},
                'scripts/atlas_controller_input_web.py': {'kind': 'new', **src('scripts/atlas_controller_input_web.py')},
                'web/v2/controller-map.js': {'kind': 'new', **src('web/v2/controller-map.js')},
                'web/v2/controller-viz.js': {'kind': 'new', **src('web/v2/controller-viz.js')},
                'web/v2/assets/xbox360-controller-black.webp': {'kind': 'new', **src('web/v2/assets/xbox360-controller-black.webp')},
                'web/v2/assets/flysky-fs-i6s-front.webp': {'kind': 'new', **src('web/v2/assets/flysky-fs-i6s-front.webp')},
                'web/v2/assets/CONTROLLER-IMAGES.txt': {'kind': 'new', **src('web/v2/assets/CONTROLLER-IMAGES.txt')},
                'web/v2/flysky-drive.html': {'kind': 'replace', 'baseline_sha256': pinned('web/v2/flysky-drive.html')['candidate_sha256'],
                                             **src('web/v2/flysky-drive.html')},
                'web/v2/flysky-drive.js': {'kind': 'replace', 'baseline_sha256': pinned('web/v2/flysky-drive.js')['candidate_sha256'],
                                           **src('web/v2/flysky-drive.js')},
                'web/v2/flysky.css': {'kind': 'replace', 'baseline_sha256': pinned('web/v2/flysky.css')['candidate_sha256'],
                                      **src('web/v2/flysky.css')}}},
        },
        'unchanged_required': {'scripts/atlas_flysky_core.py': '3e4b379e', 'scripts/atlas_remote_stop.py': '1a44fb37a532',
                               'firmware': 'V3.6.161, no flash'},
    }


if __name__ == '__main__':
    m = build()
    out = json.dumps(m, indent=2) + '\n'
    if '--check' in sys.argv:
        sys.exit(0 if (HERE / 'MANIFEST.json').read_text() == out else 1)
    (HERE / 'MANIFEST.json').write_text(out)
    print('MANIFEST.json written')

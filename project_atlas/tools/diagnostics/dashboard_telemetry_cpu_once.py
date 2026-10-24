"""Owner-run Python GIL capture of ONE fixed service; never changes production."""
import hashlib
from pathlib import Path
import sys
import types

HELPER_SHA = '2b0cd1ee5872070ee21c93780445e8296b9f1a2574b84ad3e7375e98bc959e18'
STAGE = Path('/home/jetson/project-atlas-migration/dashboard-telemetry-python-20261024')
TARGETS = {
    'dashboard': ('rover-status-web', 'scripts/atlas_status_web.py'),
    'telemetry': ('rover-base-telemetry.service', 'scripts/yahboom_base.py'),
}
HASHES = {
    'scripts/atlas_status_web.py': 'acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439',
    'scripts/yahboom_base.py': 'c551be0053a43755578fc8e60b534338818a690411322c63a293376e6e560141',
    'scripts/atlas_voice_companion.py': 'a88ff78df1ae2dded4f9984cdcf5e94d5335d1d12c77fd9c9131219725298870',
    'scripts/atlas_safety_status.py': '94f52bcc1d535378adf6d4f54f6d29fc52f0cd7b12b11a8da0df39117f510bd4',
}
UNITS = ('atlas-camera.service', 'rover-base-telemetry.service',
         'atlas-cmd-vel-mux.service', 'atlas-ekf.service', 'atlas-localization.service',
         'atlas-lidar.service', 'atlas-voice-companion.service',
         'atlas-safety-status.service', 'atlas-localization-monitor.service',
         'atlas-mission-control.service', 'rover-status-web')


def parse(arguments):
    if len(arguments) != 2 or arguments[0] not in TARGETS or arguments[1] != '--diagnostic-cpu-report-only':
        raise ValueError('Require dashboard|telemetry and --diagnostic-cpu-report-only')
    return arguments[0]


def load_helper(path, target):
    unit, script = TARGETS[target]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != HELPER_SHA:
        raise RuntimeError('Reviewed helper hash mismatch')
    source = raw.decode()
    anchor = '        import stationary_gate as G'
    if source.count(anchor) != 1:
        raise RuntimeError('Unexpected helper structure')
    source = source.replace(anchor, anchor + '\n        G.UNITS = tuple(dict.fromkeys(G.UNITS + EXTRA_UNITS))')
    module = types.ModuleType('fixed_python_profile_helper')
    exec(compile(source, str(path), 'exec'), module.__dict__)
    module.EXTRA_UNITS = UNITS
    module.STAGE = STAGE
    module.TARGET_UNIT, module.TARGET_SCRIPT = unit, script
    module.HASHES.update(HASHES)
    return module


def main():
    target = parse(sys.argv[1:])
    module = load_helper(Path(__file__).with_name('native_dashboard_cpu_once.py'), target)
    sys.argv = [sys.argv[0], '--python-gil', '--diagnostic-cpu-report-only']
    return module.main()


if __name__ == '__main__':
    sys.exit(main())

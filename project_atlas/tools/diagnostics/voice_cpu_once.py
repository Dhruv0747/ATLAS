#!/usr/bin/env python3
"""Owner-run bounded voice GIL profile; no recording of audio or local variables.

Uses the reviewed shared observer, with current production hashes and a fixed
voice service target. Only the explicit owner diagnostic CPU exception is accepted.
"""
import hashlib
from pathlib import Path
import sys
import types

HELPER_SHA = '2b0cd1ee5872070ee21c93780445e8296b9f1a2574b84ad3e7375e98bc959e18'
STAGE = Path('/home/jetson/project-atlas-migration/voice-cpu-20261023')
VOICE_SHA = '37f275ddb5e259466b909b0da2654fdaaf8a06b06cf02d969813c8affc0c2f72'

def load_helper(path):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=HELPER_SHA:
        raise RuntimeError('reviewed profiling helper hash mismatch')
    module=types.ModuleType('atlas_voice_profile_helper')
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module

def configure(module):
    module.STAGE=STAGE
    module.TARGET_UNIT='atlas-voice-companion.service'
    module.TARGET_SCRIPT='scripts/atlas_voice_companion.py'
    module.HASHES=dict(module.HASHES)
    module.HASHES.update({
        'scripts/atlas_voice_companion.py':VOICE_SHA,
        'scripts/atlas_status_web.py':'acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439',
        'scripts/atlas_dashboard_executor.py':'2b6ceeae09ec63cafd8a93084ba086c0e5145661f56a245966de4eed389f11ab',
        'scripts/atlas_dashboard_executor_impl.py':'543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1',
    })
    return module

def main():
    arguments=sys.argv[1:]
    if arguments not in ([],['--diagnostic-cpu-report-only']):
        raise SystemExit('Only the explicit owner diagnostic CPU exception is allowed')
    module=configure(load_helper(Path(__file__).with_name('native_dashboard_cpu_once.py')))
    # Exception affects this observer only, never production/camera thresholds.
    sys.argv=[sys.argv[0],'--python-gil',*arguments]
    return module.main()

if __name__=='__main__': sys.exit(main())

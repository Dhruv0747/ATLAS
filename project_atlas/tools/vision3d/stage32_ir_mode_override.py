"""Stage32 D2: TEMPORARY IR-mode override for one diagnostic session (640x480@30 instead of 320x240@30).

  python3 stage32_ir_mode_override.py check
  OWNER_APPROVED=yes python3 stage32_ir_mode_override.py apply     # writes the override, keeps a verified backup
  OWNER_APPROVED=yes python3 stage32_ir_mode_override.py restore   # restores the exact verified runtime file

Why this file: the Vision Lab worker is a fresh `python3 atlas_vision3d_runtime.py --worker MODE` process for every
Start and builds the driver arguments from the file on disk; rover-status-web only validates the mode name with its
already-imported copy. So editing one literal changes the NEXT session's IR resolution without restarting anything.
Exactly one line changes; depth/RGB arguments, guards, limits and every other byte stay identical (checked by hash).
"""
import hashlib
import json
import os
import py_compile
import shutil
import sys
from pathlib import Path

TARGET = Path(os.environ.get('ATLAS_RUNTIME_FILE', '/home/jetson/project_atlas/scripts/atlas_vision3d_runtime.py'))
STATE = Path(os.environ.get('ATLAS_IR_DIAG_STATE', '/home/jetson/project-atlas-migration/stage32-takeover-ir-diag')) / 'd2'
BASE_SHA = '454dd25fd0e5bafbb25b63983af865cca78a01354547e4129c2e2016b8023151'
OLD = b"values.update(ir_width='320',ir_height='240',ir_fps='30')"
NEW = b"values.update(ir_width='640',ir_height='480',ir_fps='30')"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def override_bytes(data):
    if sha(data) != BASE_SHA or data.count(OLD) != 1:
        raise ValueError('runtime file is not the verified Stage32 baseline')
    return data.replace(OLD, NEW)


def main(cmd):
    data = TARGET.read_bytes()
    state = 'baseline' if sha(data) == BASE_SHA else 'override' if data.count(NEW) == 1 and sha(data.replace(NEW, OLD)) == BASE_SHA else 'UNKNOWN'
    out = {'cmd': cmd, 'state_before': state, 'sha_before': sha(data)}
    if cmd == 'check':
        return out
    if os.environ.get('OWNER_APPROVED') != 'yes':
        raise SystemExit('REFUSE: set OWNER_APPROVED=yes only after the owner approved this exact step')
    STATE.mkdir(parents=True, exist_ok=True)
    backup = STATE / 'atlas_vision3d_runtime.py.baseline'
    tmp = TARGET.with_name(TARGET.name + '.s32d2.tmp')
    if cmd == 'apply':
        if state != 'baseline':
            raise SystemExit('REFUSE: runtime file is %s' % state)
        shutil.copy2(TARGET, backup)
        if sha(backup.read_bytes()) != BASE_SHA:
            raise RuntimeError('backup verification failed')
        new = override_bytes(data)
        tmp.write_bytes(new); shutil.copymode(TARGET, tmp)
        py_compile.compile(str(tmp), doraise=True, cfile=str(STATE / 'compile_check.pyc'))
        os.replace(tmp, TARGET)
    elif cmd == 'restore':
        if state == 'baseline':
            out['note'] = 'already baseline'
        elif state != 'override' or sha(backup.read_bytes()) != BASE_SHA:
            raise SystemExit('REFUSE: unexpected state %s or bad backup' % state)
        else:
            shutil.copy2(backup, tmp); os.replace(tmp, TARGET)
    after = TARGET.read_bytes()
    out.update(sha_after=sha(after), state_after='baseline' if sha(after) == BASE_SHA else 'override' if cmd == 'apply' else 'UNKNOWN',
               changed_lines=sum(1 for a, b in zip(data.splitlines(), after.splitlines()) if a != b))
    if cmd == 'restore' and sha(after) != BASE_SHA:
        raise RuntimeError('restore did not reproduce the baseline')
    (STATE / ('%s.json' % cmd)).write_text(json.dumps(out, indent=2))
    return out


if __name__ == '__main__':
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else 'check'), indent=2))

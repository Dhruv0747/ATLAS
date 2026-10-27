"""Immutable PC-only status snapshots; no hardware access."""
import json
import os
import time
from pathlib import Path


class Evidence:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.sequence = 0

    def save(self, state):
        # Readers can keep old files open on Windows: never replace those files.
        self.sequence += 1
        target = self.directory / ('status-%06d.json' % self.sequence)
        temp = target.with_suffix('.pending')
        with temp.open('x', encoding='utf-8') as stream:
            json.dump(dict(state, observed_wall=time.time()), stream, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        # Exclusive session ownership ensures target cannot already exist.
        if target.exists():
            raise FileExistsError(target)
        os.rename(temp, target)
        return target


def read_status(directory, now=None, max_age=2.0):
    """Fail closed; never promote an old snapshot after corrupt/missing evidence."""
    directory = Path(directory)
    try:
        # Also recognizes terminal evidence left by the original monitor.
        terminal = directory / 'result.json'
        if terminal.exists():
            value = json.loads(terminal.read_text(encoding='utf-8'))
            return dict(value, live=False)
        paths = sorted(directory.glob('status-*.json'))
        if not paths:
            raise ValueError('no committed status')
        value = json.loads(paths[-1].read_text(encoding='utf-8'))
        age = (time.time() if now is None else now) - value['observed_wall']
        live = (value['status'] == 'MONITORING' and value.get('drive_disabled') is True
                and value.get('port_closed') is not True and 0 <= age <= max_age)
        return dict(value, live=live, evidence_age_seconds=age)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {'status': 'EVIDENCE_UNAVAILABLE', 'live': False, 'error': str(error)}

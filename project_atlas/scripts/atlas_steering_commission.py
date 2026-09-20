"""Steering-only lease, called exclusively by the existing motor owner.

No serial access. Expiry freezes targets and inhibits traction until explicit
exit. Saving is explicit; defaults are never written by entering a session.
"""
import copy
import json
import os
from pathlib import Path
import time
import threading


class SteeringCommission:
    def __init__(self, path, defaults):
        self.path = Path(path)
        self.envelope = copy.deepcopy(defaults)
        # Supervised front-left calibration extension approved 2026-09-20.
        # This does NOT change the operating endpoint until explicitly saved.
        self.envelope['front']['left'] = 126
        # Supervised rear-right extension approved 2026-09-20.  Expand only
        # five servo degrees at a time and require operator visual confirmation
        # before the operating endpoint can be saved.
        self.envelope['rear']['right'] = 59
        self.saved = copy.deepcopy(defaults)
        self.error = ''
        if self.path.exists():
            try:
                candidate = json.loads(self.path.read_text())['steering']
                self.validate(candidate)
                self.saved = candidate
            except (OSError, ValueError, KeyError, TypeError):
                self.error = 'Invalid saved calibration; defaults retained, commissioning required'
        self.draft = copy.deepcopy(self.saved)
        self.targets = {s: self.saved[s]['center'] for s in self.saved}
        self.locked = False
        self.token = None
        self.deadline = 0
        self.sequence = -1
        self.result = 'IDLE'
        self.saving = False

    def validate(self, cfg):
        for side in ('front', 'rear'):
            c, e = cfg[side], self.envelope[side]
            if any(type(c[k]) is not int for k in ('center', 'left', 'right')):
                raise ValueError('Integer servo degrees required')
            lo, hi = sorted((e['left'], e['right']))
            if not lo <= c['right'] < c['center'] < c['left'] <= hi:
                raise ValueError('Require right < centre < left within existing envelope')

    def freeze(self, applied, reason):
        if self.locked:
            self.targets = dict(applied)
            self.token = None
            self.result = reason + '; traction inhibited; re-enter or exit explicitly'

    def tick(self, now, applied, safe):
        if self.locked and self.token and (now > self.deadline or not safe):
            self.freeze(applied, 'Lease expired or stop state lost')

    def command(self, msg, now, applied, safe):
        action = msg.get('op')
        if self.saving and action != 'heartbeat':
            raise ValueError('Save in progress')
        token = msg.get('session')
        if not isinstance(token, str) or not 16 <= len(token) <= 80:
            raise ValueError('Invalid session')
        if action == 'enter':
            if not safe or msg.get('lifted') is not True:
                raise ValueError('Fresh latched stop and lifted-wheel confirmation required')
            if self.token and token != self.token:
                raise ValueError('Another operator owns steering')
            if not self.locked:
                self.draft = copy.deepcopy(self.saved)
            self.targets = dict(applied)
            self.locked, self.token, self.sequence = True, token, -1
        elif not self.locked or self.token != token or now > self.deadline or not safe:
            raise ValueError('No live steering lease; re-enter after stop')
        seq = msg.get('seq')
        if type(seq) is not int or seq <= self.sequence:
            raise ValueError('Old or invalid command sequence')
        self.sequence, self.deadline = seq, now + 1.5
        side = msg.get('side')
        if action in ('jog', 'mark') and side not in self.targets:
            raise ValueError('Choose front or rear')
        if action == 'jog':
            step = msg.get('step')
            if type(step) is not int or step not in (-5, -1, 1, 5):
                raise ValueError('Jog must be 1 or 5 servo degrees')
            lo, hi = sorted((self.envelope[side]['left'], self.envelope[side]['right']))
            self.targets[side] = max(lo, min(hi, self.targets[side] + step))
        elif action == 'mark':
            key = msg.get('point')
            if key not in ('center', 'left', 'right'):
                raise ValueError('Unknown calibration point')
            if abs(applied[side] - self.targets[side]) > 0.1:
                raise ValueError('Wait for commanded position to settle')
            self.draft[side][key] = int(applied[side])
        elif action == 'reset_draft':
            # Reset means discard unsaved marks, never move or erase saved data.
            self.draft = copy.deepcopy(self.saved)
        elif action == 'save':
            if msg.get('confirmed') is not True:
                raise ValueError('Physical visual confirmation required')
            self.validate(self.draft)
            self.saving = True
            threading.Thread(target=self._save, args=(copy.deepcopy(self.draft),), daemon=True).start()
        elif action == 'exit':
            self.locked, self.token = False, None
        elif action not in ('enter', 'heartbeat'):
            raise ValueError('Unsupported steering command')
        self.result = action.upper() + ' accepted'

    def _save(self, candidate):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'version': 1, 'saved_at': time.time(),
                                      'steering': candidate, 'feedback': 'operator visual only'}, indent=2))
            os.replace(tmp, self.path)
            self.saved = candidate
            self.error = ''
        except OSError as exc:
            self.error = 'Calibration not saved: ' + str(exc)
        finally:
            self.saving = False

    def status(self):
        return {'locked': self.locked, 'lease_active': self.token is not None, 'saving': self.saving, 'session': self.token,
                'targets': self.targets, 'saved': self.saved, 'draft': self.draft,
                'result': self.result, 'error': self.error,
                'feedback': 'COMMANDED, NOT MEASURED', 'envelope': self.envelope}

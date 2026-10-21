#!/usr/bin/env python3
"""FlySky channel mapping config and calibrated stick conversion: OFFLINE MODEL, not deployed, drives nothing.

Nothing here assumes which channel is throttle/steering: a mapping is a reviewed file that the owner creates from observed
stick movements (Phase D).  `validate` refuses an unreviewed, incomplete or unsafe mapping.  `axis_value` turns a raw
count into -1..1 using the *measured* min/centre/max, a deadband and an optional reversal (reversal is applied here, never
by changing motor polarity).  `FrozenDetector` flags a receiver that keeps repeating the last values (a failsafe-less hold).
"""
from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

ROLES = ('throttle', 'steering', 'mode', 'estop', 'arm')
REQUIRED = ('throttle', 'steering', 'estop')
MAX_DEADBAND = 0.25
MIN_SPAN = 200          # counts between measured min and max below which an axis is considered uncalibrated


def validate(cfg: Dict[str, Any], nchan: int = 16) -> List[str]:
    """Return a list of problems; empty means acceptable for review (still needs the owner's 'reviewed' flag)."""
    errs: List[str] = []
    if not isinstance(cfg, dict):
        return ['mapping must be an object']
    if cfg.get('reviewed_by_owner') is not True:
        errs.append('mapping has not been reviewed and accepted by the owner')
    roles = cfg.get('roles') or {}
    for r in REQUIRED:
        if r not in roles:
            errs.append('missing role: ' + r)
    used: Dict[int, str] = {}
    for r, spec in roles.items():
        if r not in ROLES:
            errs.append('unknown role: %s' % r); continue
        ch = spec.get('channel') if isinstance(spec, dict) else None
        if not isinstance(ch, int) or isinstance(ch, bool) or not 1 <= ch <= nchan:
            errs.append('%s: channel must be 1..%d' % (r, nchan)); continue
        if ch in used:
            errs.append('%s and %s share channel %d' % (r, used[ch], ch))
        used[ch] = r
        if r in ('throttle', 'steering'):
            lo, ce, hi = spec.get('min'), spec.get('centre'), spec.get('max')
            if not all(isinstance(v, int) for v in (lo, ce, hi)) or not lo < ce < hi:
                errs.append('%s: need measured min < centre < max' % r)
            elif hi - lo < MIN_SPAN:
                errs.append('%s: travel too small (%d counts), recalibrate' % (r, hi - lo))
            db = spec.get('deadband', 0.05)
            if not isinstance(db, (int, float)) or not 0 <= db <= MAX_DEADBAND:
                errs.append('%s: deadband must be 0..%.2f' % (r, MAX_DEADBAND))
        if r in ('estop', 'arm', 'mode'):
            if not isinstance(spec.get('active_above'), int):
                errs.append('%s: needs an integer active_above threshold' % r)
    return errs


def axis_value(raw: Optional[int], spec: Dict[str, Any]) -> float:
    """Calibrated -1..1; None/invalid/out-of-range raw returns 0 (fails to neutral)."""
    if not isinstance(raw, int):
        return 0.0
    lo, ce, hi = spec['min'], spec['centre'], spec['max']
    if raw < lo - 60 or raw > hi + 60:               # impossible reading: reject rather than clamp to full deflection
        return 0.0
    v = (raw - ce) / float(hi - ce) if raw >= ce else (raw - ce) / float(ce - lo)
    v = max(-1.0, min(1.0, v))
    db = float(spec.get('deadband', 0.05))
    if abs(v) <= db:
        return 0.0
    v = (abs(v) - db) / (1.0 - db) * (1 if v > 0 else -1)
    return -v if spec.get('reversed') else v


def switch_active(raw: Optional[int], spec: Dict[str, Any]) -> bool:
    return isinstance(raw, int) and raw > spec['active_above']


class FrozenDetector:
    """True when every channel is bit-identical for `window` consecutive frames while the link claims to be live.
    A real transmitter always has a few counts of jitter; a frozen receiver does not."""

    def __init__(self, window: int = 40):
        self.window = window
        self.hist: Deque[Tuple[int, ...]] = deque(maxlen=window)

    def update(self, raw: Tuple[int, ...]) -> bool:
        self.hist.append(tuple(raw))
        return len(self.hist) == self.window and len(set(self.hist)) == 1

#!/usr/bin/env python3
"""Dual-remote arbitration: DESIGN MODEL ONLY.  Not imported by any production node, not deployed, drives nothing.

It states, as testable code, the rules a future second manual remote (FlySky FS-i6S) must obey before it may command
ATLAS.  The existing remote stays untouched and remains the only drive source; FlySky driving is disabled by a constant
that only a separate owner approval may change.

Rules (each has a test):
  R1  Exactly one source may command at a time. The active source is chosen explicitly; there is no automatic fallback.
  R2  E-STOP always wins: a latched stop (or a stop request from ANY source or the dashboard) forces a zero output,
      and a source switch can never release it. Release stays on the existing path only.
  R3  Stale never moves the rover: a command older than its timeout, or a source whose link is not verified, yields zero.
  R4  Loss of the ACTIVE source stops the rover and latches SOURCE_LOST. Regaining the link does not resume driving; the
      operator must select a source again (fail closed).
  R5  Switching needs: E-STOP latched or output already zero, the candidate link verified and fresh for >= SWITCH_FRESH_S,
      and the candidate's sticks neutral. Otherwise the switch is refused with a reason.
  R6  A non-active source is monitored, never forwarded. Its deflection while another source drives is reported as a
      CONFLICT (for the operator), and is dropped.
  R7  FlySky drive is disabled (FLYSKY_DRIVE_ENABLED = False). Selecting it is refused.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

EXISTING = 'existing_remote'
FLYSKY = 'flysky'
SOURCES = (EXISTING, FLYSKY)
FLYSKY_DRIVE_ENABLED = False      # R7: only a separate, explicit owner approval changes this
COMMAND_TIMEOUT_S = 0.5
SWITCH_FRESH_S = 1.0
NEUTRAL = 0.05


@dataclass
class SourceInput:
    link_verified: bool = False
    age_s: Optional[float] = None            # age of the newest command from this source
    linear: float = 0.0                      # -1..1
    angular: float = 0.0
    deadman: bool = False
    stop_request: bool = False
    fresh_since_s: float = 0.0               # how long the link has been continuously verified+fresh

    def neutral(self) -> bool:
        return abs(self.linear) <= NEUTRAL and abs(self.angular) <= NEUTRAL

    def usable(self) -> bool:
        return self.link_verified and self.age_s is not None and self.age_s <= COMMAND_TIMEOUT_S


@dataclass(frozen=True)
class Decision:
    linear: float
    angular: float
    source: Optional[str]
    reason: str
    stop_latched: bool
    conflict: bool = False


class Arbiter:
    def __init__(self, active: Optional[str] = EXISTING):
        self.active = active
        self.stop_latched = False
        self.source_lost = False

    def _zero(self, reason: str, conflict: bool = False) -> Decision:
        return Decision(0.0, 0.0, self.active, reason, self.stop_latched, conflict)

    def select(self, source: str, inputs: Dict[str, SourceInput], dashboard_stop: bool = False) -> Tuple[bool, str]:
        """Operator asks to make `source` the active one."""
        if source not in SOURCES:
            return False, 'unknown source'
        if source == FLYSKY and not FLYSKY_DRIVE_ENABLED:
            return False, 'FlySky driving is disabled (not approved)'
        cand = inputs.get(source, SourceInput())
        if not (self.stop_latched or dashboard_stop or self._output_zero(inputs)):
            return False, 'latch the E-STOP (or bring the rover to zero) before switching remotes'
        if not cand.usable():
            return False, 'candidate link is not verified and fresh'
        if cand.fresh_since_s < SWITCH_FRESH_S:
            return False, 'candidate link has not been fresh for %.1f s yet' % SWITCH_FRESH_S
        if not cand.neutral():
            return False, 'candidate sticks are not neutral'
        self.active, self.source_lost = source, False
        return True, 'selected ' + source

    def _output_zero(self, inputs: Dict[str, SourceInput]) -> bool:
        a = inputs.get(self.active) if self.active else None
        return a is None or (a.neutral() or not a.deadman)

    def step(self, inputs: Dict[str, SourceInput], dashboard_stop: bool = False) -> Decision:
        # R2: any stop request latches; nothing here releases it.
        if dashboard_stop or any(i.stop_request for i in inputs.values()):
            self.stop_latched = True
        if self.stop_latched:
            return self._zero('E-STOP latched')
        if self.active is None:
            return self._zero('no source selected')
        if self.active == FLYSKY and not FLYSKY_DRIVE_ENABLED:      # R7 also holds if state was forced
            return self._zero('FlySky driving is disabled')
        if self.source_lost:
            return self._zero('active source lost; select a source again')
        a = inputs.get(self.active, SourceInput())
        # R4: loss of the active source fails closed and latches
        if not a.usable():
            self.source_lost = True
            return self._zero('active source lost or stale')
        # R6: conflicting deflection from a non-active source is reported and dropped
        conflict = any(s != self.active and i.usable() and not i.neutral() and i.deadman for s, i in inputs.items())
        if not a.deadman:
            return self._zero('deadman not held', conflict)
        return Decision(max(-1.0, min(1.0, a.linear)), max(-1.0, min(1.0, a.angular)), self.active, 'driving', False, conflict)

    def release_stop_existing_path_only(self) -> None:   # pragma: no cover - documents R2; deliberately inert
        raise NotImplementedError('E-STOP release stays on the existing, owner-controlled path')

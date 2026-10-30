#!/usr/bin/env python3
"""ATLAS Stage 29: FlySky SwD (CH8) E-STOP reset. Pure logic, no ROS, no I/O. OFF unless ATLAS_FLYSKY_RESET_ENABLED=1.

Two independent halves; BOTH must agree before the E-STOP is released, and neither can ever command motion:

  ResetGesture (FlySky teleop)  recognises the deliberate gesture on the receiver frames and sends ONE request;
  MuxResetGate (cmd_vel mux)    re-checks everything the mux itself owns and is the only part that can release.

Gesture (all conditions must hold for the WHOLE gesture; any break aborts and the gesture starts again from step 1):
  0. FlySky is the selected controller and the E-STOP is latched; receiver LIVE (fresh frames, no failsafe, no
     frame-lost) continuously for >= LINK_HEALTHY_S; SwA OFF (disarmed); SwB at RUN; right stick centred.
  1. SwD UP for >= UP_QUALIFY_S  (power-on with SwD down, a stuck switch, or a just-restored link never counts)
  2. SwD DOWN and hold for HOLD_S .. MAX_HOLD_S  (shorter = ignored; longer = treated as stuck, aborted)
  3. SwD back UP -> one reset request.
The mux then also requires: reset gate on, FlySky driving gate on, FlySky selected, latched for >= MIN_LATCHED_S,
Xbox connected and untouched for >= 1 s (it stays the independent stop device), no motion commanded, encoders fresh,
healthy and still for >= STATIONARY_S, a fresh request (system monotonic time, <= REQUEST_MAX_AGE_S) with a new
sequence number, and no other request in the last RATE_LIMIT_S.
After a release nothing moves: the FlySky drive core needs SwA OFF -> ON with the throttle centred (a fresh arm).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

GATE_ENV = 'ATLAS_FLYSKY_RESET_ENABLED'
RESET_CHANNEL = 8                 # SwD on this FS-i6S (owner-verified 2026-10-29: 240 up / 1807 down)
SWD_UP_BELOW = 400
SWD_DOWN_ABOVE = 1700             # a centre failsafe (992/1024) is neither UP nor DOWN: it aborts the gesture
UP_QUALIFY_S = 1.0
HOLD_S = 2.0
MAX_HOLD_S = 5.0
LINK_HEALTHY_S = 3.0
MIN_LATCHED_S = 2.0
STATIONARY_S = 1.0
ENCODER_MAX_AGE_S = 0.5
STILL_M = 0.0005                  # per encoder interval
REQUEST_MAX_AGE_S = 0.3
RATE_LIMIT_S = 3.0
XBOX_MAX_AGE_S = 0.5
XBOX_NEUTRAL_S = 1.0
GESTURE = 'SWD_UP_DOWN_HOLD_UP'


def channel_conflict(cfg: Dict[str, Any]) -> Optional[str]:
    """None when RESET_CHANNEL is not used by any drive role."""
    for role in ('throttle', 'steering', 'arm', 'stop', 'speed_mode'):
        spec = cfg.get(role) if isinstance(cfg, dict) else None
        if isinstance(spec, dict) and spec.get('channel') == RESET_CHANNEL:
            return 'CH%d is already used by %s' % (RESET_CHANNEL, role)
    return None


# ------------------------------------------------------------------ teleop side
@dataclass
class ResetGesture:
    enabled: bool
    state: str = 'OFF'
    blocked: List[str] = field(default_factory=list)
    healthy_since: Optional[float] = None
    up_since: Optional[float] = None
    down_since: Optional[float] = None
    qualified: bool = False
    seq: int = 0                  # the node starts it at wall-clock ms so a teleop restart never reuses old numbers
    last_request: Optional[Dict[str, Any]] = None

    def _abort(self, state: str, reasons: List[str]) -> None:
        self.state, self.blocked = state, reasons
        self.up_since = self.down_since = None
        self.qualified = False

    def step(self, logic: Any, now: float) -> Optional[Dict[str, Any]]:
        """Advance on the drive core's current view (`logic` is a DriveLogic). Returns a request dict at most once per
        completed gesture, else None. Never touches the drive core's state."""
        if not self.enabled:
            self._abort('OFF', ['FlySky reset is off (%s is not 1)' % GATE_ENV]); self.healthy_since = None
            return None
        c, f, p = logic.cfg, logic.frame, logic.policy
        if not logic.enabled:
            self._abort('OFF', ['FlySky driving is disabled']); self.healthy_since = None
            return None
        conflict = channel_conflict(c)
        if conflict:
            self._abort('OFF', [conflict]); return None
        # receiver link health, tracked continuously (also while not latched) so a restored link must wait
        link_ok = (f is not None and now - f.rx <= c['frame_timeout_s'] and not f.failsafe and not f.frame_lost
                   and len(f.raw) >= RESET_CHANNEL)
        if not link_ok:
            self.healthy_since = None
        elif self.healthy_since is None:
            self.healthy_since = now
        if p is None or now - p.rx > c['policy_timeout_s']:
            self._abort('BLOCKED', ['mux policy missing or stale']); return None
        if p.manual_controller != 'FLYSKY':
            self._abort('UNAVAILABLE', ['FlySky is not the selected controller']); return None
        if not p.stop_latched:
            self._abort('NOT_NEEDED', ['E-STOP is not latched']); return None
        reasons = []
        if not link_ok:
            reasons.append('receiver not LIVE (no fresh frame, failsafe or frame lost)')
        elif now - self.healthy_since < LINK_HEALTHY_S:
            reasons.append('receiver link healthy for %.1f s of %.1f s' % (now - self.healthy_since, LINK_HEALTHY_S))
        if link_ok:
            import atlas_flysky_drive_core as dc
            raw = lambda role: f.raw[c[role]['channel'] - 1]
            if raw('arm') > c['arm']['off_below']:
                reasons.append('SwA must be OFF (up)')
            if raw('stop') >= c['stop']['run_below']:
                reasons.append('SwB must be at RUN (up)')
            if dc.axis(raw('throttle'), c['throttle']) != 0.0 or dc.axis(raw('steering'), c['steering']) != 0.0:
                reasons.append('centre the right stick')
            d = f.raw[RESET_CHANNEL - 1]
            swd = 'UP' if d < SWD_UP_BELOW else 'DOWN' if d > SWD_DOWN_ABOVE else 'INVALID'
            if swd == 'INVALID':
                reasons.append('SwD reads between positions (CH8 %d)' % d)
        if reasons:
            self._abort('BLOCKED', reasons); return None
        self.blocked = []
        if swd == 'UP':
            if self.down_since is not None:                     # released after a hold
                held = now - self.down_since
                self.down_since = None
                if self.qualified and HOLD_S <= held <= MAX_HOLD_S:
                    self.qualified = False
                    self.up_since = now
                    self.seq += 1
                    self.state = 'SENT'
                    self.last_request = {'gesture': GESTURE, 'seq': self.seq, 't_mono': now, 'hold_s': round(held, 3),
                                         'channel': RESET_CHANNEL}
                    return dict(self.last_request)
                self.qualified = False
                self.up_since = now
                self.state = 'WAIT_SWD_UP'
                self.blocked = ['SwD released after %.1f s; hold it %.0f-%.0f s' % (held, HOLD_S, MAX_HOLD_S)]
                return None
            if self.up_since is None:
                self.up_since = now
            if now - self.up_since >= UP_QUALIFY_S:
                self.qualified = True
                if self.state != 'SENT' or now - self.up_since > 2.0:
                    self.state = 'READY'
            else:
                self.state = 'WAIT_SWD_UP' if self.state != 'SENT' else 'SENT'
            return None
        # SwD DOWN
        if not self.qualified:
            self._abort('WAIT_SWD_UP', ['SwD must be UP for %.0f s first (power-on, stuck or early flip)' % UP_QUALIFY_S])
            return None
        if self.down_since is None:
            self.down_since = now
        held = now - self.down_since
        if held > MAX_HOLD_S:
            self._abort('WAIT_SWD_UP', ['SwD held over %.0f s (stuck?): put it UP and start again' % MAX_HOLD_S])
            return None
        self.state = 'RELEASE_NOW' if held >= HOLD_S else 'HOLDING'
        return None

    def status(self, now: float) -> Dict[str, Any]:
        held = None if self.down_since is None else round(now - self.down_since, 2)
        return {'enabled': self.enabled, 'state': self.state, 'blocked': list(self.blocked), 'held_s': held,
                'hold_s': HOLD_S, 'max_hold_s': MAX_HOLD_S, 'channel': RESET_CHANNEL, 'switch': 'SwD',
                'available': self.state in ('READY', 'HOLDING', 'RELEASE_NOW'), 'last_seq': self.seq}


# ------------------------------------------------------------------ mux side
@dataclass
class MuxResetGate:
    enabled: bool
    latched_since: Optional[float] = None
    stationary_since: Optional[float] = None
    last_seq: int = 0
    last_attempt: float = -1e9
    last_result: Optional[str] = None
    last_reason: str = ''
    last_t: Optional[float] = None

    def observe(self, now: float, latched: bool, commanding: bool, enc: Dict[str, Any], enc_rx: float) -> None:
        """Called on every encoder-health message and before every decision."""
        if not latched:
            self.latched_since = None
        elif self.latched_since is None:
            self.latched_since = now
        if commanding or not self._encoders_still(now, enc, enc_rx):
            self.stationary_since = None
        elif self.stationary_since is None:
            self.stationary_since = now

    @staticmethod
    def _encoders_still(now, enc, enc_rx) -> bool:
        if not isinstance(enc, dict) or now - enc_rx > ENCODER_MAX_AGE_S:
            return False
        if enc.get('state') != 'READY' or enc.get('packet_fresh') is not True:
            return False
        d = enc.get('encoder_interval_delta_m')
        return (isinstance(d, list) and len(d) == 4
                and all(isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) <= STILL_M for x in d))

    def decide(self, now: float, text: str, *, drive_enabled: bool, controller: str, latched: bool,
               commanding: bool, xbox_rx: Optional[float], xbox_neutral_since: Optional[float],
               enc: Dict[str, Any], enc_rx: float):
        """(release?, reason). Records the result for the policy."""
        self.observe(now, latched, commanding, enc, enc_rx)
        ok, why = self._decide(now, text, drive_enabled, controller, latched, xbox_rx, xbox_neutral_since)
        self.last_result, self.last_reason, self.last_t = ('RELEASED' if ok else 'REFUSED'), why, now
        return ok, why

    def _decide(self, now, text, drive_enabled, controller, latched, xbox_rx, xbox_neutral_since):
        try:
            req = json.loads(text)
        except (TypeError, ValueError):
            req = None
        if not isinstance(req, dict) or req.get('gesture') != GESTURE or req.get('channel') != RESET_CHANNEL:
            return False, 'not a FlySky SwD reset request'
        seq, t = req.get('seq'), req.get('t_mono')
        if not (isinstance(seq, int) and not isinstance(seq, bool)) or not isinstance(t, (int, float)) or isinstance(t, bool):
            return False, 'malformed request'
        if seq <= self.last_seq:
            return False, 'repeated or old request'
        self.last_seq = seq
        if not (-0.05 <= now - t <= REQUEST_MAX_AGE_S):
            return False, 'stale request (%.2f s old)' % (now - t)
        hold = req.get('hold_s')
        if not isinstance(hold, (int, float)) or not HOLD_S <= hold <= MAX_HOLD_S:
            return False, 'hold time outside %.0f-%.0f s' % (HOLD_S, MAX_HOLD_S)
        if now - self.last_attempt < RATE_LIMIT_S:
            return False, 'another reset request less than %.0f s ago' % RATE_LIMIT_S
        self.last_attempt = now
        if not self.enabled:
            return False, 'FlySky reset is off on this rover (%s)' % GATE_ENV
        if not drive_enabled:
            return False, 'FlySky driving gate is off'
        if controller != 'FLYSKY':
            return False, 'FlySky is not the selected controller'
        if not latched:
            return False, 'E-STOP is not latched'
        if self.latched_since is None or now - self.latched_since < MIN_LATCHED_S:
            return False, 'E-STOP latched less than %.0f s ago' % MIN_LATCHED_S
        if xbox_rx is None or now - xbox_rx > XBOX_MAX_AGE_S:
            return False, 'Xbox not connected (it stays the independent stop device)'
        if xbox_neutral_since is None or now - xbox_neutral_since < XBOX_NEUTRAL_S:
            return False, 'Xbox must be untouched (nothing pressed, sticks centred) for 1 s'
        if self.stationary_since is None or now - self.stationary_since < STATIONARY_S:
            return False, 'rover not confirmed stationary (encoders fresh, healthy and still for 1 s)'
        return True, 'REMOTE STOP: released by FlySky SwD reset'

    def status(self, now: float) -> Dict[str, Any]:
        return {'enabled': self.enabled, 'last_result': self.last_result, 'last_reason': self.last_reason,
                'age_s': None if self.last_t is None else round(now - self.last_t, 2),
                'stationary': self.stationary_since is not None and now - self.stationary_since >= STATIONARY_S}

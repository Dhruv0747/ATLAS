#!/usr/bin/env python3
"""ATLAS FlySky driving: pure decision core (no ROS, no I/O). DISABLED unless explicitly enabled and owner-reviewed.

Turns /atlas/rc/frames SBUS frames into a bounded (linear, angular) request for the existing cmd_vel multiplexer.
It never talks to the motor board: its only outputs are a request on /cmd_vel_flysky (which the mux accepts only when
FlySky is the selected controller), a stop request (which the mux turns into its normal latched E-STOP), and a status.

Fail-closed rules (each is tested):
  * Nothing is produced unless the drive gate is enabled AND the config is valid AND reviewed_by_owner is true.
  * The arm switch must be at its far ON end. A receiver failsafe that sets every channel to centre (1024) puts the
    arm switch in the INVALID band, so a centre-value failsafe can never be armed or keep the rover armed.
  * Arming needs the arm switch to be seen OFF first (no arm-through at power-on or after any stop) and the throttle
    centred at the moment of arming.
  * Signal loss (no new frame within frame_timeout_s), the SBUS failsafe flag, or a stale/latched mux policy while
    armed -> zero immediately, disarm, and request the mux E-STOP latch. The SBUS frame-lost flag -> zero + disarm.
  * The stop switch is a stop unless it is clearly at its RUN end; it requests the mux latch while FlySky is selected.
  * Speeds are capped by the config and by hard ceilings equal to the Xbox non-turbo limits (0.25 m/s, 0.8 rad/s).
    Increases in linear speed are slew-limited; decreases are immediate.
  * The throttle stick must be declared self-centring by the owner (the FS-i6S left vertical stick is not).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import atlas_flysky_core as core

HARD_MAX_LINEAR_MPS = 0.25        # Xbox teleop non-turbo linear scale (config/joy_config.yaml)
HARD_MAX_ANGULAR_RADPS = 0.80     # Xbox teleop non-turbo angular scale
HARD_MAX_ACCEL_MPS2 = 1.0
MIN_DEADBAND, MAX_DEADBAND = 0.03, 0.25
MAX_FRAME_TIMEOUT_S = 0.5
MAX_POLICY_TIMEOUT_S = 0.5
MIN_SPAN = 600                    # counts between measured min and max; less means the axis is not calibrated
RAW_MARGIN = 60                   # a raw value this far outside the measured range is impossible: reject
STOP_RESEND_S = 0.5
# Centre values a failsafe may output: the generic SBUS mid (992) and this FS-iA receiver's measured centre (1024).
CENTRES = (core.SBUS_MID, 1024)

STATES = ('DISABLED', 'POLICY_STALE', 'NOT_SELECTED', 'STOP_LATCHED', 'NO_SIGNAL', 'FAILSAFE', 'FRAME_LOST',
          'STOP_SWITCH', 'INVALID_INPUT', 'WAIT_ARM_OFF', 'WAIT_ARM_ON', 'WAIT_NEUTRAL', 'ARMED')


# ------------------------------------------------------------------ config
def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate(cfg: Any, nchan: int = 10) -> List[str]:
    """Problems with a drive config; empty list = usable (the reviewed flag is checked separately by `usable`)."""
    if not isinstance(cfg, dict):
        return ['config must be an object']
    errs: List[str] = []
    used: Dict[int, str] = {}

    def chan(role, spec):
        ch = spec.get('channel') if isinstance(spec, dict) else None
        if not _int(ch) or not 1 <= ch <= nchan:
            errs.append('%s: channel must be 1..%d' % (role, nchan)); return
        if ch in used:
            errs.append('%s and %s share channel %d' % (role, used[ch], ch))
        used[ch] = role

    for role in ('throttle', 'steering'):
        s = cfg.get(role)
        if not isinstance(s, dict):
            errs.append('missing ' + role); continue
        chan(role, s)
        lo, ce, hi = s.get('min'), s.get('centre'), s.get('max')
        if not all(_int(v) for v in (lo, ce, hi)) or not lo < ce < hi:
            errs.append('%s: need measured integer min < centre < max' % role)
        elif hi - lo < MIN_SPAN or min(ce - lo, hi - ce) < MIN_SPAN // 2:
            errs.append('%s: travel %d/%d counts each side of centre is too small; recalibrate' % (role, ce - lo, hi - ce))
        db = s.get('deadband')
        if not _num(db) or not MIN_DEADBAND <= db <= MAX_DEADBAND:
            errs.append('%s: deadband must be %.2f..%.2f' % (role, MIN_DEADBAND, MAX_DEADBAND))
        if not isinstance(s.get('reversed'), bool):
            errs.append('%s: reversed must be true or false' % role)
    t = cfg.get('throttle')
    if isinstance(t, dict) and t.get('self_centring') is not True:
        errs.append('throttle: the owner must confirm the stick springs back to centre (self_centring: true)')
    a = cfg.get('arm')
    if not isinstance(a, dict):
        errs.append('missing arm')
    else:
        chan('arm', a)
        if not (_int(a.get('on_above')) and _int(a.get('off_below')) and a['off_below'] < min(CENTRES) and a['on_above'] > max(CENTRES)):
            errs.append('arm: need integer off_below < %d and on_above > %d so a centre failsafe is never ON or OFF' % (min(CENTRES), max(CENTRES)))
    s = cfg.get('stop')
    if not isinstance(s, dict):
        errs.append('missing stop')
    else:
        chan('stop', s)
        if not (_int(s.get('run_below')) and s['run_below'] < min(CENTRES)):
            errs.append('stop: need integer run_below < %d so a centre failsafe reads as STOP' % min(CENTRES))
    m = cfg.get('speed_mode')
    if m is not None:
        if not isinstance(m, dict):
            errs.append('speed_mode must be an object')
        else:
            chan('speed_mode', m)
            sc = m.get('scales')
            if not (isinstance(sc, list) and len(sc) == 3 and all(_num(x) and 0 < x <= 1 for x in sc)):
                errs.append('speed_mode: scales must be three numbers in (0, 1]')
    for key, ceiling in (('max_linear_mps', HARD_MAX_LINEAR_MPS), ('max_angular_radps', HARD_MAX_ANGULAR_RADPS),
                         ('max_accel_mps2', HARD_MAX_ACCEL_MPS2)):
        v = cfg.get(key)
        if not _num(v) or not 0 < v <= ceiling:
            errs.append('%s must be in (0, %.2f]' % (key, ceiling))
    for key, ceiling in (('frame_timeout_s', MAX_FRAME_TIMEOUT_S), ('policy_timeout_s', MAX_POLICY_TIMEOUT_S)):
        v = cfg.get(key)
        if not _num(v) or not 0.05 <= v <= ceiling:
            errs.append('%s must be in [0.05, %.2f]' % (key, ceiling))
    return errs


def usable(cfg: Any) -> Tuple[bool, List[str]]:
    errs = validate(cfg)
    if isinstance(cfg, dict) and cfg.get('reviewed_by_owner') is not True:
        errs.append('config has not been reviewed and accepted by the owner (reviewed_by_owner: true)')
    return not errs, errs


def axis(raw: int, spec: Dict[str, Any]) -> Optional[float]:
    """Calibrated -1..1 with deadband and reversal; None for an impossible reading (caller fails to zero)."""
    lo, ce, hi = spec['min'], spec['centre'], spec['max']
    if not _int(raw) or raw < lo - RAW_MARGIN or raw > hi + RAW_MARGIN:
        return None
    v = (raw - ce) / float(hi - ce) if raw >= ce else (raw - ce) / float(ce - lo)
    v = max(-1.0, min(1.0, v))
    db = float(spec['deadband'])
    v = 0.0 if abs(v) <= db else math.copysign((abs(v) - db) / (1.0 - db), v)
    return -v if spec['reversed'] else v


# ------------------------------------------------------------------ input
@dataclass
class RcFrame:
    raw: Tuple[int, ...]
    frame_lost: bool
    failsafe: bool
    rx: float
    seq: Optional[int] = None


def parse_message(msg: Any, rx: float) -> Optional[RcFrame]:
    """{"proto":"sbus","hex":"0f..","seq":n} -> RcFrame, or None for anything that is not one valid SBUS frame."""
    try:
        if msg.get('proto') != 'sbus':
            return None
        data = bytes.fromhex(msg['hex'])
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    f = core.decode_sbus(data, rx)
    if f is None:
        return None
    seq = msg.get('seq')
    return RcFrame(f.raw, bool(f.frame_lost), bool(f.failsafe), rx, seq if _int(seq) else None)


@dataclass
class Policy:
    rx: float
    stop_latched: bool
    manual_controller: str


def parse_policy(text: str, rx: float) -> Optional[Policy]:
    import json
    try:
        d = json.loads(text)
        if not isinstance(d, dict) or not isinstance(d.get('stop_latched'), bool):
            return None
        return Policy(rx, d['stop_latched'], str(d.get('manual_controller', 'XBOX')))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ decision
@dataclass
class Output:
    command: Optional[Tuple[float, float]]    # (linear m/s, angular rad/s); None = publish nothing
    stop_request: bool
    state: str
    reason: str


@dataclass
class DriveLogic:
    cfg: Dict[str, Any]
    gate_enabled: bool
    frame: Optional[RcFrame] = None
    policy: Optional[Policy] = None
    armed: bool = False
    arm_off_seen: bool = False
    last_linear: float = 0.0
    last_t: Optional[float] = None
    last_stop_sent: float = -1e9
    latch_pending: bool = False             # an armed-loss stop request not yet confirmed latched by the mux
    errors: List[str] = field(default_factory=list)

    def __post_init__(self):
        ok, self.errors = usable(self.cfg)
        self.enabled = bool(self.gate_enabled) and ok
        if not self.gate_enabled:
            self.errors = ['FlySky driving gate is off (ATLAS_FLYSKY_DRIVE_ENABLED is not 1)'] + self.errors

    # inputs
    def on_frame(self, f: Optional[RcFrame]) -> None:
        if f is None:
            return
        if self.frame is not None and f.seq is not None and self.frame.seq is not None and f.seq == self.frame.seq:
            return                                    # a repeated frame is not fresh
        self.frame = f

    def on_policy(self, p: Optional[Policy]) -> None:
        if p is not None:
            self.policy = p

    # helpers
    def _disarm(self) -> None:
        self.armed = False
        self.arm_off_seen = False
        self.last_linear = 0.0

    def _stop(self, now: float) -> bool:
        if now - self.last_stop_sent >= STOP_RESEND_S:
            self.last_stop_sent = now
            return True
        return False

    def _out(self, now, cmd, stop, state, reason) -> Output:
        self.last_t = now
        if stop and state in ('POLICY_STALE', 'NO_SIGNAL', 'FAILSAFE'):
            self.latch_pending = True
        elif self.latch_pending and state not in ('STOP_LATCHED', 'NOT_SELECTED', 'DISABLED'):
            stop = self._stop(now)                    # keep asking until the mux reports the latch
        return Output(cmd, stop, state, reason)

    def step(self, now: float) -> Output:
        c = self.cfg
        if not self.enabled:
            self._disarm()
            return self._out(now, None, False, 'DISABLED', '; '.join(self.errors) or 'disabled')
        p = self.policy
        if p is None or now - p.rx > c['policy_timeout_s']:
            was = self.armed; self._disarm()
            return self._out(now, (0.0, 0.0), was and self._stop(now), 'POLICY_STALE', 'mux policy missing or stale')
        if p.manual_controller != 'FLYSKY':
            self._disarm()
            return self._out(now, None, False, 'NOT_SELECTED', 'selected controller is %s' % p.manual_controller)
        if p.stop_latched:
            self._disarm()
            self.latch_pending = False
            return self._out(now, (0.0, 0.0), False, 'STOP_LATCHED', 'E-STOP latched')
        f = self.frame
        if f is None or now - f.rx > c['frame_timeout_s']:
            was = self.armed; self._disarm()
            return self._out(now, (0.0, 0.0), was and self._stop(now), 'NO_SIGNAL',
                             'no new receiver frame for %.2f s' % (now - f.rx) if f else 'no receiver frame yet')
        if f.failsafe:
            was = self.armed; self._disarm()
            return self._out(now, (0.0, 0.0), was and self._stop(now), 'FAILSAFE', 'receiver failsafe flag set')
        if f.frame_lost:
            self._disarm()
            return self._out(now, (0.0, 0.0), False, 'FRAME_LOST', 'receiver frame-lost flag set')
        raw = lambda role: f.raw[c[role]['channel'] - 1]
        if raw('stop') >= c['stop']['run_below']:
            self._disarm()
            return self._out(now, (0.0, 0.0), self._stop(now), 'STOP_SWITCH', 'stop switch is not at RUN')
        thr, steer = axis(raw('throttle'), c['throttle']), axis(raw('steering'), c['steering'])
        if thr is None or steer is None:
            self._disarm()
            return self._out(now, (0.0, 0.0), False, 'INVALID_INPUT', 'impossible stick reading')
        a = raw('arm')
        arm_on, arm_off = a >= c['arm']['on_above'], a <= c['arm']['off_below']
        if not arm_on:
            if self.armed:
                self._disarm()
            if arm_off:
                self.arm_off_seen = True
                return self._out(now, (0.0, 0.0), False, 'WAIT_ARM_ON', 'arm switch OFF')
            self.arm_off_seen = False
            return self._out(now, (0.0, 0.0), False, 'INVALID_INPUT', 'arm switch between positions (failsafe centre?)')
        if not self.armed:
            if not self.arm_off_seen:
                return self._out(now, (0.0, 0.0), False, 'WAIT_ARM_OFF', 'switch arm OFF, then ON, to arm')
            if thr != 0.0:
                return self._out(now, (0.0, 0.0), False, 'WAIT_NEUTRAL', 'centre the throttle to arm')
            self.armed = True
            self.last_linear = 0.0
        scale = 1.0
        if c.get('speed_mode'):
            m = raw('speed_mode')
            band = 0 if m < 400 else 2 if m > 1700 else 1
            scale = float(c['speed_mode']['scales'][band])
        want = thr * c['max_linear_mps'] * scale
        dt = max(0.0, now - self.last_t) if self.last_t is not None else 0.0
        if abs(want) > abs(self.last_linear) or want * self.last_linear < 0:
            step = c['max_accel_mps2'] * dt
            if want * self.last_linear < 0:                 # direction change: through zero first
                want = 0.0
            else:
                want = math.copysign(min(abs(want), abs(self.last_linear) + step), want)
        self.last_linear = want
        lin = max(-HARD_MAX_LINEAR_MPS, min(HARD_MAX_LINEAR_MPS, want))
        ang = max(-HARD_MAX_ANGULAR_RADPS, min(HARD_MAX_ANGULAR_RADPS, steer * c['max_angular_radps'] * scale))
        return self._out(now, (lin, ang), False, 'ARMED', 'armed')

    def inputs(self) -> Optional[Dict[str, Any]]:
        """What the logic sees in the latest frame, for the dashboard (None before a frame or with a bad config)."""
        f, c = self.frame, self.cfg
        if f is None or validate(c):
            return None
        raw = lambda role: f.raw[c[role]['channel'] - 1]
        a = raw('arm')
        out = {'throttle': axis(raw('throttle'), c['throttle']), 'steering': axis(raw('steering'), c['steering']),
               'arm': 'ON' if a >= c['arm']['on_above'] else 'OFF' if a <= c['arm']['off_below'] else 'INVALID',
               'stop': 'RUN' if raw('stop') < c['stop']['run_below'] else 'STOP',
               'failsafe': f.failsafe, 'frame_lost': f.frame_lost}
        if c.get('speed_mode'):
            m = raw('speed_mode')
            out['speed_scale'] = c['speed_mode']['scales'][0 if m < 400 else 2 if m > 1700 else 1]
        return out

    def summary(self) -> Dict[str, Any]:
        c = self.cfg if isinstance(self.cfg, dict) else {}
        pick = lambda r: {k: c.get(r, {}).get(k) for k in ('channel', 'reversed', 'deadband')} if isinstance(c.get(r), dict) else None
        return {'enabled': self.enabled, 'errors': self.errors, 'reviewed_by_owner': c.get('reviewed_by_owner') is True,
                'throttle': pick('throttle'), 'steering': pick('steering'),
                'arm_channel': (c.get('arm') or {}).get('channel'), 'stop_channel': (c.get('stop') or {}).get('channel'),
                'speed_mode_channel': (c.get('speed_mode') or {}).get('channel'),
                'max_linear_mps': c.get('max_linear_mps'), 'max_angular_radps': c.get('max_angular_radps'),
                'hard_max_linear_mps': HARD_MAX_LINEAR_MPS, 'hard_max_angular_radps': HARD_MAX_ANGULAR_RADPS}

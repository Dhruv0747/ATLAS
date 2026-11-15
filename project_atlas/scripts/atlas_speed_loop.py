"""Closed-loop drive speed for AUTONOMOUS (non-REMOTE) commands with three encoders. Pure Python, no ROS.

2026-11-15 (owner chose "Closed-loop speed (3 enc)"). NOT wired into yahboom_base yet; offline + tests only.

Problem it solves: the open-loop map in yahboom_base._drive_pwm gives every non-remote command >= 60 PWM, and on
the ground 60-90 PWM all drive ~0.3-0.4 m/s (recordings 2026-11-15). A 0.07 m/s Nav2/mux command therefore moved
~0.4-0.5 m/s. This loop sets the PWM from the error between the commanded speed and the measured speed from the
3-encoder consensus (EncoderDeltaEstimator distance per tick).

Fail-safe rules (each covered by tests/test_speed_loop.py):
  * |target| <= deadband -> 0 PWM, integrator reset.
  * feedback invalid (consensus unavailable, encoder packet stale, non-finite) -> 0 PWM, integrator reset.
  * HARD overspeed cut: |measured| > max(overspeed_ratio * |target|, |target| + overspeed_margin) -> 0 PWM this
    tick and the integrator is cut back, so a breakaway jump can never keep accelerating.
  * direction change goes through zero: while the rover still moves against the new command -> 0 PWM.
  * output magnitude clamped to [0, max_pwm]; max_pwm (default 75) is below the open-loop 100.
  * the REMOTE path never uses this module.
"""
import math
from collections import deque

DEFAULTS = {
    'deadband_mps': 0.02,
    'ff_pwm': 44.0,            # starting PWM (2026-11-15 ground: PWM 50 held 0.5 s did not break away)
    'kp_pwm_per_mps': 60.0,
    'ki_pwm_per_m': 60.0,      # integral gain: PWM per (m/s * s) of error
    'integrator_max_pwm': 40.0,
    'max_pwm': 75,
    'overspeed_ratio': 1.5,
    'overspeed_margin_mps': 0.08,
    'window_ticks': 3,         # measured speed = distance over the last N ticks (encoder counts arrive in bursts)
    'reverse_block_mps': 0.03,
    'stall_ramp_pwm_per_s': 25.0,   # while still (speed < stall_fraction x target): raise PWM this fast to break away
    'stall_fraction': 0.25,
    'breakaway_margin_pwm': 6.0,    # next start begins this far below the PWM that last broke away
    'release_drop_pwm': 6.0,        # once rolling, drop this far below the breakaway PWM (kinetic < static friction)
    'detect_lag_ticks': 3,          # base slew + motor + encoder delay between a PWM and the motion it causes
    'restall_ticks': 4,             # rolling but still for this many ticks -> breakaway search again
    'overspeed_drop_pwm': 4.0,      # each overspeed tick lowers the integrator by this much
    # 2026-11-15 ground check (rover twitched 3-5 mm, never rolled): one bursty encoder tick at ~0.017 m/s was taken
    # as breakaway at PWM ~43 and the loop released to ~37. Breakaway now needs the WINDOW speed above an absolute
    # floor for consecutive ticks; a single burst no longer counts.
    'motion_floor_mps': 0.03,
    'breakaway_confirm_ticks': 2,
}


def _finite(*values):
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


class SpeedLoop:
    def __init__(self, params=None):
        p = dict(DEFAULTS)
        p.update(params or {})
        for k, v in p.items():
            if not _finite(v) or v < 0:
                raise ValueError(f'speed loop parameter {k}={v!r} must be finite and >= 0')
        if not 0 < p['max_pwm'] <= 100 or p['window_ticks'] < 1 or p['overspeed_ratio'] < 1.0:
            raise ValueError('speed loop: max_pwm in (0,100], window_ticks >= 1, overspeed_ratio >= 1')
        self.p = p
        self.samples = deque(maxlen=int(p['window_ticks']))
        self.learned_start_pwm = None   # PWM that last produced motion from rest (per run; never persisted)
        self.reset()

    def reset(self):
        self.integrator = 0.0
        self.rolling = False
        self.still_ticks = 0
        self.moving_ticks = 0
        self.history = deque(maxlen=12)
        self.last_output = 0
        self.last_reason = 'idle'

    def measured_speed(self):
        dist = sum(d for d, _ in self.samples)
        dt = sum(t for _, t in self.samples)
        return dist / dt if dt > 0 else 0.0

    def update(self, target_mps, delta_m, dt_s, feedback_ok):
        """One control tick. target_mps signed (from the mux command), delta_m signed body-centre distance since the
        last tick (encoder consensus), dt_s tick duration, feedback_ok = consensus available AND packet fresh.
        Returns a signed PWM int."""
        p = self.p
        if not _finite(target_mps, delta_m, dt_s) or dt_s <= 0 or dt_s > 0.5 or not feedback_ok:
            self.samples.clear()
            return self._out(0, 'feedback invalid', reset=True)
        self.samples.append((float(delta_m), float(dt_s)))
        v = self.measured_speed()
        tgt = abs(target_mps)
        if tgt <= p['deadband_mps']:
            return self._out(0, 'zero command', reset=True)
        sign = 1 if target_mps > 0 else -1
        if v * sign < -p['reverse_block_mps']:
            return self._out(0, 'moving against the command: stop first', reset=True)
        speed = v * sign                                   # >0 when moving in the commanded direction
        moving_now = speed >= max(p['stall_fraction'] * tgt, p['motion_floor_mps'])
        if moving_now:
            self.still_ticks = 0
            self.moving_ticks += 1
        else:
            self.still_ticks += 1
            self.moving_ticks = 0
        if not self.rolling and self.moving_ticks >= p['breakaway_confirm_ticks']:
            # first motion since (re)start: remember the PWM that broke away (accounting for the actuation and
            # measurement delay) and release at once — kinetic friction is lower than static
            self.rolling = True
            lag = int(p['detect_lag_ticks']) + int(p['breakaway_confirm_ticks']) - 1
            hist = list(self.history)
            self.learned_start_pwm = hist[-lag] if len(hist) >= lag else (hist[0] if hist else p['ff_pwm'])
            self.integrator = self.learned_start_pwm - p['release_drop_pwm'] - p['ff_pwm']
        elif self.rolling and self.still_ticks >= p['restall_ticks']:
            self.rolling = False                           # stopped again: search for breakaway again
            self.integrator = 0.0
        limit = max(p['overspeed_ratio'] * tgt, tgt + p['overspeed_margin_mps'])
        if abs(v) > limit:
            self.integrator -= p['overspeed_drop_pwm']
            self._clamp_integrator()
            return self._out(0, f'overspeed {abs(v):.2f} > {limit:.2f} m/s')
        err = tgt - speed
        if not self.rolling:
            # still at rest: ramp quickly, starting just below the last learned breakaway (if any)
            if self.integrator == 0.0 and self.learned_start_pwm is not None:
                self.integrator = max(0.0, self.learned_start_pwm - p['breakaway_margin_pwm'] - p['ff_pwm'])
            self.integrator += p['stall_ramp_pwm_per_s'] * dt_s
            u = p['ff_pwm'] + self.integrator
        else:
            self.integrator += p['ki_pwm_per_m'] * err * dt_s
            self._clamp_integrator()
            u = p['ff_pwm'] + p['kp_pwm_per_mps'] * err + self.integrator
        self._clamp_integrator()
        u = max(0.0, min(float(p['max_pwm']), u))
        if u >= p['max_pwm'] and err > 0 and self.rolling:
            self.integrator -= p['ki_pwm_per_m'] * err * dt_s       # anti-windup at the clamp
        return self._out(sign * int(round(u)), 'breakaway search' if not self.rolling else 'tracking')

    def _clamp_integrator(self):
        m = self.p['integrator_max_pwm']
        self.integrator = max(-m, min(m, self.integrator))

    def _out(self, pwm, reason, reset=False):
        if reset:
            self.integrator = 0.0
            self.rolling = False
            self.still_ticks = 0
            self.moving_ticks = 0
        self.history.append(abs(pwm))
        self.last_output, self.last_reason = pwm, reason
        return pwm


# --------------------------------------------------------------------------------------------------------------------
# yahboom_base glue (pure; tested in tests/test_speed_loop_base.py). The base calls feed() from its odometry tick and
# take() from its 0.1 s drive tick. Both timers run on one single-threaded rclpy executor.

FEEDBACK_MAX_AGE_S = 0.25    # newest consensus sample older than this -> feedback invalid -> 0 PWM


class SpeedFeedback:
    """Accumulates encoder-consensus distance between drive ticks.

    feed(delta_m, ok, now): one odometry sample. ok = packet fresh AND >= 2 coherent channels accepted.
    take(now) -> (delta_m, dt_s, ok, has_sample). When no new sample has arrived since the last take but the newest
    sample is still fresh, has_sample is False: the caller holds its last output (timer jitter, not a fault). Any
    not-ok sample since the last take makes the whole interval invalid.
    """
    def __init__(self, max_age_s=FEEDBACK_MAX_AGE_S):
        self.max_age_s = float(max_age_s)
        self.pending_m = 0.0
        self.pending_ok = True
        self.pending_n = 0
        self.last_sample_t = None
        self.last_take_t = None

    def feed(self, delta_m, ok, now):
        try:
            delta_m = float(delta_m)
        except (TypeError, ValueError):
            delta_m = math.nan
        if not math.isfinite(delta_m):
            ok, delta_m = False, 0.0
        self.pending_m += delta_m
        self.pending_ok = self.pending_ok and bool(ok)
        self.pending_n += 1
        self.last_sample_t = float(now)

    def take(self, now):
        now = float(now)
        dt = 0.0 if self.last_take_t is None else now - self.last_take_t
        fresh = self.last_sample_t is not None and now - self.last_sample_t <= self.max_age_s
        if self.pending_n == 0:
            if fresh and self.last_take_t is not None:
                return 0.0, dt, True, False          # hold; last_take_t kept so the next dt spans both ticks
            self.last_take_t = now
            return 0.0, dt, False, True
        delta, ok = self.pending_m, self.pending_ok and fresh
        self.pending_m, self.pending_ok, self.pending_n = 0.0, True, 0
        self.last_take_t = now
        return delta, dt, ok, True


def turn_split(magnitude, bias, ceiling):
    """Inside/outside PWM for a 4WS arc under the speed loop. Unlike the open-loop path (inside >= MIN_RUN_PWM 80)
    there is no high floor: the loop measures body-centre speed and closes on it."""
    magnitude = abs(int(magnitude))
    if magnitude == 0:
        return 0, 0
    return max(0, magnitude - int(bias)), min(int(ceiling), magnitude + int(bias))


def load_speed_loop_config(path):
    """Return (enabled, SpeedLoop or None, error str).

    Missing file or enabled: false -> (False, None, '') and the base keeps the legacy open-loop map.
    enabled: true with any problem -> (True, None, error): the base must then FAIL CLOSED for non-REMOTE sources
    (0 PWM), never silently fall back to the 60-PWM open-loop floor that caused the 2026-11-15 overspeed.
    """
    import yaml
    from pathlib import Path
    try:
        text = Path(path).read_text(encoding='utf-8')
    except FileNotFoundError:
        return False, None, ''
    except OSError as exc:
        return True, None, f'unreadable:{exc}'
    try:
        raw = yaml.safe_load(text) or {}
        section = raw.get('speed_loop', {}) if isinstance(raw, dict) else None
        if not isinstance(section, dict):
            return True, None, 'malformed: speed_loop section missing'
    except yaml.YAMLError as exc:
        return True, None, f'malformed:{exc}'
    enabled = section.get('enabled', False)
    if enabled is not True:
        return False, None, ''
    params = section.get('params') or {}
    if not isinstance(params, dict):
        return True, None, 'malformed: params must be a mapping'
    unknown = sorted(set(params) - set(DEFAULTS))
    if unknown:
        return True, None, f'unknown parameters: {unknown}'
    try:
        return True, SpeedLoop(params), ''
    except (ValueError, TypeError) as exc:
        return True, None, f'invalid:{exc}'

"""Phone-style battery time estimates for the ATLAS dashboard (2026-11-16, owner: "like my smartphone: 16 h left,
7 min to full"). Pure, no ROS. Read-only advice: never used for any safety or motion decision.

Inputs: the Daly BMS status (soc_percent from its coulomb counter, net pack current_a: + charging, - discharging).
- Average current: time-weighted mean over the last AVG_WINDOW_S of samples in the same mode, so short drive bursts do
  not make the estimate jump.
- Capacity (Ah): from config if given; otherwise LEARNED from the BMS itself (integrated current / change in SOC over
  a stretch of >= LEARN_MIN_DSOC percent), persisted between restarts. Until known, no time is shown.
- Time to full: constant-current part to TAPER_START_PCT at the measured current, then the LiFePO4 constant-voltage
  tail at TAPER_CURRENT_FACTOR x that current. Always labelled approximate.
- Time left: down to RESERVE_PCT (the level at which ATLAS should be back on the charger), not to 0 %.
"""
import json
import math
import time
from collections import deque
from pathlib import Path

DEFAULTS = {
    'avg_window_charge_s': 120.0,
    'avg_window_discharge_s': 300.0,
    'min_avg_span_s': 45.0,          # need this much data in one mode before showing a time
    'idle_current_a': 0.3,           # |I| below this = idle (no estimate)
    'reserve_pct': 10.0,
    'taper_start_pct': 95.0,
    'taper_current_factor': 0.4,
    'learn_min_dsoc': 3.0,           # % SOC change needed for one capacity sample
    'learn_max_gap_s': 30.0,         # a gap in BMS data restarts the learning stretch
    'capacity_min_ah': 2.0,
    'capacity_max_ah': 400.0,
    'max_sample_age_s': 15.0,
    # 2026-11-16 owner: "tell if it is fast or normal charging". LiFePO4 charge rate in C (current / capacity);
    # until the capacity is known, by pack power (W) for this 4S 12.8 V pack.
    'slow_below_c': 0.2,
    'fast_from_c': 0.5,              # 32140 LiFePO4: 0.5C is the usual standard charge rate
    'very_fast_from_c': 1.0,         # above 1C: flag it (check the cell datasheet's maximum charge current)
    'slow_below_w': 30.0,
    'fast_from_w': 80.0,
}


def charge_speed(current_a, capacity_ah, voltage_v=12.8, params=None):
    """('धीमी' | 'सामान्य' | 'तेज़', detail) for a positive charging current."""
    p = dict(DEFAULTS); p.update(params or {})
    if not _finite(current_a) or current_a <= 0:
        return None, ''
    if _finite(capacity_ah) and capacity_ah and capacity_ah > 0:
        c = current_a / capacity_ah
        if c >= p['very_fast_from_c']:
            return 'बहुत तेज़ (1C से ऊपर — cell datasheet जाँचें)', f'{c:.2f}C'
        label = 'धीमी' if c < p['slow_below_c'] else ('तेज़' if c >= p['fast_from_c'] else 'सामान्य')
        return label, f'{c:.2f}C'
    w = current_a * (voltage_v if _finite(voltage_v) and voltage_v > 0 else 12.8)
    label = 'धीमी' if w < p['slow_below_w'] else ('तेज़' if w >= p['fast_from_w'] else 'सामान्य')
    return label, f'{w:.0f} W'


def _finite(*v):
    return all(isinstance(x, (int, float)) and math.isfinite(x) for x in v)


def format_minutes_hi(minutes):
    """'≈ 2 घंटे 10 मिनट', '≈ 45 मिनट', '≈ 1 मिनट से कम'."""
    if minutes is None or not _finite(minutes) or minutes < 0:
        return None
    m = int(round(minutes))
    if m < 1:
        return '≈ 1 मिनट से कम'
    h, mm = divmod(m, 60)
    if h and mm:
        return f'≈ {h} घंटे {mm} मिनट'
    if h:
        return f'≈ {h} घंटे'
    return f'≈ {mm} मिनट'


class BatteryEta:
    def __init__(self, capacity_ah=None, state_path=None, params=None):
        self.p = dict(DEFAULTS)
        self.p.update(params or {})
        self.config_capacity = capacity_ah if _finite(capacity_ah) and capacity_ah > 0 else None
        self.state_path = Path(state_path) if state_path else None
        self.learned_capacity = None
        self.learned_samples = 0
        self._load()
        self.samples = deque(maxlen=2000)        # (t, soc, current)
        self.last_voltage = None
        self._learn = None                       # (t0, soc0, ah_acc, last_t, last_i, sign)

    # ---------------- persistence ----------------
    def _load(self):
        if not self.state_path:
            return
        try:
            d = json.loads(self.state_path.read_text(encoding='utf-8'))
            cap = float(d.get('capacity_ah'))
            if self.p['capacity_min_ah'] <= cap <= self.p['capacity_max_ah']:
                self.learned_capacity, self.learned_samples = cap, int(d.get('samples', 1))
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def _save(self):
        if not self.state_path:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'capacity_ah': round(self.learned_capacity, 3),
                                       'samples': self.learned_samples, 'updated': time.time()}), encoding='utf-8')
            tmp.replace(self.state_path)
        except OSError:
            pass

    @property
    def capacity(self):
        if self.config_capacity:
            return self.config_capacity, 'config'
        if self.learned_capacity:
            return self.learned_capacity, 'learned'
        return None, 'learning'

    # ---------------- input ----------------
    def update(self, t, soc, current, ok=True, voltage=None):
        if _finite(voltage) and voltage > 0:
            self.last_voltage = float(voltage)
        if not ok or not _finite(t, soc, current) or not 0.0 <= soc <= 100.0:
            self._learn = None
            return
        if self.samples and t <= self.samples[-1][0]:
            return
        self.samples.append((float(t), float(soc), float(current)))
        self._learn_step(float(t), float(soc), float(current))

    def _learn_step(self, t, soc, i):
        p = self.p
        sign = 1 if i > p['idle_current_a'] else (-1 if i < -p['idle_current_a'] else 0)
        L = self._learn
        if sign == 0 or L is None or L['sign'] != sign or t - L['last_t'] > p['learn_max_gap_s']:
            self._learn = None if sign == 0 else {'t0': t, 'soc0': soc, 'ah': 0.0, 'last_t': t, 'last_i': i, 'sign': sign}
            return
        L['ah'] += 0.5 * (L['last_i'] + i) * (t - L['last_t']) / 3600.0      # trapezoid, signed
        L['last_t'], L['last_i'] = t, i
        dsoc = soc - L['soc0']
        if abs(dsoc) >= p['learn_min_dsoc'] and (dsoc > 0) == (sign > 0):
            cap = abs(L['ah']) / (abs(dsoc) / 100.0)
            if p['capacity_min_ah'] <= cap <= p['capacity_max_ah']:
                n = self.learned_samples
                self.learned_capacity = cap if not self.learned_capacity else \
                    (self.learned_capacity * min(n, 9) + cap) / (min(n, 9) + 1)
                self.learned_samples = n + 1
                self._save()
            self._learn = {'t0': t, 'soc0': soc, 'ah': 0.0, 'last_t': t, 'last_i': i, 'sign': sign}

    # ---------------- output ----------------
    def _avg_current(self, now, sign):
        p = self.p
        window = p['avg_window_charge_s'] if sign > 0 else p['avg_window_discharge_s']
        pts = [(t, i) for t, _, i in self.samples if now - window <= t <= now]
        # only the most recent run in this mode
        run = []
        for t, i in reversed(pts):
            s = 1 if i > p['idle_current_a'] else (-1 if i < -p['idle_current_a'] else 0)
            if s != sign:
                break
            run.append((t, i))
        run.reverse()
        if len(run) < 2 or run[-1][0] - run[0][0] < p['min_avg_span_s']:
            return None
        area = sum(0.5 * (a[1] + b[1]) * (b[0] - a[0]) for a, b in zip(run, run[1:]))
        return area / (run[-1][0] - run[0][0])

    def estimate(self, now=None):
        p = self.p
        now = time.time() if now is None else now
        cap, cap_src = self.capacity
        out = {'mode': 'unknown', 'soc_percent': None, 'avg_current_a': None, 'capacity_ah': cap and round(cap, 2),
               'capacity_source': cap_src, 'minutes_to_full': None, 'minutes_to_reserve': None,
               'reserve_percent': p['reserve_pct'], 'text': 'Battery data नहीं है', 'approximate': True,
               'charge_speed': None, 'charge_rate': ''}
        if not self.samples or now - self.samples[-1][0] > p['max_sample_age_s']:
            return out
        _, soc, i_now = self.samples[-1]
        out['soc_percent'] = round(soc, 1)
        sign = 1 if i_now > p['idle_current_a'] else (-1 if i_now < -p['idle_current_a'] else 0)
        if sign == 0:
            out.update(mode='idle', text='न charge हो रहा, न ख़र्च (idle)')
            return out
        out['mode'] = 'charging' if sign > 0 else 'discharging'
        speed_prefix = ''
        if sign > 0:
            speed, rate = charge_speed(i_now, cap, self.last_voltage or 12.8, p)
            out['charge_speed'], out['charge_rate'] = speed, rate
            if speed:
                speed_prefix = f'{speed} charging ({rate}) · '
        avg = self._avg_current(now, sign)
        if avg is None:
            out['text'] = (speed_prefix + 'समय निकाल रहा हूँ…') if sign > 0 else 'समय निकाल रहा हूँ…'
            return out
        out['avg_current_a'] = round(avg, 2)
        if cap is None:
            out['text'] = (speed_prefix if sign > 0 else 'Discharging · ') + 'battery की क्षमता सीख रहा हूँ'
            return out
        if sign > 0:
            ts = p['taper_start_pct']
            cc = max(0.0, ts - soc) / 100.0 * cap / avg
            tail_pct = 100.0 - max(soc, ts)
            tail = tail_pct / 100.0 * cap / (avg * p['taper_current_factor']) if tail_pct > 0 else 0.0
            mins = (cc + tail) * 60.0
            out['minutes_to_full'] = round(mins, 1)
            out['text'] = speed_prefix + ('पूरा charge होने में ' + format_minutes_hi(mins) if soc < 99.5 else 'लगभग पूरा charge')
        else:
            usable = max(0.0, soc - p['reserve_pct']) / 100.0 * cap
            mins = usable / abs(avg) * 60.0
            out['minutes_to_reserve'] = round(mins, 1)
            out['text'] = (format_minutes_hi(mins) + f' बाकी ({int(p["reserve_pct"])}% तक)') if usable > 0 \
                else f'{int(p["reserve_pct"])}% से नीचे — charge कीजिए'
        return out

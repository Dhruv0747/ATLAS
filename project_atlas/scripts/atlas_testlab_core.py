#!/usr/bin/env python3
"""Motor & Encoder Test Lab: pure logic (no ROS, no HTTP, no serial, no motor API).

Everything here is deterministic and unit-testable.  Nothing in this module can move a motor: the only thing that
leaves it is a JSON *request dictionary* for the EXISTING lifted-drive commissioning protocol
(atlas_drive_pid_lifted).  The hardware owner (yahboom_base.py) validates every request again and remains the only
process that touches the STM32 board.

Safety limits are IMPORTED from atlas_drive_pid_lifted so the Test Lab can never be more permissive than the
approved commissioning limits.
"""
from __future__ import annotations

import csv
import io
import math
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Sequence

from atlas_drive_pid_lifted import (
    CONFIRMATION_PHRASE,
    MAX_HEARTBEAT_LEASE_S,
    MAX_RAW_DURATION_S,
    MAX_RAW_PWM,
    MIN_RAW_DURATION_S,
    LiftedDriveCommission,
)

WHEEL_NAMES = {1: 'M1 rear-left', 2: 'M2 rear-right', 3: 'M3 front-left', 4: 'M4 front-right'}
CIRCUMFERENCE_M = 0.392699

# Observation thresholds (display and diagnosis only; they never feed a control decision).
STALE_FRAME_S = 0.5            # newest /atlas/encoder_update older than this => STALE_DATA
STALE_PACKET_S = 0.35          # base-reported packet age limit (same as the commissioning limit)
FAULT_WINDOW_S = 4.0
FROZEN_MIN_WINDOW_S = 1.5
OTHERS_MOVING_TURNS = 0.25     # other wheels must have turned this much before "frozen / missing" is meaningful
FROZEN_TURNS = 0.02
MISSING_RATIO = 0.5
COUNT_JUMP_TURNS = 0.6
ASYMMETRY_WARN = 0.15
PASS_LO, PASS_HI = 0.75, 1.30  # one hand-turned revolution, same window as tools/diagnostics/encoder_hand_test.py
CROSSTALK_WARN = 0.10
MAX_SESSION_ROWS = 160_000
MAX_SESSION_S = 1800.0
HISTORY_FRAMES = 3000

# Heartbeat period for the lifted lease (lease is 0.5 s at the owner; 0.2 s leaves two missed beats of margin).
HEARTBEAT_PERIOD_S = 0.20
PULSE_REQUEST_FIELDS = ('op', 'session', 'seq', 'mode', 'wheel', 'pwm', 'duration_s')


def _finite(v: Any) -> bool:
    return type(v) in (int, float) and math.isfinite(v)


# ---------------------------------------------------------------- frames
@dataclass(frozen=True)
class Frame:
    rx: float                      # local monotonic receive time
    wall: float
    seq: int
    raw: tuple
    dist: tuple                    # sign-corrected, forward-positive metres (as consumed by odometry)
    cpr: tuple
    signs: tuple
    packet_fresh: Optional[bool]
    packet_age_s: Optional[float]
    accepted: tuple
    rejected: tuple


def parse_update(data: Any, rx: float, wall: float) -> Optional[Frame]:
    """Parse one /atlas/encoder_update String payload; None when it is malformed (never raises)."""
    import json
    try:
        d = json.loads(data) if isinstance(data, (str, bytes)) else data
        raw, dist = d['raw_counts'], d['wheel_distances_m']
        cpr = d.get('counts_per_revolution') or [2238.4, 2215.0, 2199.1, 2230.5]
        signs = d.get('encoder_signs') or [1, -1, 1, -1]
        for seq4 in (raw, dist, cpr, signs):
            if len(seq4) != 4 or not all(_finite(x) for x in seq4):
                return None
        age = d.get('packet_age_s')
        return Frame(rx, wall, int(d.get('sequence', -1)), tuple(int(x) for x in raw), tuple(float(x) for x in dist),
                     tuple(float(x) for x in cpr), tuple(int(x) for x in signs), d.get('packet_fresh'),
                     float(age) if _finite(age) else None,
                     tuple(int(x) for x in d.get('accepted_channels', [])),
                     tuple(int(x) for x in d.get('rejected_channels', [])))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


class FrameBuffer:
    """Thread-safe ring of recent frames."""

    def __init__(self, maxlen: int = HISTORY_FRAMES):
        self._lock = threading.Lock()
        self._frames: Deque[Frame] = deque(maxlen=maxlen)
        self.health: Dict[str, Any] = {}
        self.health_rx: Optional[float] = None
        self.total = 0

    def add(self, frame: Frame) -> None:
        with self._lock:
            self._frames.append(frame)
            self.total += 1

    def set_health(self, payload: Mapping[str, Any], rx: float) -> None:
        with self._lock:
            self.health = dict(payload)
            self.health_rx = rx

    def frames(self, window_s: Optional[float] = None, now: Optional[float] = None) -> List[Frame]:
        with self._lock:
            fr = list(self._frames)
        if window_s is None or not fr:
            return fr
        now = fr[-1].rx if now is None else now
        return [f for f in fr if now - f.rx <= window_s]

    def last(self) -> Optional[Frame]:
        with self._lock:
            return self._frames[-1] if self._frames else None

    def snapshot_health(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.health)


# ------------------------------------------------------------ per-channel view
def channel_view(frames: Sequence[Frame], health: Mapping[str, Any], now: float) -> Dict[str, Any]:
    """Live table row per channel: raw count, delta, direction, rpm estimate, freshness, health."""
    out: Dict[str, Any] = {'channels': [], 'frame_age_s': None, 'frame_rate_hz': None}
    if not frames:
        return out
    last = frames[-1]
    out['frame_age_s'] = round(max(0.0, now - last.rx), 3)
    recent = [f for f in frames if last.rx - f.rx <= 2.0]
    if len(recent) >= 2 and recent[-1].rx > recent[0].rx:
        out['frame_rate_hz'] = round((len(recent) - 1) / (recent[-1].rx - recent[0].rx), 1)
    prev = frames[-2] if len(frames) >= 2 else None
    one_s = next((f for f in reversed(frames) if last.rx - f.rx >= 1.0), frames[0])
    dt_1s = max(1e-6, last.rx - one_s.rx)
    ages = health.get('last_change_age_s') or [None] * 4
    for i in range(4):
        d_frame = (last.raw[i] - prev.raw[i]) if prev else 0
        d_1s = last.raw[i] - one_s.raw[i]
        turns_1s = (last.dist[i] - one_s.dist[i]) / CIRCUMFERENCE_M
        rpm = turns_1s / dt_1s * 60.0 if last.rx - one_s.rx >= 0.5 else None
        direction = 'still'
        if abs(turns_1s) >= 0.003:
            direction = 'forward' if turns_1s > 0 else 'reverse'
        ch = i + 1
        out['channels'].append({
            'channel': ch, 'name': WHEEL_NAMES[ch],
            'raw_count': last.raw[i], 'delta_frame': d_frame, 'delta_1s': d_1s,
            'direction': direction, 'rpm_estimate': None if rpm is None else round(rpm, 1),
            'distance_m': round(last.dist[i], 4), 'cpr': last.cpr[i], 'sign': last.signs[i],
            'last_change_age_s': ages[i] if i < len(ages) else None,
            'consensus': 'rejected' if ch in last.rejected else ('accepted' if ch in last.accepted else 'unknown'),
        })
    out['packet_fresh'] = last.packet_fresh
    out['packet_age_s'] = last.packet_age_s
    out['health_state'] = health.get('state')
    out['consensus_state'] = health.get('consensus_state')
    out['seq'] = last.seq
    return out


# --------------------------------------------------------------- fault analysis
def _turns(frames: Sequence[Frame]) -> List[float]:
    a, b = frames[0], frames[-1]
    return [(b.dist[i] - a.dist[i]) / CIRCUMFERENCE_M for i in range(4)]


def detect_faults(frames: Sequence[Frame], health: Mapping[str, Any], now: float,
                  expect: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    """Return fault dicts {code, channel, severity, detail}.  expect={'channel':n,'sign':+1|-1} during a pulse/hand test."""
    faults: List[Dict[str, Any]] = []

    def add(code, ch, sev, detail):
        faults.append({'code': code, 'channel': ch, 'severity': sev, 'detail': detail,
                       'name': WHEEL_NAMES.get(ch, 'all channels')})

    if not frames:
        add('NO_DATA', 0, 'fault', 'No /atlas/encoder_update received. Is the base driver running?')
        return faults
    last = frames[-1]
    if now - last.rx > STALE_FRAME_S:
        add('STALE_DATA', 0, 'fault', 'Last encoder frame is %.1f s old.' % (now - last.rx))
    if last.packet_fresh is False or (last.packet_age_s is not None and last.packet_age_s > STALE_PACKET_S):
        add('STALE_DATA', 0, 'fault', 'Base reports the STM32 encoder packet is stale (age %s s).' %
            ('?' if last.packet_age_s is None else '%.2f' % last.packet_age_s))
    if health and health.get('packet_fresh') is False:
        add('STALE_DATA', 0, 'fault', 'encoder_health: packet_fresh=false.')
    for ch in last.rejected:
        add('CONSENSUS_REJECTED', ch, 'warn', 'The base driver is currently excluding this encoder from odometry consensus.')
    window = [f for f in frames if last.rx - f.rx <= FAULT_WINDOW_S]
    if len(window) >= 2:
        for a, b in zip(window, window[1:]):
            if b.seq != -1 and a.seq != -1 and b.seq < a.seq:
                add('SEQUENCE_GAP', 0, 'warn', 'Encoder update sequence went backwards (base restarted?).')
                break
            for i in range(4):
                if abs(b.raw[i] - a.raw[i]) / b.cpr[i] > COUNT_JUMP_TURNS:
                    add('COUNT_JUMP', i + 1, 'warn', 'A single update changed the raw count by more than %.1f turn.' % COUNT_JUMP_TURNS)
    # Cross-channel analysis only applies to free observation; during a single-wheel pulse / hand step the other
    # wheels are EXPECTED to be still, so it is replaced by the explicit expectation below.
    if not expect and len(window) >= 2 and (window[-1].rx - window[0].rx) >= FROZEN_MIN_WINDOW_S and now - last.rx <= STALE_FRAME_S:
        t = _turns(window)
        for i in range(4):
            others = [abs(t[j]) for j in range(4) if j != i]
            moving = [x for x in others if x >= OTHERS_MOVING_TURNS]
            if not moving:
                continue
            ref = statistics.median(sorted(others, reverse=True)[:2])
            if abs(t[i]) < FROZEN_TURNS:
                add('FROZEN_COUNTS', i + 1, 'fault', 'Count did not change while other wheels moved %.2f turn.' % max(moving))
            elif abs(t[i]) / max(ref, 1e-9) < MISSING_RATIO and ref >= OTHERS_MOVING_TURNS:
                add('MISSING_PULSES', i + 1, 'fault',
                    'Counted %.2f turn while other wheels counted about %.2f turn.' % (abs(t[i]), ref))
            same = [t[j] for j in range(4) if j != i and abs(t[j]) >= OTHERS_MOVING_TURNS]
            if (len(same) >= 2 and abs(t[i]) >= 0.05 and all(s > 0 for s in same) and t[i] < 0) or \
               (len(same) >= 2 and abs(t[i]) >= 0.05 and all(s < 0 for s in same) and t[i] > 0):
                add('UNEXPECTED_SIGN', i + 1, 'warn',
                    'Moved opposite to the other wheels (ignore while the rover is pivoting or the wheels are turned separately).')
    if expect and len(window) >= 2:
        ch, sign = int(expect['channel']), int(expect['sign'])
        t = _turns(window)[ch - 1]
        if abs(t) >= 0.05 and (t > 0) != (sign > 0):
            add('UNEXPECTED_SIGN', ch, 'fault', 'Counted the wrong direction (expected %s).' % ('forward' if sign > 0 else 'reverse'))
    seen, uniq = set(), []
    for f in faults:
        k = (f['code'], f['channel'])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def direction_comparison(frames: Sequence[Frame]) -> Dict[str, Any]:
    """Forward vs reverse counting efficiency of every channel relative to the median of the other three.

    ratio ~1.0 in both directions is healthy; a direction-dependent drop is the Stage 25 failure signature.
    Only frames where the reference wheels moved are used; needs >= 0.25 turn of reference travel per direction."""
    acc = {i: {'fwd': [0.0, 0.0], 'rev': [0.0, 0.0]} for i in range(4)}
    for a, b in zip(frames, frames[1:]):
        d = [b.dist[i] - a.dist[i] for i in range(4)]
        for i in range(4):
            others = [d[j] for j in range(4) if j != i]
            ref = statistics.median(others)
            if abs(ref) < 1e-5:
                continue
            key = 'fwd' if ref > 0 else 'rev'
            acc[i][key][0] += d[i]
            acc[i][key][1] += ref
    out = []
    for i in range(4):
        row: Dict[str, Any] = {'channel': i + 1, 'name': WHEEL_NAMES[i + 1]}
        for key in ('fwd', 'rev'):
            own, ref = acc[i][key]
            row[key + '_ref_turns'] = round(abs(ref) / CIRCUMFERENCE_M, 3)
            row[key + '_ratio'] = round(own / ref, 3) if abs(ref) / CIRCUMFERENCE_M >= OTHERS_MOVING_TURNS else None
        f, r = row['fwd_ratio'], row['rev_ratio']
        row['asymmetry'] = None
        row['verdict'] = 'NEED_MORE_MOTION'
        if f is not None and r is not None and max(f, r) > 0:
            row['asymmetry'] = round(abs(f - r) / max(f, r), 3)
            row['verdict'] = 'ASYMMETRIC' if row['asymmetry'] > ASYMMETRY_WARN else 'BALANCED'
        elif f is not None or r is not None:
            row['verdict'] = 'ONE_DIRECTION_ONLY'
        out.append(row)
    return {'rows': out, 'reference': 'median of the other three channels'}


# ------------------------------------------------------------------ hand test
def evaluate_step(wheel: int, direction: str, deltas_m: Sequence[float]) -> Dict[str, Any]:
    """Classify one hand-turned revolution (same logic and thresholds as tools/diagnostics/encoder_hand_test.py)."""
    expected = CIRCUMFERENCE_M * (1.0 if direction == 'forward' else -1.0)
    own = float(deltas_m[wheel - 1])
    ratio = own / expected
    cross = max(abs(float(v)) for i, v in enumerate(deltas_m) if i != wheel - 1)
    if ratio < -0.3:
        status = 'WRONG_DIRECTION'
    elif abs(ratio) < 0.10 or ratio < 0:
        status = 'NO_COUNT'
    elif ratio < PASS_LO:
        status = 'PARTIAL'
    elif ratio > PASS_HI:
        status = 'OVERCOUNT'
    else:
        status = 'PASS'
    return {'wheel': wheel, 'direction': direction, 'ratio': round(ratio, 3), 'status': status,
            'crosstalk_turns': round(cross / CIRCUMFERENCE_M, 3), 'crosstalk_warn': cross / CIRCUMFERENCE_M > CROSSTALK_WARN}


def summarize_hand(results: Sequence[Mapping[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for w in WHEEL_NAMES:
        rs = [r for r in results if r['wheel'] == w]
        if not rs:
            out[w] = {'verdict': 'NOT_TESTED', 'notes': []}
            continue
        notes: List[str] = []
        bad = [r for r in rs if r['status'] != 'PASS']
        fw = [r['ratio'] for r in rs if r['direction'] == 'forward']
        rv = [r['ratio'] for r in rs if r['direction'] == 'reverse']
        if fw and rv:
            f, b = sum(fw) / len(fw), sum(rv) / len(rv)
            if max(f, b) > 0 and abs(f - b) / max(f, b) > ASYMMETRY_WARN:
                notes.append('DIRECTION_ASYMMETRY forward %.2f vs reverse %.2f' % (f, b))
        if any(r['crosstalk_warn'] for r in rs):
            notes.append('CROSSTALK another wheel counted while this one was turned')
        verdict = 'PASS' if not bad and not notes else 'FAIL'
        if bad:
            notes.insert(0, ', '.join('%s=%s' % (r['direction'], r['status']) for r in bad))
        out[w] = {'verdict': verdict, 'notes': notes}
    return out


class HandTest:
    """READ-ONLY guided hand rotation.  It never publishes anything; it compares two encoder snapshots."""

    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self._open: Optional[Dict[str, Any]] = None

    def begin(self, wheel: int, direction: str, frame: Frame) -> Dict[str, Any]:
        if wheel not in WHEEL_NAMES or direction not in ('forward', 'reverse'):
            raise ValueError('wheel must be 1-4 and direction forward or reverse')
        self._open = {'wheel': wheel, 'direction': direction, 'frame': frame}
        return {'wheel': wheel, 'direction': direction, 'started_seq': frame.seq}

    def finish(self, frame: Frame) -> Dict[str, Any]:
        if self._open is None:
            raise ValueError('no hand-test step is open')
        o, f0 = self._open, self._open['frame']
        deltas = [frame.dist[i] - f0.dist[i] for i in range(4)]
        res = evaluate_step(o['wheel'], o['direction'], deltas)
        res['delta_raw'] = [frame.raw[i] - f0.raw[i] for i in range(4)]
        res['delta_m'] = [round(x, 5) for x in deltas]
        self.results.append(res)
        self._open = None
        return res

    @property
    def open_step(self) -> Optional[Dict[str, Any]]:
        if self._open is None:
            return None
        o = {k: v for k, v in self._open.items() if k != 'frame'}
        o['start_dist_m'] = [round(x, 5) for x in self._open['frame'].dist]
        return o

    def summary(self) -> Dict[int, Dict[str, Any]]:
        return summarize_hand(self.results)


# ----------------------------------------------------------------- CSV session
CSV_COLUMNS = ('iso_time_utc', 'monotonic_s', 'session_id', 'mode', 'event', 'channel', 'motor', 'position',
               'raw_count', 'delta_counts', 'direction', 'rpm_estimate', 'wheel_distance_m', 'packet_age_s',
               'packet_fresh', 'health_state', 'faults', 'note')
POSITIONS = {1: 'rear_left', 2: 'rear_right', 3: 'front_left', 4: 'front_right'}


def _iso(wall: float) -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(wall)) + '.%03dZ' % int((wall % 1) * 1000)


class LabSession:
    """One recorded test session.  Rows are bounded; CSV has one row per channel per encoder frame plus event rows."""

    def __init__(self, session_id: str, mode: str, wall: float, mono: float):
        self.id, self.mode, self.started_wall, self.started_mono = session_id, mode, wall, mono
        self.rows: List[tuple] = []
        self.events: List[Dict[str, Any]] = []
        self.closed = False
        self.truncated = False
        self._prev: Optional[Frame] = None
        self.last_seq = -2

    def event(self, name: str, wall: float, mono: float, channel: Optional[int] = None, note: str = '') -> None:
        self.events.append({'t': round(mono - self.started_mono, 3), 'event': name, 'channel': channel, 'note': note})
        if len(self.rows) < MAX_SESSION_ROWS:
            self.rows.append((_iso(wall), round(mono, 4), self.id, self.mode, name, channel or '',
                              WHEEL_NAMES.get(channel, '') if channel else '', POSITIONS.get(channel, '') if channel else '',
                              '', '', '', '', '', '', '', '', '', note))

    def add_frame(self, f: Frame, health_state: Optional[str], faults: str = '') -> None:
        if self.closed or f.seq == self.last_seq:
            return
        self.last_seq = f.seq
        if f.rx - self.started_mono > MAX_SESSION_S or len(self.rows) + 4 > MAX_SESSION_ROWS:
            self.truncated = True
            self.closed = True
            return
        prev = self._prev
        for i in range(4):
            d = f.raw[i] - prev.raw[i] if prev else 0
            dd = f.dist[i] - prev.dist[i] if prev else 0.0
            dt = f.rx - prev.rx if prev else 0.0
            rpm = (dd / CIRCUMFERENCE_M) / dt * 60.0 if dt > 0 else ''
            direction = 'still' if abs(dd) < 1e-6 else ('forward' if dd > 0 else 'reverse')
            self.rows.append((_iso(f.wall), round(f.rx, 4), self.id, self.mode, 'sample', i + 1, WHEEL_NAMES[i + 1],
                              POSITIONS[i + 1], f.raw[i], d, direction, round(rpm, 2) if rpm != '' else '',
                              round(f.dist[i], 5), '' if f.packet_age_s is None else f.packet_age_s,
                              '' if f.packet_fresh is None else f.packet_fresh, health_state or '', faults, ''))
        self._prev = f

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator='\n')
        w.writerow(CSV_COLUMNS)
        w.writerows(self.rows)
        return buf.getvalue()


# --------------------------------------------------------------- pulse request
def validate_pulse(wheel: Any, direction: Any, pwm: Any, duration_s: Any) -> Dict[str, Any]:
    """Return {'wheel','pwm' (signed),'duration_s'} or raise ValueError.  Limits are the approved commissioning limits."""
    if type(wheel) is not int or wheel not in (1, 2, 3, 4):
        raise ValueError('wheel must be exactly one of 1, 2, 3, 4')
    if direction not in ('forward', 'reverse'):
        raise ValueError('direction must be forward or reverse')
    if type(pwm) is not int or not 1 <= pwm <= MAX_RAW_PWM:
        raise ValueError('pwm must be a whole number from 1 to %d' % MAX_RAW_PWM)
    if not _finite(duration_s) or not MIN_RAW_DURATION_S <= float(duration_s) <= MAX_RAW_DURATION_S:
        raise ValueError('duration must be %.2f to %.2f s' % (MIN_RAW_DURATION_S, MAX_RAW_DURATION_S))
    return {'wheel': wheel, 'pwm': pwm if direction == 'forward' else -pwm, 'duration_s': round(float(duration_s), 2)}


# ---------------------------------------------------------------- pulse run
def entry_ready(s: Mapping[str, Any]) -> bool:
    age, cells, stable = s.get('bms_age_s'), s.get('bms_cells_v'), s.get('entry_stable_s')
    return (str(s.get('state', '')).upper() == 'IDLE' and _finite(stable) and stable >= 5.0 and s.get('entry_problem') == ''
            and s.get('stop_latched') is True and s.get('remote_b_stop') is False and s.get('bms_ok') is True
            and _finite(age) and 0.0 <= age <= 10.0 and isinstance(cells, (list, tuple)) and len(cells) == 4
            and all(_finite(v) and 3.0 <= v <= 3.65 for v in cells) and max(cells) - min(cells) <= 0.1)


def operator_ready(s: Mapping[str, Any]) -> bool:
    return str(s.get('state', '')).upper() == 'LOCKED' and s.get('stop_latched') is False and s.get('arm_ready') is True


def release_ready(s: Mapping[str, Any]) -> bool:
    return (str(s.get('state', '')).upper() == 'ABORTED' and s.get('stop_latched') is True
            and s.get('remote_b_stop') is False and s.get('exit_ready') is True)


def gate_report(s: Optional[Mapping[str, Any]], status_age_s: Optional[float]) -> Dict[str, Any]:
    """Human-readable list of every commissioning condition and whether it is met right now.

    Pulse controls are enabled only when `entry_ok` is true.  Unknown / missing => NOT met (fail closed)."""
    gates: List[Dict[str, Any]] = []

    def g(key, label, ok, detail=''):
        gates.append({'key': key, 'label': label, 'ok': bool(ok), 'detail': detail})

    have = isinstance(s, Mapping) and status_age_s is not None and status_age_s <= 2.0
    s = s if have else {}
    g('status', 'Owner status topic is live', have,
      'No fresh /atlas/drive_pid/lifted/status. The base driver is not running or is an older version.' if not have else '')
    g('raw_enabled', 'Lifted raw interface enabled in the base driver', s.get('raw_interface_enabled') is True,
      'Disabled. Needs ATLAS_PID_LIFTED_RAW_ENABLED=1 in the base driver environment (owner-approved restart).')
    g('power_cut', 'Physical motor-power cut-off confirmed to the base driver', s.get('physical_power_cut_confirmed') is True,
      'Needs ATLAS_PID_LIFTED_PHYSICAL_CUTOFF_READY=1, set only after you have verified a reachable cut-off.')
    g('stop', 'Software stop latched', s.get('stop_latched') is True)
    g('remote_b', 'Remote stop button B not held', s.get('remote_b_stop') is False)
    bms = s.get('bms_ok') is True
    g('bms', 'Battery data fresh and healthy', bms)
    problem = s.get('entry_problem')
    g('entry', 'Owner entry check clean for 5 s', str(s.get('state', '')).upper() == 'IDLE' and problem == '' and
      _finite(s.get('entry_stable_s')) and s.get('entry_stable_s') >= 5.0, str(problem or ''))
    entry_ok = have and entry_ready(s) and s.get('raw_interface_enabled') is True and s.get('physical_power_cut_confirmed') is True
    return {'gates': gates, 'entry_ok': entry_ok, 'state': s.get('state') if have else None,
            'owner_problem': problem if have else 'status_unavailable'}


class PulseRun:
    """Drives exactly ONE bounded single-motor pulse through the existing lifted protocol.

    Mirrors atlas_drive_pid_lifted_client.RosStringTransport flow: enter -> (operator releases software stop) -> arm ->
    pulse -> abort -> (operator re-latches stop) -> exit.  The OWNER enforces every limit again; this class only
    sequences requests.  `publish(dict)` and `clock()` are injected.  Any failure ends in the fail-safe path
    (abort, then exit once the operator has re-latched the stop).
    """
    PHASES = ('WAIT_ENTRY', 'WAIT_LOCKED', 'WAIT_RELEASE', 'WAIT_ARMED', 'WAIT_PULSE', 'WAIT_PULSE_DONE', 'WAIT_ABORTED',
              'WAIT_RELATCH', 'WAIT_IDLE', 'DONE', 'FAILED')
    ENTRY_TIMEOUT_S = 15.0
    ACK_TIMEOUT_S = 5.0
    OPERATOR_TIMEOUT_S = 60.0
    STATUS_MAX_AGE_S = 1.0

    def __init__(self, plan: Mapping[str, Any], publish: Callable[[Dict[str, Any]], None],
                 clock: Callable[[], float] = time.monotonic, token: Optional[str] = None, first_seq: int = 0,
                 persist: Optional[Callable[[str, int], None]] = None):
        self.plan = dict(plan)
        self.publish_fn, self.clock, self.persist = publish, clock, persist
        self.session = token or LiftedDriveCommission.new_session_token()
        self.seq = first_seq - 1
        self.phase = 'WAIT_ENTRY'
        self.phase_at = clock()
        self.status: Optional[Dict[str, Any]] = None
        self.status_at = 0.0
        self.entered = False
        self.next_hb = 0.0
        self.pending_seq = -1
        self.error = ''
        self.observation: Optional[Dict[str, Any]] = None
        self.cancel_requested = False
        self.log: List[Dict[str, Any]] = []
        self.failed_over = False

    # -- helpers
    def _note(self, event: str, **kw: Any) -> None:
        self.log.append({'t': round(self.clock(), 3), 'event': event, 'phase': self.phase, **kw})

    def _set(self, phase: str) -> None:
        self.phase, self.phase_at = phase, self.clock()
        self._note('phase')

    def _send(self, op: str, **fields: Any) -> int:
        self.seq += 1
        msg = {'op': op, 'session': self.session, 'seq': self.seq, **fields}
        if self.persist:
            self.persist(self.session, self.seq + 1)
        self.publish_fn(msg)
        self._note('send', op=op, seq=self.seq)
        self.pending_seq = self.seq
        if op in ('enter', 'heartbeat'):
            self.next_hb = self.clock() + HEARTBEAT_PERIOD_S
        if op == 'enter':
            self.entered = True
        return self.seq

    @property
    def done(self) -> bool:
        return self.phase in ('DONE', 'FAILED')

    def on_status(self, status: Mapping[str, Any]) -> None:
        if not isinstance(status, Mapping):
            return
        st = dict(status)
        if str(st.get('state', '')).upper() != 'IDLE':
            fp = st.get('session_fingerprint')
            import hashlib
            if fp != hashlib.sha256(self.session.encode('ascii')).hexdigest():
                self._note('ignored_foreign_status')
                return
        self.status, self.status_at = st, self.clock()

    def _acked(self) -> bool:
        try:
            return int((self.status or {}).get('sequence_ack', (self.status or {}).get('sequence', -1))) >= self.pending_seq
        except (TypeError, ValueError):
            return False

    def _state(self) -> str:
        return str((self.status or {}).get('state', '')).upper()

    def cancel(self, reason: str = 'operator_cancel') -> None:
        self.cancel_requested = True
        self._fail_safe(reason)

    def _fail_safe(self, reason: str) -> None:
        if not self.error:
            self.error = reason
        if self.done:
            return
        if self.entered and self.phase not in ('WAIT_ABORTED', 'WAIT_RELATCH', 'WAIT_IDLE') and not self.failed_over:
            self.failed_over = True
            try:
                self._send('abort', reason=reason[:80] or 'fail_safe')
            except Exception:       # a broken transport must not hide the failure
                pass
            self._set('WAIT_ABORTED')
        elif not self.entered:
            self._set('FAILED')

    def recover(self) -> None:
        """Resume at the release step with a persisted token (web service restarted while a session was locked)."""
        self.entered = True
        self.failed_over = True
        self.error = self.error or 'recovered_after_restart'
        self._set('WAIT_RELATCH')

    # -- main step (call at 20 Hz or faster)
    def tick(self) -> None:
        if self.done:
            return
        now = self.clock()
        st = self.status
        fresh = st is not None and now - self.status_at <= self.STATUS_MAX_AGE_S
        in_lease = self.entered and self.phase not in ('WAIT_ABORTED', 'WAIT_RELATCH', 'WAIT_IDLE')
        if in_lease and now >= self.next_hb and self.phase not in ('WAIT_ENTRY',):
            self._send('heartbeat')
        if self.phase == 'WAIT_ENTRY':
            if fresh and entry_ready(st) and st.get('raw_interface_enabled') and st.get('physical_power_cut_confirmed'):
                self._send('enter', confirm=CONFIRMATION_PHRASE, lifted=True)
                self._set('WAIT_LOCKED')
            elif now - self.phase_at > self.ENTRY_TIMEOUT_S:
                self.error = 'entry_not_ready: %s' % ((st or {}).get('entry_problem') or 'status_unavailable')
                self._set('FAILED')
            return
        if self.phase != 'WAIT_RELATCH' and self.phase != 'WAIT_IDLE' and fresh is False and self.entered \
                and self.phase not in ('WAIT_ABORTED',):
            return self._fail_safe('owner_status_lost')
        if fresh and self._state() == 'ABORTED' and self.phase not in ('WAIT_ABORTED', 'WAIT_RELATCH', 'WAIT_IDLE'):
            self.error = self.error or 'owner_aborted: %s' % st.get('fault_reason')
            self.failed_over = True
            return self._set('WAIT_RELATCH')
        if self.cancel_requested and self.phase not in ('WAIT_ABORTED', 'WAIT_RELATCH', 'WAIT_IDLE'):
            return self._fail_safe('operator_cancel')
        waited = now - self.phase_at
        if self.phase == 'WAIT_LOCKED':
            if self._state() == 'LOCKED' and self._acked():
                self._set('WAIT_RELEASE')
            elif waited > self.ACK_TIMEOUT_S:
                self._fail_safe('enter_not_acknowledged')
        elif self.phase == 'WAIT_RELEASE':
            if fresh and operator_ready(st):
                self._send('arm')
                self._set('WAIT_ARMED')
            elif waited > self.OPERATOR_TIMEOUT_S:
                self._fail_safe('operator_did_not_release_stop')
        elif self.phase == 'WAIT_ARMED':
            if self._state() == 'ARMED' and self._acked():
                self._send('pulse', mode='raw_pulse', wheel=self.plan['wheel'], pwm=self.plan['pwm'],
                           duration_s=float(self.plan['duration_s']))
                self._set('WAIT_PULSE')
            elif waited > self.ACK_TIMEOUT_S:
                self._fail_safe('arm_not_acknowledged')
        elif self.phase == 'WAIT_PULSE':
            if self._state() in ('PULSE', 'REST', 'ARMED') and self._acked():
                self._set('WAIT_PULSE_DONE')
            elif waited > self.ACK_TIMEOUT_S:
                self._fail_safe('pulse_not_acknowledged')
        elif self.phase == 'WAIT_PULSE_DONE':
            obs = (st or {}).get('pulse_observation')
            if self._state() in ('REST', 'ARMED') and isinstance(obs, Mapping) and obs.get('wheel') == self.plan['wheel'] \
                    and obs.get('result') in ('MATCH', 'REVERSED', 'NO_DELTA', 'UNAVAILABLE'):
                self.observation = dict(obs)
                self._send('abort', reason='commissioning_complete')
                self._set('WAIT_ABORTED')
            elif waited > float(self.plan['duration_s']) + self.ACK_TIMEOUT_S:
                self._fail_safe('pulse_observation_missing')
        elif self.phase == 'WAIT_ABORTED':
            if self._state() == 'ABORTED':
                self._set('WAIT_RELATCH')
            elif waited > self.ACK_TIMEOUT_S and self.phase_at:
                # keep trying: abort is idempotent at the owner
                self._send('abort', reason='fail_safe_retry')
                self.phase_at = now
        elif self.phase == 'WAIT_RELATCH':
            if fresh and release_ready(st):
                self._send('exit')
                self._set('WAIT_IDLE')
            elif waited > self.OPERATOR_TIMEOUT_S * 2:
                self.error = self.error or 'operator_did_not_relatch_stop'
                self._set('FAILED')
        elif self.phase == 'WAIT_IDLE':
            if self._state() == 'IDLE' and self._acked():
                self._set('DONE')
            elif waited > self.ACK_TIMEOUT_S:
                self.error = self.error or 'exit_not_acknowledged'
                self._set('FAILED')

    def public(self) -> Dict[str, Any]:
        guidance = {
            'WAIT_ENTRY': 'Checking every commissioning condition…',
            'WAIT_LOCKED': 'Entering the owner-locked session…',
            'WAIT_RELEASE': 'ACTION NEEDED: release the software stop now (remote: sticks neutral, hold LB). No pulse happens until then.',
            'WAIT_ARMED': 'Arming…', 'WAIT_PULSE': 'Pulse requested…', 'WAIT_PULSE_DONE': 'Pulse running (bounded by the base driver).',
            'WAIT_ABORTED': 'Zeroing output…',
            'WAIT_RELATCH': 'ACTION NEEDED: latch the E-STOP / software stop again and release remote button B to close the session.',
            'WAIT_IDLE': 'Closing the session…', 'DONE': 'Finished. Output is zero and the session is closed.',
            'FAILED': 'Stopped. Output is zero.'}
        import hashlib
        return {'phase': self.phase, 'guidance': guidance[self.phase], 'error': self.error, 'plan': self.plan,
                'observation': self.observation, 'done': self.done,
                'session_fingerprint': hashlib.sha256(self.session.encode('ascii')).hexdigest()[:12],
                'needs_operator': self.phase in ('WAIT_RELEASE', 'WAIT_RELATCH')}

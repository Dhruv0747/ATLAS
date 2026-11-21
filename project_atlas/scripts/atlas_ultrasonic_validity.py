"""Local, fail-closed ultrasonic sample contract; no ROS or hardware access.

UVALID1 adds actual sample sequence/age to the legacy UNO display protocol.
host_monotonic_s is meaningful ONLY to consumers on the same Jetson boot.
This is sample validity, not physical qualification or a PATH CLEAR guarantee.
"""
import math
import os

SIDES = ('front', 'left', 'right', 'rear')

# 2026-11-20 radius-aware side stop (owner: "Yes, build it"). A 4WS turn rotates the 0.50 x 0.36 m body about the
# instantaneous centre of rotation (ICR); only the INNER side (towards the ICR) sweeps sideways much: about 9 cm at
# R 0.35 m, 6 cm at R 0.5 m and 3 cm at R >= 1 m over SIDE_SWEEP_HORIZON_M of travel (outer side <= 6 cm). The stop
# distance is that sweep + SIDE_MARGIN_M, clamped to [SIDE_MIN_STOP_M, side_stop]. Bags hall_auto2/3 (2026-11-20):
# the fixed 0.28 m blocked 15-26 % of turning commands, mostly gentle turns that sweep 2-4 cm.
SIDE_HALF_LENGTH_M, SIDE_HALF_WIDTH_M = 0.25, 0.18
SIDE_SWEEP_HORIZON_M = 0.15
SIDE_MARGIN_M = 0.05
SIDE_MIN_STOP_M = 0.10
_SWEEP_CACHE = {}


def inner_side_sweep_m(radius_m, horizon_m=SIDE_SWEEP_HORIZON_M):
    """Largest sideways reach beyond the inner side line, beside the body, while the footprint rotates about an ICR at
    |radius_m| for horizon_m of travel. Cached on 5 cm radius steps (rounded DOWN, i.e. the tighter, safer radius)."""
    r = abs(float(radius_m))
    if not math.isfinite(r) or r > 50.0:
        return 0.0
    key = max(0.05, math.floor(r / 0.05) * 0.05)
    if key in _SWEEP_CACHE:
        return _SWEEP_CACHE[key]
    hl, hw = SIDE_HALF_LENGTH_M, SIDE_HALF_WIDTH_M
    pts = [(-hl + 2 * hl * i / 25, y) for i in range(26) for y in (-hw, hw)]
    pts += [(x, -hw + 2 * hw * j / 18) for j in range(19) for x in (-hl, hl)]
    reach, steps = 0.0, 30
    for k in range(1, steps + 1):
        th = horizon_m * k / steps / key
        c, sn = math.cos(th), math.sin(th)
        for x, y in pts:
            qx = c * x - sn * (y - key)
            qy = sn * x + c * (y - key) + key           # ICR at (0, +key): left turn, inner side = +y
            if -hl <= qx <= hl and qy > hw:
                reach = max(reach, qy - hw)
    if len(_SWEEP_CACHE) > 4096:
        _SWEEP_CACHE.clear()
    _SWEEP_CACHE[key] = reach
    return reach


def side_stop_limit_m(linear, angular, side_stop):
    """Stop distance for the inner-side ultrasonic: sweep + margin, clamped to [SIDE_MIN_STOP_M, side_stop]."""
    if abs(angular) < 1e-6:
        return SIDE_MIN_STOP_M
    return max(SIDE_MIN_STOP_M, min(side_stop, inner_side_sweep_m(linear / angular) + SIDE_MARGIN_M))
CODES = ('F', 'L', 'R', 'B')
SOURCE = 'uno_r4_uvalid1'
MIN_MM, MAX_MM = 20, 4200
UINT32_MAX = 4294967295


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def invalid_snapshot(reason, stream_id, now):
    return dict(schema_version=1, source=SOURCE, stream_id=stream_id,
                host_monotonic_s=now, reason=reason, sensors={})


def parse_frame(raw, stream_id, now):
    """Decode an atomic MCU report. Never combine asynchronous Float32 topics."""
    parts = raw.split(',')
    if len(parts) != 6 or parts[0] != 'UVALID1' or not parts[1].startswith('T='):
        raise ValueError('Invalid UVALID1 frame')
    uptime = int(parts[1][2:])
    if not 0 <= uptime <= UINT32_MAX:
        raise ValueError('Invalid MCU uptime')
    sensors = {}
    for side, code, part in zip(SIDES, CODES, parts[2:]):
        if not part.startswith(code + '='):
            raise ValueError('Missing/duplicate/out-of-order ultrasonic channel')
        enabled, mm, seq, age_ms = map(int, part[2:].split(':'))
        if enabled not in (0, 1) or not 0 <= seq <= UINT32_MAX or not -1 <= age_ms <= UINT32_MAX:
            raise ValueError('Invalid sample metadata')
        if mm != -1 and not MIN_MM <= mm <= MAX_MM:
            raise ValueError('Out-of-range echo')
        state = ('DISABLED' if not enabled else 'UNINITIALIZED'
                 if seq == 0 or age_ms < 0 else 'NO_ECHO' if mm == -1 else 'VALID')
        sensors[side] = dict(state=state, range_mm=mm if state == 'VALID' else None,
                             sample_sequence=seq, sample_age_s=age_ms / 1000 if age_ms >= 0 else None)
    result = invalid_snapshot('SAMPLE_REPORT', stream_id, now)
    result.update(mcu_uptime_ms=uptime, sensors=sensors)
    return result


class ValidityWindow:
    """Expire from original receipt + MCU sample age; repeats cannot renew it.

    Malformed input invalidates every channel immediately. No automatic profile
    selection, recovery command or motion publication occurs here.
    """
    def __init__(self, timeout=1.0):
        if not finite(timeout) or not 0 < timeout <= 2:
            raise ValueError('Ultrasonic timeout must be in (0, 2] seconds')
        self.timeout = timeout
        self.stream = None
        self.samples = {}
        self.sequences = {}
        self.reason = 'MISSING'
        self.last_host = None
        self.last_uptime = None
        self.clock_offset = None

    def reject(self, reason):
        self.samples = {}
        self.reason = reason

    def ingest(self, data, now):
        try:
            stamp = data['host_monotonic_s']
            stream = data['stream_id']
            if (type(data.get('schema_version')) is not int or data.get('schema_version') != 1 or data.get('source') != SOURCE
                    or not isinstance(stream, str) or not 1 <= len(stream) <= 64
                    or not finite(stamp) or not finite(now) or not 0 <= now - stamp <= self.timeout):
                raise ValueError('INVALID_OR_STALE_ENVELOPE')
            if data.get('reason') != 'SAMPLE_REPORT':
                raise ValueError(str(data.get('reason', 'INVALID_REPORT'))[:80])
            uptime = data['mcu_uptime_ms']
            if type(uptime) is not int or not 0 <= uptime <= UINT32_MAX:
                raise ValueError('INVALID_UPTIME')
            if stream != self.stream:
                self.stream, self.sequences = stream, {}
                self.last_host = self.last_uptime = self.clock_offset = None
            if self.last_host is not None and stamp <= self.last_host:
                raise ValueError('REPLAY_OR_OUT_OF_ORDER')
            # A reboot/wrap needs a new bridge stream, never inherit old samples.
            if self.last_uptime is not None and uptime < self.last_uptime:
                raise ValueError('MCU_CLOCK_RESET')
            offset = stamp - uptime / 1000
            best_offset = offset if self.clock_offset is None else min(offset, self.clock_offset)
            transport_lag = max(0.0, offset - best_offset)
            items = data['sensors']
            if set(items) != set(SIDES):
                raise ValueError('MISSING_CHANNEL')
            samples, sequences = {}, dict(self.sequences)
            for side in SIDES:
                s = items[side]
                state, mm, age, seq = (s[k] for k in ('state', 'range_mm', 'sample_age_s', 'sample_sequence'))
                if state not in ('VALID', 'NO_ECHO', 'DISABLED', 'UNINITIALIZED') or type(seq) is not int or not 0 <= seq <= UINT32_MAX:
                    raise ValueError('INVALID_SAMPLE')
                if state == 'VALID' and (not finite(mm) or not MIN_MM <= mm <= MAX_MM or seq == 0 or not finite(age) or age < 0):
                    raise ValueError('INVALID_ECHO')
                if state in ('VALID', 'NO_ECHO') and (not finite(age) or age < 0 or seq == 0):
                    raise ValueError('INVALID_SAMPLE_AGE')
                sample_time = stamp - age - transport_lag if finite(age) else None
                previous = self.sequences.get(side)
                if state in ('VALID', 'NO_ECHO'):
                    if previous and seq == previous[0]:
                        # Same sample cannot change its measurement/state or age backwards.
                        if (mm, state) != previous[2:]:
                            raise ValueError('SAMPLE_CHANGED_WITHOUT_SEQUENCE')
                        sample_time = min(sample_time, previous[1])
                    elif previous and seq < previous[0]:
                        raise ValueError('SAMPLE_SEQUENCE_RESET')
                    sequences[side] = (seq, sample_time, mm, state)
                samples[side] = dict(state=state, range_mm=mm if state == 'VALID' else None,
                                     sample_time=sample_time)
            self.samples, self.sequences = samples, sequences
            self.last_host, self.last_uptime, self.clock_offset = stamp, uptime, best_offset
            self.reason = 'SAMPLE_REPORT'
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            self.reject(str(exc) or 'INVALID_REPORT')

    def reading(self, side, now):
        s = self.samples.get(side)
        if not s:
            return None, self.reason
        if self.last_host is None or not finite(now) or not 0 <= now - self.last_host <= self.timeout:
            return None, 'STALE_REPORT'
        if s['state'] != 'VALID':
            return None, s['state']
        if not 0 <= now - s['sample_time'] <= self.timeout:
            return None, 'STALE_SAMPLE'
        return s['range_mm'] / 1000, 'VALID'

    def veto(self, linear, angular, now, front_stop, rear_stop, side_stop):
        if (not all(finite(v) for v in (linear, angular, now, front_stop, rear_stop, side_stop))
                or min(front_stop, rear_stop, side_stop) <= 0):
            return 'AUTONOMY BLOCKED: INVALID ULTRASONIC GUARD INPUT'
        # Directional installed front/rear are required. Uninstalled side sensors
        # are not forced into service; LiDAR/footprint protection remains active.
        required = 'front' if linear > 0 else 'rear' if linear < 0 else None
        if required:
            distance, state = self.reading(required, now)
            if state != 'VALID':
                # 2026-11-15 owner: front/rear ultrasonic are a CLOSE-RANGE backup only ("not too much reliance").
                # With ATLAS_ULTRASONIC_ADVISORY=1 a missing/backlogged report no longer blocks (LiDAR availability,
                # costmaps and the camera gate stay in force); a VALID close reading still blocks below.
                if os.environ.get('ATLAS_ULTRASONIC_ADVISORY', '0') == '1':
                    return None
                return f'AUTONOMY BLOCKED: {required.upper()} ULTRASONIC {state}'
            limit = front_stop if required == 'front' else rear_stop
            if distance <= limit:
                return f'AUTONOMY BLOCKED: {required.upper()} {distance:.2f} m (stop {limit:.2f} m)'
        # Inner side of the turn = side of the ICR: sign(linear * angular). Reversing with angular > 0 turns about an ICR
        # on the RIGHT, so the right sensor guards the sweeping side (the former sign(angular) rule checked the outer
        # side when reversing). With no travel (steering only) keep the former side choice and the full limit.
        if angular > 0.05 or angular < -0.05:
            if abs(linear) >= 0.01:
                side = 'left' if linear * angular > 0 else 'right'
                limit = side_stop_limit_m(linear, angular, side_stop)
            else:
                side = 'left' if angular > 0 else 'right'
                limit = side_stop
            distance, state = self.reading(side, now)
            if state == 'VALID' and distance <= limit:
                return f'AUTONOMY BLOCKED: {side.upper()} {distance:.2f} m (stop {limit:.2f} m)'
        return None

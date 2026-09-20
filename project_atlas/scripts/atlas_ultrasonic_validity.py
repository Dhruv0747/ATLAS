"""Local, fail-closed ultrasonic sample contract; no ROS or hardware access.

UVALID1 adds actual sample sequence/age to the legacy UNO display protocol.
host_monotonic_s is meaningful ONLY to consumers on the same Jetson boot.
This is sample validity, not physical qualification or a PATH CLEAR guarantee.
"""
import math

SIDES = ('front', 'left', 'right', 'rear')
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
                return f'AUTONOMY BLOCKED: {required.upper()} ULTRASONIC {state}'
            limit = front_stop if required == 'front' else rear_stop
            if distance <= limit:
                return f'AUTONOMY BLOCKED: {required.upper()} {distance:.2f} m (stop {limit:.2f} m)'
        side = 'left' if angular > 0.05 else 'right' if angular < -0.05 else None
        if side:
            distance, state = self.reading(side, now)
            if state == 'VALID' and distance <= side_stop:
                return f'AUTONOMY BLOCKED: {side.upper()} {distance:.2f} m'
        return None

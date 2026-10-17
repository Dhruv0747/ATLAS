#!/usr/bin/env python3
"""FlySky Remote Test Lab: pure logic (no ROS, no serial, no network, no actuation).

Everything here decodes and displays radio-receiver frames.  Nothing in this module can command a motor, a servo,
the E-STOP or navigation: it has no publisher, no serial port and imports no message type.

Facts the page must never blur (see ATLAS_FLYSKY_SBUS_TEST_LAB.md):
  * A paired receiver with a lit LED proves nothing about usable data.  The link is "CONNECTED" only while valid,
    decoded frames are arriving.  Otherwise it is "SIGNAL NOT VERIFIED" (or STALE / LOST / FAILSAFE) with the exact reason.
  * SBUS carries no signal strength.  RSSI is reported as unavailable, never estimated.
  * Failsafe / frame-lost are only shown for SBUS, whose flags byte carries them.  iBUS has neither, so they are
    reported as "not observable", not as "OK".
  * Channel meaning is discovered from movement (and the owner's labels), never assumed (CH1 is not "steering").
"""
from __future__ import annotations

import csv
import io
import math
import struct
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

# ----------------------------------------------------------------- protocol constants
SBUS_LEN = 25
SBUS_HEADER = 0x0F
SBUS_ENDS = (0x00, 0x04, 0x14, 0x24, 0x34)     # 0x00 plain; the others carry SBUS2 telemetry slot ids
SBUS_CHANNELS = 16
SBUS_MIN, SBUS_MID, SBUS_MAX = 172, 992, 1811  # nominal full-scale counts (11 bit)
IBUS_LEN = 32
IBUS_HEADER = (0x20, 0x40)
IBUS_CHANNELS = 14
IBUS_MIN, IBUS_MID, IBUS_MAX = 1000, 1500, 2000

# ----------------------------------------------------------------- timing / limits
LIVE_MAX_AGE_S = 0.5      # a valid frame newer than this is "live"
STALE_MAX_AGE_S = 3.0     # older than LIVE but newer than this is "stale"; beyond it the signal is "lost"
PARTIAL_TIMEOUT_S = 0.05  # a partial frame older than this is dropped as incomplete
BUF_MAX = 256             # parser buffer bound
GRAPH_S = 30.0
GRAPH_HZ = 10.0
MOVE_SPAN = 60            # counts of travel before a channel counts as "moved" (SBUS counts; scaled for iBUS)
DIR_WINDOW_S = 0.3
MAX_SESSION_ROWS = 30_000
MAX_SESSION_S = 1500.0
SESSION_HZ = 20.0         # recorded frame rate (frames are decimated; flag changes are always recorded)
RATE_WINDOW_S = 2.0


# ----------------------------------------------------------------- frames
@dataclass(frozen=True)
class Frame:
    proto: str                      # 'sbus' | 'ibus'
    raw: Tuple[int, ...]            # channel values as received (SBUS 11-bit counts / iBUS microseconds)
    rx: float                       # monotonic receive time
    wall: float
    ch17: Optional[bool] = None     # SBUS digital channels
    ch18: Optional[bool] = None
    frame_lost: Optional[bool] = None   # SBUS flags; None = not observable on this protocol
    failsafe: Optional[bool] = None


def decode_sbus(frame: Sequence[int], rx: float = 0.0, wall: float = 0.0) -> Optional[Frame]:
    """25 bytes -> Frame, or None when it is not a well-formed SBUS frame."""
    if len(frame) != SBUS_LEN or frame[0] != SBUS_HEADER or frame[24] not in SBUS_ENDS:
        return None
    n = int.from_bytes(bytes(frame[1:23]), 'little')
    raw = tuple((n >> (11 * i)) & 0x7FF for i in range(SBUS_CHANNELS))
    flags = frame[23]
    return Frame('sbus', raw, rx, wall, bool(flags & 1), bool(flags & 2), bool(flags & 4), bool(flags & 8))


def encode_sbus(channels: Sequence[int], ch17: bool = False, ch18: bool = False, frame_lost: bool = False,
                failsafe: bool = False, end: int = 0x00) -> bytes:
    """Used by tests and the simulator only."""
    vals = list(channels) + [SBUS_MID] * (SBUS_CHANNELS - len(channels))
    n = 0
    for i, v in enumerate(vals[:SBUS_CHANNELS]):
        n |= (int(v) & 0x7FF) << (11 * i)
    flags = int(ch17) | int(ch18) << 1 | int(frame_lost) << 2 | int(failsafe) << 3
    return bytes([SBUS_HEADER]) + n.to_bytes(22, 'little') + bytes([flags, end])


def decode_ibus(frame: Sequence[int], rx: float = 0.0, wall: float = 0.0) -> Optional[Frame]:
    """32 bytes -> Frame, or None.  Checksum = 0xFFFF - sum of the first 30 bytes, little endian."""
    if len(frame) != IBUS_LEN or (frame[0], frame[1]) != IBUS_HEADER:
        return None
    if (0xFFFF - sum(frame[:30])) & 0xFFFF != frame[30] | frame[31] << 8:
        return None
    raw = tuple(frame[2 + 2 * i] | frame[3 + 2 * i] << 8 for i in range(IBUS_CHANNELS))
    return Frame('ibus', raw, rx, wall)


def encode_ibus(channels: Sequence[int]) -> bytes:
    vals = list(channels) + [IBUS_MID] * (IBUS_CHANNELS - len(channels))
    body = bytes(IBUS_HEADER) + b''.join(int(v).to_bytes(2, 'little') for v in vals[:IBUS_CHANNELS])
    return body + ((0xFFFF - sum(body)) & 0xFFFF).to_bytes(2, 'little')


class StreamParser:
    """Incremental, resynchronising parser for one protocol.  Bounded memory; counts everything it rejects."""

    def __init__(self, proto: str):
        if proto not in ('sbus', 'ibus'):
            raise ValueError('proto must be sbus or ibus')
        self.proto = proto
        self.length = SBUS_LEN if proto == 'sbus' else IBUS_LEN
        self.buf = bytearray()
        self.buf_at = 0.0
        self.bytes_in = 0
        self.valid = 0
        self.invalid = 0        # looked like a frame (header found, full length) but failed the checks
        self.incomplete = 0     # partial frame that never completed
        self.garbage = 0        # bytes skipped while looking for a header
        self.resyncs = 0

    def _header_at(self, i: int) -> bool:
        b = self.buf
        if self.proto == 'sbus':
            return b[i] == SBUS_HEADER
        return b[i] == IBUS_HEADER[0] and (i + 1 >= len(b) or b[i + 1] == IBUS_HEADER[1])

    def feed(self, data: bytes, rx: float, wall: float) -> List[Frame]:
        out: List[Frame] = []
        self.bytes_in += len(data)
        if self.buf and rx - self.buf_at > PARTIAL_TIMEOUT_S:
            self.incomplete += 1
            self.buf.clear()
        self.buf.extend(data)
        if len(self.buf) > BUF_MAX:
            del self.buf[:-BUF_MAX]
        dec = decode_sbus if self.proto == 'sbus' else decode_ibus
        while self.buf:
            i = 0
            while i < len(self.buf) and not self._header_at(i):
                i += 1
            if i:
                self.garbage += i
                self.resyncs += 1
                del self.buf[:i]
            if not self.buf:
                break
            if len(self.buf) < self.length:
                self.buf_at = rx
                break
            f = dec(bytes(self.buf[:self.length]), rx, wall)
            if f is None:
                self.invalid += 1
                self.resyncs += 1
                del self.buf[:1]
                continue
            self.valid += 1
            out.append(f)
            del self.buf[:self.length]
        return out

    def stats(self) -> Dict[str, int]:
        return {'bytes': self.bytes_in, 'valid': self.valid, 'invalid': self.invalid, 'incomplete': self.incomplete,
                'garbage_bytes': self.garbage, 'resyncs': self.resyncs}


# ----------------------------------------------------------------- normalisation
def nominal(proto: str) -> Tuple[int, int, int]:
    return (SBUS_MIN, SBUS_MID, SBUS_MAX) if proto == 'sbus' else (IBUS_MIN, IBUS_MID, IBUS_MAX)


def normalize(proto: str, raw: int) -> float:
    """-1..+1 around the nominal centre; clamped to +-1.25 so a glitch cannot fill the screen.  A nominal scale only:
    real FlySky end-points differ per transmitter, so the observed scale is shown alongside (see ChannelTracker)."""
    lo, mid, hi = nominal(proto)
    v = (raw - mid) / ((hi - mid) if raw >= mid else (mid - lo))
    return max(-1.25, min(1.25, v))


# ----------------------------------------------------------------- per-channel tracking
@dataclass
class Channel:
    index: int
    last: Optional[int] = None
    lo: Optional[int] = None
    hi: Optional[int] = None
    changes: int = 0
    last_change: Optional[float] = None
    levels: List[int] = field(default_factory=list)          # clustered values seen
    hist: Deque[Tuple[float, int]] = field(default_factory=lambda: deque(maxlen=64))


class ChannelTracker:
    LEVEL_TOL = 30

    def __init__(self, proto_hint: str = 'sbus'):
        self.proto = proto_hint
        self.ch: Dict[int, Channel] = {}

    def reset_ranges(self) -> None:
        self.ch = {}

    def update(self, f: Frame) -> None:
        self.proto = f.proto
        for i, v in enumerate(f.raw, 1):
            c = self.ch.get(i)
            if c is None:
                c = self.ch[i] = Channel(i)
            if c.last is None or abs(v - c.last) >= (2 if f.proto == 'sbus' else 3):
                if c.last is not None:
                    c.changes += 1
                    c.last_change = f.rx
            c.last = v
            c.lo = v if c.lo is None else min(c.lo, v)
            c.hi = v if c.hi is None else max(c.hi, v)
            c.hist.append((f.rx, v))
            if not any(abs(v - L) <= self.LEVEL_TOL for L in c.levels) and len(c.levels) < 9:
                c.levels.append(v)

    def move_span(self) -> int:
        return MOVE_SPAN if self.proto == 'sbus' else MOVE_SPAN * 2 // 3

    def view(self, now: float) -> List[Dict[str, Any]]:
        out = []
        span_floor = self.move_span()
        for i in sorted(self.ch):
            c = self.ch[i]
            rng = (c.hi - c.lo) if c.lo is not None else 0
            moved = rng >= span_floor
            # direction over the last DIR_WINDOW_S
            direction = 'steady'
            if c.hist:
                t1, v1 = c.hist[-1]
                ref = next((v for t, v in c.hist if t1 - t <= DIR_WINDOW_S), v1)
                thr = max(8, span_floor // 3)
                if v1 - ref > thr:
                    direction = 'up'
                elif ref - v1 > thr:
                    direction = 'down'
            n_levels = len(c.levels)
            kind = 'not moved yet'
            if moved:
                kind = 'switch' if 2 <= n_levels <= 3 else 'analog'
            norm = normalize(self.proto, c.last) if c.last is not None else None
            if c.lo is not None and rng >= 4 * span_floor:
                obs = 2.0 * (c.last - c.lo) / rng - 1.0
            else:
                obs = None
            pos = None
            if kind == 'switch' and norm is not None:
                pos = ('low' if norm < -0.33 else 'high' if norm > 0.33 else 'mid')
            out.append({'channel': i, 'raw': c.last, 'norm': None if norm is None else round(norm, 3),
                        'norm_observed': None if obs is None else round(obs, 3),
                        'min': c.lo, 'max': c.hi, 'range': rng, 'moved': moved, 'direction': direction, 'kind': kind,
                        'switch_position': pos, 'levels': n_levels,
                        'changed_ago_s': None if c.last_change is None else round(max(0.0, now - c.last_change), 2)})
        return out


# ----------------------------------------------------------------- link state
LINK_LABEL = {
    'NO_SOURCE': 'SIGNAL NOT VERIFIED', 'NO_FRAMES': 'SIGNAL NOT VERIFIED', 'LIVE': 'CONNECTED',
    'STALE': 'SIGNAL STALE', 'LOST': 'SIGNAL LOST', 'FAILSAFE': 'RECEIVER FAILSAFE', 'FRAME_LOST': 'FRAMES DROPPED',
}
NO_SOURCE_REASON = ('No receiver data source is publishing to the Jetson. The Yahboom motor board does not forward SBUS '
                    'channels to ROS, so a paired receiver is not visible here yet. A separate read-only receiver input '
                    'is needed (see the FlySky Test Lab document).')


def link_state(source_available: bool, last: Optional[Frame], now: float, invalid: int = 0,
               source_reason: str = '') -> Tuple[str, str]:
    """(state, exact reason).  CONNECTED only while valid frames are fresh and no failsafe/lost flag is set."""
    if not source_available:
        return 'NO_SOURCE', source_reason or NO_SOURCE_REASON
    if last is None:
        why = 'A receiver data source is present but no valid frame has been decoded yet'
        if invalid:
            why += ' (%d invalid frames rejected: wrong length, header, end byte or checksum, or the wrong baud/polarity)' % invalid
        return 'NO_FRAMES', why + '.'
    age = now - last.rx
    if age > STALE_MAX_AGE_S:
        return 'LOST', 'No valid frame for %.1f s. Check the receiver power and the transmitter.' % age
    if age > LIVE_MAX_AGE_S:
        return 'STALE', 'Last valid frame was %.1f s ago.' % age
    if last.failsafe:
        return 'FAILSAFE', 'The receiver is reporting failsafe (the transmitter link is lost). Channel values are the failsafe values.'
    if last.frame_lost:
        return 'FRAME_LOST', 'The receiver flagged a dropped frame. Values may be repeated.'
    return 'LIVE', 'Valid frames are arriving.'


# ----------------------------------------------------------------- session record
def csv_columns(n: int = SBUS_CHANNELS) -> Tuple[str, ...]:
    return (('iso_time_utc', 'monotonic_s', 'session_id', 'event', 'protocol', 'link_state', 'frame_age_s', 'frame_lost',
             'failsafe', 'ch17', 'ch18') + tuple('ch%d_raw' % i for i in range(1, n + 1))
            + tuple('ch%d_norm' % i for i in range(1, n + 1)) + ('note',))


def _iso(wall: float) -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(wall)) + '.%03dZ' % int((wall % 1) * 1000)


class LabSession:
    """Rows are stored compactly (ints and floats) and only formatted to text when the CSV is written."""

    def __init__(self, session_id: str, wall: float, mono: float):
        self.id, self.started_wall, self.started_mono = session_id, wall, mono
        self.rows: List[tuple] = []     # (wall, mono, event, proto, state, age, lost, failsafe, ch17, ch18, raw as packed uint16, note)
        self.closed = False
        self.truncated = False
        self._last_t = -1e9
        self._last_flags: Optional[tuple] = None
        self.frames = 0

    def event(self, name: str, wall: float, mono: float, note: str = '') -> None:
        if len(self.rows) < MAX_SESSION_ROWS:
            self.rows.append((wall, mono, name, '', '', None, None, None, None, None, b'', note))

    def add_frame(self, f: Frame, state: str, age: float) -> None:
        if self.closed:
            return
        if f.rx - self.started_mono > MAX_SESSION_S or len(self.rows) >= MAX_SESSION_ROWS:
            self.truncated = self.closed = True
            return
        flags = (f.frame_lost, f.failsafe, f.ch17, f.ch18, state)
        if f.rx - self._last_t < 1.0 / SESSION_HZ and flags == self._last_flags:
            return
        self._last_t, self._last_flags = f.rx, flags
        self.rows.append((f.wall, f.rx, 'sample', f.proto, state, age, f.frame_lost, f.failsafe, f.ch17, f.ch18,
                          struct.pack('<%dH' % len(f.raw), *f.raw), ''))
        self.frames += 1

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator='\n')
        w.writerow(csv_columns())
        yn = lambda v: '' if v is None else int(bool(v))   # noqa: E731  (None = not observable on this protocol)
        pad = SBUS_CHANNELS
        for wall, mono, ev, proto, state, age, lost, fs, c17, c18, raw, note in self.rows:
            raw = struct.unpack('<%dH' % (len(raw) // 2), raw)
            rawc = list(raw) + [''] * (pad - len(raw))
            norm = [round(normalize(proto, v), 4) for v in raw] + [''] * (pad - len(raw))
            w.writerow((_iso(wall), round(mono, 4), self.id, ev, proto, state, '' if age is None else round(age, 3),
                        yn(lost), yn(fs), yn(c17), yn(c18)) + tuple(rawc) + tuple(norm) + (note,))
        return buf.getvalue()


# ----------------------------------------------------------------- the lab (everything but I/O)
class FlyskyLab:
    """Feed it receiver frames (as hex strings from a data source); read a snapshot.  Holds no I/O and no threads."""

    def __init__(self):
        self.parsers = {'sbus': StreamParser('sbus'), 'ibus': StreamParser('ibus')}
        self.tracker = ChannelTracker()
        self.last: Optional[Frame] = None
        self.arrivals: Deque[float] = deque(maxlen=512)
        self.t: Deque[float] = deque(maxlen=int(GRAPH_S * GRAPH_HZ) + 8)
        self.g: Deque[Tuple[float, ...]] = deque(maxlen=int(GRAPH_S * GRAPH_HZ) + 8)
        self._g_at = -1e9
        self.flag_counts = {'frame_lost': 0, 'failsafe': 0}
        self.total_frames = 0
        self.session: Optional[LabSession] = None
        self.source_msgs = 0
        self.bad_messages = 0

    def ingest_message(self, msg: Any, rx: float, wall: float) -> int:
        """msg: {"proto":"sbus"|"ibus","hex":"0f..."} from the data source.  Returns the number of valid frames."""
        try:
            proto = msg['proto']
            data = bytes.fromhex(msg['hex'])
            if proto not in self.parsers or not 0 < len(data) <= 4 * IBUS_LEN:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            self.bad_messages += 1
            return 0
        self.source_msgs += 1
        n = 0
        for f in self.parsers[proto].feed(data, rx, wall):
            self._accept(f)
            n += 1
        return n

    def _accept(self, f: Frame) -> None:
        self.last = f
        self.total_frames += 1
        self.arrivals.append(f.rx)
        self.tracker.update(f)
        if f.frame_lost:
            self.flag_counts['frame_lost'] += 1
        if f.failsafe:
            self.flag_counts['failsafe'] += 1
        if f.rx - self._g_at >= 1.0 / GRAPH_HZ:
            self._g_at = f.rx
            self.t.append(f.rx)
            self.g.append(tuple(round(normalize(f.proto, v), 3) for v in f.raw))
        if self.session is not None:
            st, _ = link_state(True, f, f.rx)
            self.session.add_frame(f, st, 0.0)

    def invalid_total(self) -> int:
        return sum(p.invalid + p.incomplete for p in self.parsers.values())

    def rate_hz(self, now: float) -> float:
        n = sum(1 for a in self.arrivals if now - a <= RATE_WINDOW_S)
        return round(n / RATE_WINDOW_S, 1)

    def tick(self, now: float) -> None:
        """Expire partial frames even when no new bytes arrive."""
        for p in self.parsers.values():
            if p.buf and now - p.buf_at > PARTIAL_TIMEOUT_S:
                p.incomplete += 1
                p.buf.clear()

    def snapshot(self, now: float, source_available: bool, source_reason: str = '', history: bool = True) -> Dict[str, Any]:
        state, why = link_state(source_available, self.last, now, self.invalid_total(), source_reason)
        f = self.last
        age = None if f is None else round(now - f.rx, 3)
        sbus = f is not None and f.proto == 'sbus'
        snap: Dict[str, Any] = {
            'link': {'state': state, 'label': LINK_LABEL[state], 'reason': why, 'verified': state == 'LIVE',
                     'frame_age_s': age, 'rate_hz': self.rate_hz(now), 'frames_total': self.total_frames,
                     'protocol': None if f is None else f.proto,
                     'live_max_age_s': LIVE_MAX_AGE_S, 'stale_max_age_s': STALE_MAX_AGE_S},
            'frames': {p: s.stats() for p, s in ((k, v) for k, v in self.parsers.items())},
            'bad_source_messages': self.bad_messages,
            'flags': {
                'observable': sbus,
                'frame_lost': None if not sbus else bool(f.frame_lost),
                'failsafe': None if not sbus else bool(f.failsafe),
                'frame_lost_count': self.flag_counts['frame_lost'], 'failsafe_count': self.flag_counts['failsafe'],
                'note': ('SBUS flags byte.' if sbus else
                         'Not observable: iBUS carries no failsafe or frame-lost flag.' if f is not None
                         else 'Not observable until a frame is decoded.'),
            },
            'rssi': {'available': False, 'note': 'Not available. SBUS and iBUS carry no signal-strength value; none is estimated.'},
            'digital': None if not sbus else {'ch17': bool(f.ch17), 'ch18': bool(f.ch18)},
            'channels': self.tracker.view(now) if f is not None else [],
            'session': None if self.session is None else {'id': self.session.id, 'rows': len(self.session.rows),
                                                          'frames': self.session.frames, 'truncated': self.session.truncated},
        }
        if history:
            n = len(f.raw) if f is not None else 0
            snap['graph'] = {'t': [round(x - now, 2) for x in self.t],
                             'ch': [[row[i] if i < len(row) else None for row in self.g] for i in range(n)]}
        return snap

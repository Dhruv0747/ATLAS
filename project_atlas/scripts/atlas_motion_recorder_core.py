"""Bounded, motor-independent capture state machine for diagnostic ROS bags.

The caller supplies a bag sink. The core never publishes ROS messages, touches
motor services, or deletes data. All timing decisions use monotonic seconds;
each message retains its original ROS receive timestamp for bag playback.
"""

from collections import Counter, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Sample:
    topic: str
    type_name: str
    payload: bytes
    monotonic_s: float
    ros_time_ns: int


class RecorderEngine:
    def __init__(self, sink_factory, *, pre_s=10.0, post_s=10.0,
                 pre_max_bytes=64 * 1024 * 1024, cap_bytes=500 * 1024 * 1024):
        self.sink_factory = sink_factory
        self.pre_s = pre_s
        self.post_s = post_s
        self.pre_max_bytes = pre_max_bytes
        self.cap_bytes = cap_bytes
        self.buffer = deque()
        self.buffer_bytes = 0
        self.sink = None
        self.capture_bytes = 0
        self.last_motion_s = None
        self.capture_start_s = None
        self.dropped = Counter()
        self.received = Counter()
        self.last_seen = {}
        self.pinned = {}
        self.completed = []
        self.disabled_reason = None

    def _evict(self, now_s):
        while self.buffer and (now_s - self.buffer[0].monotonic_s > self.pre_s
                               or self.buffer_bytes > self.pre_max_bytes):
            old = self.buffer.popleft()
            self.buffer_bytes -= len(old.payload)
            self.dropped['prebuffer_evicted'] += 1

    def _write(self, sample):
        if self.capture_bytes + len(sample.payload) > self.capture_limit_bytes:
            self.dropped['capture_cap'] += 1
            self.close('capture_cap')
            self.disabled_reason = 'capture_cap'
            return
        try:
            self.sink.write(sample)
            self.capture_bytes += len(sample.payload)
        except Exception as exc:
            self.dropped['write_error'] += 1
            self.close('write_error')
            self.disabled_reason = f'write_error:{type(exc).__name__}'

    def ingest(self, sample):
        self.received[sample.topic] += 1
        self.last_seen[sample.topic] = sample.monotonic_s
        if self.disabled_reason:
            return
        self.buffer.append(sample)
        self.buffer_bytes += len(sample.payload)
        self._evict(sample.monotonic_s)
        if self.sink is not None:
            self._write(sample)

    def pin(self, sample):
        """Retain the newest latched context without extending the ten-second ring."""
        self.pinned[sample.topic] = sample
        self.received[sample.topic] += 1
        self.last_seen[sample.topic] = sample.monotonic_s
        if self.sink is not None:
            self._write(sample)

    def motion(self, now_s):
        if self.disabled_reason:
            return
        self.last_motion_s = now_s
        if self.sink is not None:
            return
        try:
            self.sink = self.sink_factory()
            self.capture_limit_bytes = min(self.cap_bytes,
                                           getattr(self.sink, 'budget_bytes', self.cap_bytes))
            self.capture_start_s = now_s
            self.capture_bytes = 0
            first_ns = self.buffer[0].ros_time_ns if self.buffer else 0
            for sample in self.pinned.values():
                if self.sink is None:
                    break
                self._write(Sample(sample.topic, sample.type_name, sample.payload,
                                   now_s, first_ns or sample.ros_time_ns))
            for sample in self.buffer:
                if self.sink is None:
                    break
                self._write(sample)
        except Exception as exc:
            self.sink = None
            self.disabled_reason = f'open_error:{type(exc).__name__}'
            self.dropped['open_error'] += 1

    def tick(self, now_s):
        self._evict(now_s)
        if (self.sink is not None and self.last_motion_s is not None
                and now_s - self.last_motion_s >= self.post_s):
            self.close('stopped')

    def close(self, reason='shutdown'):
        if self.sink is None:
            return
        sink, self.sink = self.sink, None
        try:
            sink.close(reason, dict(self.dropped), dict(self.received))
        except Exception:
            self.dropped['close_error'] += 1
        self.completed.append(reason)
        self.capture_start_s = None
        self.capture_bytes = 0

    def health(self, now_s, required_topics):
        missing = sorted(t for t in required_topics if t not in self.last_seen)
        stale = sorted(t for t in required_topics
                       if t in self.last_seen and now_s - self.last_seen[t] > 2.0)
        return dict(active=self.sink is not None, disabled=self.disabled_reason,
                    missing=missing, stale=stale, dropped=dict(self.dropped),
                    received=dict(self.received),
                    buffered_bytes=self.buffer_bytes,
                    payload_bytes=self.capture_bytes,
                    middleware_drops='unmeasured')

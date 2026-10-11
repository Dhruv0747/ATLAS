"""Bounded, ordered bag worker. Caller never performs disk I/O or waits for it."""
from collections import Counter, deque
import threading
import time


class QueuedWriter:
    def __init__(self, sink_factory, max_bytes=32*1024*1024, max_messages=30000):
        self.sink_factory = sink_factory
        self.max_bytes, self.max_messages = max_bytes, max_messages
        self.cv = threading.Condition()
        self.queue = deque()
        self.bytes = 0
        self.peak_bytes = 0
        self.peak_messages = 0
        self.busy = False
        self.stopping = False
        self.error = None
        self.counts = Counter()
        self.capture_count = 0
        self.last_path = None
        self.thread = threading.Thread(target=self._run, name='atlas-bag-writer', daemon=True)
        self.thread.start()

    def _enqueue(self, kind, data):
        size = len(data.payload) if kind == 'write' else 0
        with self.cv:
            if self.stopping:
                raise RuntimeError('writer stopping')
            if self.error and kind != 'close':
                self.counts['rejected_after_error'] += 1
                raise RuntimeError(self.error)
            if kind != 'close' and (self.bytes+size > self.max_bytes or len(self.queue) >= self.max_messages):
                self.counts['queue_overflow'] += 1
                raise BufferError('bounded recorder queue full')
            self.queue.append((kind, data, size))
            self.bytes += size
            self.peak_bytes = max(self.peak_bytes, self.bytes)
            self.peak_messages = max(self.peak_messages, len(self.queue))
            if kind == 'write':
                self.counts['accepted'] += 1
            self.cv.notify_all()

    def open_capture(self):
        self._enqueue('open', None)
        owner = self

        class Capture:
            def write(self, sample):
                owner._enqueue('write', sample)

            def write_many(self, samples):
                # Atomic bounded transfer: no per-sample lock/notify or disk I/O.
                batch = [('write', s, len(s.payload)) for s in samples]
                size = sum(entry[2] for entry in batch)
                with owner.cv:
                    if owner.stopping or owner.error:
                        raise RuntimeError(owner.error or 'writer stopping')
                    if owner.bytes+size > owner.max_bytes or len(owner.queue)+len(batch) > owner.max_messages:
                        owner.counts['queue_overflow'] += len(batch)
                        raise BufferError('bounded recorder queue full')
                    owner.queue.extend(batch)
                    owner.bytes += size
                    owner.peak_bytes = max(owner.peak_bytes, owner.bytes)
                    owner.peak_messages = max(owner.peak_messages, len(owner.queue))
                    owner.counts['accepted'] += len(batch)
                    owner.cv.notify_all()

            def close(self, reason, dropped, received):
                owner._enqueue('close', (reason, dropped, received))

        return Capture()

    def _run(self):
        sink = None
        payload_bytes = 0
        while True:
            with self.cv:
                self.cv.wait_for(lambda: self.queue or self.stopping)
                if not self.queue:
                    return
                kind, data, size = self.queue.popleft()
                self.bytes -= size
                self.busy = True
            try:
                if kind == 'open':
                    if self.error:
                        continue
                    if sink is not None:
                        raise RuntimeError('capture ordering violation')
                    sink = self.sink_factory()
                    payload_bytes = 0
                    self.last_path = str(getattr(sink, 'path', ''))
                    self.capture_count += 1
                elif kind == 'write':
                    if self.error or sink is None:
                        self.counts['discarded_after_error'] += 1
                        continue
                    if payload_bytes+size > getattr(sink, 'budget_bytes', 500*1024*1024):
                        raise OSError('capture storage budget exhausted')
                    sink.write(data)
                    payload_bytes += size
                    self.counts['written'] += 1
                elif kind == 'close' and sink is not None:
                    closing, sink = sink, None
                    reason, dropped, received = data
                    drops = dict(dropped)
                    drops.update({'worker_'+k: v for k,v in self.counts.items()
                                  if k not in ('accepted','written')})
                    closing.close('worker_error' if self.error else reason, drops, received)
            except Exception as exc:
                self.error = f'{kind}:{type(exc).__name__}:{exc}'
                self.counts['worker_errors'] += 1
                if kind == 'write':
                    self.counts['failed_writes'] += 1
                if sink is not None:
                    failed, sink = sink, None
                    try:
                        failed.close('worker_error', dict(self.counts), {})
                    except Exception:
                        self.counts['close_errors'] += 1
            finally:
                with self.cv:
                    self.busy = False
                    self.cv.notify_all()

    def wait_idle(self, timeout=15):
        with self.cv:
            return self.cv.wait_for(lambda: not self.queue and not self.busy, timeout)

    def shutdown(self, timeout=15):
        with self.cv:
            self.stopping = True
            self.cv.notify_all()
        self.thread.join(timeout)
        return not self.thread.is_alive()

    def health(self):
        with self.cv:
            return {'queue_bytes': self.bytes, 'queue_messages': len(self.queue),
                    'peak_queue_bytes': self.peak_bytes, 'peak_queue_messages': self.peak_messages,
                    'busy': self.busy, 'alive': self.thread.is_alive(), 'error': self.error,
                    'captures': self.capture_count, 'last_path': self.last_path,
                    'counters': dict(self.counts)}

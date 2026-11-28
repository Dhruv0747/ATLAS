"""Optional bounded original-message cache for existing web callbacks.
No node, subscriber, publisher, camera access or background thread. Disabled
unless the host explicitly constructs it. Overflow is latched, never truncated
into apparently complete TF evidence. Messages are treated as immutable.
"""
from collections import deque
import threading
import time

class ContextCache:
    def __init__(self, clock=time.monotonic):
        self.clock=clock;self.lock=threading.Lock();self.dynamic=deque()
        self.static={};self.latest={};self.error=None

    def put(self, kind, message):
        try:
            with self.lock:
                now=self.clock()
                if kind=='tf':
                    while self.dynamic and now-self.dynamic[0][0]>.5:self.dynamic.popleft()
                    if len(message.transforms)>64 or len(self.dynamic)>=128:
                        raise ValueError('dynamic TF cache bound exceeded')
                    self.dynamic.append((now,message))
                elif kind=='tf_static':
                    key=tuple((t.header.frame_id,t.child_frame_id) for t in message.transforms)
                    if not key or len(key)>64:raise ValueError('invalid static TF batch')
                    self.static[key]=message
                    if sum(len(m.transforms) for m in self.static.values())>128:
                        self.static.pop(key,None)
                        raise ValueError('static TF cache bound exceeded')
                elif kind in ('odom','scan'):
                    if kind=='scan' and len(message.ranges)>10000:raise ValueError('scan cache bound exceeded')
                    self.latest[kind]=(now,message)
                else:raise ValueError('unsupported context kind')
        except Exception as exc:
            # Optional evidence must not interrupt existing Recovery/TF callbacks.
            self.error=str(exc)

    def snapshot(self):
        with self.lock:
            if self.error:raise ValueError(self.error)
            now=self.clock()
            dynamic=[m for received,m in self.dynamic if 0<=now-received<=.5]
            if not dynamic or not self.static or set(self.latest)!={'odom','scan'}:
                raise ValueError('original TF/odom/scan evidence missing')
            if any(not 0<=now-t<=.5 for t,m in self.latest.values()):raise ValueError('context receipt stale')
            return dict(tf=dynamic,tf_static=list(self.static.values()),
                        **{k:m for k,(t,m) in self.latest.items()})


def listener_class(base):
    """Decorate the EXISTING TransformListener, retaining original TFMessage CDR."""
    class RecordingListener(base):
        def __init__(self, buffer, node, cache):
            self.capture_cache=cache
            super().__init__(buffer,node)
        def callback(self,data):
            super().callback(data)
            self.capture_cache.put('tf',data)
        def static_callback(self,data):
            super().static_callback(data)
            self.capture_cache.put('tf_static',data)
    return RecordingListener

"""Opt-in service-call evidence; never adds calls, retries, waits or control authority.

An empty response proves transport completion, not particle-filter acceptance.
Diagnostic failure must leave the original Future and exception semantics intact.
"""
import hashlib
import json
import os
import time
import uuid

class InitializationObserver:
    def __init__(self, node, *, emit=None, encode=None):
        self.session = uuid.uuid4().hex
        self.node, self.emit, self.encode = node, emit, encode
        self.failures = 0
        if emit is None and os.environ.get('ATLAS_CHECKPOINT_EVENTS') == '1':
            try:
                from std_msgs.msg import String
                from rclpy.qos import QoSProfile, ReliabilityPolicy
                from rclpy.serialization import serialize_message
                pub = node.create_publisher(String, '/atlas/diagnostics/initialization_event',
                    QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT))
                self.emit = lambda e: pub.publish(String(data=json.dumps(e, separators=(',', ':'))))
                self.encode = serialize_message
            except Exception:
                self.failures += 1

    def event(self, phase, service, token, message=None, error=None):
        if self.emit is None: return
        try:
            e = {'schema':1, 'session':self.session, 'call_id':token,
                 'phase':phase, 'service':service, 'monotonic_ns':time.monotonic_ns(),
                 'ros_ns':self.node.get_clock().now().nanoseconds,
                 'semantic_acceptance':'unverified'}
            if message is not None:
                raw = bytes(self.encode(message))
                if len(raw)>4096: raise ValueError('bounded service evidence limit exceeded')
                e.update(cdr_hex=raw.hex(), sha256=hashlib.sha256(raw).hexdigest(),
                         type=type(message).__module__+'.'+type(message).__name__)
            if error is not None: e['error_class']=type(error).__name__
            self.emit(e)
        except Exception: self.failures += 1

    def call(self, client, request, service):
        if self.emit is None: return client.call_async(request)
        token = uuid.uuid4().hex
        self.event('request_attempt', service, token, request)
        try: future = client.call_async(request)
        except Exception as exc:
            self.event('request_exception', service, token, error=exc)
            raise
        def done(f):
            try:
                response = f.result()
                self.event('response_received', service, token, response)
            except Exception as exc: self.event('response_exception', service, token, error=exc)
        try: future.add_done_callback(done)
        except Exception: self.failures += 1
        return future

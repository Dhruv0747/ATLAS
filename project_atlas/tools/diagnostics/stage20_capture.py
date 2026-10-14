#!/usr/bin/env python3
"""Finite startup evidence collector. Development sandbox only; no ROS publishers.

Reuses commissioned topic list, CDR SQLite sink and bounded disk worker. Collector
receipt order is NOT estimator consumption order. Missing proof fails fidelity.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from atlas_motion_recorder import TOPICS, STEERING_VALIDATION_EXTRA, RosbagSink, owned_bytes, MIB
from atlas_motion_recorder_core import Sample
from atlas_motion_recorder_writer import QueuedWriter
from stage19_contract import require_isolation

EXTRA = ('/initialpose', '/parameter_events', '/amcl/transition_event',
         '/atlas/diagnostics/ekf_state', '/atlas/diagnostics/initialization_event',
         '/atlas_amcl/processing', '/diagnostics')
TOPIC_LIST = tuple(dict.fromkeys(TOPICS + STEERING_VALIDATION_EXTRA + EXTRA))

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(MIB), b''): h.update(block)
    return h.hexdigest()

def process_io():
    try: return Path('/proc/self/io').read_text()
    except OSError: return 'unavailable in private proc namespace; use rusage block I/O'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', action='store_true')
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--duration', type=float, default=30)
    p.add_argument('--quota-mib', type=int, default=500)
    p.add_argument('--identity-file', action='append', default=[], type=Path)
    a = p.parse_args()
    if not a.record or not 5 <= a.duration <= 600 or not 64 <= a.quota_mib <= 500:
        p.error('explicit opt-in; duration 5..600 s and quota 64..500 MiB required')
    isolation = require_isolation()
    if not a.root.is_absolute() or a.root == Path('/') or a.root.is_symlink():
        p.error('specific absolute non-symlink root required')
    a.root.mkdir(parents=True, exist_ok=True)
    if a.root.resolve() != a.root: p.error('symlinked parent refused')
    import fcntl
    lock = (a.root / '.stage20.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    import rclpy
    import rosbag2_py
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from rclpy.serialization import serialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from std_msgs.msg import String
    from rcl_interfaces.srv import ListParameters, GetParameters
    started = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_SELF)
    io_before = process_io()
    quota = a.quota_mib * MIB
    remaining = quota - owned_bytes(a.root)
    if remaining < 40*MIB: raise OSError('root quota reserve exhausted; no evidence deleted')
    worker = QueuedWriter(lambda: RosbagSink(a.root, remaining-32*MIB, rosbag2_py), max_bytes=8*MIB)
    capture = worker.open_capture()
    rclpy.init()
    n = Node('atlas_stage20_capture', enable_rosout=False, start_parameter_services=False)
    counts, drops = Counter(), Counter()
    subs, endpoints, parameter_snapshots, futures, clients = {}, {}, {}, [], []
    seq = 0
    session = uuid.uuid4().hex
    reason = 'duration_complete'
    first_headers = {}

    def receive(topic, type_name, message):
        nonlocal seq
        received = n.get_clock().now().nanoseconds
        mono = time.monotonic()
        seq += 1; counts[topic] += 1
        stamp = getattr(getattr(message, 'header', None), 'stamp', None)
        source = None if stamp is None else stamp.sec*1000000000+stamp.nanosec
        first_headers.setdefault(topic, source)
        raw = serialize_message(message)
        ledger = String(data=json.dumps({'seq': seq, 'topic': topic, 'source_ns': source,
            'receive_ros_ns': received, 'receive_monotonic_ns': time.monotonic_ns(),
            'payload_sha256': hashlib.sha256(raw).hexdigest()}, separators=(',', ':')))
        try:
            capture.write_many((Sample(topic, type_name, raw, mono, received),
                Sample('/atlas/diagnostics/capture_receipt', 'std_msgs/msg/String',
                       serialize_message(ledger), mono, received)))
        except (BufferError, RuntimeError): drops[topic] += 1

    def discover():
        for topic, types in n.get_topic_names_and_types():
            if topic not in TOPIC_LIST or topic in subs or len(types) != 1: continue
            pubs = n.get_publishers_info_by_topic(topic)
            if not pubs: continue
            # BEST_EFFORT accepts reliable and best-effort writers; static state is transient.
            q = QoSProfile(depth=200, reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.TRANSIENT_LOCAL if topic == '/tf_static'
                else DurabilityPolicy.VOLATILE)
            endpoints[topic] = [{'node': x.node_namespace+'/'+x.node_name,
                'gid': list(x.endpoint_gid), 'qos': str(x.qos_profile)} for x in pubs]
            try:
                t = types[0]
                subs[topic] = n.create_subscription(get_message(t), topic,
                    lambda m, topic=topic, t=t: receive(topic, t, m), q)
            except Exception as exc: drops['subscription:'+topic] += 1
        for node in ('/atlas_ekf', '/amcl'):
            if node in parameter_snapshots: continue
            client = n.create_client(ListParameters, node+'/list_parameters'); clients.append(client)
            if not client.service_is_ready(): n.destroy_client(client); clients.remove(client); continue
            parameter_snapshots[node] = {'status': 'pending'}
            f = client.call_async(ListParameters.Request(depth=0)); futures.append(f)
            def names_done(f, node=node):
                try:
                    names = f.result().result.names
                    c = n.create_client(GetParameters, node+'/get_parameters'); clients.append(c)
                    g = c.call_async(GetParameters.Request(names=names)); futures.append(g)
                    def values_done(g):
                        try: parameter_snapshots[node] = {'names': names,
                            'values': message_to_ordereddict(g.result()), 'sampled_ns': n.get_clock().now().nanoseconds}
                        except Exception: parameter_snapshots[node] = {'status':'failed'}
                    g.add_done_callback(values_done)
                except Exception: parameter_snapshots[node] = {'status':'failed'}
            f.add_done_callback(names_done)

    identities = {str(x): digest(x) for x in a.identity_file}
    try:
        next_discovery = started
        while time.monotonic()-started < a.duration:
            if time.monotonic() >= next_discovery:
                discover(); next_discovery = time.monotonic()+1
                if owned_bytes(a.root) > quota-16*MIB:
                    reason = 'storage_reserve_reached'; break
            if worker.error: reason = 'writer_error'; break
            rclpy.spin_once(n, timeout_sec=.05)
    finally:
        capture.close(reason, dict(drops), dict(counts))
        drained = worker.wait_idle(20); stopped = worker.shutdown(20)
        n.destroy_node(); rclpy.shutdown()
        if not drained or not stopped: raise RuntimeError('writer did not finalize; checkpoint incomplete')
    after = resource.getrusage(resource.RUSAGE_SELF)
    path = Path(worker.last_path)
    if not path.is_dir(): raise RuntimeError('no completed bag')
    evidence = {'schema':1, 'session_id':session,
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'isolation':isolation, 'counts':dict(counts), 'drops':dict(drops),
        'middleware_drops':'unmeasured', 'first_source_stamps':first_headers,
        'endpoints':endpoints, 'parameter_snapshots':parameter_snapshots,
        'identities':identities, 'writer':worker.health(),
        'status':'NATIVE_PUBLIC_CAPTURE_ONLY', 'complete_restorable_checkpoint':False,
        'consumer_order_verified':False, 'startup_before_sources':False,
        'service_events_complete':False, 'amcl_rng_restored':False,
        'cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
        'wall_seconds':time.monotonic()-started, 'peak_rss_kib':after.ru_maxrss,
        'io_before':io_before, 'io_after':process_io(),
        'block_write_bytes':(after.ru_oublock-before.ru_oublock)*512,
        'free_bytes':__import__('shutil').disk_usage(a.root).free,
        'files':{x.name:digest(x) for x in path.iterdir() if x.is_file()}}
    (path/'stage20_evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps({'path':str(path), 'cpu_seconds':evidence['cpu_seconds'],
        'wall_seconds':evidence['wall_seconds'], 'peak_rss_kib':evidence['peak_rss_kib'],
        'counts':dict(counts), 'complete_restorable_checkpoint':False}))

if __name__ == '__main__': main()

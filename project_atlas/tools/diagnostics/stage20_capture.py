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
import signal
import socket
import struct
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from atlas_motion_recorder import TOPICS, STEERING_VALIDATION_EXTRA, RosbagSink, owned_bytes, MIB
from atlas_motion_recorder_core import Sample
from atlas_motion_recorder_writer import QueuedWriter
from stage19_contract import require_isolation

EXTRA = ('/initialpose', '/parameter_events', '/amcl/transition_event',
         '/clock',
         '/atlas/diagnostics/ekf_state', '/atlas/diagnostics/initialization_event',
         '/atlas/diagnostics/amcl_event', '/atlas/diagnostics/ekf_event',
         '/atlas_amcl/processing', '/diagnostics')
TOPIC_LIST = tuple(dict.fromkeys(TOPICS + STEERING_VALIDATION_EXTRA + EXTRA))
KNOWN_TYPES = {
    '/amcl_pose':'geometry_msgs/msg/PoseWithCovarianceStamped',
    '/scan':'sensor_msgs/msg/LaserScan','/scan_raw':'sensor_msgs/msg/LaserScan',
    '/odom':'nav_msgs/msg/Odometry','/yahboom/odom':'nav_msgs/msg/Odometry',
    '/im10a/imu/bias_corrected_candidate':'sensor_msgs/msg/Imu',
    '/im10a/imu/unvalidated':'sensor_msgs/msg/Imu', '/imu/data':'sensor_msgs/msg/Imu',
    '/tf':'tf2_msgs/msg/TFMessage','/tf_static':'tf2_msgs/msg/TFMessage',
    '/particle_cloud':'nav2_msgs/msg/ParticleCloud',
    '/initialpose':'geometry_msgs/msg/PoseWithCovarianceStamped',
    '/parameter_events':'rcl_interfaces/msg/ParameterEvent',
    '/atlas/diagnostics/ekf_state':'std_msgs/msg/String',
    '/atlas/diagnostics/ekf_event':'std_msgs/msg/String',
    '/atlas/diagnostics/amcl_event':'std_msgs/msg/String',
    '/atlas/diagnostics/initialization_event':'std_msgs/msg/String',
    '/clock':'rosgraph_msgs/msg/Clock',
}
KNOWN_TYPES.update({t:'geometry_msgs/msg/Twist' for t in TOPICS if t.startswith('/cmd_vel')})
KNOWN_TYPES.update({'/yahboom/encoder/m'+str(i):'std_msgs/msg/Int32' for i in range(1,5)})
KNOWN_TYPES.update({t:'std_msgs/msg/String' for t in (
    '/atlas/encoder_update','/atlas/encoder_health','/atlas/control_policy','/steering/mode')})
KNOWN_TYPES.update({t:'std_msgs/msg/Float32' for t in (
    '/steering/front_angle_deg','/steering/rear_angle_deg')})

# Required continuous sources for the opt-in stationary profile. AMCL/particles
# can legitimately be event-driven while stopped: require receipt, not a new pose
# every two seconds. Raw IMU is retained when published, but is not a second gyro
# authority. No required localization topic is removed from the inherited list.
STATIONARY_CONTINUOUS=('/scan','/odom','/yahboom/odom','/im10a/imu/bias_corrected_candidate',
    '/tf','/atlas/encoder_update','/atlas/control_policy','/cmd_vel',
    '/steering/front_angle_deg','/steering/rear_angle_deg')+tuple('/yahboom/encoder/m'+str(i) for i in range(1,5))
STATIONARY_ONCE=('/amcl_pose','/particle_cloud','/tf_static')

def stationary_health(last_seen, now):
    missing=sorted(set(STATIONARY_CONTINUOUS+STATIONARY_ONCE)-last_seen.keys())
    stale=sorted(t for t in STATIONARY_CONTINUOUS if t in last_seen and
                 (not 0<=now-last_seen[t]<=2.0))
    return {'missing':missing,'stale':stale}

def final_reason(reason, stopping):
    # The last callback may request a stop exactly at the receipt deadline.
    return stopping[0] if reason == 'duration_complete' and stopping else reason

def public_profile(duration, quota, stationary_30):
    expected=30 if stationary_30 else 120
    if duration!=expected or quota!=500:
        raise ValueError('production public capture requires exact %s s/500 MiB profile'%expected)
    return 'stationary_30_v1' if stationary_30 else 'legacy_public_120'

class Timing:
    def __init__(self):
        self.bounds=(.001,.005,.01,.05,.1,.5,1.,float('inf'))
        self.counts=[0]*len(self.bounds);self.maximum=0.;self.total=0.;self.n=0
    def add(self,value):
        value=max(0.,value);self.maximum=max(self.maximum,value);self.total+=value;self.n+=1
        for i,bound in enumerate(self.bounds):
            if value<=bound:self.counts[i]+=1;break
    def summary(self):
        return {'count':self.n,'max_s':self.maximum,'mean_s':self.total/max(1,self.n),
            'bucket_upper_s':[v if v!=float('inf') else None for v in self.bounds],
            'bucket_counts':self.counts}

HEADER_TYPES={'sensor_msgs/msg/LaserScan','sensor_msgs/msg/Imu','nav_msgs/msg/Odometry',
              'geometry_msgs/msg/PoseWithCovarianceStamped','nav2_msgs/msg/ParticleCloud'}

def serialized_source_stamp(raw,type_name):
    """Read only the first standard CDR Header/TF stamp, without reserialization.

The entire original CDR is retained. TF ledger uses its first transform stamp,
not an assertion that every transform has that stamp. Unsupported types return None.
"""
    if len(raw)<12:return None
    endian='<' if raw[1]&1 else '>'
    offset=4 if type_name in HEADER_TYPES else None
    if type_name=='tf2_msgs/msg/TFMessage':
        count=struct.unpack_from(endian+'I',raw,4)[0]
        if count==0 or len(raw)<16:return None
        offset=8
    if offset is None:return None
    sec,nsec=struct.unpack_from(endian+'iI',raw,offset)
    if nsec>=1000000000:raise ValueError('invalid source nanoseconds')
    return sec*1000000000+nsec

class TimedSink(RosbagSink):
    def __init__(self,*args):
        super().__init__(*args);self.delay=Timing();self.write_latency=Timing()
    def write(self,sample):
        started=time.monotonic();self.delay.add(started-sample.monotonic_s)
        super().write(sample);self.write_latency.add(time.monotonic()-started)
    def close(self,*args):
        super().close(*args)
        (self.path/'stage20_writer_timing.json').write_text(json.dumps({
            'queue_to_sqlite_call':self.delay.summary(),'sqlite_write_call':self.write_latency.summary(),
            'physical_fsync_latency':'unmeasured'},indent=2))

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(MIB), b''): h.update(block)
    return h.hexdigest()

def process_io():
    try: return Path('/proc/self/io').read_text()
    except OSError: return 'unavailable in private proc namespace; use rusage block I/O'

def notify_ready():
    address=os.environ.get('NOTIFY_SOCKET')
    if address:
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sock:
            sock.sendto(b'READY=1\nSTATUS=Known subscriptions created; fidelity not yet verified',
                '\0'+address[1:] if address.startswith('@') else address)

def main():
    import resource
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', action='store_true')
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--duration', type=float, default=30)
    p.add_argument('--quota-mib', type=int, default=500)
    p.add_argument('--identity-file', action='append', default=[], type=Path)
    p.add_argument('--ready-file', type=Path, help='exclusive sandbox readiness marker; not fidelity proof')
    p.add_argument('--recording-ready-file',type=Path,help='exclusive test marker after stationary sensor preflight')
    p.add_argument('--sim-time', action='store_true',help='isolated deterministic fixtures only')
    p.add_argument('--approval-config',type=Path,help='separately approved finite production capture; default OFF')
    p.add_argument('--public-only',action='store_true',help='lower-fidelity read-only sidecar; never requests internal checkpoint services')
    p.add_argument('--stationary-30',action='store_true',help='separate opt-in: 10s sensor preflight, at most 30s receipts, shared 10s flush budget')
    a = p.parse_args()
    if not a.record or not 5 <= a.duration <= 600 or not 64 <= a.quota_mib <= 500:
        p.error('explicit opt-in; duration 5..600 s and quota 64..500 MiB required')
    if a.stationary_30:
        if not a.public_only:p.error('stationary-30 requires public-only scope')
        public_profile(a.duration,a.quota_mib,True)
    if a.approval_config:
        if a.sim_time:p.error('production capture cannot change its clock')
        from stage20_production_gate import verify_approval
        isolation=verify_approval(a.approval_config,stationary_30=a.stationary_30)
        if isolation['mode']=='read_only_partial_public' and not a.public_only:
            p.error('partial-sidecar approval requires public-only mode')
        if a.public_only:
            if isolation['mode']!='read_only_partial_public' or str(a.root)!=isolation['capture_root']:
                p.error('production partial capture requires exact approved scope and output root')
            public_profile(a.duration,a.quota_mib,a.stationary_30)
            from stage20_public_preflight import check
            check()  # GET only: reject this diagnostic, never change safety state.
    else:isolation = require_isolation()
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
    from rclpy.serialization import serialize_message, deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from std_msgs.msg import String
    from rcl_interfaces.srv import ListParameters, GetParameters
    from std_srvs.srv import Trigger
    started = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_SELF)
    io_before = process_io()
    quota = a.quota_mib * MIB
    remaining = quota - owned_bytes(a.root)
    if remaining < 40*MIB: raise OSError('root quota reserve exhausted; no evidence deleted')
    worker = QueuedWriter(lambda: TimedSink(a.root, remaining-32*MIB, rosbag2_py), max_bytes=8*MIB)
    capture = worker.open_capture()
    rclpy.init()
    n = Node('atlas_stage20_capture', enable_rosout=False, start_parameter_services=False)
    if a.sim_time:
        from rclpy.parameter import Parameter
        n.set_parameters([Parameter('use_sim_time',value=True)])
    counts, drops = Counter(), Counter()
    subs, endpoints, parameter_snapshots, futures, clients = {}, {}, {}, [], []
    publisher_seen={}
    seq = 0
    last_seen={}
    recording_started=None if a.stationary_30 else started
    recording_deadline=None if a.stationary_30 else started+a.duration
    sensor_preflight=None
    receipt_first=None;receipt_last=None
    session = uuid.uuid4().hex
    reason = 'duration_complete'
    stopping = []
    signal.signal(signal.SIGTERM, lambda *ignored: stopping.append('sigterm'))
    signal.signal(signal.SIGINT, lambda *ignored: stopping.append('sigint'))
    first_headers = {}
    callback_timing=Timing()
    boot_future=[]
    boot_client=None if a.public_only else n.create_client(Trigger,'/atlas_ekf/checkpoint_bootstrap')

    def receive(topic, type_name, message):
        nonlocal seq,receipt_first,receipt_last
        received = n.get_clock().now().nanoseconds
        mono = time.monotonic()
        if a.stationary_30 and isinstance(message,bytes):
            source=serialized_source_stamp(message,type_name)
            if topic in STATIONARY_CONTINUOUS and source is not None and not -.5<= (received-source)/1e9 <=2:
                stopping.append('invalid_source_freshness');return
            if topic in ('/atlas/control_policy','/cmd_vel'):
                value=deserialize_message(message,get_message(type_name))
                if topic=='/atlas/control_policy':
                    policy=json.loads(value.data)
                    safe=policy.get('stop_latched') is True and policy.get('source')=='STOPPED' and policy.get('commission_armed') is False
                else:
                    safe=all(v==0 for v in (value.linear.x,value.linear.y,value.linear.z,value.angular.x,value.angular.y,value.angular.z))
                if not safe:stopping.append('nonstationary_control_state');return
        last_seen[topic]=mono
        if a.stationary_30 and (recording_deadline is None or mono>=recording_deadline):return
        receipt_first=mono if receipt_first is None else receipt_first
        receipt_last=mono
        seq += 1; counts[topic] += 1
        if isinstance(message,bytes):
            raw=message;source=serialized_source_stamp(raw,type_name)
        else:
            stamp = getattr(getattr(message, 'header', None), 'stamp', None)
            source = None if stamp is None else stamp.sec*1000000000+stamp.nanosec
            raw=serialize_message(message)
        first_headers.setdefault(topic, source)
        ledger = String(data=json.dumps({'seq': seq, 'topic': topic, 'source_ns': source,
            'receive_ros_ns': received, 'receive_monotonic_ns': time.monotonic_ns(),
            'payload_sha256': hashlib.sha256(raw).hexdigest()}, separators=(',', ':')))
        try:
            capture.write_many((Sample(topic, type_name, raw, mono, received),
                Sample('/atlas/diagnostics/capture_receipt', 'std_msgs/msg/String',
                       serialize_message(ledger), mono, received)))
        except (BufferError, RuntimeError): drops[topic] += 1
        callback_timing.add(time.monotonic()-mono)

    def subscribe(topic, t):
        q = QoSProfile(depth=200, reliability=ReliabilityPolicy.RELIABLE if a.stationary_30 and topic=='/tf_static' else ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL if topic in (
                '/tf_static','/atlas/diagnostics/amcl_event','/atlas/diagnostics/ekf_event')
            else DurabilityPolicy.VOLATILE)
        subs[topic] = n.create_subscription(get_message(t), topic,
            lambda m, topic=topic, t=t: receive(topic, t, m), q, raw=True)

    # Subscribe BEFORE producers advertise. Discovery only verifies actual endpoints/types.
    for topic,t in KNOWN_TYPES.items(): subscribe(topic,t)
    ready = {'session_id':session, 'phase':'KNOWN_SUBSCRIPTIONS_CREATED',
        'ros_ns':n.get_clock().now().nanoseconds,'monotonic_ns':time.monotonic_ns(),
        'topics':KNOWN_TYPES,'consumer_startup_verified':False}
    if a.ready_file:
        if not a.ready_file.is_absolute() or a.ready_file.exists() or a.ready_file.is_symlink():
            raise ValueError('new absolute readiness path required')
        with a.ready_file.open('x') as f: json.dump(ready,f)
    notify_ready()

    def discover():
        if boot_client is not None and not boot_future and boot_client.service_is_ready():
            f=boot_client.call_async(Trigger.Request());boot_future.append(f)
            def boot_done(f):
                try:
                    result=f.result()
                    if result.success:
                        receive('/atlas/diagnostics/ekf_bootstrap','std_msgs/msg/String',String(data=result.message))
                    else:drops['bootstrap_unavailable']+=1
                except Exception:drops['bootstrap_request_failed']+=1
            f.add_done_callback(boot_done)
        for topic, types in n.get_topic_names_and_types():
            if topic not in TOPIC_LIST or len(types) != 1: continue
            pubs = n.get_publishers_info_by_topic(topic)
            if not pubs: continue
            endpoints[topic] = [{'node': x.node_namespace+'/'+x.node_name,
                'gid': list(x.endpoint_gid), 'qos': str(x.qos_profile)} for x in pubs]
            identity=json.dumps(endpoints[topic],sort_keys=True)
            if publisher_seen.get(topic)!=identity:
                receive('/atlas/diagnostics/publisher_event','std_msgs/msg/String',
                    String(data=json.dumps({'phase':'PUBLISHER_DISCOVERED',
                        'topic':topic,'endpoints':endpoints[topic],
                        'readiness_proves_consumption':False})))
                publisher_seen[topic]=identity
            if topic in KNOWN_TYPES and types[0]!=KNOWN_TYPES[topic]:
                drops['type_mismatch:'+topic]+=1
            if topic in subs: continue
            try:
                subscribe(topic,types[0])
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
        if a.stationary_30:
            # No samples written during this finite readiness phase. Existing raw
            # subscriptions collect receipt freshness without synthetic data.
            preflight_deadline=time.monotonic()+10
            while time.monotonic()<preflight_deadline and not stopping:
                rclpy.spin_once(n,timeout_sec=.05)
                sensor_preflight=stationary_health(last_seen,time.monotonic())
                if not sensor_preflight['missing'] and not sensor_preflight['stale']:break
            sensor_preflight=stationary_health(last_seen,time.monotonic())
            if stopping:reason=stopping[0]
            elif sensor_preflight['missing'] or sensor_preflight['stale']:reason='sensor_preflight_failed'
            else:
                if a.approval_config:check()
                recording_started=time.monotonic();recording_deadline=recording_started+30
                # Preflight is not bag evidence. Re-request retained static TF
                # through normal DDS subscription semantics; never republish or
                # request an AMCL update merely to obtain a pose sample.
                n.destroy_subscription(subs['/tf_static'])
                subscribe('/tf_static',KNOWN_TYPES['/tf_static'])
                if a.recording_ready_file:
                    if not a.recording_ready_file.is_absolute() or a.recording_ready_file.is_symlink():raise ValueError('absolute exclusive marker required')
                    with a.recording_ready_file.open('x') as f:json.dump({'started':recording_started,'deadline':recording_deadline},f)
        next_discovery = started
        while recording_deadline is not None and time.monotonic()<recording_deadline:
            if stopping: reason = stopping[0]; break
            if time.monotonic() >= next_discovery:
                discover(); next_discovery = time.monotonic()+1
                if a.stationary_30:
                    health=stationary_health(last_seen,time.monotonic())
                    if health['missing'] or health['stale']:
                        reason='sensor_became_unavailable';break
                    if a.approval_config:
                        try:check()
                        except Exception:reason='resource_or_safety_refused';break
                if owned_bytes(a.root) > quota-16*MIB:
                    reason = 'storage_reserve_reached'; break
                if __import__('shutil').disk_usage(a.root).free < 1024*MIB:
                    reason = 'disk_free_reserve_reached'; break
                if drops:
                    reason = 'capture_loss'; break
            if worker.error: reason = 'writer_error'; break
            rclpy.spin_once(n, timeout_sec=min(.05,max(0.,recording_deadline-time.monotonic())))
    except BaseException:
        reason='capture_exception'
        raise
    finally:
        reason=final_reason(reason, stopping)
        flush_started=time.monotonic()
        capture.close(reason, dict(drops), dict(counts))
        if a.stationary_30:
            drained=worker.wait_idle(10)
            stopped=worker.shutdown(max(0.,10-(time.monotonic()-flush_started)))
        else:
            drained = worker.wait_idle(20); stopped = worker.shutdown(20)
        n.destroy_node(); rclpy.shutdown()
        flush_elapsed=time.monotonic()-flush_started
        if not drained or not stopped: raise RuntimeError('writer did not finalize; checkpoint incomplete')
    after = resource.getrusage(resource.RUSAGE_SELF)
    path = Path(worker.last_path)
    if not path.is_dir(): raise RuntimeError('no completed bag')
    capture_missing_required=sorted(set(STATIONARY_CONTINUOUS+STATIONARY_ONCE)-counts.keys()) if a.stationary_30 else []
    evidence = {'schema':1, 'session_id':session,
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'isolation':isolation, 'counts':dict(counts), 'drops':dict(drops),
        'readiness':ready, 'missing_topics':sorted(set(KNOWN_TYPES)-counts.keys()),
        'callback_timing':callback_timing.summary(),
        'capture_profile':'stationary_30_v1' if a.stationary_30 else 'legacy',
        'end_reason':reason,'sensor_preflight':sensor_preflight,
        'recording_started_monotonic_s':recording_started,
        'recording_deadline_monotonic_s':recording_deadline,
        'first_receipt_monotonic_s':receipt_first,'last_receipt_monotonic_s':receipt_last,
        'capture_missing_required':capture_missing_required,
        'public_topic_window_complete':reason=='duration_complete' and not drops and not worker.error and not capture_missing_required,
        'flush_elapsed_s':flush_elapsed,
        'middleware_drops':'unmeasured', 'first_source_stamps':first_headers,
        'endpoints':endpoints, 'parameter_snapshots':parameter_snapshots,
        'identities':identities, 'writer':worker.health(),
        'status':'PARTIAL_PUBLIC_CAPTURE' if a.public_only else 'NATIVE_PUBLIC_CAPTURE_ONLY',
        'public_only':a.public_only, 'initial_state_history':'NOT_CAPTURED' if a.public_only else 'requires_event_audit',
        'full_ekf_covariance_available':False if a.public_only else 'requires_event_audit',
        'actual_consumed_measurements_available':False if a.public_only else 'requires_event_audit',
        'relative_wheel_reference_available':False if a.public_only else 'requires_event_audit',
        'complete_restorable_checkpoint':False,
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
    if (a.stationary_30 and (reason!='duration_complete' or capture_missing_required)) or reason not in ('duration_complete','sigterm','sigint') or drops or worker.error:
        return 2  # Optional diagnostic service fails; never retries or affects controls.
    return 0

if __name__ == '__main__': sys.exit(main())

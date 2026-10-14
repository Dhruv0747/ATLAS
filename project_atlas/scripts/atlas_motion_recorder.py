#!/usr/bin/env python3
"""Opt-in motion-triggered ROS bag recorder; no control publications.

This is deliberately not installed as a service. `--record` is required to
write bags; deployment and any background operation need operator approval.
"""

import argparse
import gc
import json
import math
import os
from pathlib import Path
import shutil
import signal
import time
import urllib.request
import uuid

from atlas_motion_recorder_core import RecorderEngine, Sample
from atlas_motion_recorder_writer import QueuedWriter


# Subset of record_atlas_demonstration.sh: no camera stream or full /map.
TOPICS = (
    '/scan', '/scan_raw', '/odom', '/yahboom/odom', '/amcl_pose',
    '/tf', '/tf_static', '/imu/data',
    '/im10a/imu/bias_corrected_candidate',
    '/yahboom/encoder/m1', '/yahboom/encoder/m2',
    '/yahboom/encoder/m3', '/yahboom/encoder/m4',
    '/atlas/encoder_health', '/atlas/control_policy',
    '/cmd_vel', '/cmd_vel_joy', '/cmd_vel_web', '/cmd_vel_teleop',
    '/cmd_vel_nav', '/cmd_vel_commission', '/cmd_vel_recovery',
    '/steering/front_angle_deg', '/steering/rear_angle_deg', '/steering/mode',
)
REQUIRED = ('/scan', '/odom', '/yahboom/odom', '/amcl_pose', '/tf',
            '/atlas/encoder_health', '/atlas/control_policy')
# Opt-in engineering profile. The existing/default recorder remains unchanged.
STEERING_VALIDATION_EXTRA = (
    '/atlas/encoder_update', '/im10a/imu/unvalidated', '/im10a/status',
    '/particle_cloud', '/lidar/odom', '/lidar/odom_raw',
    '/odom/lidar_fused_candidate', '/atlas/steering_calibration/status',
    '/joy', '/bms/status', '/bms/voltage',
    '/atlas/steering_validation/marker',
    '/atlas/steering_validation/event', '/atlas/steering_validation/status',
    '/atlas/steering_calibration/request', '/im10a/dashboard_json',
)
STEERING_VALIDATION_REQUIRED = REQUIRED + (
    '/scan_raw', '/atlas/encoder_update', '/im10a/imu/unvalidated',
    '/im10a/imu/bias_corrected_candidate', '/particle_cloud', '/lidar/odom',
    '/yahboom/encoder/m1', '/yahboom/encoder/m2',
    '/yahboom/encoder/m3', '/yahboom/encoder/m4',
    '/steering/front_angle_deg', '/steering/rear_angle_deg', '/bms/status',
)
MIB = 1024 * 1024


def recording_profile(name):
    if name == 'default':
        return TOPICS, REQUIRED, 10.0
    if name == 'steering-validation':
        return TOPICS + STEERING_VALIDATION_EXTRA, STEERING_VALIDATION_REQUIRED, 20.0
    raise ValueError('unknown recorder profile')


def topic_health(recorder, now, required):
    health = recorder.health(now, required)
    # BMS normally publishes every five seconds; do not call normal cadence stale.
    health['stale'] = sorted(t for t in required if t in recorder.last_seen
                             and now - recorder.last_seen[t] > (12.0 if t == '/bms/status' else 2.0))
    return health


def steering_changed(previous, value):
    """A recording trigger only; no steering or traction command is generated."""
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('nonfinite commanded steering sample')
    return previous is not None and abs(value - previous) >= 0.1


def owned_bytes(root):
    """Count only this recorder's sessions; never remove or alter old evidence."""
    return sum(p.stat().st_size for d in root.glob('capture_*') if d.is_dir()
               for p in d.rglob('*') if p.is_file())


class RosbagSink:
    def __init__(self, root, budget_bytes, rosbag2_py):
        if budget_bytes < 5 * MIB:
            raise OSError('recorder quota exhausted')
        if shutil.disk_usage(root).free < 1024 * MIB:
            raise OSError('less than 1 GiB free; recording disabled')
        self.path = root / ('capture_' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
                            + '_' + uuid.uuid4().hex[:8])
        self.writer = rosbag2_py.SequentialWriter()
        self.writer.open(rosbag2_py.StorageOptions(uri=str(self.path), storage_id='sqlite3'),
                         rosbag2_py.ConverterOptions('', ''))
        self.rosbag2_py = rosbag2_py
        self.budget_bytes = budget_bytes
        self.topics = set()
        self.counts = {}
        self.payload_bytes = 0
        self.started_utc = time.time()

    def write(self, sample):
        if sample.topic not in self.topics:
            self.writer.create_topic(self.rosbag2_py.TopicMetadata(
                name=sample.topic, type=sample.type_name, serialization_format='cdr'))
            self.topics.add(sample.topic)
        self.writer.write(sample.topic, sample.payload, sample.ros_time_ns)
        self.counts[sample.topic] = self.counts.get(sample.topic, 0) + 1
        self.payload_bytes += len(sample.payload)

    def close(self, reason, dropped=None, received=None):
        writer, self.writer = self.writer, None
        if hasattr(writer, 'close'):
            writer.close()
        del writer
        gc.collect()  # Humble bindings may only finalize metadata on destruction.
        manifest = dict(reason=reason, started_utc=self.started_utc,
                        closed_utc=time.time(), counts=self.counts,
                        dropped=dropped or {}, received=received or {},
                        middleware_drops='unmeasured',
                        payload_bytes=self.payload_bytes,
                        bag_bytes=sum(p.stat().st_size for p in self.path.rglob('*')
                                      if p.is_file()))
        (self.path / 'atlas_capture_manifest.json').write_text(
            json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


def is_motion(topic, message):
    if topic == '/cmd_vel':
        return (abs(message.linear.x) > 0.01 or abs(message.angular.z) > 0.01)
    if topic == '/yahboom/odom':
        return (abs(message.twist.twist.linear.x) > 0.02 or
                abs(message.twist.twist.angular.z) > 0.03)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true',
                        help='explicit opt-in; do not use before deployment approval')
    parser.add_argument('--root', type=Path,
                        default=Path('/home/jetson/project_atlas/data/diagnostics/motion_capture'))
    parser.add_argument('--duration', type=float, default=0,
                        help='exit after this many seconds; zero runs until stopped')
    parser.add_argument('--stationary-probe', action='store_true',
                        help='one diagnostic-only capture after 12 s; requires fresh latched/stopped status')
    parser.add_argument('--profile', choices=('default', 'steering-validation'), default='default',
                        help='Stage 17 adds raw gyro/exact encoder/particle data and steering-change capture')
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration < 0:
        parser.error('duration must be finite and nonnegative')
    if not args.record:
        parser.error('no recording started; --record is required')
    if args.profile == 'steering-validation' and not 30 <= args.duration <= 600:
        parser.error('steering-validation requires a bounded --duration of 30..600 seconds')
    if not args.root.is_absolute() or args.root == Path('/'):
        parser.error('root must be a specific absolute diagnostics directory')

    import rclpy
    import rosbag2_py
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    args.root.mkdir(parents=True, exist_ok=True)
    if args.root.is_symlink():
        parser.error('recording root must not be a symlink')
    import fcntl
    lock = (args.root / '.recorder.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error('another recorder already owns this capture root')

    rclpy.init()
    node = Node('atlas_motion_recorder')
    subscriptions = {}
    quota = 500 * MIB

    def open_sink():
        remaining = quota - owned_bytes(args.root) - 20 * MIB
        return RosbagSink(args.root, remaining, rosbag2_py)

    writer = QueuedWriter(open_sink)
    selected_topics, required_topics, post_s = recording_profile(args.profile)
    recorder = RecorderEngine(writer.open_capture, cap_bytes=quota, post_s=post_s)
    steering_previous = {}
    started = time.monotonic()
    probe_done = False
    stopped = False
    reported_state = None
    middleware_events = {'reported_lost': 0, 'unsupported_topics': []}
    sensor_qos = QoSProfile(depth=50, reliability=ReliabilityPolicy.BEST_EFFORT)
    reliable_qos = QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE)
    static_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                            durability=DurabilityPolicy.TRANSIENT_LOCAL)

    def make_callback(topic, type_name, msg_class):
        def callback(raw):
            mono = time.monotonic()
            sample = Sample(topic, type_name, bytes(raw), mono,
                            node.get_clock().now().nanoseconds)
            if topic == '/tf_static':
                recorder.pin(sample)
            else:
                recorder.ingest(sample)
            if args.profile == 'steering-validation' and topic in (
                    '/steering/front_angle_deg', '/steering/rear_angle_deg'):
                try:
                    value = float(deserialize_message(raw, msg_class).data)
                    changed = steering_changed(steering_previous.get(topic), value)
                    steering_previous[topic] = value
                    if changed:
                        recorder.motion(mono)  # Capture event only, including stationary sweeps.
                except (ValueError, TypeError, AttributeError):
                    recorder.dropped['steering_decode_error'] += 1
            if topic in ('/cmd_vel', '/yahboom/odom'):
                try:
                    moving = is_motion(topic, deserialize_message(raw, msg_class))
                except Exception:
                    recorder.dropped['motion_decode_error'] += 1
                    return
                if moving:
                    recorder.motion(mono)
        return callback

    def discover():
        for topic, types in node.get_topic_names_and_types():
            if topic not in selected_topics or topic in subscriptions or len(types) != 1:
                continue
            try:
                msg_class = get_message(types[0])
                qos = static_qos if topic == '/tf_static' else (
                    sensor_qos if topic in ('/scan', '/scan_raw', '/imu/data')
                    or topic.startswith('/im10a/') else reliable_qos)
                endpoints = node.get_publishers_info_by_topic(topic)
                if topic != '/tf_static' and any(e.qos_profile.reliability == ReliabilityPolicy.BEST_EFFORT for e in endpoints):
                    qos = sensor_qos
                try:
                    from rclpy.qos_event import SubscriptionEventCallbacks
                    def lost(event):
                        middleware_events['reported_lost'] += event.total_count_change
                    events = SubscriptionEventCallbacks(message_lost=lost)
                    subscriptions[topic] = node.create_subscription(
                        msg_class, topic, make_callback(topic, types[0], msg_class), qos,
                        raw=True, event_callbacks=events)
                except Exception as event_error:
                    if not isinstance(event_error, ImportError) and type(event_error).__name__ not in ('UnsupportedEventTypeException', 'UnsupportedEventTypeError'):
                        raise
                    middleware_events['unsupported_topics'].append(topic)
                    subscriptions[topic] = node.create_subscription(
                        msg_class, topic, make_callback(topic, types[0], msg_class), qos, raw=True)
            except Exception as exc:
                node.get_logger().warning(f'Cannot subscribe {topic}: {type(exc).__name__}')

    def heartbeat():
        nonlocal probe_done, reported_state
        if writer.error:
            recorder.close('worker_error')
            recorder.disabled_reason = writer.error
        recorder.tick(time.monotonic())
        if recorder.sink is not None and owned_bytes(args.root) >= quota:
            recorder.close('storage_cap')
            recorder.disabled_reason = 'storage_cap'
        health = topic_health(recorder, time.monotonic(), required_topics)
        health['profile'] = args.profile
        health['postroll_s'] = post_s
        health['preroll_ready'] = time.monotonic() - started >= 12.0
        health['owned_bytes'] = owned_bytes(args.root)
        health['subscribed'] = sorted(subscriptions)
        health['writer'] = writer.health()
        health['middleware_events'] = middleware_events
        health['state'] = ('STOPPED' if stopped else 'ERROR' if recorder.disabled_reason else
                           'RECORDING' if recorder.sink else
                           'WAITING_FOR_TOPICS' if health['missing'] else
                           'STALE_TOPICS' if args.profile == 'steering-validation' and health['stale'] else
                           'WARMING_UP' if args.profile == 'steering-validation' and not health['preroll_ready'] else 'READY')
        health['updated_utc'] = time.time()
        if health['state'] != reported_state:
            print(json.dumps({'recorder': health['state'], 'root': str(args.root)}), flush=True)
            reported_state = health['state']
        # One summary file only; never changes or prunes a bag.
        tmp = args.root / 'recorder_health.json.tmp'
        final = args.root / 'recorder_health.json'
        try:
            tmp.write_text(json.dumps(health, sort_keys=True) + '\n', encoding='utf-8')
            os.replace(tmp, final)
        except OSError:
            recorder.dropped['health_write_error'] += 1
        if not stopped and args.stationary_probe and not probe_done and time.monotonic()-started >= 12:
            probe_done = True
            try:
                with urllib.request.urlopen('http://127.0.0.1:8088/api/status', timeout=2) as response:
                    status = json.load(response)
                policy = status['ros']['control_policy']
                command = status['ros']['cmd_vel']
                values = json.loads(policy['value'])
                if (policy['age'] > 2 or command['age'] > 2 or not values.get('stop_latched')
                    or command['value']['lin'] != 0 or command['value']['ang'] != 0
                    or any(status['services'].get(k) != 'inactive' for k in ('atlas-nav2','atlas-explore'))):
                    raise RuntimeError('stationary probe requires fresh latched stop and inactive navigation')
                recorder.motion(time.monotonic())  # Recorder trigger only. No ROS publication.
                print('STATIONARY_CAPTURE_STARTED: no motion requested', flush=True)
            except Exception as exc:
                recorder.disabled_reason = 'stationary_probe_refused:' + type(exc).__name__

    node.create_timer(2.0, discover)
    node.create_timer(1.0, heartbeat)
    discover()
    def terminate(signum, frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, terminate)
    try:
        while rclpy.ok() and not stopped and (args.duration <= 0 or time.monotonic()-started < args.duration):
            rclpy.spin_once(node, timeout_sec=0.25)
    finally:
        recorder.close('shutdown')
        if not writer.shutdown():
            recorder.disabled_reason = 'writer_shutdown_timeout'
        stopped = True
        heartbeat()
        node.destroy_node()
        rclpy.try_shutdown()
        lock.close()


if __name__ == '__main__':
    main()

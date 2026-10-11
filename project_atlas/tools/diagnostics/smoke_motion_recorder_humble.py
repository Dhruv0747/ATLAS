#!/usr/bin/env python3
"""Synthetic Humble serialization/bag test. Never initializes ROS or publishes.

Run in a NEW absolute directory. Uses real time for resource measurement and
synthetic monotonic time for reproducible trigger assertions. No live inputs.
"""
import argparse
from collections import Counter
import gc
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from atlas_motion_recorder import RosbagSink, TOPICS, MIB, owned_bytes
from atlas_motion_recorder_core import RecorderEngine, Sample


def proc_values(path):
    if not Path(path).exists():
        return {}
    return {line.split(':')[0]: int(line.split(':')[1].split()[0])
            for line in Path(path).read_text().splitlines() if ':' in line
            and line.split(':')[1].split() and line.split(':')[1].split()[0].isdigit()}


def system_sample():
    cpu = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    mem = proc_values('/proc/meminfo')
    return {'cpu_ticks': sum(cpu), 'idle_ticks': cpu[3] + cpu[4],
            'available_ram_kib': mem['MemAvailable'],
            'nvme_written_sectors': int(Path('/sys/block/nvme0n1/stat').read_text().split()[6])}


def templates():
    from geometry_msgs.msg import Twist, PoseWithCovarianceStamped, TransformStamped
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import Imu, LaserScan
    from std_msgs.msg import Int32, Float32, String
    from tf2_msgs.msg import TFMessage
    result = {}
    for topic in TOPICS:
        if topic in ('/scan', '/scan_raw'):
            msg = LaserScan()
            msg.header.frame_id = 'synthetic_laser'
            msg.ranges = [1.25] * 720
            msg.intensities = [12.0] * 720
            cls, period = 'sensor_msgs/msg/LaserScan', 10
        elif topic in ('/odom', '/yahboom/odom'):
            msg, cls, period = Odometry(), 'nav_msgs/msg/Odometry', 2
        elif 'imu' in topic:
            msg, cls, period = Imu(), 'sensor_msgs/msg/Imu', 1
        elif topic == '/amcl_pose':
            msg, cls, period = PoseWithCovarianceStamped(), 'geometry_msgs/msg/PoseWithCovarianceStamped', 20
        elif topic in ('/tf', '/tf_static'):
            transform = TransformStamped()
            transform.header.frame_id = 'synthetic_parent'
            transform.child_frame_id = 'synthetic_child'
            transform.transform.rotation.w = 1.0
            msg, cls, period = TFMessage(transforms=[transform]), 'tf2_msgs/msg/TFMessage', 2
        elif '/encoder/m' in topic:
            msg, cls, period = Int32(data=123), 'std_msgs/msg/Int32', 2
        elif topic.startswith('/cmd_vel'):
            msg, cls, period = Twist(), 'geometry_msgs/msg/Twist', 5
        elif topic.endswith('angle_deg'):
            msg, cls, period = Float32(data=90.0), 'std_msgs/msg/Float32', 5
        else:
            msg, cls, period = String(data='synthetic diagnostic fixture'), 'std_msgs/msg/String', 10
        result[topic] = (msg, cls, period)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--flush-probe', action='store_true',
                        help='only measure three ten-second preroll flushes')
    args = parser.parse_args()
    if not args.root.is_absolute() or args.root.exists():
        parser.error('requires a NEW absolute directory; existing evidence is never reused')
    args.root.mkdir(parents=True)
    import rosbag2_py
    from rclpy.serialization import serialize_message, deserialize_message
    from rosidl_runtime_py.utilities import get_message

    if args.flush_probe:
        results = []
        fixtures = templates()
        for attempt in range(3):
            engine = RecorderEngine(lambda: RosbagSink(args.root, 480*MIB, rosbag2_py))
            for tick in range(1001):
                for topic, (msg, type_name, period) in fixtures.items():
                    if topic == '/tf_static' or tick % period:
                        continue
                    engine.ingest(Sample(topic, type_name, serialize_message(msg), tick/100,
                                         1_000_000_000 + tick*10_000_000))
            count = len(engine.buffer)
            begin = time.monotonic()
            engine.motion(10.0)
            elapsed = time.monotonic()-begin
            assert engine.sink is not None, engine.disabled_reason
            results.append({'attempt': attempt+1, 'buffered_messages': count,
                            'callback_block_seconds': elapsed})
            engine.close('flush_probe')
        (args.root/'flush_result.json').write_text(json.dumps(results, indent=2)+'\n')
        print(json.dumps(results, indent=2), flush=True)
        return

    sinks = []
    expected = []

    class CheckedSink(RosbagSink):
        def __init__(self):
            super().__init__(args.root, 480 * MIB - owned_bytes(args.root), rosbag2_py)
            self.digest = hashlib.sha256()
            self.first_ns = self.last_ns = None

        def write(self, sample):
            super().write(sample)
            self.digest.update(sample.topic.encode() + str(sample.ros_time_ns).encode() + sample.payload)
            if self.first_ns is None:
                self.first_ns = sample.ros_time_ns
            self.last_ns = sample.ros_time_ns

    def factory():
        sink = CheckedSink()
        sinks.append(sink)
        return sink

    engine = RecorderEngine(factory)
    messages = templates()
    base_ns = time.time_ns()
    static_msg, static_type, _ = messages['/tf_static']
    engine.pin(Sample('/tf_static', static_type, serialize_message(static_msg), 0, base_ns))
    before_io = proc_values('/proc/self/io')
    before_system = system_sample()
    free_before = shutil.disk_usage(args.root).free
    cpu_before = time.process_time()
    start = time.monotonic()
    peaks = {'rss_kib': 0, 'buffer_bytes': 0}
    free_min = free_before
    late_ticks = 0
    # First movement 12-24 s, short restart 28-30 s extends its postroll.
    # Second movement 45-48 s opens a separate capture after the first closes.
    for tick in range(6000):
        target = start + tick / 100
        delay = target - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        elif delay < -0.1:
            late_ticks += 1
        t = tick / 100
        for topic, (msg, type_name, period) in messages.items():
            if topic == '/tf_static' or tick % period:
                continue
            stamp = base_ns + tick * 10_000_000
            if hasattr(msg, 'header'):
                msg.header.stamp.sec = stamp // 1_000_000_000
                msg.header.stamp.nanosec = stamp % 1_000_000_000
            payload = serialize_message(msg)
            engine.ingest(Sample(topic, type_name, payload, t, stamp))
        if 12 <= t < 24 or 28 <= t < 30 or 45 <= t < 48:
            engine.motion(t)
        engine.tick(t)
        if tick % 100 == 0:
            peaks['rss_kib'] = max(peaks['rss_kib'], proc_values('/proc/self/status').get('VmRSS', 0))
            peaks['buffer_bytes'] = max(peaks['buffer_bytes'], engine.buffer_bytes)
            free_min = min(free_min, shutil.disk_usage(args.root).free)
        if tick % 1500 == 0:
            print(json.dumps({'progress_s': t, 'captures': len(sinks), 'active': engine.sink is not None}), flush=True)
    engine.close('smoke_end')
    wall = time.monotonic() - start
    cpu = time.process_time() - cpu_before
    after_io = proc_values('/proc/self/io')
    after_system = system_sample()
    free_after = shutil.disk_usage(args.root).free
    assert not engine.disabled_reason, engine.disabled_reason
    assert len(sinks) == 2, len(sinks)
    assert engine.completed == ['stopped', 'stopped'], engine.completed

    for sink in sinks:
        reader = rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(sink.path), storage_id='sqlite3'),
                    rosbag2_py.ConverterOptions('', ''))
        digest = hashlib.sha256()
        counts = Counter()
        types = {entry.name: entry.type for entry in reader.get_all_topics_and_types()}
        while reader.has_next():
            topic, payload, stamp = reader.read_next()
            decoded = deserialize_message(payload, get_message(types[topic]))
            # CDR padding is not canonical. Compare reserialized message values;
            # the digest below independently checks exact original bag bytes.
            assert deserialize_message(serialize_message(decoded), get_message(types[topic])) == decoded, topic
            digest.update(topic.encode() + str(stamp).encode() + payload)
            counts[topic] += 1
        del reader
        gc.collect()
        assert counts == sink.counts
        assert digest.hexdigest() == sink.digest.hexdigest(), 'timestamp/payload/order mismatch'
        for db in sink.path.glob('*.db3'):
            with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as conn:
                assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert (sink.path / 'metadata.yaml').is_file()
        expected.append({'bag': sink.path.name, 'messages': sum(counts.values()),
                         'topics': len(counts), 'first_s': (sink.first_ns-base_ns)/1e9,
                         'last_s': (sink.last_ns-base_ns)/1e9,
                         'readback_identical': True, 'sqlite_integrity': 'ok'})

    assert expected[0]['first_s'] == 2.0, expected[0]
    assert expected[1]['first_s'] == 35.0, expected[1]
    assert 39.98 <= expected[0]['last_s'] <= 40.01, expected[0]
    assert 57.98 <= expected[1]['last_s'] <= 58.01, expected[1]

    result = {'ros_distro': 'humble', 'synthetic_only': True, 'ros_node_initialized': False,
              'wall_s': wall, 'cpu_s': cpu, 'cpu_one_core_percent': 100*cpu/wall,
              'peak_rss_mib': peaks['rss_kib']/1024,
              'process_peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
              'peak_buffer_mib': peaks['buffer_bytes']/MIB,
              'process_write_bytes': after_io['write_bytes']-before_io['write_bytes'] if before_io else None,
              'process_wchar_bytes': after_io['wchar']-before_io['wchar'] if before_io else None,
              'process_io_accounting_available': bool(before_io),
              'nvme_system_write_bytes': 512*(after_system['nvme_written_sectors']-before_system['nvme_written_sectors']),
              'bag_allocated_bytes': sum(p.stat().st_blocks*512 for p in args.root.rglob('*') if p.is_file()),
              'bag_bytes': owned_bytes(args.root), 'free_before_bytes': free_before,
              'free_min_bytes': free_min, 'free_after_bytes': free_after,
              'system_cpu_percent': 100*(1-(after_system['idle_ticks']-before_system['idle_ticks'])/
                                        (after_system['cpu_ticks']-before_system['cpu_ticks'])),
              'available_ram_before_mib': before_system['available_ram_kib']/1024,
              'available_ram_after_mib': after_system['available_ram_kib']/1024,
              'late_ticks_over_100ms': late_ticks, 'dropped': dict(engine.dropped),
              'bags': expected, 'result': 'PASS'}
    (args.root / 'smoke_result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()

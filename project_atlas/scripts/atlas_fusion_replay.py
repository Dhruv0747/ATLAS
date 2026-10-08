"""Command-free, isolated EKF/SLAM comparison. Run in a sourced ROS Humble shell.

Creates a new output directory; never edits the supplied live configuration.
Caller must reserve ROS domain 178 before running. No actuator nodes are launched.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import rosbag2_py
from rclpy.serialization import deserialize_message, serialize_message
from tf2_msgs.msg import TFMessage
import yaml

ALLOWED = {'/scan', '/tf', '/tf_static', '/yahboom/odom',
           '/im10a/imu/bias_corrected_candidate'}


def prepare(source, destination):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(source), storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('', ''))
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(destination), storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('', ''))
    for topic in reader.get_all_topics_and_types():
        if topic.name in ALLOWED:
            writer.create_topic(topic)
    counts = {}
    frames = set()
    while reader.has_next():
        topic, data, stamp = reader.read_next()
        if topic not in ALLOWED:
            continue
        if topic in {'/tf', '/tf_static'}:
            msg = deserialize_message(data, TFMessage)
            msg.transforms = [t for t in msg.transforms
                              if not ({t.header.frame_id.strip('/'),
                                       t.child_frame_id.strip('/')} & {'map', 'odom'})]
            if not msg.transforms:
                continue
            frames.update((t.header.frame_id, t.child_frame_id) for t in msg.transforms)
            data = serialize_message(msg)
        writer.write(topic, data, stamp)
        counts[topic] = counts.get(topic, 0) + 1
    if any(not counts.get(t) for t in ALLOWED - {'/tf'}):
        raise RuntimeError('Missing required input: ' + str(counts))
    return {'counts': counts, 'retained_frames': sorted(frames)}


def configurations(raw, comparison='wheel_pose'):
    baseline = yaml.safe_load(raw)
    params = baseline['atlas_ekf']['ros__parameters']
    if params['odom0'] != '/yahboom/odom' or params['imu0'] != '/im10a/imu/bias_corrected_candidate':
        raise ValueError('Unexpected fusion inputs: review before replay')
    params['use_sim_time'] = True
    candidate = copy.deepcopy(baseline)
    if comparison == 'tf_offset':
        candidate['atlas_ekf']['ros__parameters']['transform_time_offset'] = 0.0
        return {'offset_current': baseline, 'offset_zero': candidate}
    candidate['atlas_ekf']['ros__parameters']['odom0_config'][0:2] = [False, False]
    return {'pose_velocity': baseline, 'velocity_only': candidate}


def stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('ekf_config')
    parser.add_argument('output')
    parser.add_argument('--rate', type=float, default=0.5)
    parser.add_argument('--comparison', choices=['wheel_pose', 'tf_offset'], default='wheel_pose')
    args = parser.parse_args()
    if not 0.1 <= args.rate <= 1.0:
        parser.error('Replay rate must be 0.1 to 1.0')
    output = Path(args.output)
    output.mkdir(parents=False, exist_ok=False)
    raw = Path(args.ekf_config).read_text()
    configs = configurations(raw, args.comparison)
    manifest = prepare(args.bag, output / 'input')
    manifest.update(source=args.bag, config_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                    rate=args.rate, domain=178,
                    only_variant_change=('transform_time_offset set to zero' if args.comparison == 'tf_offset'
                                         else 'odom0_config x/y pose disabled'))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    env = dict(os.environ, ROS_DOMAIN_ID='178', ROS_LOCALHOST_ONLY='1',
               FASTDDS_BUILTIN_TRANSPORTS='UDPv4', PYTHONUNBUFFERED='1')
    for variant, config in configs.items():
        config_path = output / (variant + '.yaml')
        config_path.write_text(yaml.safe_dump(config))
        processes, files = [], []
        def launch(name, command):
            log = (output / (variant + '_' + name + '.log')).open('w')
            files.append(log)
            process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process)
            return process
        print('START ' + variant, flush=True)
        try:
            ekf = launch('ekf', ['/opt/ros/humble/lib/robot_localization/ekf_node', '--ros-args',
                                '-r', '__node:=atlas_ekf', '--params-file', str(config_path),
                                '-r', 'odometry/filtered:=/odom'])
            slam_params = dict(use_sim_time='true', odom_frame='odom', map_frame='map',
                               base_frame='base_link', scan_topic='/scan', mode='mapping',
                               min_laser_range='0.20', max_laser_range='8.0',
                               minimum_time_interval='0.10', minimum_travel_distance='0.05',
                               minimum_travel_heading='0.10', map_update_interval='1.5',
                               scan_queue_size='20', transform_timeout='1.5',
                               tf_buffer_duration='30.0', use_scan_matching='true', do_loop_closing='true')
            command = ['/opt/ros/humble/lib/slam_toolbox/async_slam_toolbox_node', '--ros-args']
            for key, value in slam_params.items():
                command += ['-p', key + ':=' + value]
            slam = launch('slam', command)
            recorder = launch('record', ['ros2', 'bag', 'record', '-o', str(output / variant),
                                          '/tf', '/tf_static', '/map', '/scan', '/odom', '/diagnostics'])
            time.sleep(5)
            if any(p.poll() is not None for p in (ekf, slam, recorder)):
                raise RuntimeError('A replay component exited before playback')
            player = launch('play', ['ros2', 'bag', 'play', str(output / 'input'),
                                    '--clock', '50', '--rate', str(args.rate), '--topics', *sorted(ALLOWED)])
            code = player.wait(timeout=2200)
            if code != 0 or any(p.poll() is not None for p in (ekf, slam, recorder)):
                raise RuntimeError('Replay component failed; inspect logs')
            time.sleep(3)
        finally:
            for process in reversed(processes):
                stop(process)
            for log in files:
                log.close()
        print('COMPLETE ' + variant, flush=True)
    print('ALL COMPLETE', flush=True)


if __name__ == '__main__':
    main()

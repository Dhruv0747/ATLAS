"""PC-only bounded RTAB-Map runner. Never connects to production ROS.

An admitted metadata manifest is necessary, not proof of physical accuracy.
Input publishers/replay must use the isolated localhost domain 179 namespace.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import resource
import subprocess
import time

from calibration_validation import validate_calibration


def isolated_env():
    env = dict(os.environ)
    for key in ('ROS_DISCOVERY_SERVER', 'FASTRTPS_DEFAULT_PROFILES_FILE',
                'FASTDDS_DEFAULT_PROFILES_FILE', 'CYCLONEDDS_URI'):
        env.pop(key, None)
    env.update(ROS_DOMAIN_ID='179', ROS_LOCALHOST_ONLY='1',
               RMW_IMPLEMENTATION='rmw_fastrtps_cpp',
               SKIP_DEFAULT_XML='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='1')
    return env


def admit(m):
    for name in ('rgb', 'depth'):
        c = m[name]
        validate_calibration(c, m['serial'], c['width'], c['height'], c['frame_id'])
    if m['depth_encoding'] not in ('16UC1', '32FC1'):
        raise ValueError('unsupported depth encoding')
    expected = .001 if m['depth_encoding'] == '16UC1' else 1.0
    if m['units_to_m'] != expected or m['scale_verified'] is not True:
        raise ValueError('depth scale unverified')
    if m['registered_to_rgb'] is not True or not m['registration_evidence']:
        raise ValueError('RGB registration unverified')
    if m['rgb']['width'] != m['depth']['width'] or m['rgb']['height'] != m['depth']['height']:
        raise ValueError('registered image dimensions differ')
    if not m['tf_evidence'] or m['tf_at_all_frame_stamps'] is not True:
        raise ValueError('TF missing at image stamps')
    stamps = [m[k] for k in ('rgb_stamp', 'depth_stamp', 'info_stamp', 'odom_stamp')]
    if not all(type(v) in (int, float) and math.isfinite(v) for v in stamps + [m['replay_time']]):
        raise ValueError('invalid timestamps')
    if any(not 0 <= m['replay_time'] - s <= .5 for s in stamps):
        raise ValueError('stale or future data')
    if max(stamps)-min(stamps) > .03:
        raise ValueError('synchronization skew exceeds 30 ms')
    return True


def main():
    def terminate(signum, frame):
        raise KeyboardInterrupt('bounded runner terminated')
    signal.signal(signal.SIGTERM, terminate)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=30, choices=range(1, 61))
    a = p.parse_args()
    admit(json.loads(a.manifest.read_text()))
    a.output.mkdir(parents=True, exist_ok=False)
    env = isolated_env()
    exe = '/opt/ros/humble/lib/rtabmap_slam/rtabmap'
    config = Path(__file__).with_name('rtabmap_offline.yaml')
    cmd = [exe, '--ros-args', '--params-file', str(config),
           '-r', '__ns:=/atlas_offline', '-p', 'database_path:='+str(a.output/'map.db'),
           '-r', 'rgb/image:=input/rgb', '-r', 'depth/image:=input/depth',
           '-r', 'rgb/camera_info:=input/camera_info', '-r', 'odom:=input/odom',
           '-r', 'scan:=input/scan']
    start = time.monotonic()
    samples = []
    with (a.output/'node.log').open('w') as log:
        child = subprocess.Popen(cmd, env=env, stdout=log, stderr=log, start_new_session=True)
        try:
            while child.poll() is None and time.monotonic()-start < a.seconds:
                try:
                    stat = Path('/proc/'+str(child.pid)+'/stat').read_text().rsplit(')',1)[1].split()
                    samples.append({'elapsed':time.monotonic()-start,
                                    'cpu_seconds':(int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK'),
                                    'rss_bytes':int(stat[21])*os.sysconf('SC_PAGE_SIZE')})
                except FileNotFoundError:
                    break
                if sum(f.stat().st_size for f in a.output.glob('*') if f.is_file()) > 256*1024**2:
                    raise RuntimeError('256 MiB output budget exceeded')
                time.sleep(.1)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGINT)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            (a.output/'resource_samples.json').write_text(json.dumps(samples))
    if child.returncode != 0:
        raise RuntimeError('RTAB-Map exited '+str(child.returncode))


if __name__ == '__main__':
    main()

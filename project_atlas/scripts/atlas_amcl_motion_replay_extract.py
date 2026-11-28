#!/usr/bin/env python3
"""Export one saved drive into a bundle for the offline AMCL motion replay.

Read-only. Reads a rosbag2 SQLite recording and writes JSON containing:

- the /map grid recorded in the same bag;
- the laser pose in base_link from /tf_static;
- every /scan (header stamp, bearings in base_link, ranges);
- the odom->base_link pose AMCL would have looked up at each scan stamp,
  in three variants:
    recorded      exactly as recorded on /tf (includes the EKF's
                  transform_time_offset future-dating);
    scaled        recorded, with every translation increment multiplied by
                  --distance-scale (diagnostic: simulates corrected encoder
                  distance; yaw unchanged);
    scaled_shift  scaled, looked up at stamp + --time-offset (diagnostic:
                  removes the EKF future-dating at lookup time);
- whether /odom reported motion at each scan;
- the first recorded /particle_cloud (with weights) as the initial cloud;
- the recorded /amcl_pose stream for comparison.

No ROS node, publisher, service or actuator is created.
"""
import argparse
import glob
import json
import math
import sqlite3
from pathlib import Path

from rosbags.typesys import Stores, get_typestore

TS = get_typestore(Stores.ROS2_HUMBLE)
try:
    from rosbags.typesys import get_types_from_msg
    TS.register({**get_types_from_msg('geometry_msgs/Pose pose\nfloat64 weight', 'nav2_msgs/msg/Particle'),
                 **get_types_from_msg('std_msgs/Header header\nnav2_msgs/Particle[] particles',
                                      'nav2_msgs/msg/ParticleCloud')})
except KeyError:  # already registered
    pass
MOVING_MPS = 0.03
MOVING_RADPS = 0.05


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def stamp(header):
    return header.stamp.sec + header.stamp.nanosec * 1e-9


def interpolate(series, t):
    """Pose at time t from a time-sorted [(t, x, y, yaw)] list; clamps at ends."""
    lo, hi = 0, len(series) - 1
    if t <= series[0][0]:
        return series[0][1:]
    if t >= series[-1][0]:
        return series[-1][1:]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if series[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    a, b = series[lo], series[hi]
    f = (t - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
    return (a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), wrap(a[3] + f * wrap(b[3] - a[3])))


def rescale(series, scale):
    """Re-integrate a pose series with translation increments scaled."""
    if not series:
        return []
    out = [series[0]]
    x, y = series[0][1], series[0][2]
    for a, b in zip(series, series[1:]):
        dx, dy = b[1] - a[1], b[2] - a[2]
        c, s = math.cos(a[3]), math.sin(a[3])
        fwd, lat = c * dx + s * dy, -s * dx + c * dy
        fwd, lat = fwd * scale, lat * scale
        x += c * fwd - s * lat
        y += s * fwd + c * lat
        out.append((b[0], x, y, b[3]))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bag')
    p.add_argument('output')
    p.add_argument('--distance-scale', type=float, default=1.0)
    p.add_argument('--time-offset', type=float, default=0.2)
    a = p.parse_args()
    files = glob.glob(str(Path(a.bag) / '*.db3'))
    if len(files) != 1:
        raise ValueError('requires one SQLite segment')
    db = sqlite3.connect('file:' + files[0] + '?mode=ro', uri=True)
    topics = {n: (i, t) for i, n, t in db.execute('SELECT id,name,type FROM topics')}

    def rows(name, limit=-1):
        if name not in topics:
            return []
        ident, typ = topics[name]
        return [(r / 1e9, TS.deserialize_cdr(raw, typ)) for r, raw in db.execute(
            'SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp LIMIT ?', (ident, limit))]

    maps = rows('/map')
    if not maps:
        raise ValueError('bag has no /map')
    grid = maps[0][1]
    laser = None
    for _, m in rows('/tf_static'):
        for tr in m.transforms:
            if tr.child_frame_id.strip('/') in ('laser_frame', 'laser'):
                t = tr.transform
                laser = (t.translation.x, t.translation.y, yaw_of(t.rotation))
    if laser is None:
        raise ValueError('no laser transform in /tf_static')
    odom_tf = []
    for _, m in rows('/tf'):
        for tr in m.transforms:
            if (tr.header.frame_id.strip('/'), tr.child_frame_id.strip('/')) == ('odom', 'base_link'):
                t = tr.transform
                odom_tf.append((stamp(tr.header), t.translation.x, t.translation.y, yaw_of(t.rotation)))
    odom_tf.sort()
    twist = [(stamp(m.header), m.twist.twist.linear.x, m.twist.twist.angular.z) for _, m in rows('/odom')]
    if not odom_tf or not twist:
        raise ValueError('bag needs odom->base_link on /tf and /odom')
    scaled = rescale(odom_tf, a.distance_scale)
    clouds = rows('/particle_cloud', 1)
    if not clouds:
        raise ValueError('bag has no /particle_cloud')
    cloud_rx, cloud = clouds[0]
    cloud_t = stamp(cloud.header)
    scans = []
    ti = 0
    for _, m in rows('/scan'):
        t = stamp(m.header)
        if t < cloud_t:
            continue
        while ti + 1 < len(twist) and twist[ti + 1][0] <= t:
            ti += 1
        moving = abs(twist[ti][1]) >= MOVING_MPS or abs(twist[ti][2]) >= MOVING_RADPS
        ranges = [float(r) if math.isfinite(r) else None for r in m.ranges]
        scans.append({
            'time_s': t, 'angle_min': m.angle_min + laser[2], 'angle_increment': m.angle_increment,
            'range_min': m.range_min, 'range_max': m.range_max, 'ranges': ranges,
            'moving': moving,
            'odom': {'recorded': interpolate(odom_tf, t), 'scaled': interpolate(scaled, t),
                     'scaled_shift': interpolate(scaled, t + a.time_offset)}})
    amcl = []
    for _, m in rows('/amcl_pose'):
        c = m.pose.covariance
        amcl.append({'time_s': stamp(m.header), 'x': m.pose.pose.position.x, 'y': m.pose.pose.position.y,
                     'yaw': yaw_of(m.pose.pose.orientation),
                     'xy_std': math.sqrt(max(0.0, c[0]) + max(0.0, c[7])),
                     'yaw_std_deg': math.degrees(math.sqrt(max(0.0, c[35])))})
    bundle = {
        'source_bag': Path(a.bag).name, 'navigation_authorized': False,
        'distance_scale': a.distance_scale, 'time_offset_s': a.time_offset,
        'map': {'width': grid.info.width, 'height': grid.info.height, 'resolution': grid.info.resolution,
                'origin': [grid.info.origin.position.x, grid.info.origin.position.y],
                'cells': [int(v) for v in grid.data]},
        'laser': list(laser),
        'particles': [[q.pose.position.x, q.pose.position.y, yaw_of(q.pose.orientation), q.weight]
                      for q in cloud.particles],
        'cloud_time_s': cloud_t,
        'scans': scans, 'recorded_amcl': amcl,
    }
    Path(a.output).write_text(json.dumps(bundle, allow_nan=False))
    print(json.dumps({'output': a.output, 'scans': len(scans), 'particles': len(cloud.particles),
                      'laser_in_base': laser, 'navigation_authorized': False}))


if __name__ == '__main__':
    main()

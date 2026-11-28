"""Minimal ROS 2 bag (sqlite3 .db3, CDR little-endian) reader for offline replays without ROS (2026-11-16).

Decodes only what the guided-mapping replay needs: sensor_msgs/LaserScan, std_msgs/Float32, std_msgs/String,
tf2_msgs/TFMessage, geometry_msgs/PoseWithCovarianceStamped. Read-only; never writes to the bag.
"""
import math
import sqlite3
import struct
from pathlib import Path


class _Cdr:
    def __init__(self, data):
        self.b = data
        self.o = 4                                   # skip the 4-byte encapsulation header

    def _align(self, n):
        r = (self.o - 4) % n
        if r:
            self.o += n - r

    def u32(self):
        self._align(4)
        v = struct.unpack_from('<I', self.b, self.o)[0]
        self.o += 4
        return v

    def i32(self):
        self._align(4)
        v = struct.unpack_from('<i', self.b, self.o)[0]
        self.o += 4
        return v

    def f32(self):
        self._align(4)
        v = struct.unpack_from('<f', self.b, self.o)[0]
        self.o += 4
        return v

    def f64(self):
        self._align(8)
        v = struct.unpack_from('<d', self.b, self.o)[0]
        self.o += 8
        return v

    def string(self):
        n = self.u32()
        s = self.b[self.o:self.o + n - 1].decode('utf-8', 'replace') if n else ''
        self.o += n
        return s

    def f32_seq(self):
        n = self.u32()
        self._align(4)
        v = struct.unpack_from(f'<{n}f', self.b, self.o) if n else ()
        self.o += 4 * n
        return list(v)

    def header(self):
        sec = self.i32()
        nsec = self.u32()
        frame = self.string()
        return sec + nsec * 1e-9, frame


def laser_scan(data):
    c = _Cdr(data)
    stamp, frame = c.header()
    amin, amax, inc, _, _, rmin, rmax = (c.f32() for _ in range(7))
    ranges = c.f32_seq()
    return {'stamp': stamp, 'frame': frame, 'angle_min': amin, 'angle_max': amax, 'angle_increment': inc,
            'range_min': rmin, 'range_max': rmax, 'ranges': ranges}


def float32(data):
    return _Cdr(data).f32()


def string(data):
    return _Cdr(data).string()


def _yaw(qx, qy, qz, qw):
    return math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))


def tf_message(data):
    """[(stamp, parent, child, x, y, yaw)]"""
    c = _Cdr(data)
    out = []
    for _ in range(c.u32()):
        stamp, parent = c.header()
        child = c.string()
        x, y, _z = c.f64(), c.f64(), c.f64()
        qx, qy, qz, qw = c.f64(), c.f64(), c.f64(), c.f64()
        out.append((stamp, parent, child, x, y, _yaw(qx, qy, qz, qw)))
    return out


def pose_cov_stamped(data):
    c = _Cdr(data)
    stamp, frame = c.header()
    x, y, _z = c.f64(), c.f64(), c.f64()
    qx, qy, qz, qw = c.f64(), c.f64(), c.f64(), c.f64()
    return {'stamp': stamp, 'frame': frame, 'x': x, 'y': y, 'yaw': _yaw(qx, qy, qz, qw)}


DECODERS = {
    'sensor_msgs/msg/LaserScan': laser_scan,
    'std_msgs/msg/Float32': float32,
    'std_msgs/msg/String': string,
    'tf2_msgs/msg/TFMessage': tf_message,
    'geometry_msgs/msg/PoseWithCovarianceStamped': pose_cov_stamped,
}


def read(bag_dir, topics):
    """Yield (t_receive_s, topic, decoded) in receive-time order for the requested topics."""
    dbs = sorted(Path(bag_dir).glob('*.db3'))
    if not dbs:
        raise FileNotFoundError(f'no .db3 in {bag_dir}')
    for db in dbs:
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        try:
            meta = {tid: (name, typ) for tid, name, typ in con.execute('SELECT id, name, type FROM topics')}
            ids = [tid for tid, (name, typ) in meta.items() if name in topics and typ in DECODERS]
            if not ids:
                continue
            q = f'SELECT topic_id, timestamp, data FROM messages WHERE topic_id IN ({",".join("?" * len(ids))}) ' \
                'ORDER BY timestamp'
            for tid, ts, data in con.execute(q, ids):
                name, typ = meta[tid]
                yield ts * 1e-9, name, DECODERS[typ](bytes(data))
        finally:
            con.close()

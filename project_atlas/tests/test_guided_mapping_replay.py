"""Guided mapping offline replay: pure bag reader (sqlite3 + CDR) and an end-to-end replay on a synthetic bag. 2026-11-16."""
import json
import math
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools' / 'mapping'))
import bag_reader  # noqa: E402
import replay_guided_mapping as rgm  # noqa: E402


class Cdr:
    def __init__(self):
        self.b = bytearray(b'\x00\x01\x00\x00')

    def _align(self, n):
        while (len(self.b) - 4) % n:
            self.b.append(0)

    def u32(self, v):
        self._align(4)
        self.b += struct.pack('<I', v)

    def i32(self, v):
        self._align(4)
        self.b += struct.pack('<i', v)

    def f32(self, v):
        self._align(4)
        self.b += struct.pack('<f', v)

    def f64(self, v):
        self._align(8)
        self.b += struct.pack('<d', v)

    def string(self, s):
        raw = s.encode() + b'\x00'
        self.u32(len(raw))
        self.b += raw

    def header(self, t, frame):
        self.i32(int(t))
        self.u32(int(round((t - int(t)) * 1e9)))
        self.string(frame)


def scan_msg(t, ranges, frame='laser_frame', amin=-math.pi, inc=2 * math.pi / 360, rmin=0.15, rmax=12.0):
    c = Cdr()
    c.header(t, frame)
    for v in (amin, amin + inc * (len(ranges) - 1), inc, 0.0, 0.1, rmin, rmax):
        c.f32(v)
    c.u32(len(ranges))
    for r in ranges:
        c.f32(r)
    c.u32(0)
    return bytes(c.b)


def tf_msg(edges):
    c = Cdr()
    c.u32(len(edges))
    for t, parent, child, x, y, yaw in edges:
        c.header(t, parent)
        c.string(child)
        for v in (x, y, 0.0, 0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)):
            c.f64(v)
    return bytes(c.b)


def string_msg(s):
    c = Cdr()
    c.string(s)
    return bytes(c.b)


def make_bag(path, messages):
    """messages: [(t, topic, type, bytes)]"""
    path.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path / 'b_0.db3')
    con.execute('CREATE TABLE topics(id INTEGER PRIMARY KEY, name TEXT, type TEXT, serialization_format TEXT, '
                'offered_qos_profiles TEXT)')
    con.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, topic_id INTEGER, timestamp INTEGER, data BLOB)')
    ids = {}
    for t, topic, typ, data in messages:
        if topic not in ids:
            ids[topic] = len(ids) + 1
            con.execute('INSERT INTO topics VALUES (?,?,?,?,?)', (ids[topic], topic, typ, 'cdr', ''))
        con.execute('INSERT INTO messages(topic_id, timestamp, data) VALUES (?,?,?)', (ids[topic], int(t * 1e9), data))
    con.commit()
    con.close()


def write_map(d, w=80, h=60, res=0.05, origin=(-1.0, -1.0)):
    """Room x in [0, 2.5], y in [0, 1.5] (walls), 205 unknown outside; PGM row 0 = top."""
    pix = bytearray()
    for row in range(h):
        gy = h - 1 - row
        for gx in range(w):
            x, y = origin[0] + (gx + 0.5) * res, origin[1] + (gy + 0.5) * res
            inside = -0.05 <= x <= 2.55 and -0.05 <= y <= 1.55
            wall = inside and (x < 0.05 or x > 2.45 or y < 0.05 or y > 1.45)
            pix.append(0 if wall else (254 if inside else 205))
    (d / 'm.pgm').write_bytes(b'P5\n%d %d\n255\n' % (w, h) + bytes(pix))
    (d / 'm.yaml').write_text(f'image: m.pgm\nmode: trinary\nresolution: {res}\norigin: [{origin[0]}, {origin[1]}, 0]\n'
                              'negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')
    return d / 'm.yaml'


def room_ranges(grid, pose, box=None):
    """Simulated LiDAR from the laser (x-0.05, yaw+180). box = (x0, x1, y0, y1) extra object NOT in the map."""
    x, y, yaw = pose
    lx, ly = x - 0.05 * math.cos(yaw), y - 0.05 * math.sin(yaw)
    out = []
    for i in range(360):
        a = yaw + math.pi - math.pi + math.radians(i)
        r, hit = 0.05, float('inf')
        while r < 6.0:
            px, py = lx + r * math.cos(a), ly + r * math.sin(a)
            if box and box[0] <= px <= box[1] and box[2] <= py <= box[3]:
                hit = r
                break
            c = grid.cell(px, py)
            if c is None or grid.value(*c) == -1:
                break
            if grid.value(*c) >= 65:
                hit = r
                break
            r += 0.02
        out.append(hit)
    return out


class ReaderTests(unittest.TestCase):
    def test_roundtrip_decoders(self):
        with tempfile.TemporaryDirectory() as d:
            bag = Path(d) / 'bag'
            make_bag(bag, [(1.0, '/scan', 'sensor_msgs/msg/LaserScan', scan_msg(0.9, [1.0, float('inf'), 2.5])),
                           (1.1, '/tf', 'tf2_msgs/msg/TFMessage', tf_msg([(1.05, 'map', 'odom', 0.5, -0.2, 0.3)])),
                           (1.2, '/x', 'std_msgs/msg/String', string_msg('{"a": 1}')),
                           (1.3, '/other', 'unknown/Type', b'\x00')])
            got = list(bag_reader.read(bag, {'/scan', '/tf', '/x', '/other'}))
            self.assertEqual([g[1] for g in got], ['/scan', '/tf', '/x'])
            s = got[0][2]
            self.assertAlmostEqual(s['stamp'], 0.9, places=6)
            self.assertEqual(s['frame'], 'laser_frame')
            self.assertEqual(len(s['ranges']), 3)
            self.assertTrue(math.isinf(s['ranges'][1]))
            e = got[1][2][0]
            self.assertEqual(e[1:3], ('map', 'odom'))
            self.assertAlmostEqual(e[5], 0.3, places=6)
            self.assertEqual(json.loads(got[2][2]), {'a': 1})

    def test_map_205_is_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            g = rgm.load_map(write_map(Path(d)))
            self.assertEqual(g.value(*g.cell(-0.5, -0.5)), -1)       # 205 outside
            self.assertEqual(g.value(*g.cell(1.0, 0.7)), 0)          # 254 inside
            self.assertEqual(g.value(*g.cell(0.0, 0.7)), 100)        # 0 wall


class ReplayTests(unittest.TestCase):
    def test_end_to_end_finds_unmapped_box(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ymap = write_map(d)
            grid = rgm.load_map(ymap)
            box = (1.6, 1.8, 0.6, 0.9)                               # furniture added after the map was made
            msgs = [(0.0, '/tf_static', 'tf2_msgs/msg/TFMessage', tf_msg([]))]
            t = 100.0
            path = [(0.4 + 0.1 * k, 0.4 + 0.02 * k, 0.1 * math.sin(k / 3)) for k in range(10)]
            for x, y, yaw in path:
                msgs.append((t, '/tf', 'tf2_msgs/msg/TFMessage',
                             tf_msg([(t, 'map', 'odom', 0.0, 0.0, 0.0), (t, 'odom', 'base_link', x, y, yaw)])))
                msgs.append((t + 0.01, '/scan', 'sensor_msgs/msg/LaserScan',
                             scan_msg(t, room_ranges(grid, (x, y, yaw), box))))
                t += 1.0
            make_bag(d / 'bag', msgs)
            out = d / 'r'
            self.assertEqual(rgm.main([str(d / 'bag'), str(ymap), str(out)]), 0)
            res = json.loads((d / 'r.json').read_text())
            self.assertEqual(res['counts']['scans'], 10)
            self.assertTrue(res['map_changes'], res)
            mc = res['map_changes'][0]
            xs = [q[0] for q in mc['polygon']]
            ys = [q[1] for q in mc['polygon']]
            self.assertLess(min(xs), 1.65)
            self.assertGreater(max(xs), 1.55)
            self.assertTrue(min(ys) < 0.85 and max(ys) > 0.65)
            self.assertEqual(res['candidates'], [])                  # no depth / ultrasonic in this bag
            self.assertTrue((d / 'r.png').read_bytes().startswith(b'\x89PNG'))


if __name__ == '__main__':
    unittest.main()

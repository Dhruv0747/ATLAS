"""Guided mapping phase 1b: the ROS node wiring, with stubbed rclpy / tf2 (no DDS participant). 2026-11-26."""
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent))
import atlas_guided_mapping as node_mod  # noqa: E402
from test_map_quality_core import room, simulate  # noqa: E402


class String:
    def __init__(self):
        self.data = ''


class FakeNode:
    def __init__(self, name):
        self.name, self.pubs, self.subs, self.destroyed, self.timers, self.logs = name, [], [], [], [], []

    def create_publisher(self, typ, topic, qos):
        pub = NS(typ=typ, topic=topic, sent=[])
        pub.publish = pub.sent.append
        self.pubs.append(pub)
        return pub

    def create_subscription(self, typ, topic, cb, qos):
        s = NS(typ=typ, topic=topic, cb=cb)
        self.subs.append(s)
        return s

    def destroy_subscription(self, s):
        self.destroyed.append(s)

    def create_timer(self, period, cb):
        self.timers.append((period, cb))

    def get_logger(self):
        log = self.logs
        return NS(info=lambda m: log.append(('info', m)), warn=lambda m: log.append(('warn', m)),
                  error=lambda m: log.append(('error', m)))


class Tf:
    def __init__(self):
        self.poses = {('map', 'base_link'): (1.0, 1.5, 0.0), ('map', 'odom'): (0.0, 0.0, 0.0)}
        self.unregistered = 0
        tf = self

        class Buffer:
            def lookup_transform(self, parent, child, when):
                x, y, yaw = tf.poses[(parent, child)]
                return NS(transform=NS(translation=NS(x=x, y=y, z=0.0),
                                       rotation=NS(x=0.0, y=0.0, z=math.sin(yaw / 2), w=math.cos(yaw / 2))))

        class TransformListener:
            def __init__(self, buffer, node):
                pass

            def unregister(self):
                tf.unregistered += 1

        self.Buffer, self.TransformListener = Buffer, TransformListener


def occ_msg(grid):
    return NS(info=NS(width=grid.w, height=grid.h, resolution=grid.res,
                      origin=NS(position=NS(x=grid.ox, y=grid.oy), orientation=NS(x=0.0, y=0.0, z=0.0, w=1.0))),
              data=grid.data)


def scan_msg(t, ranges):
    return NS(header=NS(stamp=NS(sec=int(t), nanosec=int((t % 1) * 1e9))), angle_min=-math.pi,
              angle_increment=2 * math.pi / 360, ranges=ranges, range_min=0.15, range_max=12.0)


class NodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session = Path(self.tmp.name) / 'mapping_session.json'
        self.mono = [100.0]
        self.wall = [1_800_000_000.0]
        self.tf = Tf()
        self.node = node_mod.make_node(
            NS(time=NS(Time=lambda: 0)), FakeNode, {'map': 'm', 'sensor': 's', 'status': 'st'},
            {'String': String, 'OccupancyGrid': 'OccupancyGrid', 'LaserScan': 'LaserScan'}, self.tf,
            session_file=self.session, clock=lambda: self.mono[0], proc_stat=lambda: None,
            wall=lambda: self.wall[0])

    def tearDown(self):
        self.tmp.cleanup()

    def tick(self, dt=1.0):
        self.mono[0] += dt
        self.wall[0] += dt
        self.node.tick()

    def last_payload(self):
        return json.loads(self.node.pubs[0].sent[-1].data)

    def test_publishes_only_the_status_topic(self):
        self.assertEqual([p.topic for p in self.node.pubs], ['/atlas/mapping_quality'])
        self.assertEqual(self.node.timers[0][0], 1.0)

    def test_idle_no_subscriptions_and_slow_publish(self):
        for _ in range(12):
            self.tick()
        self.assertEqual(self.node.subs, [])
        self.assertEqual(len(self.node.pubs[0].sent), 2)                  # first tick + after 10 s
        self.assertEqual(self.last_payload()['state'], 'inactive')

    def test_session_lifecycle(self):
        self.session.write_text(json.dumps({'id': 'abc', 'state': 'active'}))
        self.tick()
        self.assertEqual(sorted(s.topic for s in self.node.subs),
                         ['/astra/obstacle_scan', '/map', '/scan', '/ultrasonic/validity'])
        self.assertEqual(self.last_payload()['state'], 'waiting_for_map')
        cbs = {s.topic: s.cb for s in self.node.subs}
        g = room()
        cbs['/map'](occ_msg(g))
        cbs['/scan'](scan_msg(self.wall[0], simulate(g, (1.0, 1.5, 0.0))))
        self.tick(2.0)
        p = self.last_payload()
        self.assertEqual(p['state'], 'active')
        self.assertEqual(p['samples'], 1)
        self.assertEqual(p['session_id'], 'abc')
        self.session.unlink()
        self.tick()
        self.assertEqual(len(self.node.destroyed), 4)
        self.assertEqual(self.tf.unregistered, 1)
        self.assertEqual(self.node.subs, [])

    def test_scan_rate_is_limited(self):
        self.session.write_text(json.dumps({'id': 'abc', 'state': 'active'}))
        self.tick()
        cbs = {s.topic: s.cb for s in self.node.subs}
        g = room()
        cbs['/map'](occ_msg(g))
        for k in range(5):                                              # 5 scans within 0.5 s: only the first used
            self.mono[0] += 0.05
            cbs['/scan'](scan_msg(self.wall[0] + k * 0.05, simulate(g, (1.0 + 0.2 * k, 1.5, 0.0))))
        self.assertEqual(self.node.engine.quality.samples, 1)

    def test_bad_messages_never_raise(self):
        self.session.write_text(json.dumps({'id': 'abc', 'state': 'active'}))
        self.tick()
        cbs = {s.topic: s.cb for s in self.node.subs}
        cbs['/map'](NS(info=None, data=[]))
        cbs['/scan'](NS(header=None))
        self.mono[0] += 1
        cbs['/astra/obstacle_scan'](NS(header=None))
        cbs['/ultrasonic/validity'](NS(data='{broken'))
        self.tick(2.0)
        self.assertIn(self.last_payload()['state'], ('waiting_for_map', 'active'))

    def test_jump_uses_wall_clock_like_scans(self):
        self.session.write_text(json.dumps({'id': 'abc', 'state': 'active'}))
        self.tick()
        self.tf.poses[('map', 'odom')] = (1.3, 0.0, 0.2)
        self.tick()
        jump_ts = [t.jump_t for t in self.node.engine.quality.tiles.values() if t.jump_t is not None]
        self.assertTrue(jump_ts)
        self.assertGreater(min(jump_ts), 1e9)                           # wall time, same clock as scan stamps


if __name__ == '__main__':
    unittest.main()

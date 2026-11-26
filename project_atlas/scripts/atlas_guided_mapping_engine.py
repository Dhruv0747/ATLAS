"""Guided mapping assistant, phase 1b: the live engine (2026-11-26; design docs/design/guided_mapping_assistant.md).

Pure Python, no ROS: atlas_guided_mapping.py feeds it from ROS topics, and tests feed it directly.
READ-ONLY ADVICE: no motion, no goals, no place or map writes, never replaces the map acceptance gate. SLAM stays
LiDAR-only; depth and ultrasonic only build the separate "objects the LiDAR cannot see" list for the owner.

Active only while mission control's mapping session file says state == "active". A new session id resets everything
(the map frame of the old session is meaningless for the new one).

payload() -> compact JSON-ready dict (<= MAX_PAYLOAD_BYTES) for /atlas/mapping_quality:
  schema 1, state inactive | waiting_for_map | active | paused_cpu, session_id, verdict_text, ready, prompts (<= 3),
  notes, counts, tile_m, rows (run-length tiles: [iy, ix0, "AW.A"], A accepted, W weak, '.' not shown),
  weak (<= 10 nearest [ix, iy, reason]), frontiers (<= 5), objects (<= 5 candidates), samples, sources (ages, s).
All text is English (dashboard rule; Hindi only in chat and the voice narrator).
"""
import json
import math
from pathlib import Path
from typing import Dict, Optional, Tuple

import atlas_invisible_objects_core as ioc
import atlas_map_quality_core as mq

SCHEMA = 1
MAX_PAYLOAD_BYTES = 4096
CPU_PAUSE_BELOW = 0.25          # idle fraction; design section 4
CPU_RESUME_ABOVE = 0.35
LIDAR_PAIR_S = 1.0              # depth / ultrasonic need a LiDAR scan this recent (to know where the LiDAR is silent)
US_MAX_AGE_S = 0.3
SOURCE_FRESH_S = 10.0
FRONTIER_PERIOD_S = 5.0
MAX_WEAK, MAX_FRONTIERS, MAX_OBJECTS, MAX_PROMPTS = 10, 5, 5, 3
NOTE_NO_DEPTH = 'Depth camera: no data (the light mapping profile pauses it); ultrasonic and LiDAR only'
NOTE_NO_US = 'Ultrasonic: no data'


def _finite(*v):
    return all(isinstance(x, (int, float)) and math.isfinite(x) for x in v)


def read_session(path) -> Optional[dict]:
    """Mission control's mapping session file, or None if missing / unreadable / without an id."""
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or not isinstance(value.get('id'), str) or not value['id']:
        return None
    return value


def grid_from_msg(msg) -> mq.Grid:
    """nav_msgs/OccupancyGrid (duck-typed) -> Grid. Raises ValueError for a rotated origin or bad size."""
    info = msg.info
    o = info.origin.orientation
    if abs(o.x) > 1e-6 or abs(o.y) > 1e-6 or abs(o.z) > 1e-6:
        raise ValueError('rotated map origin not supported')
    return mq.Grid(info.width, info.height, info.resolution, info.origin.position.x, info.origin.position.y,
                   list(msg.data))


def encode_rows(tiles: Dict[Tuple[int, int], str]):
    """{(ix, iy): 'A'|'W'} -> [[iy, ix0, 'AW.A'], ...] sorted by iy (gaps inside a row are '.')."""
    rows = {}
    for (ix, iy), code in tiles.items():
        rows.setdefault(iy, {})[ix] = code
    out = []
    for iy in sorted(rows):
        r = rows[iy]
        x0, x1 = min(r), max(r)
        out.append([iy, x0, ''.join(r.get(x, '.') for x in range(x0, x1 + 1))])
    return out


def decode_rows(rows):
    out = {}
    for iy, x0, s in rows:
        for k, ch in enumerate(s):
            if ch != '.':
                out[(x0 + k, iy)] = ch
    return out


class GuidedMappingEngine:
    def __init__(self, quality_policy=mq.QualityPolicy(), invisible_policy=ioc.InvisiblePolicy()):
        self.qp = quality_policy
        self.ip = invisible_policy
        self.session_id = None
        self.active = False
        self.paused = False
        self._reset()

    def _reset(self):
        self.quality = mq.QualityTracker(self.qp)
        self.invisible = ioc.InvisibleObjects(self.ip)
        self.grid = None
        self.map_version = 0
        self.fronts = None
        self.fronts_version = -1
        self.fronts_t = None
        self.scan = None                       # (t, angle_min, inc, ranges, rmin, rmax)
        self.sectors = None                    # (scan t, LidarSectors)
        self.last_map_odom = None
        self.us_seq = {}
        self.seen = {'lidar': None, 'depth': None, 'ultrasonic': None}

    # ---------------------------------------------------------------- control
    def set_session(self, session: Optional[dict]) -> bool:
        active = bool(session) and session.get('state') == 'active' and isinstance(session.get('id'), str)
        if active and session['id'] != self.session_id:
            self.session_id = session['id']
            self._reset()
        self.active = active
        return active

    def on_cpu_idle(self, idle: Optional[float]):
        if idle is None or not _finite(idle):
            self.paused = False
        elif idle < CPU_PAUSE_BELOW:
            self.paused = True
        elif idle > CPU_RESUME_ABOVE:
            self.paused = False

    def _working(self):
        return self.active and not self.paused

    # ---------------------------------------------------------------- inputs
    def on_map(self, grid: mq.Grid):
        if not self.active:
            return
        self.grid = grid
        self.map_version += 1

    def on_scan(self, t, pose, angle_min, angle_increment, ranges, range_min, range_max):
        if not self._working() or pose is None or not _finite(t, *pose):
            return
        self.scan = (t, angle_min, angle_increment, ranges, range_min, range_max)
        self.seen['lidar'] = t
        if self.grid is not None:
            self.quality.add_scan(t, pose, ioc.LASER_IN_BASE, angle_min, angle_increment, ranges, range_min,
                                  range_max, self.grid)

    def _lidar_at(self, t):
        if self.scan is None or abs(t - self.scan[0]) > LIDAR_PAIR_S:
            return None
        if self.sectors is None or self.sectors[0] != self.scan[0]:
            st, amin, inc, ranges, rmin, rmax = self.scan
            self.sectors = (st, ioc.LidarSectors(amin, inc, ranges, rmin, rmax, ioc.LASER_IN_BASE))
        return self.sectors[1]

    def on_depth(self, t, pose, angle_min, angle_increment, ranges):
        if not self._working() or pose is None or not _finite(t, *pose):
            return 0
        self.seen['depth'] = t
        lidar = self._lidar_at(t)
        if lidar is None:
            return 0
        return self.invisible.add_depth(t, pose, angle_min, angle_increment, ranges, lidar, self.grid)

    def on_ultrasonic(self, t, pose, validity_json):
        """/ultrasonic/validity JSON. Only fresh VALID samples with a new sequence number count. Returns the number
        of sides that added evidence."""
        if not self._working() or pose is None or not _finite(t, *pose):
            return 0
        try:
            sensors = json.loads(validity_json).get('sensors') or {}
        except (ValueError, AttributeError, TypeError):
            return 0
        lidar = self._lidar_at(t)
        added = 0
        for side in ('front', 'rear'):
            s = sensors.get(side) if isinstance(sensors, dict) else None
            if not isinstance(s, dict) or s.get('state') != 'VALID':
                continue
            seq, mm, age = s.get('sample_sequence'), s.get('range_mm'), s.get('sample_age_s')
            if seq is None or seq == self.us_seq.get(side) or not _finite(mm, age) or age > US_MAX_AGE_S:
                continue
            self.us_seq[side] = seq
            self.seen['ultrasonic'] = t
            if lidar is not None and self.invisible.add_ultrasonic(t, pose, side, mm / 1000.0, lidar, self.grid):
                added += 1
        return added

    def on_map_odom(self, t, x, y, yaw, robot_xy):
        """map->odom (SLAM's correction). A step over the policy thresholds marks the rover's tiles WEAK."""
        if not self._working() or not _finite(t, x, y, yaw) or robot_xy is None or not _finite(*robot_xy):
            return False
        prev, self.last_map_odom = self.last_map_odom, (t, x, y, yaw)
        if prev is None:
            return False
        d = math.hypot(x - prev[1], y - prev[2])
        dyaw = math.degrees(math.atan2(math.sin(yaw - prev[3]), math.cos(yaw - prev[3])))
        return self.quality.add_jump(t, robot_xy, d, dyaw)

    # ---------------------------------------------------------------- output
    def _frontiers(self, now):
        if self.fronts is None or (self.fronts_version != self.map_version and
                                   (self.fronts_t is None or now - self.fronts_t >= FRONTIER_PERIOD_S)):
            self.fronts = self.quality.frontiers(self.grid)
            self.fronts_version, self.fronts_t = self.map_version, now
        return self.fronts

    def _notes(self, now_scan_t):
        notes = []
        ref = now_scan_t
        for key, text in (('depth', NOTE_NO_DEPTH), ('ultrasonic', NOTE_NO_US)):
            seen = self.seen[key]
            if ref is not None and (seen is None or ref - seen > SOURCE_FRESH_S):
                notes.append(text)
        return notes

    def payload(self, now, robot_pose=None):
        base = {'schema': SCHEMA, 'session_id': self.session_id if self.active else None,
                'samples': self.quality.samples if self.active else 0, 'ready': False, 'prompts': [], 'notes': [],
                'counts': {}, 'tile_m': self.qp.tile_m, 'rows': [], 'weak': [], 'frontiers': [], 'objects': []}
        if not self.active:
            return dict(base, state='inactive', verdict_text='Mapping assistant: no mapping session')
        if self.paused:
            return dict(base, state='paused_cpu',
                        verdict_text='Mapping assistant paused: the rover CPU is busy (idle below 25 %)')
        if self.grid is None:
            return dict(base, state='waiting_for_map', verdict_text='Waiting for the live map from SLAM')
        robot = robot_pose if robot_pose is not None and _finite(*robot_pose) else None
        s = self.quality.summary(self.grid, robot=robot, frontiers=self._frontiers(now))
        tiles = {(t[0], t[1]): t[2] for t in s['tiles']}
        weak = [t for t in s['tiles'] if t[2] == 'W']
        if robot is not None:
            tm = self.qp.tile_m
            weak.sort(key=lambda t: math.hypot((t[0] + .5) * tm - robot[0], (t[1] + .5) * tm - robot[1]))
        objects = [{'name': c['name'], 'polygon': c['polygon'], 'sources': c['evidence']['sources'],
                    'area_m2': c['evidence']['area_m2']} for c in self.invisible.candidates()[:MAX_OBJECTS]]
        prompts = list(s['prompts'])
        if objects:
            prompts.insert(0 if not s['ready'] else 1,
                           f"Object the LiDAR cannot see: {objects[0]['name']} (check it on the map)")
        out = dict(base, state='active', verdict_text=s['verdict_text'], ready=s['ready'],
                   prompts=prompts[:MAX_PROMPTS], notes=self._notes(self.seen['lidar']), counts=s['counts'],
                   rows=encode_rows(tiles), weak=[[t[0], t[1], t[3]] for t in weak[:MAX_WEAK]],
                   frontiers=[{'x': f['x'], 'y': f['y'], 'length_m': f['length_m']}
                              for f in s['frontiers'][:MAX_FRONTIERS]],
                   objects=objects,
                   sources={k: (None if v is None or self.seen['lidar'] is None
                                else round(self.seen['lidar'] - v, 1)) for k, v in self.seen.items()})
        # Keep within the Wi-Fi budget: drop detail lists before ever dropping the tile rows.
        for key in ('weak', 'frontiers', 'objects'):
            while len(json.dumps(out, separators=(',', ':'))) > MAX_PAYLOAD_BYTES and out[key]:
                out[key] = out[key][:-1]
        return out

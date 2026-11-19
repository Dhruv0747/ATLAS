"""Guided mapping assistant: objects the LiDAR cannot see (2026-11-16, design docs/design/guided_mapping_assistant.md).

Pure Python, no ROS. Evidence comes from the Astra depth obstacle scan (/astra/obstacle_scan, base_link, about +-30 deg,
0.35-3.0 m) and the VALID front/rear ultrasonic ranges, ONLY where the LiDAR has no echo in the same direction (or its
echo is clearly farther). Hits on walls that are already in the map are dropped. Depth rays that pass through a cell
count against it, so people walking by fade out.

Output: CANDIDATE polygons in the config/virtual_obstacles.json format plus "candidate": true and evidence. Nothing here
changes SLAM, Nav2 or the guard: a candidate becomes a virtual obstacle only after the owner confirms it and approves a
deploy. SLAM stays LiDAR-only.
"""
from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Sequence, Tuple

LASER_IN_BASE = (-0.05, 0.0, math.pi)                       # ATLAS laser_frame (mux LASER_X, yaw 180 deg)
US_MOUNTS = {'front': (0.25, 0.0, 0.0), 'rear': (-0.25, 0.0, math.pi)}   # base_link x, y, axis (atlas_lidar_availability)


@dataclass(frozen=True)
class InvisiblePolicy:
    cell_m: float = 0.05
    lidar_margin_m: float = 0.25          # LiDAR echo must be this much farther than the depth hit (or absent)
    lidar_window_deg: float = 2.5         # LiDAR bearing window around a depth bin
    depth_min_m: float = 0.35
    depth_max_m: float = 3.0
    us_half_cone_deg: float = 10.0
    us_min_m: float = 0.05
    us_max_m: float = 2.0
    us_weight: float = 0.5                # the cone is wide: weaker evidence per cell
    us_arc_step_deg: float = 2.5
    occupied_threshold: int = 65
    map_wall_clear_cells: int = 2         # a hit within this many cells of a mapped wall is "already mapped"
    min_hit_weight: float = 3.0
    min_hit_ratio: float = 0.5            # per cell; the map-change layer uses MAP_CHANGE_POLICY (LiDAR flickers on
                                          # black leather, so a real object may only answer 1 beam in 3)
    viewpoint_xy_m: float = 0.3
    viewpoint_yaw_deg: float = 30.0
    min_area_m2: float = 0.02
    pad_m: float = 0.05
    join_cells: int = 2                   # cells this close belong to the same object
    pool_cells: int = 2                   # evidence is pooled over +-2 cells (+-10 cm): hits move as the rover moves
    pool_misses: bool = True              # hit ratio over the neighbourhood (depth / ultrasonic) or per cell
    min_sample_period_s: float = 0.4


def _finite(*v):
    return all(isinstance(x, (int, float)) and math.isfinite(x) for x in v)


MAP_CHANGE_POLICY = InvisiblePolicy(min_hit_ratio=0.25, min_hit_weight=6.0, pool_misses=False)


class LidarSectors:
    """LiDAR returns seen from base_link: min range per 1 deg bearing (base frame, degrees 0..359), inf = no echo."""

    def __init__(self, angle_min, angle_increment, ranges, range_min, range_max, laser_in_base=LASER_IN_BASE):
        self.best = [float('inf')] * 360
        lx, ly, lyaw = laser_in_base
        for i, r in enumerate(ranges):
            if r is None or not _finite(r) or r < range_min or r > range_max:
                continue
            a = lyaw + angle_min + i * angle_increment
            px, py = lx + r * math.cos(a), ly + r * math.sin(a)
            d = math.hypot(px, py)
            b = int(math.floor(math.degrees(math.atan2(py, px)))) % 360
            if d < self.best[b]:
                self.best[b] = d

    def min_range(self, bearing_rad, half_window_deg):
        c = math.degrees(bearing_rad)
        lo = int(math.floor(c - half_window_deg))
        hi = int(math.floor(c + half_window_deg))
        return min(self.best[b % 360] for b in range(lo, hi + 1))


class InvisibleObjects:
    def __init__(self, policy=InvisiblePolicy()):
        self.p = policy
        self.cells: Dict[Tuple[int, int], List] = {}    # key -> [hit_weight, misses, viewpoints (<= 4), sources]
        self.last_t = None
        self.frames = 0

    # ---------------------------------------------------------------- helpers
    def _key(self, x, y):
        return int(math.floor(x / self.p.cell_m)), int(math.floor(y / self.p.cell_m))

    def _vp(self, pose):
        p = self.p
        return (int(round(pose[0] / p.viewpoint_xy_m)), int(round(pose[1] / p.viewpoint_xy_m)),
                int(round(math.degrees(pose[2]) / p.viewpoint_yaw_deg)) % int(round(360 / p.viewpoint_yaw_deg)))

    def _near_mapped_wall(self, grid, x, y):
        if grid is None:
            return False
        c = grid.cell(x, y)
        if c is None:
            return False
        n = self.p.map_wall_clear_cells
        gx, gy = c
        for yy in range(gy - n, gy + n + 1):
            for xx in range(gx - n, gx + n + 1):
                if grid.value(xx, yy) >= self.p.occupied_threshold:
                    return True
        return False

    def _hit(self, x, y, weight, vp, source):
        k = self._key(x, y)
        c = self.cells.get(k)
        if c is None:
            self.cells[k] = [weight, 0, {vp}, {source}]
        else:
            c[0] += weight
            if len(c[2]) < 4:
                c[2].add(vp)
            c[3].add(source)

    def _miss(self, x0, y0, x1, y1):
        """Depth ray from the camera to just before its return: cells it passed are seen free."""
        d = math.hypot(x1 - x0, y1 - y0)
        step = self.p.cell_m
        n = int((d - 2 * step) / step)
        for i in range(1, max(0, n)):
            f = i * step / d
            c = self.cells.get(self._key(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
            if c is not None:
                c[1] += 1

    def want(self, t):
        if self.last_t is not None and t - self.last_t < self.p.min_sample_period_s:
            return False
        return True

    # ---------------------------------------------------------------- inputs
    def add_depth(self, t, pose, angle_min, angle_increment, ranges, lidar: LidarSectors, grid=None,
                  camera_xy=(0.21, 0.0)):
        """Astra obstacle scan in base_link at the map pose of base_link. Returns the number of invisible hits."""
        if not _finite(*pose) or lidar is None or not self.want(t):
            return 0
        p = self.p
        self.last_t = t
        self.frames += 1
        x, y, yaw = pose
        c, s = math.cos(yaw), math.sin(yaw)
        cam = (x + camera_xy[0] * c - camera_xy[1] * s, y + camera_xy[0] * s + camera_xy[1] * c)
        vp = self._vp(pose)
        hits = 0
        for i, r in enumerate(ranges):
            if r is None or not _finite(r) or r < p.depth_min_m or r > p.depth_max_m:
                continue
            a = angle_min + i * angle_increment
            wx, wy = x + r * math.cos(yaw + a), y + r * math.sin(yaw + a)
            self._miss(cam[0], cam[1], wx, wy)
            if lidar.min_range(a, p.lidar_window_deg) <= r + p.lidar_margin_m:
                continue                                       # the LiDAR sees it: not invisible
            if self._near_mapped_wall(grid, wx, wy):
                continue
            self._hit(wx, wy, 1.0, vp, 'depth')
            hits += 1
        return hits

    def add_ultrasonic(self, t, pose, side, range_m, lidar: LidarSectors, grid=None):
        """One VALID ultrasonic range (metres from the sensor). Marks the cone arc if the LiDAR has no echo there."""
        p = self.p
        mount = US_MOUNTS.get(side)
        if mount is None or not _finite(*pose) or lidar is None or not _finite(range_m) or \
                not p.us_min_m <= range_m <= p.us_max_m:
            return 0
        mx, my, axis = mount
        x, y, yaw = pose
        c, s = math.cos(yaw), math.sin(yaw)
        sx, sy = x + mx * c - my * s, y + mx * s + my * c
        base_range = math.hypot(mx, my) + range_m                     # distance from base_link along the axis
        if lidar.min_range(axis, p.us_half_cone_deg) <= base_range + p.lidar_margin_m:
            return 0
        vp = self._vp(pose)
        hits = 0
        n = int(p.us_half_cone_deg / p.us_arc_step_deg)
        for k in range(-n, n + 1):
            a = yaw + axis + math.radians(k * p.us_arc_step_deg)
            wx, wy = sx + range_m * math.cos(a), sy + range_m * math.sin(a)
            if self._near_mapped_wall(grid, wx, wy):
                continue
            self._hit(wx, wy, p.us_weight, vp, 'ultrasonic')
            hits += 1
        return hits

    def add_unmapped_lidar(self, t, pose, angle_min, angle_increment, ranges, range_min, range_max, grid,
                           laser_in_base=LASER_IN_BASE, beam_step=2, max_range=4.0):
        """MAP-CHANGE evidence (use a separate InvisibleObjects instance): LiDAR returns on cells the map says are
        FREE with no mapped wall within map_wall_clear_cells, e.g. furniture added after the map was made (the hall
        sofa). LiDAR rays through a cell count against it. Returns the number of hits."""
        if not _finite(*pose) or grid is None or not self.want(t):
            return 0
        self.last_t = t
        self.frames += 1
        x, y, yaw = pose
        lx, ly, lyaw = laser_in_base
        ox = x + lx * math.cos(yaw) - ly * math.sin(yaw)
        oy = y + lx * math.sin(yaw) + ly * math.cos(yaw)
        vp = self._vp(pose)
        hits = 0
        for i in range(0, len(ranges), max(1, beam_step)):
            r = ranges[i]
            if r is None or not _finite(r) or r < range_min or r > min(range_max, max_range):
                continue
            a = yaw + lyaw + angle_min + i * angle_increment
            wx, wy = ox + r * math.cos(a), oy + r * math.sin(a)
            self._miss(ox, oy, wx, wy)
            c = grid.cell(wx, wy)
            if c is None or grid.value(*c) != 0 or self._near_mapped_wall(grid, wx, wy):
                continue
            self._hit(wx, wy, 1.0, vp, 'lidar-unmapped')
            hits += 1
        return hits

    # ---------------------------------------------------------------- output
    def candidate_cells(self):
        """Cells with hits whose +-pool_cells neighbourhood has enough hit weight from >= 2 viewpoints and a hit
        ratio (hits / (hits + rays that passed through)) of at least min_hit_ratio. With pool_misses (depth /
        ultrasonic) the ratio is over the neighbourhood, which keeps sparse depth noise out; without it (LiDAR
        map-change layer) the ratio is the cell's own, because grazing LiDAR rays cross the cells just in front of
        a real surface."""
        p = self.p
        out = {}
        n = p.pool_cells
        for (kx, ky), c in self.cells.items():
            if c[0] <= 0:
                continue
            if not p.pool_misses and c[0] / (c[0] + c[1]) < p.min_hit_ratio:
                continue
            w = miss = 0.0
            vps, src = set(), set()
            for dx in range(-n, n + 1):
                for dy in range(-n, n + 1):
                    o = self.cells.get((kx + dx, ky + dy))
                    if o is None:
                        continue
                    miss += o[1]
                    if o[0] <= 0:
                        continue
                    w += o[0]
                    vps |= o[2]
                    src |= o[3]
            if w < p.min_hit_weight or len(vps) < 2:
                continue
            if p.pool_misses and w / (w + miss) < p.min_hit_ratio:
                continue
            out[(kx, ky)] = src
        return out

    def candidates(self, places: Optional[Dict[str, Tuple[float, float]]] = None):
        """[{'name', 'polygon', 'candidate': True, 'evidence': {...}}], largest first."""
        p = self.p
        cells = self.candidate_cells()
        todo = set(cells)
        out = []
        j = p.join_cells
        while todo:
            seed = todo.pop()
            comp, stack = [seed], [seed]
            while stack:
                cx, cy = stack.pop()
                for dx in range(-j, j + 1):
                    for dy in range(-j, j + 1):
                        n = (cx + dx, cy + dy)
                        if n in todo:
                            todo.remove(n)
                            stack.append(n)
                            comp.append(n)
            area = len(comp) * p.cell_m ** 2
            if area < p.min_area_m2:
                continue
            xs = [k[0] for k in comp]
            ys = [k[1] for k in comp]
            x0, x1 = min(xs) * p.cell_m - p.pad_m, (max(xs) + 1) * p.cell_m + p.pad_m
            y0, y1 = min(ys) * p.cell_m - p.pad_m, (max(ys) + 1) * p.cell_m + p.pad_m
            sources = set()
            weight = 0.0
            for k in comp:
                sources |= cells[k]
                weight += self.cells[k][0]
            ev = {'cells': len(comp), 'area_m2': round(area, 3), 'hit_weight': round(weight, 1),
                  'sources': sorted(sources)}
            if places:
                d = min(_dist_rect(px, py, x0, x1, y0, y1) for px, py in places.values())
                nearest = min(places, key=lambda n: _dist_rect(*places[n], x0, x1, y0, y1))
                ev['nearest_place'] = nearest
                ev['nearest_place_m'] = round(d, 2)
            out.append({'polygon': [[round(x0, 2), round(y0, 2)], [round(x1, 2), round(y0, 2)],
                                    [round(x1, 2), round(y1, 2)], [round(x0, 2), round(y1, 2)]],
                        'candidate': True, 'evidence': ev})
        out.sort(key=lambda c: -c['evidence']['area_m2'])
        for i, c in enumerate(out, 1):
            c['name'] = f'Candidate {i}'
        return [{'name': c['name'], **{k: v for k, v in c.items() if k != 'name'}} for c in out]


def _dist_rect(px, py, x0, x1, y0, y1):
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return math.hypot(dx, dy)


def overlaps(candidate_polygon: Sequence[Sequence[float]], known_polygon: Sequence[Sequence[float]]):
    """Axis-aligned bounding-box overlap (used to tell a new candidate from an already confirmed obstacle)."""
    ax = [q[0] for q in candidate_polygon]
    ay = [q[1] for q in candidate_polygon]
    bx = [q[0] for q in known_polygon]
    by = [q[1] for q in known_polygon]
    return not (max(ax) < min(bx) or max(bx) < min(ax) or max(ay) < min(by) or max(by) < min(ay))

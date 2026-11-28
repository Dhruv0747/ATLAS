"""Guided mapping assistant: live map quality per area (2026-11-16, design docs/design/guided_mapping_assistant.md).

Pure Python, no ROS, no NumPy: the same code runs live (1 Hz node), in offline bag replays and in unit tests.
READ-ONLY ADVICE. It never commands motion, never writes places or maps, and never replaces the map acceptance gate
(atlas_map_acceptance_core.evaluate_acceptance_evidence), which alone decides accept/reject.

Per 0.5 m tile it reports ACCEPTED / WEAK / UNSEEN with a reason:
- coverage: fraction of the tile's known map cells observed from >= 2 distinct viewpoints;
- scan-match confidence: recent scan fits (fraction of LiDAR returns within 0.15 m of an occupied cell of the current
  map, the atlas_scan_fit_core metric) of samples that saw the tile;
- pose jumps: map->odom corrections (SLAM flip-flop, hall remaps 9-13) at the rover's position; cleared only by enough
  good re-check samples after the jump ("drive here again");
- frontiers: free cells next to unknown cells, clustered; openings >= the rover width are reported.
"""
from dataclasses import dataclass
import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

UNKNOWN = -1


@dataclass(frozen=True)
class QualityPolicy:
    tile_m: float = 0.5
    occupied_threshold: int = 65          # map_server trinary thresholds (occupied 0.65, free 0.25)
    free_threshold: int = 25
    min_sample_move_m: float = 0.10       # like slam_toolbox minimum_travel_distance
    min_sample_turn_deg: float = 5.0
    min_sample_period_s: float = 0.5      # <= 2 Hz
    beam_step: int = 2                    # ray-cast every 2nd beam (CPU)
    max_ray_m: float = 6.0
    min_range_m: float = 0.15
    fit_tolerance_m: float = 0.15         # atlas_scan_fit_core.ScanFitPolicy.wall_tolerance_m
    min_fit_endpoints: int = 30
    viewpoint_xy_m: float = 0.3
    viewpoint_yaw_deg: float = 30.0
    accept_coverage: float = 0.6
    accept_fit: float = 0.85              # same bar as the scan-fit gate / stop-and-go coach GO
    min_known_cells: int = 10             # tiles with fewer known cells are not judged
    min_tile_endpoints: int = 5           # a sample "saw" a tile with at least this many returns in it
    recent_fits: int = 10
    jump_m: float = 0.25
    jump_deg: float = 5.0
    recheck_samples: int = 3              # good samples needed in a tile after a jump
    frontier_min_m: float = 0.30          # report openings at least this wide (rover is 0.36 m wide)
    frontier_ready_block_m: float = 0.60  # an opening this wide near the driven path blocks "ready for review"
    corridor_m: float = 1.0               # tiles within this distance of the driven path are "on the corridor"
    frontier_near_m: float = 2.0
    prompt_near_m: float = 2.0
    ready_start_m: float = 0.5


class Grid:
    """Row-major occupancy grid, nav_msgs layout (row 0 at origin_y), -1 unknown, 0..100. No rotation."""
    def __init__(self, width, height, resolution, origin_x, origin_y, data):
        if width <= 0 or height <= 0 or resolution <= 0 or len(data) != width * height:
            raise ValueError('bad occupancy grid')
        self.w, self.h, self.res = int(width), int(height), float(resolution)
        self.ox, self.oy = float(origin_x), float(origin_y)
        self.data = data

    def cell(self, x, y):
        gx = int(math.floor((x - self.ox) / self.res))
        gy = int(math.floor((y - self.oy) / self.res))
        if 0 <= gx < self.w and 0 <= gy < self.h:
            return gx, gy
        return None

    def value(self, gx, gy):
        if 0 <= gx < self.w and 0 <= gy < self.h:
            return self.data[gy * self.w + gx]
        return UNKNOWN

    def centre(self, gx, gy):
        return self.ox + (gx + 0.5) * self.res, self.oy + (gy + 0.5) * self.res


def _wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def scan_endpoints(pose, laser_in_base, angle_min, angle_increment, ranges, range_min, range_max, step=1,
                   max_range=None):
    """World (x, y) LiDAR endpoints + the laser origin. pose and laser_in_base are (x, y, yaw)."""
    x, y, yaw = pose
    lx, ly, lyaw = laser_in_base
    ox = x + lx * math.cos(yaw) - ly * math.sin(yaw)
    oy = y + lx * math.sin(yaw) + ly * math.cos(yaw)
    base = yaw + lyaw
    hi = range_max if max_range is None else min(range_max, max_range)
    pts = []
    for i in range(0, len(ranges), max(1, step)):
        r = ranges[i]
        if r is None or not math.isfinite(r) or r < range_min or r > hi:
            continue
        a = base + angle_min + i * angle_increment
        pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
    return (ox, oy), pts


def ray_cells(x0, y0, x1, y1, res):
    """Integer world-cell keys (floor(x/res), floor(y/res)) from (x0,y0) up to but excluding the end cell."""
    cx, cy = int(math.floor(x0 / res)), int(math.floor(y0 / res))
    ex, ey = int(math.floor(x1 / res)), int(math.floor(y1 / res))
    dx, dy = abs(ex - cx), abs(ey - cy)
    sx, sy = (1 if ex > cx else -1), (1 if ey > cy else -1)
    err = dx - dy
    out = []
    while (cx, cy) != (ex, ey):
        out.append((cx, cy))
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy
    return out


def scan_fit(grid, points, policy=QualityPolicy()):
    """Fraction of points with an occupied cell within fit_tolerance_m (None if too few points)."""
    if len(points) < policy.min_fit_endpoints:
        return None
    n = int(math.ceil(policy.fit_tolerance_m / grid.res))
    tol2 = policy.fit_tolerance_m ** 2
    good = 0
    for x, y in points:
        c = grid.cell(x, y)
        if c is None:
            continue
        gx, gy = c
        found = False
        for yy in range(gy - n, gy + n + 1):
            for xx in range(gx - n, gx + n + 1):
                if grid.value(xx, yy) >= policy.occupied_threshold:
                    cx, cy = grid.centre(xx, yy)
                    if (cx - x) ** 2 + (cy - y) ** 2 <= tol2 + (grid.res * 0.71) ** 2:
                        found = True
                        break
            if found:
                break
        good += found
    return good / len(points)


class _Tile:
    __slots__ = ('fits', 'jump_t', 'jump_m', 'good_after_jump', 'visited')

    def __init__(self):
        self.fits = []
        self.jump_t = None
        self.jump_m = 0.0
        self.good_after_jump = 0
        self.visited = False


class QualityTracker:
    """Accumulates observations during a mapping drive; summary() gives tiles, frontiers, prompts and a verdict."""

    def __init__(self, policy=QualityPolicy(), cell_m=0.05):
        self.p = policy
        self.res = float(cell_m)
        self.cells: Dict[Tuple[int, int], List] = {}      # world cell -> [first_viewpoint, multi_view]
        self.tiles: Dict[Tuple[int, int], _Tile] = {}
        self.path: List[Tuple[float, float]] = []
        self.start: Optional[Tuple[float, float]] = None
        self.last_sample = None                           # (t, x, y, yaw)
        self.samples = 0

    # ------------------------------------------------------------------ helpers
    def tile_of(self, x, y):
        return int(math.floor(x / self.p.tile_m)), int(math.floor(y / self.p.tile_m))

    def _tile(self, key):
        t = self.tiles.get(key)
        if t is None:
            t = self.tiles[key] = _Tile()
        return t

    def _viewpoint(self, x, y, yaw):
        p = self.p
        return (int(round(x / p.viewpoint_xy_m)), int(round(y / p.viewpoint_xy_m)),
                int(round(math.degrees(yaw) / p.viewpoint_yaw_deg)) % int(round(360 / p.viewpoint_yaw_deg)))

    def _observe(self, key, vp):
        c = self.cells.get(key)
        if c is None:
            self.cells[key] = [vp, False]
        elif not c[1] and c[0] != vp:
            c[1] = True

    def want_sample(self, t, pose):
        """Decimation like SLAM: >= min period and moved/turned enough (the first sample is always taken)."""
        if self.last_sample is None:
            return True
        lt, lx, ly, lyaw = self.last_sample
        if t - lt < self.p.min_sample_period_s:
            return False
        moved = math.hypot(pose[0] - lx, pose[1] - ly) >= self.p.min_sample_move_m
        turned = abs(_wrap_deg(math.degrees(pose[2] - lyaw))) >= self.p.min_sample_turn_deg
        return moved or turned

    # ------------------------------------------------------------------ inputs
    def add_scan(self, t, pose, laser_in_base, angle_min, angle_increment, ranges, range_min, range_max, grid,
                 force=False):
        """One LiDAR scan at SLAM pose (map frame). grid = the current map. Returns the scan fit or None if the
        sample was decimated away / had too few returns."""
        if not all(math.isfinite(v) for v in pose):
            return None
        if not force and not self.want_sample(t, pose):
            return None
        p = self.p
        self.last_sample = (t, pose[0], pose[1], pose[2])
        self.samples += 1
        if self.start is None:
            self.start = (pose[0], pose[1])
        self.path.append((pose[0], pose[1]))
        self._tile(self.tile_of(pose[0], pose[1])).visited = True
        origin, pts = scan_endpoints(pose, laser_in_base, angle_min, angle_increment, ranges,
                                     max(range_min, p.min_range_m), range_max, step=1, max_range=p.max_ray_m)
        vp = self._viewpoint(*pose)
        res = self.res
        ratio = res / p.tile_m
        counts: Dict[Tuple[int, int], int] = {}      # tiles this sample saw: returns in them or beams through them
        for i, (x, y) in enumerate(pts):
            self._observe((int(math.floor(x / res)), int(math.floor(y / res))), vp)
            k = self.tile_of(x, y)
            counts[k] = counts.get(k, 0) + 1
            if i % p.beam_step == 0:
                for key in ray_cells(origin[0], origin[1], x, y, res):
                    self._observe(key, vp)
                    k = (int(math.floor(key[0] * ratio)), int(math.floor(key[1] * ratio)))
                    counts[k] = counts.get(k, 0) + 1
        fit = scan_fit(grid, pts, p)
        if fit is None:
            return None
        seen = {k for k, n in counts.items() if n >= p.min_tile_endpoints}
        seen.add(self.tile_of(pose[0], pose[1]))
        for k in seen:
            tile = self._tile(k)
            tile.fits.append(fit)
            if len(tile.fits) > p.recent_fits:
                del tile.fits[0]
            if tile.jump_t is not None and t > tile.jump_t and fit >= p.accept_fit:
                tile.good_after_jump += 1
        return fit

    def add_jump(self, t, position, translation_m, yaw_deg):
        """A map->odom correction (SLAM changed its mind). Marks the rover's tile and its 8 neighbours."""
        if translation_m < self.p.jump_m and abs(yaw_deg) < self.p.jump_deg:
            return False
        tx, ty = self.tile_of(*position)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                tile = self._tile((tx + dx, ty + dy))
                tile.jump_t = t
                tile.jump_m = max(tile.jump_m if tile.good_after_jump < self.p.recheck_samples else 0.0,
                                  translation_m)
                tile.good_after_jump = 0
        return True

    # ------------------------------------------------------------------ outputs
    def _tile_known_cells(self, grid, key):
        """World-cell keys of known map cells (free or occupied) in the tile, on the current grid."""
        p = self.p
        x0, y0 = key[0] * p.tile_m, key[1] * p.tile_m
        n = int(round(p.tile_m / self.res))
        out = []
        for j in range(n):
            for i in range(n):
                x, y = x0 + (i + 0.5) * self.res, y0 + (j + 0.5) * self.res
                c = grid.cell(x, y)
                if c is None:
                    continue
                v = grid.value(*c)
                if v != UNKNOWN and (v <= p.free_threshold or v >= p.occupied_threshold):
                    out.append((int(math.floor(x / self.res)), int(math.floor(y / self.res))))
        return out

    def tile_verdict(self, grid, key):
        """('ACCEPTED' | 'WEAK' | 'UNSEEN', reason, metrics)."""
        p = self.p
        tile = self.tiles.get(key)
        known = self._tile_known_cells(grid, key)
        multi = sum(1 for k in known if k in self.cells and self.cells[k][1])
        seen = sum(1 for k in known if k in self.cells)
        coverage = multi / len(known) if known else 0.0
        fits = sorted(tile.fits) if tile else []
        fit = fits[len(fits) // 2] if fits else None
        m = {'known': len(known), 'seen': seen, 'coverage': round(coverage, 2),
             'fit': None if fit is None else round(fit, 2)}
        if tile is None and seen == 0:
            return 'UNSEEN', '', m
        if len(known) < p.min_known_cells:
            return 'UNSEEN', '', m
        if tile is not None and tile.jump_t is not None and tile.good_after_jump < p.recheck_samples:
            m['jump_m'] = round(tile.jump_m, 2)
            return 'WEAK', f'position jumped {tile.jump_m:.1f} m here', m
        if fit is not None and fit < p.accept_fit:
            return 'WEAK', f'scan match weak (fit {fit:.2f})', m
        if coverage < p.accept_coverage:
            return 'WEAK', 'seen from too few positions' if seen else 'not observed yet', m
        if fit is None:
            return 'WEAK', 'no scan match yet', m
        return 'ACCEPTED', '', m

    def _corridor_tiles(self, grid):
        p = self.p
        r = int(math.ceil(p.corridor_m / p.tile_m))
        keys = set()
        for x, y in self.path:
            tx, ty = self.tile_of(x, y)
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    k = (tx + dx, ty + dy)
                    cx, cy = (k[0] + 0.5) * p.tile_m, (k[1] + 0.5) * p.tile_m
                    if math.hypot(cx - x, cy - y) <= p.corridor_m + p.tile_m * 0.71:
                        keys.add(k)
        return keys

    def frontiers(self, grid):
        """Clusters of free cells next to unknown cells: [{'length_m', 'x', 'y', 'cells'}], longest first."""
        p = self.p
        is_front = set()
        for gy in range(grid.h):
            row = gy * grid.w
            for gx in range(grid.w):
                v = grid.data[row + gx]
                if v == UNKNOWN or v > p.free_threshold:
                    continue
                for nx, ny in ((gx + 1, gy), (gx - 1, gy), (gx, gy + 1), (gx, gy - 1)):
                    if 0 <= nx < grid.w and 0 <= ny < grid.h and grid.data[ny * grid.w + nx] == UNKNOWN:
                        is_front.add((gx, gy))
                        break
        out = []
        while is_front:
            seed = is_front.pop()
            stack, comp = [seed], [seed]
            while stack:
                cx, cy = stack.pop()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        n = (cx + dx, cy + dy)
                        if n in is_front:
                            is_front.remove(n)
                            stack.append(n)
                            comp.append(n)
            xs = [c[0] for c in comp]
            ys = [c[1] for c in comp]
            length = max(max(xs) - min(xs) + 1, max(ys) - min(ys) + 1) * grid.res
            if length >= p.frontier_min_m:
                cx, cy = grid.centre(sum(xs) / len(xs), sum(ys) / len(ys))
                out.append({'length_m': round(length, 2), 'x': round(cx, 2), 'y': round(cy, 2), 'cells': len(comp)})
        out.sort(key=lambda f: -f['length_m'])
        return out

    def _dist_to_path(self, x, y):
        return min((math.hypot(x - px, y - py) for px, py in self.path), default=float('inf'))

    def summary(self, grid, robot=None, include_frontiers=True, frontiers=None):
        """{'tiles': [[ix, iy, code, reason]], 'counts', 'frontiers', 'prompts', 'ready', 'verdict_text'}.
        code: 'A' accepted, 'W' weak (UNSEEN tiles are omitted). Text is English (dashboard rule).
        frontiers: optional precomputed self.frontiers(grid) (the live node refreshes them less often)."""
        p = self.p
        corridor = self._corridor_tiles(grid)
        tiles, counts = [], {'ACCEPTED': 0, 'WEAK': 0, 'UNSEEN': 0}
        weak = []
        for key in sorted(corridor | set(self.tiles)):
            verdict, reason, m = self.tile_verdict(grid, key)
            counts[verdict] += 1
            if verdict == 'UNSEEN':
                continue
            tiles.append([key[0], key[1], verdict[0], reason])
            if verdict == 'WEAK' and key in corridor:
                weak.append((key, reason))
        fronts = []
        if include_frontiers:
            fronts = [f for f in (self.frontiers(grid) if frontiers is None else frontiers)
                      if self._dist_to_path(f['x'], f['y']) <= p.frontier_near_m]
        prompts = []
        if robot is not None:
            rx, ry = robot[0], robot[1]
            near = sorted(((math.hypot((k[0] + .5) * p.tile_m - rx, (k[1] + .5) * p.tile_m - ry), k, r)
                           for k, r in weak), key=lambda e: e[0])
            near = [e for e in near if e[0] <= p.prompt_near_m]
            if near:
                d, k, r = near[0]
                if r.startswith('position jumped'):
                    prompts.append('Position jumped here: stop, wait for GO, then continue slowly')
                else:
                    prompts.append(f'Weak area ahead ({r}): drive slowly through here again')
            for f in fronts:
                if f['length_m'] >= p.frontier_ready_block_m and \
                        math.hypot(f['x'] - rx, f['y'] - ry) <= p.prompt_near_m:
                    prompts.append(f"Unexplored opening ({f['length_m']:.1f} m wide): drive closer to fill it in")
                    break
        blocking = [f for f in fronts if f['length_m'] >= p.frontier_ready_block_m]
        back_home = bool(self.start and robot is not None and
                         math.hypot(robot[0] - self.start[0], robot[1] - self.start[1]) <= p.ready_start_m)
        ready = bool(self.path) and not weak and not blocking and back_home and counts['ACCEPTED'] > 0
        if ready:
            prompts.append('Map ready for review: stop the session when parked')
            text = 'Map ready for review (the acceptance check still decides)'
        elif not self.path:
            text = 'Waiting for the first scan'
        else:
            parts = []
            if weak:
                parts.append(f'{len(weak)} weak area' + ('s' if len(weak) != 1 else ''))
            if blocking:
                parts.append(f'{len(blocking)} unexplored opening' + ('s' if len(blocking) != 1 else ''))
            if not back_home:
                parts.append('drive back to the start to close the loop')
            text = 'Keep mapping: ' + ', '.join(parts) if parts else 'Keep mapping'
        return {'tile_m': p.tile_m, 'tiles': tiles, 'counts': counts, 'weak': len(weak),
                'frontiers': fronts[:10], 'prompts': prompts, 'ready': ready, 'verdict_text': text,
                'samples': self.samples}


def pose_jumps(map_odom: Sequence[Tuple[float, float, float, float]], policy=QualityPolicy()):
    """[(t, dx_m, dyaw_deg)] for consecutive map->odom (t, x, y, yaw) changes over the jump thresholds."""
    out = []
    for (t0, x0, y0, a0), (t1, x1, y1, a1) in zip(map_odom, map_odom[1:]):
        d = math.hypot(x1 - x0, y1 - y0)
        da = _wrap_deg(math.degrees(a1 - a0))
        if d >= policy.jump_m or abs(da) >= policy.jump_deg:
            out.append((t1, d, da))
    return out

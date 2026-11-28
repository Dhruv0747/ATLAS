"""Add-only map extension (2026-11-26; owner: "the saved map is right, don't disturb it; add new places as I drive").
Design: docs/design/guided_mapping_assistant.md section 10.

Pure Python, no ROS, no NumPy. Offline/advisory: it writes a CANDIDATE map pair only; promotion stays with the
existing acceptance gate, parked review and transactionally_promote_map_pair, after the owner's OK.

1. align(): find the rigid transform T (new-piece frame -> saved-map frame) by matching the new piece's wall cells to
   the saved map's walls, coarse-to-fine around a starting guess (the localization map->odom at session start).
2. merge(): the output grid holds every saved cell BIT-EXACT (known and unknown); only cells UNKNOWN in the saved map
   are filled from the aligned new piece. The output may grow by whole cells to hold the new area.
3. evaluate(): align + merge + fail-closed checks: the piece lines up (match + enough overlap), it does not claim walls
   in saved free space, it adds something, and every added free area is reachable from the saved free space.
"""
from dataclasses import dataclass
import math
from pathlib import Path

UNKNOWN = -1


class Grid:
    """Row-major occupancy grid (nav_msgs layout, row 0 at origin_y): -1 unknown, 0 free, 100 occupied."""
    def __init__(self, width, height, resolution, origin_x, origin_y, data):
        if width <= 0 or height <= 0 or resolution <= 0 or len(data) != width * height:
            raise ValueError('bad occupancy grid')
        self.w, self.h, self.res = int(width), int(height), float(resolution)
        self.ox, self.oy = float(origin_x), float(origin_y)
        self.data = data

    def cell(self, x, y):
        gx = int(math.floor((x - self.ox) / self.res))
        gy = int(math.floor((y - self.oy) / self.res))
        return (gx, gy) if 0 <= gx < self.w and 0 <= gy < self.h else None

    def value_at(self, x, y):
        c = self.cell(x, y)
        return UNKNOWN if c is None else self.data[c[1] * self.w + c[0]]


@dataclass(frozen=True)
class ExtendPolicy:
    occupied: int = 65
    free: int = 25
    match_tol_cells: int = 2                 # 0.10 m at 5 cm cells
    coarse_xy_m: float = 0.5
    coarse_step_m: float = 0.1
    coarse_yaw_deg: float = 10.0
    coarse_yaw_step_deg: float = 2.0
    fine_xy_m: float = 0.1
    fine_step_m: float = 0.025
    fine_yaw_deg: float = 2.0
    fine_yaw_step_deg: float = 0.5
    coarse_points: int = 300
    fine_points: int = 1500
    min_match: float = 0.80                  # fraction of overlapping new wall cells on a saved wall (+-0.10 m)
    min_overlap_points: int = 100            # new wall cells over saved known space
    max_conflict: float = 0.15               # new walls in saved free space (beyond +-0.10 m of a saved wall)
    min_added_m2: float = 0.25
    max_unreachable_m2: float = 0.5          # added free space not reachable from the saved free space


def _known(v, p):
    return v != UNKNOWN and (v <= p.free or v >= p.occupied)


def _norm(v, p):
    if v == UNKNOWN:
        return UNKNOWN
    if v >= p.occupied:
        return 100
    if v <= p.free:
        return 0
    return UNKNOWN


def _occ_points(g, p):
    pts = []
    for gy in range(g.h):
        row = gy * g.w
        for gx in range(g.w):
            v = g.data[row + gx]
            if v != UNKNOWN and v >= p.occupied:
                pts.append((g.ox + (gx + 0.5) * g.res, g.oy + (gy + 0.5) * g.res))
    return pts


def _subsample(pts, n):
    if len(pts) <= n:
        return pts
    step = len(pts) / float(n)
    return [pts[int(i * step)] for i in range(n)]


def _near_walls(g, p):
    """{cell index: weight} for cells within match_tol_cells of a saved wall: 1.0 on the wall, falling by distance
    (Chebyshev) so the alignment score peaks at the true pose instead of being flat across the tolerance."""
    r = p.match_tol_cells
    near = {}
    for gy in range(g.h):
        row = gy * g.w
        for gx in range(g.w):
            v = g.data[row + gx]
            if v != UNKNOWN and v >= p.occupied:
                for yy in range(max(0, gy - r), min(g.h, gy + r + 1)):
                    base = yy * g.w
                    for xx in range(max(0, gx - r), min(g.w, gx + r + 1)):
                        wgt = 1.0 - max(abs(xx - gx), abs(yy - gy)) / (r + 1.0)
                        if wgt > near.get(base + xx, 0.0):
                            near[base + xx] = wgt
    return near


def _score(pts, T, old, near, p):
    """(weighted, matched, overlap): new wall points over saved known cells; matched = on a saved wall (+-tol);
    weighted = matched points weighted by closeness (used for the search)."""
    tx, ty, th = T
    c, s = math.cos(th), math.sin(th)
    matched = overlap = 0
    weighted = 0.0
    ox, oy, res, w, h, data = old.ox, old.oy, old.res, old.w, old.h, old.data
    for px, py in pts:
        gx = int(math.floor((tx + c * px - s * py - ox) / res))
        gy = int(math.floor((ty + s * px + c * py - oy) / res))
        if 0 <= gx < w and 0 <= gy < h:
            i = gy * w + gx
            if _known(data[i], p):
                overlap += 1
                wgt = near.get(i)
                if wgt:
                    matched += 1
                    weighted += wgt
    return weighted, matched, overlap


def _frange(lo, hi, step):
    n = int(round((hi - lo) / step))
    return [lo + k * step for k in range(n + 1)]


def align(old, new, init, policy=ExtendPolicy(), near=None):
    """(T, match_fraction, overlap_points). T maps new-piece coordinates into the saved-map frame."""
    p = policy
    if abs(old.res - new.res) > 1e-9:
        raise ValueError('saved map and new piece must have the same resolution')
    near = _near_walls(old, p) if near is None else near
    pts_all = _occ_points(new, p)
    best = (init, -1)
    for stage, (xy, xs, yaw, ys, n) in enumerate((
            (p.coarse_xy_m, p.coarse_step_m, p.coarse_yaw_deg, p.coarse_yaw_step_deg, p.coarse_points),
            (p.fine_xy_m, p.fine_step_m, p.fine_yaw_deg, p.fine_yaw_step_deg, p.fine_points))):
        pts = _subsample(pts_all, n)
        cx, cy, cth = best[0] if stage else init
        best = ((cx, cy, cth), -1)
        for dth in _frange(-yaw, yaw, ys):
            th = cth + math.radians(dth)
            for dx in _frange(-xy, xy, xs):
                for dy in _frange(-xy, xy, xs):
                    m, _, _ = _score(pts, (cx + dx, cy + dy, th), old, near, p)
                    if m > best[1]:
                        best = ((cx + dx, cy + dy, th), m)
    T = best[0]
    _, matched, overlap = _score(pts_all, T, old, near, p)
    return T, (matched / overlap if overlap else 0.0), overlap


def merge(old, new, T, policy=ExtendPolicy(), near=None):
    """(grid, stats, added_idx, conflict_idx). Saved cells are copied bit-exact; only saved-unknown cells take the
    aligned new value. The output origin is the saved origin shifted by whole cells."""
    p = policy
    res = old.res
    tx, ty, th = T
    c, s = math.cos(th), math.sin(th)
    corners = [(new.ox, new.oy), (new.ox + new.w * res, new.oy), (new.ox, new.oy + new.h * res),
               (new.ox + new.w * res, new.oy + new.h * res)]
    wx = [tx + c * x - s * y for x, y in corners]
    wy = [ty + s * x + c * y for x, y in corners]
    left = max(0, int(math.ceil((old.ox - min(wx)) / res - 1e-9)))
    down = max(0, int(math.ceil((old.oy - min(wy)) / res - 1e-9)))
    right = max(0, int(math.ceil((max(wx) - (old.ox + old.w * res)) / res - 1e-9)))
    up = max(0, int(math.ceil((max(wy) - (old.oy + old.h * res)) / res - 1e-9)))
    W, H = old.w + left + right, old.h + down + up
    ox, oy = old.ox - left * res, old.oy - down * res
    out = [UNKNOWN] * (W * H)
    is_old_known = bytearray(W * H)
    added = []
    for gy in range(H):
        cy_ = oy + (gy + 0.5) * res
        ogy = gy - down
        for gx in range(W):
            i = gy * W + gx
            ogx = gx - left
            if 0 <= ogx < old.w and 0 <= ogy < old.h:
                v = old.data[ogy * old.w + ogx]
                if _known(v, p):
                    out[i] = v
                    is_old_known[i] = 1
                    continue
                out[i] = v                                   # saved unknown/uncertain value kept unless filled
            cx_ = ox + (gx + 0.5) * res
            dx, dy = cx_ - tx, cy_ - ty                     # inverse transform into the new piece
            nx, ny = c * dx + s * dy, -s * dx + c * dy
            ngx = int(math.floor((nx - new.ox) / res))
            ngy = int(math.floor((ny - new.oy) / res))
            if 0 <= ngx < new.w and 0 <= ngy < new.h:
                nv = _norm(new.data[ngy * new.w + ngx], p)
                if nv != UNKNOWN:
                    out[i] = nv
                    added.append(i)
    grid = Grid(W, H, res, ox, oy, out)
    # conflicts: new wall cells over saved FREE space, beyond the match tolerance of a saved wall
    near = _near_walls(old, p) if near is None else near
    conflicts, new_on_known = [], 0
    for px, py in _occ_points(new, p):
        x, y = tx + c * px - s * py, ty + s * px + c * py
        ogx = int(math.floor((x - old.ox) / res))
        ogy = int(math.floor((y - old.oy) / res))
        if 0 <= ogx < old.w and 0 <= ogy < old.h:
            oi = ogy * old.w + ogx
            v = old.data[oi]
            if _known(v, p):
                new_on_known += 1
                if v <= p.free and oi not in near:
                    conflicts.append((ogy + down) * W + ogx + left)
    # reachability: flood the free space from every saved free cell
    seen = bytearray(W * H)
    stack = [i for i in range(W * H) if is_old_known[i] and out[i] <= p.free]
    for i in stack:
        seen[i] = 1
    while stack:
        i = stack.pop()
        gx, gy = i % W, i // W
        for j in ((i - 1) if gx > 0 else -1, (i + 1) if gx < W - 1 else -1,
                  (i - W) if gy > 0 else -1, (i + W) if gy < H - 1 else -1):
            if j >= 0 and not seen[j] and out[j] != UNKNOWN and out[j] <= p.free:
                seen[j] = 1
                stack.append(j)
    added_free = [i for i in added if out[i] <= p.free]
    unreachable = sum(1 for i in added_free if not seen[i])
    contact = 0
    for i in added_free:
        gx, gy = i % W, i // W
        for j in ((i - 1) if gx > 0 else -1, (i + 1) if gx < W - 1 else -1,
                  (i - W) if gy > 0 else -1, (i + W) if gy < H - 1 else -1):
            if j >= 0 and is_old_known[j] and out[j] <= p.free:
                contact += 1
                break
    changed = 0
    for gy in range(old.h):                                  # proof, not assumption: saved cells unchanged
        for gx in range(old.w):
            v = old.data[gy * old.w + gx]
            if _known(v, p) and out[(gy + down) * W + gx + left] != v:
                changed += 1
    a2 = res * res
    stats = {'added_free_m2': round(len(added_free) * a2, 2),
             'added_wall_m2': round((len(added) - len(added_free)) * a2, 2),
             'unreachable_m2': round(unreachable * a2, 2), 'contact_cells': contact,
             'conflict_fraction': round(len(conflicts) / new_on_known, 3) if new_on_known else 0.0,
             'saved_cells_changed': changed, 'grown_cells': {'left': left, 'right': right, 'down': down, 'up': up}}
    return grid, stats, added, conflicts


def evaluate(old, new, init, policy=ExtendPolicy()):
    """{'ok', 'failures' (English), 'T', 'match', 'overlap', 'stats', 'grid', 'added', 'conflicts'}."""
    p = policy
    near = _near_walls(old, p)
    T, match, overlap = align(old, new, init, p, near)
    grid, stats, added, conflicts = merge(old, new, T, p, near)
    failures = []
    if match < p.min_match or overlap < p.min_overlap_points:
        failures.append(f'the new piece does not line up with the saved map (match {match * 100:.0f} %, '
                        f'{overlap} wall points in the overlap; need {p.min_match * 100:.0f} % and '
                        f'{p.min_overlap_points})')
    if stats['conflict_fraction'] > p.max_conflict:
        failures.append(f"the new piece disagrees with the saved map ({stats['conflict_fraction'] * 100:.0f} % of "
                        f"its walls fall in saved free space; limit {p.max_conflict * 100:.0f} %)")
    if stats['added_free_m2'] < p.min_added_m2:
        failures.append(f"nothing new to add (only {stats['added_free_m2']} m² of new free space)")
    if stats['unreachable_m2'] > p.max_unreachable_m2:
        failures.append(f"part of the new area is not connected to the saved map ({stats['unreachable_m2']} m² "
                        f"cannot be reached from saved free space)")
    if stats['saved_cells_changed']:
        failures.append(f"internal error: {stats['saved_cells_changed']} saved cells changed")
    return {'ok': not failures, 'failures': failures, 'T': (round(T[0], 3), round(T[1], 3), round(T[2], 4)),
            'match': round(match, 3), 'overlap': overlap, 'stats': stats, 'grid': grid, 'added': added,
            'conflicts': conflicts}


def wide_search(old, new, policy=ExtendPolicy()):
    """Rough pose when no starting guess is trusted: all headings (10 deg) and +-3 m around the map centres, then
    the caller refines with align/evaluate. Slow (about 20 s on the Jetson), offline only."""
    from dataclasses import replace
    near = _near_walls(old, policy)
    wide = replace(policy, coarse_xy_m=3.0, coarse_step_m=0.25, coarse_yaw_deg=5.0, coarse_yaw_step_deg=5.0,
                   coarse_points=150, fine_xy_m=0.25, fine_step_m=0.125, fine_yaw_deg=5.0, fine_yaw_step_deg=2.5,
                   fine_points=300)
    best = None
    cx = old.ox + old.w * old.res / 2 - (new.ox + new.w * new.res / 2)
    cy = old.oy + old.h * old.res / 2 - (new.oy + new.h * new.res / 2)
    for yaw in range(0, 360, 10):
        T, match, overlap = align(old, new, (cx, cy, math.radians(yaw)), wide, near)
        key = match * min(1.0, overlap / 300.0)
        if best is None or key > best[0]:
            best = (key, T)
    return best[1]


# ---------------------------------------------------------------------------------------------------------------- IO
def read_map(yaml_path):
    """map_server YAML + binary PGM -> Grid (100 / 0 / -1). PGM 205 is always unknown (map_saver's value)."""
    vals = {}
    for line in Path(yaml_path).read_text().splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            vals[k.strip()] = v.strip()
    res = float(vals['resolution'])
    origin = [float(x) for x in vals['origin'].strip('[]').split(',')]
    occ, free = float(vals.get('occupied_thresh', 0.65)), float(vals.get('free_thresh', 0.196))
    negate = int(vals.get('negate', 0))
    raw = (Path(yaml_path).parent / vals['image']).read_bytes()
    parts, pos = [], 0
    while len(parts) < 4:
        while raw[pos:pos + 1].isspace():
            pos += 1
        if raw[pos:pos + 1] == b'#':
            pos = raw.index(b'\n', pos) + 1
            continue
        end = pos
        while not raw[end:end + 1].isspace():
            end += 1
        parts.append(raw[pos:end])
        pos = end
    pos += 1
    if parts[0] != b'P5':
        raise ValueError('only binary PGM (P5) maps are supported')
    w, h, maxv = int(parts[1]), int(parts[2]), int(parts[3])
    pix = raw[pos:pos + w * h]
    data = [0] * (w * h)
    for row in range(h):
        gy = h - 1 - row
        for gx in range(w):
            rv = pix[row * w + gx]
            if rv == 205 and maxv == 255 and not negate:
                data[gy * w + gx] = UNKNOWN
                continue
            v = rv / maxv
            pr = v if negate else 1.0 - v
            data[gy * w + gx] = 100 if pr > occ else (0 if pr < free else UNKNOWN)
    return Grid(w, h, res, origin[0], origin[1], data)


def write_map(grid, base_path):
    """Write base.pgm + base.yaml (trinary: 0 occupied, 254 free, 205 unknown). Returns the YAML path."""
    base = Path(base_path)
    pix = bytearray()
    for row in range(grid.h):
        gy = grid.h - 1 - row
        for gx in range(grid.w):
            v = grid.data[gy * grid.w + gx]
            pix.append(205 if v == UNKNOWN else (0 if v >= 65 else 254))
    base.with_suffix('.pgm').write_bytes(b'P5\n%d %d\n255\n' % (grid.w, grid.h) + bytes(pix))
    y = base.with_suffix('.yaml')
    y.write_text(f'image: {base.name}.pgm\nmode: trinary\nresolution: {grid.res}\n'
                 f'origin: [{grid.ox:.6f}, {grid.oy:.6f}, 0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n')
    return y

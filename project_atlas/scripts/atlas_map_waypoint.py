"""Validate a waypoint tapped on the accepted 2D map (2026-11-15, owner request: tap the map to set a waypoint).

Pure, no ROS. A tapped point becomes a waypoint only if, on the ACCEPTED occupancy map:
  * it lies inside the map and on a FREE cell (unknown is refused);
  * no occupied or unknown cell is within CLEARANCE_M (rover footprint half-diagonal 0.31 m + margin), so the rover
    can physically stand there.
Nav2 / mission control still plan and check everything before driving; this only refuses impossible targets early.
"""
import math

CLEARANCE_M = 0.35


def check_point(x, y, grid, meta, clearance_m=CLEARANCE_M):
    """grid: (width, height, pixels row-major top row first). meta: resolution, origin, occupied/free thresh, negate.
    Returns None if OK, else a short reason."""
    if not (math.isfinite(x) and math.isfinite(y)):
        return 'invalid point'
    width, height, pixels = grid
    res = float(meta['resolution'])
    ox, oy = float(meta['origin'][0]), float(meta['origin'][1])
    oyaw = float(meta['origin'][2]) if len(meta['origin']) > 2 else 0.0
    dx, dy = x - ox, y - oy
    c, s = math.cos(-oyaw), math.sin(-oyaw)
    gx, gy = int(math.floor((c * dx - s * dy) / res)), int(math.floor((s * dx + c * dy) / res))
    if not (0 <= gx < width and 0 <= gy < height):
        return 'outside the map'
    occ_t, free_t = float(meta.get('occupied_thresh', 0.65)), float(meta.get('free_thresh', 0.25))
    negate = int(meta.get('negate', 0))

    def cls(ix, iy):
        if not (0 <= ix < width and 0 <= iy < height):
            return 'unknown'
        v = pixels[(height - 1 - iy) * width + ix]
        if v == 205 and meta.get('mode', 'trinary') == 'trinary':
            return 'unknown'                     # map_saver trinary unknown value
        p = v / 255.0 if negate else (255 - v) / 255.0
        return 'occupied' if p > occ_t else ('free' if p < free_t else 'unknown')

    if cls(gx, gy) != 'free':
        return f'that spot is {cls(gx, gy)} on the map'
    r = int(math.ceil(clearance_m / res))
    for j in range(-r, r + 1):
        for i in range(-r, r + 1):
            if (i * i + j * j) * res * res > clearance_m * clearance_m:
                continue
            k = cls(gx + i, gy + j)
            if k != 'free':
                return f'too close to a wall/obstacle ({k} within {clearance_m:.2f} m)'
    return None


def heading_towards(from_xy, to_xy, fallback=0.0):
    dx, dy = to_xy[0] - from_xy[0], to_xy[1] - from_xy[1]
    return math.atan2(dy, dx) if math.hypot(dx, dy) > 0.05 else fallback

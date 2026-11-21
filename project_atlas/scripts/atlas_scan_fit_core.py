"""Pure mission-start check: does a fresh scan agree with the saved map?

Background: 2026-10-10 audits found AMCL can sit perfectly still, with tiny
covariance, at a wrong pose (outbound 1636 after a manual move: 0.55 m off,
held-out fit 0.61; failed round trip: fit 0.26-0.80). Covariance and
stationary-stability checks pass in that state. This check scores the
current AMCL pose against beams AMCL itself never uses, so it is an
independent cross-check.

Only a refusal can result. Nothing here publishes, seeds or moves anything.
"""
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Optional, Sequence, Tuple

from atlas_map_acceptance_core import _map_yaml_values, _read_pgm


@dataclass(frozen=True)
class ScanFitPolicy:
    # Evidence (docs/audits/ATLAS_AMCL_PARKED_DIVERSITY_MULTIDRIVE_2026-10-10.md):
    # correct parked poses scored 0.95-1.00; known-wrong poses 0.26-0.80.
    min_fit_fraction: float = 0.85
    wall_tolerance_m: float = 0.15
    min_endpoints: int = 60
    max_scan_age_s: float = 1.0
    min_range_m: float = 0.3
    max_range_m: float = 8.0
    amcl_max_beams: int = 60


@dataclass(frozen=True)
class ScanFitResult:
    ok: bool
    fit_fraction: Optional[float]
    endpoints: int
    reason: str


def load_occupied_points(yaml_path: Path, image_path: Path) -> Tuple[Tuple[float, float], ...]:
    """Centres of occupied cells in a Nav2 trinary map, in map metres."""
    metadata = _map_yaml_values(Path(yaml_path))
    width, height, pixels = _read_pgm(Path(image_path))
    resolution = float(metadata["resolution"])
    origin_x, origin_y = metadata["origin"]
    occupied = []
    for index, value in enumerate(pixels):
        is_occupied = value >= 254 if metadata["negate"] else value <= 1
        if not is_occupied:
            continue
        image_row, column = divmod(index, width)
        map_row = height - image_row - 1
        occupied.append((origin_x + (column + 0.5) * resolution,
                         origin_y + (map_row + 0.5) * resolution))
    if not occupied:
        raise ValueError("saved map contains no occupied cells")
    return tuple(occupied)


class OccupiedIndex:
    """Pure-Python nearest-wall lookup over occupied cell centres.

    Exact for any distance up to ``search_m``; beyond that it reports
    ``far_m``, which only matters as "not within tolerance".
    """

    def __init__(self, points: Sequence[Tuple[float, float]], resolution: float,
                 search_m: float = 0.30, far_m: float = 99.0):
        if not points:
            raise ValueError("no occupied cells")
        if not math.isfinite(resolution) or resolution <= 0:
            raise ValueError("invalid map resolution")
        self.resolution = float(resolution)
        self.far_m = far_m
        self.reach = int(math.ceil(search_m / self.resolution)) + 1
        self.cells = {}
        for x, y in points:
            key = (math.floor(x / self.resolution), math.floor(y / self.resolution))
            self.cells.setdefault(key, []).append((x, y))

    def __call__(self, world: Sequence[Tuple[float, float]]) -> list:
        out = []
        for x, y in world:
            cx, cy = math.floor(x / self.resolution), math.floor(y / self.resolution)
            best = self.far_m
            for dx in range(-self.reach, self.reach + 1):
                for dy in range(-self.reach, self.reach + 1):
                    for px, py in self.cells.get((cx + dx, cy + dy), ()):
                        d = math.hypot(px - x, py - y)
                        if d < best:
                            best = d
            out.append(best)
        return out


def load_occupied_index(yaml_path: Path, image_path: Path) -> "OccupiedIndex":
    """Nearest-wall index for the exact accepted map bytes."""
    resolution = float(_map_yaml_values(Path(yaml_path))["resolution"])
    return OccupiedIndex(load_occupied_points(yaml_path, image_path), resolution)


def unused_beam_points(angle_min: float, angle_increment: float, ranges: Sequence[float],
                       range_min: float, range_max: float, policy: ScanFitPolicy) -> list:
    """Laser-frame endpoints of beams AMCL's likelihood model does not sample."""
    count = len(ranges)
    step = max(1, (count - 1) // (policy.amcl_max_beams - 1)) if policy.amcl_max_beams > 1 else 1
    low = max(policy.min_range_m, range_min)
    high = min(policy.max_range_m, range_max)
    points = []
    for index, value in enumerate(ranges):
        if index % step == 0:
            continue
        value = float(value)
        if not math.isfinite(value) or value < low or value > high:
            continue
        angle = angle_min + index * angle_increment
        points.append((value * math.cos(angle), value * math.sin(angle)))
    return points


def compose(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], a[2] + b[2])


def evaluate(points: Sequence[Tuple[float, float]], robot_pose: Tuple[float, float, float],
             laser_in_base: Tuple[float, float, float], nearest_wall_distance,
             scan_age_s: Optional[float], policy: ScanFitPolicy = ScanFitPolicy()) -> ScanFitResult:
    """Fail closed unless enough fresh endpoints land on mapped walls.

    ``nearest_wall_distance`` maps a list of (x, y) map points to distances.
    """
    if scan_age_s is None or not math.isfinite(scan_age_s):
        return ScanFitResult(False, None, 0, "no LiDAR scan received")
    if scan_age_s < 0 or scan_age_s > policy.max_scan_age_s:
        return ScanFitResult(False, None, 0, f"LiDAR scan is stale ({scan_age_s:.1f}s old)")
    if not all(math.isfinite(v) for v in (*robot_pose, *laser_in_base)):
        return ScanFitResult(False, None, 0, "pose or laser transform is not finite")
    if len(points) < policy.min_endpoints:
        return ScanFitResult(False, None, len(points),
                             f"too few usable LiDAR returns ({len(points)} < {policy.min_endpoints})")
    laser = compose(robot_pose, laser_in_base)
    c, s = math.cos(laser[2]), math.sin(laser[2])
    world = [(laser[0] + c * x - s * y, laser[1] + s * x + c * y) for x, y in points]
    distances = list(nearest_wall_distance(world))
    if len(distances) != len(world) or not all(math.isfinite(d) for d in distances):
        return ScanFitResult(False, None, len(points), "map distance lookup failed")
    fraction = sum(d <= policy.wall_tolerance_m for d in distances) / len(distances)
    if fraction < policy.min_fit_fraction:
        return ScanFitResult(
            False, fraction, len(points),
            f"LiDAR does not match the map at the current pose: {fraction:.0%} of "
            f"returns within {policy.wall_tolerance_m * 100:.0f} cm of a wall "
            f"(need {policy.min_fit_fraction:.0%}); ATLAS may have been moved. "
            "Set the current named place, then retry")
    return ScanFitResult(True, fraction, len(points), "LiDAR agrees with the map")

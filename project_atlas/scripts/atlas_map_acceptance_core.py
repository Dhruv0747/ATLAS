#!/usr/bin/env python3
"""ROS-independent safety rules for promoting an ATLAS occupancy map."""

import ast
from collections import deque
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid


EVIDENCE_SCHEMA_VERSION = 3
UNBOUND_LEGACY_MAP_ID = "legacy-unversioned-no-accepted-map"
COMMISSIONED_SLAM_TF_FUTURE_OFFSET_S = 1.5
MAX_TF_SOURCE_FUTURE_S = 1.0


@dataclass(frozen=True)
class MapAcceptancePolicy:
    """Commissioned limits which every candidate map must satisfy."""

    max_tf_translation_jump_m: float = 0.15
    max_tf_yaw_jump_deg: float = 5.0
    max_closure_translation_m: float = 0.15
    max_closure_yaw_deg: float = 10.0
    min_tf_samples: int = 2
    max_observation_start_delay_s: float = 5.0
    max_evidence_age_s: float = 5.0
    max_tf_sample_gap_s: float = 5.0
    max_tf_source_age_s: float = 5.0
    max_tf_source_future_offset_s: float = COMMISSIONED_SLAM_TF_FUTURE_OFFSET_S
    max_tf_source_future_skew_s: float = MAX_TF_SOURCE_FUTURE_S
    min_footprint_length_m: float = 0.49
    min_footprint_width_m: float = 0.35
    min_candidate_clearance_m: float = 0.18
    min_path_poses: int = 2


def angle_delta(first: float, second: float) -> float:
    """Return the shortest signed angular difference from first to second."""

    return math.atan2(math.sin(second - first), math.cos(second - first))


def quaternion_yaw(pose: Dict[str, Any]) -> float:
    """Read planar yaw from an ATLAS pose dictionary."""

    qx = float(pose.get("qx", 0.0))
    qy = float(pose.get("qy", 0.0))
    qz = float(pose.get("qz", 0.0))
    qw = float(pose.get("qw", 1.0))
    siny = 2.0 * (qw * qz + qx * qy)
    cosy = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny, cosy)


def closure_evidence(start: Dict[str, Any], end: Dict[str, Any]) -> Dict[str, Any]:
    """Measure settled map-frame round-trip closure between two poses."""

    if start.get("frame_id") != "map" or end.get("frame_id") != "map":
        raise ValueError("round-trip closure requires map-frame poses")
    translation = math.hypot(
        float(end["x"]) - float(start["x"]),
        float(end["y"]) - float(start["y"]),
    )
    yaw = abs(math.degrees(angle_delta(quaternion_yaw(start), quaternion_yaw(end))))
    return {
        "translation_error_m": round(translation, 6),
        "yaw_error_deg": round(yaw, 6),
    }


def polygon_dimensions(points: Sequence[Tuple[float, float]]) -> Dict[str, Any]:
    """Return rotation-independent dimensions for a rectangular footprint."""

    if len(points) < 4:
        raise ValueError("footprint has fewer than four vertices")
    edges = [
        math.hypot(
            points[(index + 1) % len(points)][0] - point[0],
            points[(index + 1) % len(points)][1] - point[1],
        )
        for index, point in enumerate(points)
    ]
    finite_edges = [value for value in edges if math.isfinite(value) and value > 0.0]
    if len(finite_edges) != len(points):
        raise ValueError("footprint contains an invalid edge")
    twice_area = abs(
        sum(
            point[0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * point[1]
            for index, point in enumerate(points)
        )
    )
    if not math.isfinite(twice_area) or twice_area <= 0.0:
        raise ValueError("footprint has no finite area")
    return {
        "point_count": len(points),
        "length_m": round(max(finite_edges), 6),
        "width_m": round(min(finite_edges), 6),
        "area_m2": round(twice_area * 0.5, 6),
    }


class TransformJumpTracker:
    """Track publication-order map->odom discontinuities for one map session.

    Slam Toolbox intentionally future-dates map->odom by ``transform_timeout``.
    The configured offset is removed only for timestamp validity/age checks;
    raw stamps remain in the evidence and pose-jump sampling is unchanged.
    """

    def __init__(
        self,
        *,
        source_future_offset_s: float = 0.0,
        max_source_future_skew_s: float = MAX_TF_SOURCE_FUTURE_S,
    ) -> None:
        source_future_offset_s = float(source_future_offset_s)
        max_source_future_skew_s = float(max_source_future_skew_s)
        if not math.isfinite(source_future_offset_s) or source_future_offset_s < 0.0:
            raise ValueError("source future offset must be finite and non-negative")
        if (
            not math.isfinite(max_source_future_skew_s)
            or max_source_future_skew_s < 0.0
        ):
            raise ValueError("source future-skew limit must be finite and non-negative")
        self.source_future_offset_s = source_future_offset_s
        self.max_source_future_skew_s = max_source_future_skew_s
        self.session_id: Optional[str] = None
        self.session_started_unix: Optional[float] = None
        self.monitor_started_unix: Optional[float] = None
        self.observation_started_unix: Optional[float] = None
        self.observation_ended_unix: Optional[float] = None
        self.sample_count = 0
        self.max_translation_m = 0.0
        self.max_yaw_deg = 0.0
        self.max_sample_gap_s = 0.0
        self.time_order_valid = True
        self.source_stamp_started_unix: Optional[float] = None
        self.source_stamp_ended_unix: Optional[float] = None
        self.raw_source_stamp_started_unix: Optional[float] = None
        self.raw_source_stamp_ended_unix: Optional[float] = None
        self.max_source_age_s = 0.0
        self.max_raw_source_future_s = 0.0
        self.max_normalized_source_future_s = 0.0
        self.source_stamp_valid = True
        self.source_time_order_valid = True
        self.source_future_skew_valid = True
        self.invalid_source_stamp_count = 0
        self.source_regression_count = 0
        self.max_source_regression_s = 0.0
        self.max_translation_observation_unix: Optional[float] = None
        self.max_translation_source_unix: Optional[float] = None
        self.max_yaw_observation_unix: Optional[float] = None
        self.max_yaw_source_unix: Optional[float] = None
        self._last: Optional[Tuple[float, float, float]] = None
        self._last_sample_unix: Optional[float] = None
        self._last_source_unix: Optional[float] = None

    def begin(self, session_id: str, session_started_unix: float, now_unix: float) -> None:
        self.session_id = str(session_id)
        self.session_started_unix = float(session_started_unix)
        self.monitor_started_unix = float(now_unix)
        self.observation_started_unix = None
        self.observation_ended_unix = None
        self.sample_count = 0
        self.max_translation_m = 0.0
        self.max_yaw_deg = 0.0
        self.max_sample_gap_s = 0.0
        self.time_order_valid = True
        self.source_stamp_started_unix = None
        self.source_stamp_ended_unix = None
        self.raw_source_stamp_started_unix = None
        self.raw_source_stamp_ended_unix = None
        self.max_source_age_s = 0.0
        self.max_raw_source_future_s = 0.0
        self.max_normalized_source_future_s = 0.0
        self.source_stamp_valid = True
        self.source_time_order_valid = True
        self.source_future_skew_valid = True
        self.invalid_source_stamp_count = 0
        self.source_regression_count = 0
        self.max_source_regression_s = 0.0
        self.max_translation_observation_unix = None
        self.max_translation_source_unix = None
        self.max_yaw_observation_unix = None
        self.max_yaw_source_unix = None
        self._last = None
        self._last_sample_unix = None
        self._last_source_unix = None

    def observe(
        self,
        x_m: float,
        y_m: float,
        yaw_rad: float,
        now_unix: float,
        source_unix: Optional[float] = None,
    ) -> None:
        values = (float(x_m), float(y_m), float(yaw_rad), float(now_unix))
        if self.session_id is None or not all(math.isfinite(value) for value in values):
            return
        x_m, y_m, yaw_rad, now_unix = values
        source_stamp = None
        try:
            source_stamp = float(source_unix) if source_unix is not None else None
        except (TypeError, ValueError):
            source_stamp = None
        if source_stamp is None or not math.isfinite(source_stamp):
            self.source_stamp_valid = False
            self.invalid_source_stamp_count += 1
        else:
            if self.raw_source_stamp_started_unix is None:
                self.raw_source_stamp_started_unix = source_stamp
            self.raw_source_stamp_ended_unix = source_stamp
            self.max_raw_source_future_s = max(
                self.max_raw_source_future_s,
                max(0.0, source_stamp - now_unix),
            )
            if source_stamp <= 0.0:
                self.source_stamp_valid = False
                self.invalid_source_stamp_count += 1
                source_stamp = None
        if source_stamp is not None:
            normalized_source_stamp = source_stamp - self.source_future_offset_s
            if (
                self._last_source_unix is not None
                and normalized_source_stamp < self._last_source_unix
            ):
                self.source_time_order_valid = False
                self.source_regression_count += 1
                self.max_source_regression_s = max(
                    self.max_source_regression_s,
                    self._last_source_unix - normalized_source_stamp,
                )
                # A regressed transform remains fail-closed evidence, but it
                # must not become the geometric baseline for the next valid
                # sample and manufacture a pose jump.
                return
            source_age_s = now_unix - normalized_source_stamp
            normalized_future_s = max(0.0, -source_age_s)
            self.max_normalized_source_future_s = max(
                self.max_normalized_source_future_s,
                normalized_future_s,
            )
            if normalized_future_s > self.max_source_future_skew_s:
                self.source_future_skew_valid = False
                # Likewise, a transform outside the commissioned future-skew
                # allowance is diagnostic evidence only, not a pose sample.
                return
            if self._last_sample_unix is not None:
                gap_s = now_unix - self._last_sample_unix
                if gap_s < 0.0:
                    self.time_order_valid = False
                    return
                self.max_sample_gap_s = max(self.max_sample_gap_s, gap_s)
            if self.observation_started_unix is None:
                self.observation_started_unix = now_unix
            if self.source_stamp_started_unix is None:
                self.source_stamp_started_unix = normalized_source_stamp
            self.max_source_age_s = max(
                self.max_source_age_s,
                max(0.0, source_age_s),
            )
            self.source_stamp_ended_unix = normalized_source_stamp
            self._last_source_unix = normalized_source_stamp
        else:
            # Invalid or absent source time fails the session, but does not
            # rebase geometry, receipt time, or accepted sample count.
            return
        if self._last is not None:
            previous_x, previous_y, previous_yaw = self._last
            translation_m = math.hypot(x_m - previous_x, y_m - previous_y)
            yaw_deg = abs(math.degrees(angle_delta(previous_yaw, yaw_rad)))
            if translation_m > self.max_translation_m:
                self.max_translation_m = translation_m
                self.max_translation_observation_unix = now_unix
                self.max_translation_source_unix = normalized_source_stamp
            if yaw_deg > self.max_yaw_deg:
                self.max_yaw_deg = yaw_deg
                self.max_yaw_observation_unix = now_unix
                self.max_yaw_source_unix = normalized_source_stamp
        self._last = (x_m, y_m, yaw_rad)
        self._last_sample_unix = now_unix
        self.sample_count += 1
        self.observation_ended_unix = now_unix

    def snapshot(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_started_unix": self.session_started_unix,
            "monitor_started_unix": self.monitor_started_unix,
            "observation_started_unix": self.observation_started_unix,
            "observation_ended_unix": self.observation_ended_unix,
            "sample_count": self.sample_count,
            "max_translation_m": round(self.max_translation_m, 6),
            "max_yaw_deg": round(self.max_yaw_deg, 6),
            "max_sample_gap_s": round(self.max_sample_gap_s, 6),
            "time_order_valid": self.time_order_valid,
            "source_stamp_started_unix": self.source_stamp_started_unix,
            "source_stamp_ended_unix": self.source_stamp_ended_unix,
            "raw_source_stamp_started_unix": self.raw_source_stamp_started_unix,
            "raw_source_stamp_ended_unix": self.raw_source_stamp_ended_unix,
            "source_future_offset_s": round(self.source_future_offset_s, 6),
            "source_future_skew_limit_s": round(
                self.max_source_future_skew_s, 6
            ),
            "max_source_age_s": round(self.max_source_age_s, 6),
            "max_raw_source_future_s": round(self.max_raw_source_future_s, 6),
            "max_normalized_source_future_s": round(
                self.max_normalized_source_future_s, 6
            ),
            "source_stamp_valid": self.source_stamp_valid,
            "source_time_order_valid": self.source_time_order_valid,
            "source_future_skew_valid": self.source_future_skew_valid,
            "invalid_source_stamp_count": self.invalid_source_stamp_count,
            "source_regression_count": self.source_regression_count,
            "max_source_regression_s": round(self.max_source_regression_s, 6),
            "max_translation_observation_unix": (
                self.max_translation_observation_unix
            ),
            "max_translation_source_unix": self.max_translation_source_unix,
            "max_yaw_observation_unix": self.max_yaw_observation_unix,
            "max_yaw_source_unix": self.max_yaw_source_unix,
        }


def map_pair_id(yaml_path: Path, image_path: Path) -> Optional[str]:
    """Return an identity tied to the exact bytes of a map YAML/image pair."""

    try:
        digest = hashlib.sha256()
        digest.update(Path(yaml_path).read_bytes())
        digest.update(Path(image_path).read_bytes())
        return digest.hexdigest()[:20]
    except OSError:
        return None


def _map_yaml_values(yaml_path: Path) -> Dict[str, Any]:
    """Parse the small scalar subset emitted by Nav2's map saver."""

    values: Dict[str, Any] = {}
    for raw_line in Path(yaml_path).read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if key == "origin":
            values[key] = ast.literal_eval(raw_value)
        elif key in {"resolution", "occupied_thresh", "free_thresh"}:
            values[key] = float(raw_value)
        elif key == "negate":
            values[key] = int(raw_value)
        elif key in {"image", "mode"}:
            values[key] = raw_value.strip("'\"")
    required = {
        "resolution", "origin", "negate", "occupied_thresh", "free_thresh"
    }
    missing = sorted(required.difference(values))
    if missing:
        raise ValueError("candidate map YAML is missing: " + ", ".join(missing))
    if values.get("mode", "trinary").lower() != "trinary":
        raise ValueError("exact candidate check only accepts trinary occupancy maps")
    origin = values["origin"]
    if not isinstance(origin, (list, tuple)) or len(origin) < 2:
        raise ValueError("candidate map origin is malformed")
    values["origin"] = (float(origin[0]), float(origin[1]))
    if not math.isfinite(values["resolution"]) or values["resolution"] <= 0.0:
        raise ValueError("candidate map resolution is invalid")
    if values["negate"] not in (0, 1):
        raise ValueError("candidate map negate must be zero or one")
    return values


def _read_pgm(image_path: Path) -> Tuple[int, int, List[int]]:
    """Read the P2/P5, 8-bit PGM subset emitted by Nav2's map saver."""

    payload = Path(image_path).read_bytes()
    cursor = 0

    def token() -> bytes:
        nonlocal cursor
        while cursor < len(payload):
            if payload[cursor] == 35:  # '#'
                newline = payload.find(b"\n", cursor)
                if newline < 0:
                    raise ValueError("unterminated PGM comment")
                cursor = newline + 1
            elif chr(payload[cursor]).isspace():
                cursor += 1
            else:
                break
        start = cursor
        while cursor < len(payload) and not chr(payload[cursor]).isspace():
            cursor += 1
        if start == cursor:
            raise ValueError("PGM ended before its header was complete")
        return payload[start:cursor]

    magic = token()
    width = int(token())
    height = int(token())
    maximum = int(token())
    if magic not in (b"P2", b"P5") or width <= 0 or height <= 0:
        raise ValueError("candidate image is not a supported PGM")
    if maximum <= 0 or maximum > 255:
        raise ValueError("candidate PGM must use 8-bit samples")

    expected = width * height
    if magic == b"P2":
        pixels = [int(token()) for _ in range(expected)]
    else:
        if cursor >= len(payload) or not chr(payload[cursor]).isspace():
            raise ValueError("binary PGM header has no raster separator")
        if payload[cursor:cursor + 2] == b"\r\n":
            cursor += 2
        else:
            cursor += 1
        raster = payload[cursor:cursor + expected]
        if len(raster) != expected:
            raise ValueError("candidate PGM raster is truncated")
        pixels = list(raster)
    if any(value < 0 or value > maximum for value in pixels):
        raise ValueError("candidate PGM contains an out-of-range sample")
    if maximum != 255:
        pixels = [round(value * 255.0 / maximum) for value in pixels]
    return width, height, pixels


def exact_candidate_connectivity(
    yaml_path: Path,
    image_path: Path,
    start_pose: Dict[str, Any],
    goal_pose: Dict[str, Any],
    *,
    inflation_radius_m: float = 0.18,
) -> Dict[str, Any]:
    """Check connectivity in the exact saved bytes with unknown space blocked."""

    metadata = _map_yaml_values(Path(yaml_path))
    width, height, pixels = _read_pgm(Path(image_path))
    resolution = float(metadata["resolution"])
    radius_m = float(inflation_radius_m)
    if not math.isfinite(radius_m) or radius_m < 0.0:
        raise ValueError("candidate inflation radius is invalid")

    # Nav2 map_saver's trinary output is canonical: 254/255 is known free,
    # 205 is unknown, and 0 is occupied. Requiring the canonical free value is
    # deliberately more conservative than thresholding 205 as free.
    if metadata["negate"]:
        free = [value <= 1 for value in pixels]
    else:
        free = [value >= 254 for value in pixels]

    radius_cells = int(math.ceil(radius_m / resolution))
    inflated_free = free[:]
    offsets = [
        (dx, dy)
        for dy in range(-radius_cells, radius_cells + 1)
        for dx in range(-radius_cells, radius_cells + 1)
        # Account for the finite extent of both grid cells, not only their
        # centers, so clearance never under-runs the requested half-width.
        if math.hypot(dx, dy) * resolution
        <= radius_m + math.sqrt(2.0) * resolution + 1e-9
    ]
    blocked_cells = [index for index, is_free in enumerate(free) if not is_free]
    for index in blocked_cells:
        row, column = divmod(index, width)
        for dx, dy in offsets:
            target_column = column + dx
            target_row = row + dy
            if 0 <= target_column < width and 0 <= target_row < height:
                inflated_free[target_row * width + target_column] = False
    # Treat outside-map space as blocked and keep the whole inflated footprint
    # within the map bounds.
    for row in range(height):
        for column in range(width):
            if (
                column < radius_cells
                or column >= width - radius_cells
                or row < radius_cells
                or row >= height - radius_cells
            ):
                inflated_free[row * width + column] = False

    origin_x, origin_y = metadata["origin"]

    def pose_cell(pose: Dict[str, Any]) -> Tuple[int, int]:
        map_column = math.floor((float(pose["x"]) - origin_x) / resolution)
        map_row = math.floor((float(pose["y"]) - origin_y) / resolution)
        image_row = height - int(map_row) - 1
        cell = (int(map_column), image_row)
        if not (0 <= cell[0] < width and 0 <= cell[1] < height):
            raise ValueError(f"candidate endpoint {cell} lies outside the map")
        return cell

    start = pose_cell(start_pose)
    goal = pose_cell(goal_pose)
    start_index = start[1] * width + start[0]
    goal_index = goal[1] * width + goal[0]
    if not inflated_free[start_index]:
        raise ValueError("candidate start is not clear for the inflated rover")
    if not inflated_free[goal_index]:
        raise ValueError("candidate goal is not clear for the inflated rover")

    queue = deque([start])
    visited = {start}
    while queue and goal not in visited:
        column, row = queue.popleft()
        for dx, dy in (
            (-1, -1), (0, -1), (1, -1),
            (-1, 0),           (1, 0),
            (-1, 1),  (0, 1),  (1, 1),
        ):
            adjacent = (column + dx, row + dy)
            if not (0 <= adjacent[0] < width and 0 <= adjacent[1] < height):
                continue
            adjacent_index = adjacent[1] * width + adjacent[0]
            if adjacent in visited or not inflated_free[adjacent_index]:
                continue
            if dx and dy:
                horizontal = row * width + adjacent[0]
                vertical = adjacent[1] * width + column
                if not inflated_free[horizontal] or not inflated_free[vertical]:
                    continue
            visited.add(adjacent)
            queue.append(adjacent)

    return {
        "connected": goal in visited,
        "unknown_is_blocked": True,
        "inflation_radius_m": round(radius_m, 6),
        "resolution_m": round(resolution, 6),
        "width_cells": width,
        "height_cells": height,
        "start_cell": list(start),
        "goal_cell": list(goal),
        "reachable_cells": len(visited),
    }


def prepare_map_bound_metadata_values(
    *,
    home: Any,
    seed: Any,
    places: Any,
    session_id: str,
    new_map_id: str,
    old_map_id: Optional[str],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Return the location metadata that must commit with a candidate map."""

    prepared_pair = []
    for label, value in (("home", home), ("localization seed", seed)):
        if not isinstance(value, dict) or value.get("mapping_session_id") != session_id:
            raise ValueError(f"{label} does not belong to the active mapping session")
        prepared = dict(value)
        prepared["map_id"] = new_map_id
        prepared.pop("mapping_session_id", None)
        prepared_pair.append(prepared)

    if not isinstance(places, dict):
        raise ValueError("named places metadata is malformed")
    prepared_places: Dict[str, Any] = {}
    for name, value in places.items():
        if not isinstance(value, dict):
            prepared_places[name] = value
            continue
        pose = dict(value)
        if pose.get("mapping_session_id") == session_id:
            pose["map_id"] = new_map_id
            pose.pop("mapping_session_id", None)
        elif not pose.get("map_id"):
            # This is a legacy coordinate from before map versioning. Binding
            # it to the old map ensures it is rejected on the new map. On a
            # first acceptance there is no old map, so use a deliberately
            # non-current marker rather than leaving the pose unversioned and
            # therefore implicitly trusted.
            pose["map_id"] = old_map_id or UNBOUND_LEGACY_MAP_ID
        prepared_places[name] = pose
    return prepared_pair[0], prepared_pair[1], prepared_places


def transactionally_promote_map_pair(
    *,
    candidate_yaml: Path,
    candidate_image: Path,
    accepted_yaml: Path,
    accepted_image: Path,
    backup_dir: Path,
    expected_map_id: str,
    backup_tag: str,
    metadata_updates: Optional[Dict[Path, bytes]] = None,
) -> str:
    """Promote a verified map/location bundle and restore it on failure.

    Two files cannot be renamed as one filesystem transaction. Both candidate
    files and all map-bound metadata are therefore staged before accepted state
    is touched, and every existing member is backed up. Metadata and the image
    are committed before the authoritative YAML pointer. An exception, byte
    mismatch, or metadata mismatch restores the complete prior bundle (or
    removes newly-created members when no prior accepted state existed).
    """

    candidate_yaml = Path(candidate_yaml)
    candidate_image = Path(candidate_image)
    accepted_yaml = Path(accepted_yaml)
    accepted_image = Path(accepted_image)
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    token = uuid.uuid4().hex
    safe_tag = "".join(
        character
        for character in str(backup_tag)
        if character.isalnum() or character in "-_"
    ) or token[:8]
    backup_yaml = backup_dir / f"{accepted_yaml.stem}-{safe_tag}{accepted_yaml.suffix}"
    backup_image = backup_dir / f"{accepted_image.stem}-{safe_tag}{accepted_image.suffix}"
    staged_yaml = accepted_yaml.with_name(f".{accepted_yaml.name}.{token}.new")
    staged_image = accepted_image.with_name(f".{accepted_image.name}.{token}.new")
    rollback_yaml = accepted_yaml.with_name(f".{accepted_yaml.name}.{token}.rollback")
    rollback_image = accepted_image.with_name(f".{accepted_image.name}.{token}.rollback")

    metadata_entries = []
    for target_value, contents_value in (metadata_updates or {}).items():
        target = Path(target_value)
        if target in (accepted_yaml, accepted_image):
            raise ValueError("map paths cannot also be metadata update targets")
        contents = bytes(contents_value)
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{target.name}-{safe_tag}.metadata.bak"
        staged = target.with_name(f".{target.name}.{token}.new")
        rollback = target.with_name(f".{target.name}.{token}.rollback")
        metadata_entries.append(
            {
                "target": target,
                "contents": contents,
                "had_member": target.exists(),
                "backup": backup,
                "staged": staged,
                "rollback": rollback,
            }
        )

    had_yaml = accepted_yaml.exists()
    had_image = accepted_image.exists()
    if had_yaml:
        shutil.copy2(accepted_yaml, backup_yaml)
    if had_image:
        shutil.copy2(accepted_image, backup_image)
    shutil.copy2(candidate_yaml, staged_yaml)
    shutil.copy2(candidate_image, staged_image)
    for entry in metadata_entries:
        if entry["had_member"]:
            shutil.copy2(entry["target"], entry["backup"])
        entry["staged"].write_bytes(entry["contents"])

    try:
        for entry in metadata_entries:
            os.replace(entry["staged"], entry["target"])
        os.replace(staged_image, accepted_image)
        # Commit the authoritative map pointer only after every location file
        # and the referenced image are in place.
        os.replace(staged_yaml, accepted_yaml)
        promoted_id = map_pair_id(accepted_yaml, accepted_image)
        if not promoted_id or promoted_id != expected_map_id:
            raise RuntimeError("promoted map bytes do not match the validated candidate")
        for entry in metadata_entries:
            if entry["target"].read_bytes() != entry["contents"]:
                raise RuntimeError(
                    f"promoted metadata bytes do not match for {entry['target'].name}"
                )
        return promoted_id
    except Exception as exc:
        rollback_failures = []
        rollback_members = [
            (had_image, backup_image, rollback_image, accepted_image),
        ]
        rollback_members.extend(
            (
                entry["had_member"],
                entry["backup"],
                entry["rollback"],
                entry["target"],
            )
            for entry in metadata_entries
        )
        # Restore the YAML last so the old map does not become authoritative
        # until its referenced image and map-bound metadata are restored.
        rollback_members.append((had_yaml, backup_yaml, rollback_yaml, accepted_yaml))
        for had_member, backup, rollback, accepted in rollback_members:
            try:
                if had_member:
                    shutil.copy2(backup, rollback)
                    os.replace(rollback, accepted)
                else:
                    accepted.unlink(missing_ok=True)
            except Exception as rollback_exc:  # pragma: no cover - catastrophic I/O
                rollback_failures.append(f"{accepted.name}: {rollback_exc}")
        if rollback_failures:
            raise RuntimeError(
                "candidate promotion failed and accepted-map rollback also failed: "
                + "; ".join(rollback_failures)
            ) from exc
        raise RuntimeError(
            f"candidate promotion failed; previous accepted map restored: {exc}"
        ) from exc
    finally:
        temporaries = [staged_yaml, staged_image, rollback_yaml, rollback_image]
        temporaries.extend(
            entry[key]
            for entry in metadata_entries
            for key in ("staged", "rollback")
        )
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _check_maximum(
    failures: List[str], section: Dict[str, Any], field: str, limit: float, label: str
) -> None:
    value = _finite_number(section.get(field))
    if value is None:
        failures.append(f"{label} is missing or non-finite")
    elif value > limit:
        failures.append(f"{label} {value:.3f} exceeds {limit:.3f}")


def evaluate_acceptance_evidence(
    evidence: Any,
    *,
    expected_session_id: str,
    expected_candidate_map_id: str,
    session_started_unix: float,
    evaluated_unix: float,
    policy: MapAcceptancePolicy = MapAcceptancePolicy(),
) -> List[str]:
    """Return every fail-closed reason that prevents candidate promotion."""

    failures: List[str] = []
    if not isinstance(evidence, dict):
        return ["map-acceptance evidence is missing or malformed"]
    if evidence.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        failures.append("map-acceptance evidence schema is missing or unsupported")
    if evidence.get("session_id") != expected_session_id:
        failures.append("map-acceptance evidence belongs to a different mapping session")
    if evidence.get("candidate_map_id") != expected_candidate_map_id:
        failures.append("map-acceptance evidence belongs to different candidate bytes")
    if evidence.get("motion_dispatched") is not False:
        failures.append("map-acceptance evidence does not prove a no-motion evaluation")

    tf_jump = evidence.get("tf_jump")
    if not isinstance(tf_jump, dict):
        failures.append("map->odom jump evidence is missing")
    else:
        if tf_jump.get("session_id") != expected_session_id:
            failures.append("map->odom evidence belongs to a different mapping session")
        samples = tf_jump.get("sample_count")
        if isinstance(samples, bool) or not isinstance(samples, int) or samples < policy.min_tf_samples:
            failures.append(
                f"map->odom evidence has fewer than {policy.min_tf_samples} samples"
            )
        started = _finite_number(tf_jump.get("observation_started_unix"))
        ended = _finite_number(tf_jump.get("observation_ended_unix"))
        if started is None:
            failures.append("map->odom observation start time is missing")
        elif started < session_started_unix - 1.0:
            failures.append("map->odom observation predates the mapping session")
        elif started - session_started_unix > policy.max_observation_start_delay_s:
            failures.append("map->odom observation did not cover mapping-session start")
        if ended is None:
            failures.append("map->odom observation end time is missing")
        elif evaluated_unix - ended > policy.max_evidence_age_s:
            failures.append("map->odom evidence is stale at promotion time")
        gap = _finite_number(tf_jump.get("max_sample_gap_s"))
        if gap is None:
            failures.append("map->odom maximum sample gap is missing")
        elif gap > policy.max_tf_sample_gap_s:
            failures.append(
                "map->odom observation has an uncovered gap "
                f"of {gap:.3f}s (limit {policy.max_tf_sample_gap_s:.3f}s)"
            )
        if tf_jump.get("time_order_valid") is not True:
            failures.append("map->odom observation timestamps are not monotonic")
        source_offset = _finite_number(tf_jump.get("source_future_offset_s"))
        if source_offset is None:
            failures.append("map->odom source future-offset normalization is missing")
        elif (
            source_offset < 0.0
            or source_offset > policy.max_tf_source_future_offset_s
        ):
            failures.append(
                "map->odom source future-offset normalization "
                f"{source_offset:.3f}s is outside the commissioned bound "
                f"0.000-{policy.max_tf_source_future_offset_s:.3f}s"
            )
        source_future_limit = _finite_number(
            tf_jump.get("source_future_skew_limit_s")
        )
        if source_future_limit is None:
            failures.append("map->odom source future-skew limit is missing")
        elif (
            source_future_limit < 0.0
            or source_future_limit > policy.max_tf_source_future_skew_s
        ):
            failures.append(
                "map->odom source future-skew limit "
                f"{source_future_limit:.3f}s exceeds the commissioned "
                f"{policy.max_tf_source_future_skew_s:.3f}s bound"
            )
        source_started = _finite_number(tf_jump.get("source_stamp_started_unix"))
        source_ended = _finite_number(tf_jump.get("source_stamp_ended_unix"))
        raw_source_started = _finite_number(
            tf_jump.get("raw_source_stamp_started_unix")
        )
        raw_source_ended = _finite_number(
            tf_jump.get("raw_source_stamp_ended_unix")
        )
        if raw_source_started is None:
            failures.append("map->odom raw source timestamp start is missing")
        if raw_source_ended is None:
            failures.append("map->odom raw source timestamp end is missing")
        if source_started is None:
            failures.append("map->odom source timestamp start is missing")
        elif source_started < session_started_unix - 1.0:
            failures.append("map->odom source timestamps predate the mapping session")
        if source_ended is None:
            failures.append("map->odom source timestamp end is missing")
        elif evaluated_unix - source_ended > policy.max_tf_source_age_s:
            failures.append("map->odom source timestamp is stale at promotion time")
        source_age = _finite_number(tf_jump.get("max_source_age_s"))
        if source_age is None:
            failures.append("map->odom source timestamp age is missing")
        elif source_age > policy.max_tf_source_age_s:
            failures.append(
                f"map->odom source age {source_age:.3f}s exceeds "
                f"{policy.max_tf_source_age_s:.3f}s"
            )
        if (
            source_offset is not None
            and raw_source_started is not None
            and source_started is not None
            and abs(raw_source_started - source_offset - source_started) > 1e-5
        ):
            failures.append("map->odom source timestamp start normalization is inconsistent")
        if (
            source_offset is not None
            and raw_source_ended is not None
            and source_ended is not None
            and abs(raw_source_ended - source_offset - source_ended) > 1e-5
        ):
            failures.append("map->odom source timestamp end normalization is inconsistent")
        invalid_source_stamps = tf_jump.get("invalid_source_stamp_count")
        if (
            isinstance(invalid_source_stamps, bool)
            or not isinstance(invalid_source_stamps, int)
            or invalid_source_stamps < 0
        ):
            failures.append("map->odom invalid source-timestamp count is missing")
        elif invalid_source_stamps > 0:
            failures.append(
                "map->odom source timestamps contain "
                f"{invalid_source_stamps} invalid value(s)"
            )
        if tf_jump.get("source_stamp_valid") is not True:
            failures.append("map->odom source timestamps contain invalid values")
        source_regressions = tf_jump.get("source_regression_count")
        max_source_regression = _finite_number(
            tf_jump.get("max_source_regression_s")
        )
        regression_detected = tf_jump.get("source_time_order_valid") is not True
        if (
            isinstance(source_regressions, bool)
            or not isinstance(source_regressions, int)
            or source_regressions < 0
        ):
            failures.append("map->odom source regression count is missing")
        elif source_regressions > 0:
            regression_detected = True
        if max_source_regression is None or max_source_regression < 0.0:
            failures.append("map->odom maximum source regression is missing")
        elif max_source_regression > 0.0:
            regression_detected = True
        if regression_detected:
            detail = (
                f" by up to {max_source_regression:.3f}s"
                if max_source_regression is not None
                and max_source_regression > 0.0
                else ""
            )
            failures.append(
                "map->odom source timestamps regressed in publication order"
                + detail
            )
        raw_source_future = _finite_number(
            tf_jump.get("max_raw_source_future_s")
        )
        if raw_source_future is None or raw_source_future < 0.0:
            failures.append("map->odom raw source future-skew diagnostic is missing")
        normalized_source_future = _finite_number(
            tf_jump.get("max_normalized_source_future_s")
        )
        future_skew_detected = tf_jump.get("source_future_skew_valid") is not True
        if normalized_source_future is None or normalized_source_future < 0.0:
            failures.append("map->odom normalized source future skew is missing")
        else:
            if normalized_source_future > policy.max_tf_source_future_skew_s:
                future_skew_detected = True
            if (
                source_future_limit is not None
                and source_future_limit >= 0.0
                and normalized_source_future > source_future_limit
            ):
                future_skew_detected = True
        if future_skew_detected:
            detail = (
                f" {normalized_source_future:.3f}s exceeds "
                f"{policy.max_tf_source_future_skew_s:.3f}s"
                if normalized_source_future is not None
                and normalized_source_future >= 0.0
                else " is invalid"
            )
            failures.append("map->odom normalized source future skew" + detail)
        _check_maximum(
            failures,
            tf_jump,
            "max_translation_m",
            policy.max_tf_translation_jump_m,
            "map->odom translation jump",
        )
        _check_maximum(
            failures,
            tf_jump,
            "max_yaw_deg",
            policy.max_tf_yaw_jump_deg,
            "map->odom yaw jump",
        )

    closure = evidence.get("round_trip_closure")
    if not isinstance(closure, dict):
        failures.append("settled round-trip closure evidence is missing")
    else:
        if closure.get("session_id") != expected_session_id:
            failures.append("round-trip closure belongs to a different mapping session")
        _check_maximum(
            failures,
            closure,
            "translation_error_m",
            policy.max_closure_translation_m,
            "round-trip translation closure",
        )
        _check_maximum(
            failures,
            closure,
            "yaw_error_deg",
            policy.max_closure_yaw_deg,
            "round-trip yaw closure",
        )

    exact_map = evidence.get("exact_candidate_connectivity")
    if not isinstance(exact_map, dict):
        failures.append("exact candidate-byte connectivity evidence is missing")
    else:
        if exact_map.get("session_id") != expected_session_id:
            failures.append("exact candidate connectivity belongs to a different session")
        if exact_map.get("candidate_map_id") != expected_candidate_map_id:
            failures.append("exact connectivity was not checked on the candidate bytes")
        if exact_map.get("unknown_is_blocked") is not True:
            failures.append("exact candidate check did not treat unknown space as blocked")
        if exact_map.get("connected") is not True:
            detail = str(exact_map.get("error") or "no inflated path")
            failures.append(f"exact candidate map is not connected: {detail}")
        clearance = _finite_number(exact_map.get("inflation_radius_m"))
        if clearance is None or clearance < policy.min_candidate_clearance_m:
            failures.append(
                "exact candidate connectivity was not inflated by the rover half-width"
            )

    footprint = evidence.get("full_footprint_connectivity")
    if not isinstance(footprint, dict):
        failures.append("full-footprint connectivity evidence is missing")
    else:
        if footprint.get("connected") is not True:
            failures.append("full commissioned footprint is not connected between places")
        observed = _finite_number(footprint.get("observed_unix"))
        if observed is None:
            failures.append("global-costmap footprint observation time is missing")
        elif evaluated_unix - observed > policy.max_evidence_age_s:
            failures.append("global-costmap footprint evidence is stale")
        length = _finite_number(footprint.get("length_m"))
        width = _finite_number(footprint.get("width_m"))
        if length is None or length < policy.min_footprint_length_m:
            failures.append("global costmap is not publishing the commissioned 0.50 m footprint")
        if width is None or width < policy.min_footprint_width_m:
            failures.append("global costmap is not publishing the commissioned 0.36 m footprint")

    plans = evidence.get("bidirectional_plans")
    if not isinstance(plans, dict):
        failures.append("bidirectional plan-only evidence is missing")
    else:
        for direction in ("forward", "reverse"):
            plan = plans.get(direction)
            if not isinstance(plan, dict):
                failures.append(f"{direction} plan-only evidence is missing")
                continue
            if plan.get("passed") is not True:
                detail = str(plan.get("error") or "no collision-free path")
                failures.append(f"{direction} plan-only check failed: {detail}")
            poses = plan.get("poses")
            if isinstance(poses, bool) or not isinstance(poses, int) or poses < policy.min_path_poses:
                failures.append(f"{direction} plan contains too few poses")

    return failures

#!/usr/bin/env python3
"""Read-only rosbag2 forensics for discontinuities in the ATLAS TF chain.

This utility deliberately uses :class:`rosbag2_py.SequentialReader` directly.
It never creates a ROS node, publisher, subscriber, service, action, or bag
replay process.  A small temporary SQLite database stores only compact pose
samples so that exact header-time sorting remains bounded in RAM.

The report is intended to answer a narrow question: what else happened around
the largest ``map -> odom`` correction?  It compares record order with message
header order, composes ``map -> base`` on both sides of the correction, and
correlates odometry, corrected IM10A gyro, drive commands, steering, encoder
health, and raw/filtered LiDAR timing.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import os
import random
import sqlite3
import statistics
import tempfile
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


NANOSECONDS = 1_000_000_000
MILLISECONDS = 1_000_000

MAP_ODOM_SERIES = "tf:map->odom"
IM10A_TOPIC = "/im10a/imu/bias_corrected_candidate"
ODOM_TOPICS = ("/odom", "/yahboom/odom")
SCAN_TOPICS = ("/scan_raw", "/scan")
STEERING_TOPICS = ("/steering/front_angle_deg", "/steering/rear_angle_deg")
COMMAND_TOPICS = (
    "/cmd_vel",
    "/cmd_vel_nav",
    "/cmd_vel_joy",
    "/cmd_vel_web",
    "/cmd_vel_teleop",
    "/cmd_vel_commission",
    "/cmd_vel_recovery",
)
ENCODER_HEALTH_TOPIC = "/atlas/encoder_health"


def normalize_frame(value: str) -> str:
    """Return a TF frame without a leading slash."""

    return str(value or "").strip().lstrip("/")


def stamp_to_ns(stamp: Any) -> int:
    """Convert a ROS builtin_interfaces/Time-like object to nanoseconds."""

    return int(stamp.sec) * NANOSECONDS + int(stamp.nanosec)


def quaternion_yaw(quaternion: Any) -> float:
    """Return planar yaw from a geometry_msgs/Quaternion-like object."""

    return math.atan2(
        2.0
        * (
            float(quaternion.w) * float(quaternion.z)
            + float(quaternion.x) * float(quaternion.y)
        ),
        1.0
        - 2.0
        * (
            float(quaternion.y) * float(quaternion.y)
            + float(quaternion.z) * float(quaternion.z)
        ),
    )


def angle_delta(current: float, previous: float) -> float:
    """Shortest signed angular difference, in radians."""

    return math.atan2(math.sin(current - previous), math.cos(current - previous))


def compose_se2(
    parent_x: float,
    parent_y: float,
    parent_yaw: float,
    child_x: float,
    child_y: float,
    child_yaw: float,
) -> Tuple[float, float, float]:
    """Compose two planar transforms (A->B and B->C) into A->C."""

    cosine = math.cos(parent_yaw)
    sine = math.sin(parent_yaw)
    return (
        parent_x + cosine * child_x - sine * child_y,
        parent_y + sine * child_x + cosine * child_y,
        math.atan2(
            math.sin(parent_yaw + child_yaw),
            math.cos(parent_yaw + child_yaw),
        ),
    )


class RunningStats:
    """Online moments plus a fixed-size deterministic reservoir for quantiles."""

    def __init__(self, reservoir_size: int = 2048, seed: int = 0) -> None:
        self.count = 0
        self.minimum: Optional[float] = None
        self.maximum: Optional[float] = None
        self.mean = 0.0
        self.m2 = 0.0
        self.reservoir_size = max(0, int(reservoir_size))
        self.reservoir: List[float] = []
        self._random = random.Random(seed)

    def add(self, value: Any) -> None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        if not math.isfinite(number):
            return
        self.count += 1
        self.minimum = number if self.minimum is None else min(self.minimum, number)
        self.maximum = number if self.maximum is None else max(self.maximum, number)
        delta = number - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (number - self.mean)
        if len(self.reservoir) < self.reservoir_size:
            self.reservoir.append(number)
        elif self.reservoir_size:
            index = self._random.randrange(self.count)
            if index < self.reservoir_size:
                self.reservoir[index] = number

    def _quantile(self, fraction: float) -> Optional[float]:
        if not self.reservoir:
            return None
        ordered = sorted(self.reservoir)
        index = int(round((len(ordered) - 1) * fraction))
        return ordered[max(0, min(index, len(ordered) - 1))]

    def summary(self, digits: int = 6) -> Dict[str, Any]:
        if not self.count:
            return {"samples": 0}
        variance = self.m2 / self.count
        result: Dict[str, Any] = {
            "samples": self.count,
            "min": round(float(self.minimum), digits),
            "mean": round(self.mean, digits),
            "median": round(float(self._quantile(0.5)), digits),
            "p95": round(float(self._quantile(0.95)), digits),
            "max": round(float(self.maximum), digits),
            "stddev": round(math.sqrt(max(0.0, variance)), digits),
        }
        if self.count > len(self.reservoir):
            result["quantiles"] = "deterministic reservoir estimate"
            result["reservoir_samples"] = len(self.reservoir)
        else:
            result["quantiles"] = "exact"
        return result


class HeaderAudit:
    """Audit message-header chronology in bag record order."""

    def __init__(self, example_limit: int = 5) -> None:
        self.previous_ns: Optional[int] = None
        self.duplicates = 0
        self.regressions = 0
        self.zero_stamps = 0
        self.max_regression_ns = 0
        self.examples: List[Dict[str, Any]] = []
        self.example_limit = example_limit

    def add(self, header_ns: int, record_ns: int, sequence: int) -> None:
        if header_ns <= 0:
            self.zero_stamps += 1
            return
        if self.previous_ns is not None:
            delta = header_ns - self.previous_ns
            if delta == 0:
                self.duplicates += 1
                self._example("duplicate", header_ns, record_ns, sequence, 0)
            elif delta < 0:
                self.regressions += 1
                self.max_regression_ns = max(self.max_regression_ns, -delta)
                self._example("regression", header_ns, record_ns, sequence, delta)
        self.previous_ns = header_ns

    def _example(
        self, kind: str, header_ns: int, record_ns: int, sequence: int, delta_ns: int
    ) -> None:
        if len(self.examples) < self.example_limit:
            self.examples.append(
                {
                    "kind": kind,
                    "sequence": sequence,
                    "record_ns": record_ns,
                    "header_ns": header_ns,
                    "header_delta_ms": round(delta_ns / MILLISECONDS, 6),
                }
            )

    def summary(self) -> Dict[str, Any]:
        return {
            "duplicates": self.duplicates,
            "regressions": self.regressions,
            "zero_stamps": self.zero_stamps,
            "max_regression_ms": round(self.max_regression_ns / MILLISECONDS, 6),
            "examples": self.examples,
        }


@dataclass(frozen=True)
class PoseSample:
    sequence: int
    record_ns: int
    header_ns: int
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class StepEvent:
    previous: PoseSample
    current: PoseSample
    translation_m: float
    yaw_rad: float


def pose_step(previous: PoseSample, current: PoseSample) -> StepEvent:
    return StepEvent(
        previous=previous,
        current=current,
        translation_m=math.hypot(current.x - previous.x, current.y - previous.y),
        yaw_rad=abs(angle_delta(current.yaw, previous.yaw)),
    )


class PoseAccumulator:
    """Streaming pose statistics in bag record order."""

    def __init__(self) -> None:
        self.count = 0
        self.previous: Optional[PoseSample] = None
        self.first: Optional[PoseSample] = None
        self.last: Optional[PoseSample] = None
        self.path_length_m = 0.0
        self.max_translation: Optional[StepEvent] = None
        self.max_yaw: Optional[StepEvent] = None
        self.record_gap_ms = RunningStats()
        self.header_gap_ms = RunningStats()
        self.receipt_header_lag_ms = RunningStats()
        self.header_audit = HeaderAudit()

    def add(self, sample: PoseSample) -> None:
        self.count += 1
        self.header_audit.add(sample.header_ns, sample.record_ns, sample.sequence)
        if sample.header_ns > 0:
            self.receipt_header_lag_ms.add(
                (sample.record_ns - sample.header_ns) / MILLISECONDS
            )
        if self.first is None:
            self.first = sample
        if self.previous is not None:
            event = pose_step(self.previous, sample)
            self.path_length_m += event.translation_m
            self.record_gap_ms.add(
                (sample.record_ns - self.previous.record_ns) / MILLISECONDS
            )
            if sample.header_ns > 0 and self.previous.header_ns > 0:
                self.header_gap_ms.add(
                    (sample.header_ns - self.previous.header_ns) / MILLISECONDS
                )
            if (
                self.max_translation is None
                or event.translation_m > self.max_translation.translation_m
            ):
                self.max_translation = event
            if self.max_yaw is None or event.yaw_rad > self.max_yaw.yaw_rad:
                self.max_yaw = event
        self.previous = sample
        self.last = sample

    def summary(self, bag_start_ns: int) -> Dict[str, Any]:
        if not self.count or self.first is None or self.last is None:
            return {"samples": 0}
        return {
            "samples": self.count,
            "first": sample_to_dict(self.first, bag_start_ns),
            "last": sample_to_dict(self.last, bag_start_ns),
            "integrated_translation_m": round(self.path_length_m, 6),
            "net_translation_m": round(
                math.hypot(self.last.x - self.first.x, self.last.y - self.first.y),
                6,
            ),
            "record_gap_ms": self.record_gap_ms.summary(),
            "header_gap_ms_in_record_order": self.header_gap_ms.summary(),
            "receipt_minus_header_ms": self.receipt_header_lag_ms.summary(),
            "header_integrity_in_record_order": self.header_audit.summary(),
            "max_translation_step": event_to_dict(
                self.max_translation, bag_start_ns
            ),
            "max_yaw_step": event_to_dict(self.max_yaw, bag_start_ns),
        }


def sample_to_dict(sample: PoseSample, bag_start_ns: int = 0) -> Dict[str, Any]:
    return {
        "sequence": sample.sequence,
        "record_ns": sample.record_ns,
        "record_offset_s": round((sample.record_ns - bag_start_ns) / NANOSECONDS, 6),
        "header_ns": sample.header_ns,
        "x_m": round(sample.x, 6),
        "y_m": round(sample.y, 6),
        "yaw_deg": round(math.degrees(sample.yaw), 6),
    }


def event_to_dict(
    event: Optional[StepEvent], bag_start_ns: int = 0
) -> Optional[Dict[str, Any]]:
    if event is None:
        return None
    return {
        "translation_step_m": round(event.translation_m, 6),
        "yaw_step_deg": round(math.degrees(event.yaw_rad), 6),
        "record_gap_ms": round(
            (event.current.record_ns - event.previous.record_ns) / MILLISECONDS, 6
        ),
        "header_gap_ms": round(
            (event.current.header_ns - event.previous.header_ns) / MILLISECONDS, 6
        ),
        "previous": sample_to_dict(event.previous, bag_start_ns),
        "current": sample_to_dict(event.current, bag_start_ns),
    }


class PoseSpool:
    """Disk-backed compact pose spool used for exact timestamp ordering."""

    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(str(path))
        self.connection.execute("PRAGMA journal_mode=OFF")
        self.connection.execute("PRAGMA synchronous=OFF")
        self.connection.execute("PRAGMA temp_store=FILE")
        self.connection.execute(
            """
            CREATE TABLE pose_samples (
                series TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                record_ns INTEGER NOT NULL,
                header_ns INTEGER NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                yaw REAL NOT NULL,
                PRIMARY KEY(series, sequence)
            )
            """
        )
        self._pending = 0

    def add(self, series: str, sample: PoseSample) -> None:
        self.connection.execute(
            "INSERT INTO pose_samples VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                series,
                sample.sequence,
                sample.record_ns,
                sample.header_ns,
                sample.x,
                sample.y,
                sample.yaw,
            ),
        )
        self._pending += 1
        if self._pending >= 1000:
            self.connection.commit()
            self._pending = 0

    def finish(self) -> None:
        self.connection.commit()
        self._pending = 0
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS pose_header_idx "
            "ON pose_samples(series, header_ns, record_ns, sequence)"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS pose_record_idx "
            "ON pose_samples(series, record_ns, sequence)"
        )
        self.connection.commit()

    def series_counts(self, prefix: Optional[str] = None) -> Dict[str, int]:
        if prefix is None:
            rows = self.connection.execute(
                "SELECT series, COUNT(*) FROM pose_samples GROUP BY series"
            )
        else:
            rows = self.connection.execute(
                "SELECT series, COUNT(*) FROM pose_samples "
                "WHERE series LIKE ? GROUP BY series",
                (prefix + "%",),
            )
        return {str(name): int(count) for name, count in rows}

    def iter_series(self, series: str, order: str) -> Iterator[PoseSample]:
        if order == "header":
            clause = "header_ns, record_ns, sequence"
            where = "series = ? AND header_ns > 0"
        elif order == "record":
            clause = "record_ns, sequence"
            where = "series = ?"
        else:
            raise ValueError("order must be 'header' or 'record'")
        cursor = self.connection.execute(
            "SELECT sequence, record_ns, header_ns, x, y, yaw "
            f"FROM pose_samples WHERE {where} ORDER BY {clause}",
            (series,),
        )
        for row in cursor:
            yield PoseSample(
                sequence=int(row[0]),
                record_ns=int(row[1]),
                header_ns=int(row[2]),
                x=float(row[3]),
                y=float(row[4]),
                yaw=float(row[5]),
            )

    def nearest_by_header(self, series: str, header_ns: int) -> Optional[PoseSample]:
        row = self.connection.execute(
            "SELECT sequence, record_ns, header_ns, x, y, yaw "
            "FROM pose_samples WHERE series = ? AND header_ns > 0 "
            "ORDER BY ABS(header_ns - ?) LIMIT 1",
            (series, int(header_ns)),
        ).fetchone()
        if row is None:
            return None
        return PoseSample(
            sequence=int(row[0]),
            record_ns=int(row[1]),
            header_ns=int(row[2]),
            x=float(row[3]),
            y=float(row[4]),
            yaw=float(row[5]),
        )

    def nearest_by_record(self, series: str, record_ns: int) -> Optional[PoseSample]:
        row = self.connection.execute(
            "SELECT sequence, record_ns, header_ns, x, y, yaw "
            "FROM pose_samples WHERE series = ? "
            "ORDER BY ABS(record_ns - ?) LIMIT 1",
            (series, int(record_ns)),
        ).fetchone()
        if row is None:
            return None
        return PoseSample(
            sequence=int(row[0]),
            record_ns=int(row[1]),
            header_ns=int(row[2]),
            x=float(row[3]),
            y=float(row[4]),
            yaw=float(row[5]),
        )

    def close(self) -> None:
        self.connection.close()


def ordered_pose_summary(
    samples: Iterable[PoseSample], bag_start_ns: int
) -> Dict[str, Any]:
    """Summarize an already ordered pose iterator without retaining it."""

    count = 0
    previous: Optional[PoseSample] = None
    first: Optional[PoseSample] = None
    last: Optional[PoseSample] = None
    max_translation: Optional[StepEvent] = None
    max_yaw: Optional[StepEvent] = None
    gap_ms = RunningStats()
    path_length = 0.0
    duplicate_headers = 0
    for sample in samples:
        count += 1
        if first is None:
            first = sample
        if previous is not None:
            event = pose_step(previous, sample)
            path_length += event.translation_m
            gap_ms.add((sample.header_ns - previous.header_ns) / MILLISECONDS)
            if sample.header_ns == previous.header_ns:
                duplicate_headers += 1
            if max_translation is None or event.translation_m > max_translation.translation_m:
                max_translation = event
            if max_yaw is None or event.yaw_rad > max_yaw.yaw_rad:
                max_yaw = event
        previous = sample
        last = sample
    if count == 0 or first is None or last is None:
        return {"samples": 0}
    return {
        "samples": count,
        "first": sample_to_dict(first, bag_start_ns),
        "last": sample_to_dict(last, bag_start_ns),
        "integrated_translation_m": round(path_length, 6),
        "header_gap_ms": gap_ms.summary(),
        "duplicate_adjacent_headers": duplicate_headers,
        "max_translation_step": event_to_dict(max_translation, bag_start_ns),
        "max_yaw_step": event_to_dict(max_yaw, bag_start_ns),
    }


class TimedAccumulator:
    """Common gap/header-lag accounting for non-pose streams."""

    def __init__(self) -> None:
        self.count = 0
        self.previous_record_ns: Optional[int] = None
        self.record_gap_ms = RunningStats()
        self.receipt_header_lag_ms = RunningStats()
        self.header_audit = HeaderAudit()

    def add_time(self, record_ns: int, header_ns: int, sequence: int) -> None:
        self.count += 1
        if self.previous_record_ns is not None:
            self.record_gap_ms.add(
                (record_ns - self.previous_record_ns) / MILLISECONDS
            )
        self.previous_record_ns = record_ns
        self.header_audit.add(header_ns, record_ns, sequence)
        if header_ns > 0:
            self.receipt_header_lag_ms.add((record_ns - header_ns) / MILLISECONDS)

    def timing_summary(self) -> Dict[str, Any]:
        return {
            "samples": self.count,
            "record_gap_ms": self.record_gap_ms.summary(),
            "receipt_minus_header_ms": self.receipt_header_lag_ms.summary(),
            "header_integrity_in_record_order": self.header_audit.summary(),
        }


class ImuAccumulator(TimedAccumulator):
    def __init__(self) -> None:
        super().__init__()
        self.gyro_x = RunningStats()
        self.gyro_y = RunningStats()
        self.gyro_z = RunningStats()
        self.abs_gyro_z = RunningStats()
        self.acceleration_norm = RunningStats()
        self.integrated_yaw_rad = 0.0
        self._previous_time_ns: Optional[int] = None
        self._previous_gyro_z: Optional[float] = None

    def add(self, msg: Any, record_ns: int, header_ns: int, sequence: int) -> None:
        self.add_time(record_ns, header_ns, sequence)
        gx = float(msg.angular_velocity.x)
        gy = float(msg.angular_velocity.y)
        gz = float(msg.angular_velocity.z)
        ax = float(msg.linear_acceleration.x)
        ay = float(msg.linear_acceleration.y)
        az = float(msg.linear_acceleration.z)
        self.gyro_x.add(gx)
        self.gyro_y.add(gy)
        self.gyro_z.add(gz)
        self.abs_gyro_z.add(abs(gz))
        self.acceleration_norm.add(math.sqrt(ax * ax + ay * ay + az * az))
        integration_ns = header_ns if header_ns > 0 else record_ns
        if (
            self._previous_time_ns is not None
            and integration_ns > self._previous_time_ns
            and self._previous_gyro_z is not None
        ):
            dt = (integration_ns - self._previous_time_ns) / NANOSECONDS
            if dt <= 1.0:
                self.integrated_yaw_rad += 0.5 * (self._previous_gyro_z + gz) * dt
        self._previous_time_ns = integration_ns
        self._previous_gyro_z = gz

    def summary(self) -> Dict[str, Any]:
        result = self.timing_summary()
        result.update(
            {
                "gyro_x_rad_s": self.gyro_x.summary(),
                "gyro_y_rad_s": self.gyro_y.summary(),
                "gyro_z_rad_s": self.gyro_z.summary(),
                "abs_gyro_z_rad_s": self.abs_gyro_z.summary(),
                "acceleration_norm_m_s2": self.acceleration_norm.summary(),
                "integrated_gyro_z_deg": round(
                    math.degrees(self.integrated_yaw_rad), 6
                ),
            }
        )
        return result


class ScanAccumulator(TimedAccumulator):
    def __init__(self) -> None:
        super().__init__()
        self.total_points = RunningStats()
        self.valid_points = RunningStats()
        self.valid_fraction = RunningStats()
        self.nearest_valid_m = RunningStats()

    def add(self, msg: Any, record_ns: int, header_ns: int, sequence: int) -> None:
        self.add_time(record_ns, header_ns, sequence)
        total = len(msg.ranges)
        minimum = float(msg.range_min)
        maximum = float(msg.range_max)
        valid = [
            float(value)
            for value in msg.ranges
            if math.isfinite(float(value)) and minimum <= float(value) <= maximum
        ]
        self.total_points.add(total)
        self.valid_points.add(len(valid))
        self.valid_fraction.add(len(valid) / total if total else 0.0)
        if valid:
            self.nearest_valid_m.add(min(valid))

    def summary(self) -> Dict[str, Any]:
        result = self.timing_summary()
        result.update(
            {
                "total_points_per_scan": self.total_points.summary(),
                "valid_points_per_scan": self.valid_points.summary(),
                "valid_fraction": self.valid_fraction.summary(),
                "nearest_valid_range_m": self.nearest_valid_m.summary(),
            }
        )
        return result


class ScanPairer:
    """Pair raw/filtered scans by nearby bag receipt time with bounded state.

    Legacy ATLAS bags can contain scans from the former filter behavior that
    replaced the acquisition timestamp at publication.  Exact-header matching
    alone reports zero pairs for those bags even when the scan contents are
    clearly the same.  Bag receipt time is monotonic and each scan period is
    much longer than the raw-to-filter pipeline, making a tight, one-to-one
    nearest-receipt match the defensible fallback.  Header deltas remain in the
    report so legacy stamp replacement is visible rather than hidden.
    """

    def __init__(self, pending_limit: int = 2048, tolerance_ms: float = 50.0) -> None:
        self.pending: Dict[str, deque] = {"raw": deque(), "filtered": deque()}
        self.pending_limit = max(1, int(pending_limit))
        self.tolerance_ns = max(0, int(tolerance_ms * MILLISECONDS))
        self.pairs = 0
        self.exact_header_pairs = 0
        self.filtered_minus_raw_ms = RunningStats()
        self.absolute_pipeline_ms = RunningStats()
        self.filtered_header_minus_raw_header_ms = RunningStats()
        self.evicted = Counter()

    def add(self, side: str, header_ns: int, record_ns: int) -> None:
        if side not in ("raw", "filtered"):
            raise ValueError("scan side must be raw or filtered")
        other = "filtered" if side == "raw" else "raw"
        queue = self.pending[other]
        best_index: Optional[int] = None
        best_delta: Optional[int] = None
        for index, (_, candidate_record_ns) in enumerate(queue):
            delta = abs(record_ns - candidate_record_ns)
            if delta <= self.tolerance_ns and (best_delta is None or delta < best_delta):
                best_index = index
                best_delta = delta
            if candidate_record_ns > record_ns + self.tolerance_ns:
                break
        if best_index is not None:
            other_header_ns, other_record_ns = queue[best_index]
            del queue[best_index]
            raw_ns = record_ns if side == "raw" else other_record_ns
            filtered_ns = record_ns if side == "filtered" else other_record_ns
            raw_header_ns = header_ns if side == "raw" else other_header_ns
            filtered_header_ns = header_ns if side == "filtered" else other_header_ns
            delta_ms = (filtered_ns - raw_ns) / MILLISECONDS
            self.pairs += 1
            if raw_header_ns == filtered_header_ns:
                self.exact_header_pairs += 1
            self.filtered_minus_raw_ms.add(delta_ms)
            self.absolute_pipeline_ms.add(abs(delta_ms))
            self.filtered_header_minus_raw_header_ms.add(
                (filtered_header_ns - raw_header_ns) / MILLISECONDS
            )
            return

        self.pending[side].append((header_ns, record_ns))
        self._trim()

    def _trim(self) -> None:
        while sum(len(queue) for queue in self.pending.values()) > self.pending_limit:
            choices = [
                (queue[0][1], side)
                for side, queue in self.pending.items()
                if queue
            ]
            if not choices:
                return
            _, side = min(choices)
            self.pending[side].popleft()
            self.evicted[side] += 1

    def summary(self, raw_count: int, filtered_count: int) -> Dict[str, Any]:
        unmatched = {side: len(values) for side, values in self.pending.items()}
        denominator = max(1, min(raw_count, filtered_count))
        return {
            "matching_rule": (
                "one-to-one nearest bag receipt time within "
                f"{self.tolerance_ns / MILLISECONDS:.3f} ms"
            ),
            "paired_scans": self.pairs,
            "pairs_with_identical_header": self.exact_header_pairs,
            "pair_coverage_of_smaller_stream": round(self.pairs / denominator, 6),
            "filtered_receipt_minus_raw_receipt_ms": self.filtered_minus_raw_ms.summary(),
            "absolute_raw_to_filtered_receipt_delta_ms": self.absolute_pipeline_ms.summary(),
            "filtered_header_minus_raw_header_ms": self.filtered_header_minus_raw_header_ms.summary(),
            "unmatched_at_end": unmatched,
            "evicted_from_bounded_pair_buffer": dict(self.evicted),
            "pending_buffer_limit": self.pending_limit,
            "pair_tolerance_ms": self.tolerance_ns / MILLISECONDS,
        }


class CommandAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.nonzero = 0
        self.linear_x = RunningStats()
        self.angular_z = RunningStats()
        self.abs_linear_x = RunningStats()
        self.abs_angular_z = RunningStats()
        self.record_gap_ms = RunningStats()
        self.previous_record_ns: Optional[int] = None

    def add(self, msg: Any, record_ns: int) -> None:
        linear = float(msg.linear.x)
        angular = float(msg.angular.z)
        self.count += 1
        if abs(linear) > 1e-5 or abs(angular) > 1e-5:
            self.nonzero += 1
        self.linear_x.add(linear)
        self.angular_z.add(angular)
        self.abs_linear_x.add(abs(linear))
        self.abs_angular_z.add(abs(angular))
        if self.previous_record_ns is not None:
            self.record_gap_ms.add(
                (record_ns - self.previous_record_ns) / MILLISECONDS
            )
        self.previous_record_ns = record_ns

    def summary(self) -> Dict[str, Any]:
        return {
            "samples": self.count,
            "nonzero_samples": self.nonzero,
            "nonzero_fraction": round(self.nonzero / self.count, 6)
            if self.count
            else None,
            "linear_x_m_s": self.linear_x.summary(),
            "angular_z_rad_s": self.angular_z.summary(),
            "abs_linear_x_m_s": self.abs_linear_x.summary(),
            "abs_angular_z_rad_s": self.abs_angular_z.summary(),
            "record_gap_ms": self.record_gap_ms.summary(),
        }


class SteeringAccumulator:
    def __init__(self) -> None:
        self.values = RunningStats()
        self.changes = 0
        self.previous: Optional[float] = None

    def add(self, value: Any) -> None:
        number = float(value)
        self.values.add(number)
        if self.previous is not None and abs(number - self.previous) > 1e-6:
            self.changes += 1
        self.previous = number

    def summary(self) -> Dict[str, Any]:
        result = self.values.summary()
        result["value_changes"] = self.changes
        result["last_deg"] = round(self.previous, 6) if self.previous is not None else None
        return result


def compact_encoder_health(value: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "state",
        "reason",
        "packet_fresh",
        "packet_age_s",
        "link_state",
        "consensus_state",
        "autonomy_ready",
        "navigation_validated",
        "selected_encoders",
        "excluded_encoders",
        "faults",
        "scale",
    )
    return {key: value.get(key) for key in keys if key in value}


class EncoderHealthAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.json_errors = 0
        self.states = Counter()
        self.link_states = Counter()
        self.consensus_states = Counter()
        self.faults = Counter()
        self.selected_sets = Counter()
        self.excluded_sets = Counter()
        self.autonomy_false = 0
        self.transitions = 0
        self.previous_state: Optional[Tuple[Any, ...]] = None
        self.latest: Dict[str, Any] = {}
        self.record_gap_ms = RunningStats()
        self.previous_record_ns: Optional[int] = None

    @staticmethod
    def _tuple(value: Any) -> Tuple[Any, ...]:
        if isinstance(value, (list, tuple)):
            return tuple(value)
        return tuple()

    def add(self, data: str, record_ns: int) -> Dict[str, Any]:
        self.count += 1
        if self.previous_record_ns is not None:
            self.record_gap_ms.add(
                (record_ns - self.previous_record_ns) / MILLISECONDS
            )
        self.previous_record_ns = record_ns
        try:
            decoded = json.loads(data)
        except (TypeError, json.JSONDecodeError):
            self.json_errors += 1
            return {"parse_error": True}
        if not isinstance(decoded, dict):
            self.json_errors += 1
            return {"parse_error": True}
        compact = compact_encoder_health(decoded)
        self.latest = compact
        state = str(decoded.get("state", "UNKNOWN"))
        link = str(decoded.get("link_state", "UNKNOWN"))
        consensus = str(decoded.get("consensus_state", "UNKNOWN"))
        selected = self._tuple(decoded.get("selected_encoders"))
        excluded = self._tuple(decoded.get("excluded_encoders"))
        faults = self._tuple(decoded.get("faults"))
        self.states[state] += 1
        self.link_states[link] += 1
        self.consensus_states[consensus] += 1
        self.selected_sets[str(list(selected))] += 1
        self.excluded_sets[str(list(excluded))] += 1
        for fault in faults:
            self.faults[str(fault)] += 1
        if decoded.get("autonomy_ready") is False:
            self.autonomy_false += 1
        transition_key = (state, link, consensus, selected, excluded, faults)
        if self.previous_state is not None and transition_key != self.previous_state:
            self.transitions += 1
        self.previous_state = transition_key
        return compact

    def summary(self) -> Dict[str, Any]:
        return {
            "samples": self.count,
            "json_errors": self.json_errors,
            "states": dict(self.states),
            "link_states": dict(self.link_states),
            "consensus_states": dict(self.consensus_states),
            "fault_occurrences": dict(self.faults),
            "selected_encoder_sets": dict(self.selected_sets),
            "excluded_encoder_sets": dict(self.excluded_sets),
            "autonomy_not_ready_samples": self.autonomy_false,
            "state_or_policy_transitions": self.transitions,
            "record_gap_ms": self.record_gap_ms.summary(),
            "latest": self.latest,
        }


class ContextStream:
    """Bounded nearest-sample context and online numeric fields."""

    def __init__(self, max_nearest: int) -> None:
        self.count = 0
        self.max_nearest = max(1, int(max_nearest))
        self._heap: List[Tuple[float, int, Dict[str, Any]]] = []
        self._counter = 0
        self.numeric: Dict[str, RunningStats] = defaultdict(
            lambda: RunningStats(reservoir_size=256)
        )
        self.categorical: Dict[str, Counter] = defaultdict(Counter)

    def add(self, delta_s: float, value: Dict[str, Any]) -> None:
        self.count += 1
        self._counter += 1
        item = dict(value)
        item["event_delta_s"] = round(delta_s, 6)
        priority = -abs(delta_s)
        entry = (priority, self._counter, item)
        if len(self._heap) < self.max_nearest:
            heapq.heappush(self._heap, entry)
        elif priority > self._heap[0][0]:
            heapq.heapreplace(self._heap, entry)
        for key, raw in value.items():
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                self.numeric[key].add(raw)
            elif isinstance(raw, (str, bool)) or raw is None:
                self.categorical[key][str(raw)] += 1
            elif isinstance(raw, (list, tuple)):
                self.categorical[key][json.dumps(list(raw), sort_keys=True)] += 1

    def summary(self) -> Dict[str, Any]:
        nearest = [entry[2] for entry in self._heap]
        nearest.sort(key=lambda item: item["event_delta_s"])
        return {
            "samples_in_window": self.count,
            "numeric_summary": {
                key: stats.summary() for key, stats in sorted(self.numeric.items())
            },
            "categorical_summary": {
                key: dict(values) for key, values in sorted(self.categorical.items())
            },
            "nearest_samples": nearest,
            "nearest_sample_limit": self.max_nearest,
        }


class EventContext:
    def __init__(self, label: str, record_ns: int, radius_s: float, max_nearest: int) -> None:
        self.label = label
        self.record_ns = record_ns
        self.radius_ns = int(radius_s * NANOSECONDS)
        self.max_nearest = max_nearest
        self.streams: Dict[str, ContextStream] = {}

    def accepts(self, record_ns: int) -> bool:
        return abs(record_ns - self.record_ns) <= self.radius_ns

    def add(self, stream: str, record_ns: int, value: Dict[str, Any]) -> None:
        if not self.accepts(record_ns):
            return
        if stream not in self.streams:
            self.streams[stream] = ContextStream(self.max_nearest)
        self.streams[stream].add(
            (record_ns - self.record_ns) / NANOSECONDS,
            value,
        )

    def summary(self, bag_start_ns: int) -> Dict[str, Any]:
        return {
            "label": self.label,
            "event_record_ns": self.record_ns,
            "event_record_offset_s": round(
                (self.record_ns - bag_start_ns) / NANOSECONDS, 6
            ),
            "window_radius_s": self.radius_ns / NANOSECONDS,
            "streams": {
                name: stream.summary() for name, stream in sorted(self.streams.items())
            },
        }


def select_odom_base_series(counts: Dict[str, int]) -> Optional[str]:
    """Select the most useful direct odom-to-base TF series."""

    priority = ("base_footprint", "base_link", "base_chassis", "base")
    for child in priority:
        name = f"tf:odom->{child}"
        if counts.get(name, 0):
            return name
    candidates = [(count, name) for name, count in counts.items() if name.startswith("tf:odom->")]
    return max(candidates)[1] if candidates else None


def compose_map_base_event(
    spool: PoseSpool,
    event: Optional[StepEvent],
    odom_base_series: Optional[str],
    bag_start_ns: int,
    alignment: str = "header",
) -> Optional[Dict[str, Any]]:
    if event is None or odom_base_series is None:
        return None
    composed: List[Dict[str, Any]] = []
    raw_poses: List[Tuple[float, float, float]] = []
    for label, map_odom in (("before", event.previous), ("after", event.current)):
        if alignment == "header":
            odom_base = spool.nearest_by_header(odom_base_series, map_odom.header_ns)
            alignment_difference_ms = (
                (odom_base.header_ns - map_odom.header_ns) / MILLISECONDS
                if odom_base is not None
                else None
            )
        elif alignment == "record":
            odom_base = spool.nearest_by_record(odom_base_series, map_odom.record_ns)
            alignment_difference_ms = (
                (odom_base.record_ns - map_odom.record_ns) / MILLISECONDS
                if odom_base is not None
                else None
            )
        else:
            raise ValueError("alignment must be 'header' or 'record'")
        if odom_base is None:
            return None
        pose = compose_se2(
            map_odom.x,
            map_odom.y,
            map_odom.yaw,
            odom_base.x,
            odom_base.y,
            odom_base.yaw,
        )
        raw_poses.append(pose)
        composed.append(
            {
                "side": label,
                "map_odom": sample_to_dict(map_odom, bag_start_ns),
                "nearest_odom_base": sample_to_dict(odom_base, bag_start_ns),
                "alignment_difference_ms": round(float(alignment_difference_ms), 6),
                "map_base": {
                    "x_m": round(pose[0], 6),
                    "y_m": round(pose[1], 6),
                    "yaw_deg": round(math.degrees(pose[2]), 6),
                },
            }
        )
    return {
        "alignment": alignment,
        "odom_base_series": odom_base_series,
        "poses": composed,
        "map_base_translation_step_m": round(
            math.hypot(raw_poses[1][0] - raw_poses[0][0], raw_poses[1][1] - raw_poses[0][1]),
            6,
        ),
        "map_base_yaw_step_deg": round(
            math.degrees(abs(angle_delta(raw_poses[1][2], raw_poses[0][2]))),
            6,
        ),
    }


def ros_imports() -> Tuple[Any, Any, Any]:
    """Import ROS bag dependencies lazily so pure helpers remain testable."""

    import rosbag2_py  # type: ignore
    from rclpy.serialization import deserialize_message  # type: ignore
    from rosidl_runtime_py.utilities import get_message  # type: ignore

    return rosbag2_py, deserialize_message, get_message


def open_reader(bag: str, storage_id: str) -> Tuple[Any, Dict[str, str], Any, Any]:
    rosbag2_py, deserialize_message, get_message = ros_imports()
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=bag, storage_id=storage_id),
        rosbag2_py.ConverterOptions("", ""),
    )
    topic_types = {
        item.name: item.type for item in reader.get_all_topics_and_types()
    }
    return reader, topic_types, deserialize_message, get_message


def message_classes(
    topic_types: Dict[str, str], get_message: Any, topics: Iterable[str]
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    classes: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    for topic in topics:
        if topic not in topic_types:
            continue
        try:
            classes[topic] = get_message(topic_types[topic])
        except Exception as exc:  # pragma: no cover - depends on ROS installation
            errors[topic] = f"{type(exc).__name__}: {exc}"
    return classes, errors


def compact_scan(msg: Any, record_ns: int) -> Dict[str, Any]:
    header_ns = stamp_to_ns(msg.header.stamp)
    minimum = float(msg.range_min)
    maximum = float(msg.range_max)
    valid = [
        float(value)
        for value in msg.ranges
        if math.isfinite(float(value)) and minimum <= float(value) <= maximum
    ]
    return {
        "receipt_minus_header_ms": round((record_ns - header_ns) / MILLISECONDS, 6),
        "points": len(msg.ranges),
        "valid_points": len(valid),
        "nearest_valid_m": round(min(valid), 6) if valid else None,
    }


def compact_message(topic: str, msg: Any, record_ns: int) -> List[Tuple[str, Dict[str, Any]]]:
    """Extract small event-context records from a deserialized ROS message."""

    if topic in ODOM_TOPICS:
        pose = msg.pose.pose
        header_ns = stamp_to_ns(msg.header.stamp)
        return [
            (
                topic,
                {
                    "x_m": round(float(pose.position.x), 6),
                    "y_m": round(float(pose.position.y), 6),
                    "yaw_deg": round(math.degrees(quaternion_yaw(pose.orientation)), 6),
                    "linear_x_m_s": round(float(msg.twist.twist.linear.x), 6),
                    "angular_z_rad_s": round(float(msg.twist.twist.angular.z), 6),
                    "receipt_minus_header_ms": round(
                        (record_ns - header_ns) / MILLISECONDS, 6
                    ),
                },
            )
        ]
    if topic == IM10A_TOPIC:
        header_ns = stamp_to_ns(msg.header.stamp)
        return [
            (
                topic,
                {
                    "gyro_x_rad_s": round(float(msg.angular_velocity.x), 6),
                    "gyro_y_rad_s": round(float(msg.angular_velocity.y), 6),
                    "gyro_z_rad_s": round(float(msg.angular_velocity.z), 6),
                    "accel_x_m_s2": round(float(msg.linear_acceleration.x), 6),
                    "accel_y_m_s2": round(float(msg.linear_acceleration.y), 6),
                    "accel_z_m_s2": round(float(msg.linear_acceleration.z), 6),
                    "receipt_minus_header_ms": round(
                        (record_ns - header_ns) / MILLISECONDS, 6
                    ),
                },
            )
        ]
    if topic in SCAN_TOPICS:
        return [(topic, compact_scan(msg, record_ns))]
    if topic in COMMAND_TOPICS:
        return [
            (
                topic,
                {
                    "linear_x_m_s": round(float(msg.linear.x), 6),
                    "angular_z_rad_s": round(float(msg.angular.z), 6),
                },
            )
        ]
    if topic in STEERING_TOPICS:
        return [(topic, {"angle_deg": round(float(msg.data), 6)})]
    if topic == ENCODER_HEALTH_TOPIC:
        try:
            decoded = json.loads(msg.data)
            value = compact_encoder_health(decoded) if isinstance(decoded, dict) else {"parse_error": True}
        except (TypeError, json.JSONDecodeError):
            value = {"parse_error": True}
        return [(topic, value)]
    if topic in ("/tf", "/tf_static"):
        result = []
        for transform in msg.transforms:
            parent = normalize_frame(transform.header.frame_id)
            child = normalize_frame(transform.child_frame_id)
            if parent == "map" and child == "odom" or parent == "odom" and child.startswith("base"):
                result.append(
                    (
                        f"{topic}:{parent}->{child}",
                        {
                            "x_m": round(float(transform.transform.translation.x), 6),
                            "y_m": round(float(transform.transform.translation.y), 6),
                            "yaw_deg": round(
                                math.degrees(quaternion_yaw(transform.transform.rotation)), 6
                            ),
                            "receipt_minus_header_ms": round(
                                (
                                    record_ns
                                    - stamp_to_ns(transform.header.stamp)
                                )
                                / MILLISECONDS,
                                6,
                            ),
                        },
                    )
                )
        return result
    return []


def first_pass(
    bag: str,
    storage_id: str,
    spool: PoseSpool,
    scan_pair_buffer: int,
    scan_pair_tolerance_ms: float,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    reader, topic_types, deserialize_message, get_message = open_reader(bag, storage_id)
    relevant = set(ODOM_TOPICS + SCAN_TOPICS + STEERING_TOPICS + COMMAND_TOPICS)
    relevant.update(("/tf", "/tf_static", IM10A_TOPIC, ENCODER_HEALTH_TOPIC))
    classes, type_errors = message_classes(topic_types, get_message, relevant)

    pose_accumulators: Dict[str, PoseAccumulator] = {
        topic: PoseAccumulator() for topic in ODOM_TOPICS if topic in classes
    }
    tf_accumulators: Dict[str, PoseAccumulator] = {}
    imu = ImuAccumulator()
    scans = {topic: ScanAccumulator() for topic in SCAN_TOPICS if topic in classes}
    scan_pairer = ScanPairer(scan_pair_buffer, scan_pair_tolerance_ms)
    commands = {topic: CommandAccumulator() for topic in COMMAND_TOPICS if topic in classes}
    steering = {topic: SteeringAccumulator() for topic in STEERING_TOPICS if topic in classes}
    encoder = EncoderHealthAccumulator()
    deserialization_errors = Counter()
    bag_start_ns: Optional[int] = None
    bag_end_ns: Optional[int] = None
    messages_read = 0
    relevant_messages = 0
    sequence = 0

    while reader.has_next():
        topic, raw, record_ns = reader.read_next()
        messages_read += 1
        record_ns = int(record_ns)
        bag_start_ns = record_ns if bag_start_ns is None else min(bag_start_ns, record_ns)
        bag_end_ns = record_ns if bag_end_ns is None else max(bag_end_ns, record_ns)
        if topic not in classes:
            continue
        relevant_messages += 1
        try:
            msg = deserialize_message(raw, classes[topic])
        except Exception as exc:  # pragma: no cover - corrupt-bag dependent
            deserialization_errors[f"{topic}: {type(exc).__name__}"] += 1
            continue

        if topic in ODOM_TOPICS:
            sequence += 1
            pose = msg.pose.pose
            sample = PoseSample(
                sequence=sequence,
                record_ns=record_ns,
                header_ns=stamp_to_ns(msg.header.stamp),
                x=float(pose.position.x),
                y=float(pose.position.y),
                yaw=quaternion_yaw(pose.orientation),
            )
            pose_accumulators[topic].add(sample)
            spool.add(f"odom:{topic}", sample)
        elif topic in ("/tf", "/tf_static"):
            for transform in msg.transforms:
                parent = normalize_frame(transform.header.frame_id)
                child = normalize_frame(transform.child_frame_id)
                if not (
                    (parent == "map" and child == "odom")
                    or (parent == "odom" and child.startswith("base"))
                ):
                    continue
                sequence += 1
                transform_value = transform.transform
                sample = PoseSample(
                    sequence=sequence,
                    record_ns=record_ns,
                    header_ns=stamp_to_ns(transform.header.stamp),
                    x=float(transform_value.translation.x),
                    y=float(transform_value.translation.y),
                    yaw=quaternion_yaw(transform_value.rotation),
                )
                series = f"tf:{parent}->{child}"
                if series not in tf_accumulators:
                    tf_accumulators[series] = PoseAccumulator()
                tf_accumulators[series].add(sample)
                spool.add(series, sample)
        elif topic == IM10A_TOPIC:
            sequence += 1
            imu.add(msg, record_ns, stamp_to_ns(msg.header.stamp), sequence)
        elif topic in SCAN_TOPICS:
            sequence += 1
            header_ns = stamp_to_ns(msg.header.stamp)
            scans[topic].add(msg, record_ns, header_ns, sequence)
            scan_pairer.add("raw" if topic == "/scan_raw" else "filtered", header_ns, record_ns)
        elif topic in COMMAND_TOPICS:
            commands[topic].add(msg, record_ns)
        elif topic in STEERING_TOPICS:
            steering[topic].add(msg.data)
        elif topic == ENCODER_HEALTH_TOPIC:
            encoder.add(msg.data, record_ns)

    spool.finish()
    start_ns = bag_start_ns or 0
    end_ns = bag_end_ns or start_ns
    record_summaries = {
        topic: accumulator.summary(start_ns)
        for topic, accumulator in sorted(pose_accumulators.items())
    }
    tf_record_summaries = {
        series: accumulator.summary(start_ns)
        for series, accumulator in sorted(tf_accumulators.items())
    }
    header_summaries = {
        series: ordered_pose_summary(spool.iter_series(series, "header"), start_ns)
        for series in sorted(spool.series_counts())
    }
    report = {
        "analysis_mode": "READ_ONLY_SEQUENTIAL_READER",
        "safety_invariant": "No ROS node, publisher, subscriber, service, action, or rosbag replay is created.",
        "bag": os.path.abspath(bag),
        "storage_id": storage_id,
        "bag_start_record_ns": start_ns,
        "bag_end_record_ns": end_ns,
        "duration_s": round((end_ns - start_ns) / NANOSECONDS, 6),
        "messages_read": messages_read,
        "relevant_messages_deserialized": relevant_messages,
        "available_topics": dict(sorted(topic_types.items())),
        "missing_requested_topics": sorted(relevant - set(topic_types)),
        "message_type_resolution_errors": type_errors,
        "deserialization_errors": dict(deserialization_errors),
        "pose_series_counts": spool.series_counts(),
        "pose_record_order": record_summaries,
        "tf_record_order": tf_record_summaries,
        "pose_header_time_order": header_summaries,
        "im10a_corrected_candidate": imu.summary(),
        "lidar": {
            "streams": {topic: value.summary() for topic, value in sorted(scans.items())},
            "raw_filtered_pairing": scan_pairer.summary(
                scans.get("/scan_raw", TimedAccumulator()).count,
                scans.get("/scan", TimedAccumulator()).count,
            ),
        },
        "commands": {topic: value.summary() for topic, value in sorted(commands.items())},
        "steering": {topic: value.summary() for topic, value in sorted(steering.items())},
        "encoder_health": encoder.summary(),
    }
    state = {
        "bag_start_ns": start_ns,
        "topic_types": topic_types,
        "map_record_event": tf_accumulators.get(MAP_ODOM_SERIES).max_translation
        if MAP_ODOM_SERIES in tf_accumulators
        else None,
        "map_header_event": None,
    }
    header_map = header_summaries.get(MAP_ODOM_SERIES, {})
    header_event_dict = header_map.get("max_translation_step")
    if header_event_dict:
        # Recover the exact event objects from the disk-backed ordered iterator.
        maximum: Optional[StepEvent] = None
        previous: Optional[PoseSample] = None
        for sample in spool.iter_series(MAP_ODOM_SERIES, "header"):
            if previous is not None:
                candidate = pose_step(previous, sample)
                if maximum is None or candidate.translation_m > maximum.translation_m:
                    maximum = candidate
            previous = sample
        state["map_header_event"] = maximum
    return report, state


def second_pass_context(
    bag: str,
    storage_id: str,
    topic_types: Dict[str, str],
    events: Sequence[EventContext],
) -> List[Dict[str, Any]]:
    if not events:
        return []
    reader, current_types, deserialize_message, get_message = open_reader(bag, storage_id)
    relevant = set(ODOM_TOPICS + SCAN_TOPICS + STEERING_TOPICS + COMMAND_TOPICS)
    relevant.update(("/tf", "/tf_static", IM10A_TOPIC, ENCODER_HEALTH_TOPIC))
    classes, _ = message_classes(current_types, get_message, relevant)
    while reader.has_next():
        topic, raw, record_ns = reader.read_next()
        record_ns = int(record_ns)
        targets = [event for event in events if event.accepts(record_ns)]
        if not targets or topic not in classes:
            continue
        try:
            msg = deserialize_message(raw, classes[topic])
        except Exception:  # pragma: no cover - already counted in first pass
            continue
        compact = compact_message(topic, msg, record_ns)
        for event in targets:
            for stream, value in compact:
                event.add(stream, record_ns, value)
    return [event.summary(0) for event in events]


def anomaly_index(report: Dict[str, Any]) -> Dict[str, Any]:
    """Collect timestamp anomalies into one concise index."""

    result: Dict[str, Any] = {}
    sections = (
        report.get("pose_record_order", {}),
        report.get("tf_record_order", {}),
    )
    for section in sections:
        for series, summary in section.items():
            audit = summary.get("header_integrity_in_record_order", {})
            if audit.get("duplicates") or audit.get("regressions") or audit.get("zero_stamps"):
                result[series] = audit
    imu = report.get("im10a_corrected_candidate", {})
    audit = imu.get("header_integrity_in_record_order", {})
    if audit.get("duplicates") or audit.get("regressions") or audit.get("zero_stamps"):
        result[IM10A_TOPIC] = audit
    for topic, summary in report.get("lidar", {}).get("streams", {}).items():
        audit = summary.get("header_integrity_in_record_order", {})
        if audit.get("duplicates") or audit.get("regressions") or audit.get("zero_stamps"):
            result[topic] = audit
    return result


def classify_map_odom_event(report: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a conservative, evidence-linked classification of the max event."""

    event = report.get("map_odom_event_comparison", {}).get("record_order_max")
    if not event:
        return {
            "classification": "NO_MAP_ODOM_EVENT",
            "confidence": "HIGH",
            "evidence": ["No map->odom step was available."],
        }
    translation = float(event.get("translation_step_m", 0.0))
    yaw_deg = float(event.get("yaw_step_deg", 0.0))
    same_header = event.get("header_gap_ms") == 0.0
    odom = report.get("pose_record_order", {}).get("/odom", {})
    wheel = report.get("pose_record_order", {}).get("/yahboom/odom", {})
    odom_step = float(
        (odom.get("max_translation_step") or {}).get("translation_step_m", math.inf)
    )
    wheel_step = float(
        (wheel.get("max_translation_step") or {}).get("translation_step_m", math.inf)
    )
    context = (report.get("event_context") or [{}])[0].get("streams", {})
    cmd_numeric = context.get("/cmd_vel", {}).get("numeric_summary", {})
    cmd_turn = float((cmd_numeric.get("angular_z_rad_s") or {}).get("max", 0.0))
    cmd_turn = max(
        cmd_turn,
        abs(float((cmd_numeric.get("angular_z_rad_s") or {}).get("min", 0.0))),
    )
    imu_numeric = context.get(IM10A_TOPIC, {}).get("numeric_summary", {})
    gyro_turn = float((imu_numeric.get("gyro_z_rad_s") or {}).get("max", 0.0))
    gyro_turn = max(
        gyro_turn,
        abs(float((imu_numeric.get("gyro_z_rad_s") or {}).get("min", 0.0))),
    )
    encoder_categories = context.get(ENCODER_HEALTH_TOPIC, {}).get(
        "categorical_summary", {}
    )
    encoder_states = encoder_categories.get("state", {})
    scan_stream = context.get("/scan", {})
    scan_samples = int(scan_stream.get("samples_in_window", 0))
    evidence = [
        f"map->odom changed {translation:.3f} m and {yaw_deg:.2f} deg in one published step",
        f"largest /odom step in the entire bag was {odom_step:.3f} m",
        f"largest /yahboom/odom step in the entire bag was {wheel_step:.3f} m",
    ]
    if same_header:
        evidence.append(
            "the before/after map->odom values carry the identical TF header timestamp"
        )
    if cmd_turn or gyro_turn:
        evidence.append(
            f"the event window contains commanded |yaw rate| up to {cmd_turn:.3f} rad/s "
            f"and corrected IM10A |gyro-z| up to {gyro_turn:.3f} rad/s"
        )
    if scan_samples:
        evidence.append(f"filtered LiDAR remained live ({scan_samples} window samples)")
    if encoder_states:
        evidence.append(f"encoder states in the event window: {encoder_states}")

    large_map_only = translation >= 0.15 and odom_step < translation * 0.25 and wheel_step < translation * 0.25
    if large_map_only and same_header and max(cmd_turn, gyro_turn) >= 0.3:
        classification = "SLAM_POSE_GRAPH_OR_SCAN_MATCH_CORRECTION_DURING_TURN"
        confidence = "HIGH"
    elif large_map_only:
        classification = "LOCALIZATION_CORRECTION_WITHOUT_ODOMETRY_TELEPORT"
        confidence = "MEDIUM"
    else:
        classification = "UNCLASSIFIED_MAP_ODOM_DISCONTINUITY"
        confidence = "LOW"
    caveats = []
    if encoder_states.get("CRITICAL"):
        caveats.append(
            "Encoder consensus became CRITICAL in the surrounding window. It may have "
            "degraded the trajectory estimate, but this report does not prove causation."
        )
    return {
        "classification": classification,
        "confidence": confidence,
        "evidence": evidence,
        "contributing_conditions": caveats,
        "interpretation": (
            "The discontinuity is in localization/map correction, not a matching wheel-"
            "or fused-odometry teleport. Preserve the bag and tune only after reproducing "
            "the event with live correction limits."
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only, bounded-memory ATLAS rosbag TF event analyzer"
    )
    parser.add_argument("bag", help="rosbag2 directory")
    parser.add_argument("--storage-id", default="sqlite3")
    parser.add_argument("--window-s", type=float, default=5.0)
    parser.add_argument("--context-samples", type=int, default=12)
    parser.add_argument("--scan-pair-buffer", type=int, default=2048)
    parser.add_argument("--scan-pair-tolerance-ms", type=float, default=50.0)
    parser.add_argument("--output", help="optional JSON output path")
    parser.add_argument(
        "--temp-dir", help="directory for the compact temporary SQLite pose spool"
    )
    args = parser.parse_args(argv)
    if args.window_s <= 0:
        parser.error("--window-s must be positive")
    if args.context_samples <= 0:
        parser.error("--context-samples must be positive")

    with tempfile.TemporaryDirectory(dir=args.temp_dir) as temporary:
        spool = PoseSpool(Path(temporary) / "atlas_tf_event_spool.sqlite3")
        try:
            report, state = first_pass(
                args.bag,
                args.storage_id,
                spool,
                args.scan_pair_buffer,
                args.scan_pair_tolerance_ms,
            )
            bag_start_ns = int(state["bag_start_ns"])
            counts = spool.series_counts("tf:odom->")
            odom_base_series = select_odom_base_series(counts)
            record_event: Optional[StepEvent] = state["map_record_event"]
            header_event: Optional[StepEvent] = state["map_header_event"]
            report["map_odom_event_comparison"] = {
                "record_order_max": event_to_dict(record_event, bag_start_ns),
                "header_time_order_max": event_to_dict(header_event, bag_start_ns),
                "same_current_sample": bool(
                    record_event
                    and header_event
                    and record_event.current.sequence == header_event.current.sequence
                ),
            }
            report["map_base_composition"] = {
                "selected_odom_base_series": odom_base_series,
                "available_odom_base_series": counts,
                "record_order_event": {
                    "header_aligned": compose_map_base_event(
                        spool,
                        record_event,
                        odom_base_series,
                        bag_start_ns,
                        "header",
                    ),
                    "record_aligned": compose_map_base_event(
                        spool,
                        record_event,
                        odom_base_series,
                        bag_start_ns,
                        "record",
                    ),
                },
                "header_time_order_event": {
                    "header_aligned": compose_map_base_event(
                        spool,
                        header_event,
                        odom_base_series,
                        bag_start_ns,
                        "header",
                    ),
                    "record_aligned": compose_map_base_event(
                        spool,
                        header_event,
                        odom_base_series,
                        bag_start_ns,
                        "record",
                    ),
                },
            }

            contexts: List[EventContext] = []
            seen_record_ns = set()
            for label, event in (
                ("map_odom_record_order_max", record_event),
                ("map_odom_header_time_order_max", header_event),
            ):
                if event is None or event.current.record_ns in seen_record_ns:
                    continue
                seen_record_ns.add(event.current.record_ns)
                contexts.append(
                    EventContext(
                        label,
                        event.current.record_ns,
                        args.window_s,
                        args.context_samples,
                    )
                )
            raw_context = second_pass_context(
                args.bag,
                args.storage_id,
                state["topic_types"],
                contexts,
            )
            # second_pass_context uses zero as its offset reference to keep the
            # collector independent. Correct the display offset here.
            for item in raw_context:
                item["event_record_offset_s"] = round(
                    (item["event_record_ns"] - bag_start_ns) / NANOSECONDS, 6
                )
            report["event_context"] = raw_context
            report["header_timestamp_anomalies"] = anomaly_index(report)
            report["event_classification"] = classify_map_odom_event(report)
            report["status"] = (
                "OK"
                if record_event is not None
                else "NO_MAP_TO_ODOM_TRANSFORMS_FOUND"
            )
            report["memory_policy"] = {
                "bag_messages": "streamed; raw messages are never retained",
                "pose_samples": "compact numeric rows in temporary on-disk SQLite",
                "quantiles": "fixed-size deterministic reservoirs",
                "event_context": "fixed count of nearest compact samples per stream",
                "scan_pairing": f"at most {args.scan_pair_buffer} unmatched stamps",
            }
        finally:
            spool.close()

    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())

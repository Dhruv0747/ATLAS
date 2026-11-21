#!/usr/bin/env python3
"""Read-only wheel/IMU yaw evidence from a rosbag2 SQLite recording.

Uses the published encoder-update snapshot (the exact input to wheel odometry)
and the IM10A gyro's source timestamp. No ROS installation or rover access is
needed. Commanded steering is not a measured road-wheel angle.
"""
import argparse
import glob
import json
import math
import sqlite3
import struct
from pathlib import Path


def align(offset, width):
    # CDR alignment is relative to the byte after the four-byte encapsulation.
    return 4 + (offset - 4 + width - 1) // width * width


def decode_string(blob):
    if blob[:4] != b"\x00\x01\x00\x00":
        raise ValueError("expected little-endian CDR")
    size = struct.unpack_from("<I", blob, 4)[0]
    return json.loads(blob[8:8 + size].rstrip(b"\x00"))


def decode_imu_z(blob):
    """Decode source header time and angular_velocity.z from sensor_msgs/Imu."""
    if blob[:4] != b"\x00\x01\x00\x00":
        raise ValueError("expected little-endian CDR")
    sec, nsec = struct.unpack_from("<iI", blob, 4)
    name_size = struct.unpack_from("<I", blob, 12)[0]
    offset = align(16 + name_size, 8)
    # Quaternion(4), orientation covariance(9), angular velocity(3) doubles.
    z = struct.unpack_from("<d", blob, offset + (4 + 9 + 2) * 8)[0]
    if nsec >= 1_000_000_000 or not math.isfinite(z) or abs(z) > 35.0:
        raise ValueError("invalid IMU timestamp or gyro Z; check CDR layout")
    return sec + nsec * 1e-9, z


def load_bag(path):
    updates, gyro = [], []
    for dbpath in sorted(glob.glob(str(Path(path) / "*.db3"))):
        with sqlite3.connect(f"file:{Path(dbpath).as_posix()}?mode=ro", uri=True) as db:
            topics = {name: (ident, typ) for ident, name, typ in db.execute(
                "SELECT id,name,type FROM topics")}
            for name, expected, target, decode in (
                ("/atlas/encoder_update", "std_msgs/msg/String", updates, decode_string),
                ("/im10a/imu/bias_corrected_candidate", "sensor_msgs/msg/Imu", gyro, decode_imu_z),
            ):
                if name not in topics:
                    continue
                ident, typ = topics[name]
                if typ != expected:
                    raise ValueError(f"unexpected {name} type {typ}")
                target.extend(decode(blob) for (blob,) in db.execute(
                    "SELECT data FROM messages WHERE topic_id=? ORDER BY timestamp", (ident,)))
    return sorted(updates, key=lambda u: u["stamp_ns"]), sorted(gyro)


def integrate_gyro(gyro, start, end, max_gap=0.5):
    yaw, covered = 0.0, 0.0
    for (t0, z0), (t1, z1) in zip(gyro, gyro[1:]):
        if not 0 < t1 - t0 <= max_gap:
            continue
        left, right = max(start, t0), min(end, t1)
        if right <= left:
            continue
        fraction_left = (left - t0) / (t1 - t0)
        fraction_right = (right - t0) / (t1 - t0)
        zl = z0 + (z1 - z0) * fraction_left
        zr = z0 + (z1 - z0) * fraction_right
        yaw += (zl + zr) * (right - left) / 2
        covered += right - left
    return yaw, covered


def summarize_window(updates, gyro, start, end):
    rows = [u for u in updates if start <= u["stamp_ns"] * 1e-9 < end]
    wheel = sum(u["accepted_delta_m"] * u["applied_curvature_per_m"] for u in rows)
    distance = sum(u["accepted_delta_m"] for u in rows)
    imu, covered = integrate_gyro(gyro, start, end)
    first, last = (rows[0], rows[-1]) if rows else (None, None)
    return {
        "start_s": round(start - updates[0]["stamp_ns"] * 1e-9, 3),
        "end_s": round(end - updates[0]["stamp_ns"] * 1e-9, 3),
        "updates": len(rows),
        "distance_m": round(distance, 4),
        "wheel_yaw_deg": round(math.degrees(wheel), 3),
        "gyro_yaw_deg": round(math.degrees(imu), 3),
        "gyro_coverage_fraction": round(covered / (end - start), 3),
        "raw_count_change": [last["raw_counts"][i] - first["raw_counts"][i]
                             for i in range(4)] if rows else None,
        "signed_wheel_distance_change_m": [
            round(last["wheel_distances_m"][i] - first["wheel_distances_m"][i], 4)
            for i in range(4)] if rows else None,
        "steering_command_range_deg": [
            [min(u["steering_command_deg"][i] for u in rows),
             max(u["steering_command_deg"][i] for u in rows)]
            for i in range(2)] if rows else None,
        "accepted_3plus": sum(len(u["accepted_channels"]) >= 3 for u in rows),
        "accepted_all_four": sum(len(u["accepted_channels"]) == 4 for u in rows),
        "fresh_packets": sum(u["packet_fresh"] is True for u in rows),
    }


def audit(path, window_s=2.0):
    updates, gyro = load_bag(path)
    if not updates or len(gyro) < 2:
        return {"bag": Path(path).name, "error": "encoder snapshots or IM10A samples absent"}
    start = updates[0]["stamp_ns"] * 1e-9
    end = updates[-1]["stamp_ns"] * 1e-9
    windows = []
    at = start
    while at + window_s <= end:
        row = summarize_window(updates, gyro, at, at + window_s)
        if (row["updates"] >= 3 and row["gyro_coverage_fraction"] >= 0.9
                and abs(row["gyro_yaw_deg"]) >= 5):
            row["opposite_sign"] = row["wheel_yaw_deg"] * row["gyro_yaw_deg"] < 0
            windows.append(row)
        at += window_s
    return {"bag": Path(path).name, "encoder_updates": len(updates),
            "imu_samples": len(gyro), "window_s": window_s,
            "turn_windows": len(windows),
            "opposite_sign_windows": sum(w["opposite_sign"] for w in windows),
            "windows": windows,
            "caveat": "IMU/encoder agreement is not physical ground truth; steering values are commands."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bags", nargs="+")
    parser.add_argument("--window-s", type=float, default=2.0)
    args = parser.parse_args()
    if args.window_s <= 0:
        parser.error("--window-s must be positive")
    print(json.dumps([audit(p, args.window_s) for p in args.bags], indent=2))


if __name__ == "__main__":
    main()

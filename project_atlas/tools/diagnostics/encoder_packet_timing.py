#!/usr/bin/env python3
"""Read-only rosbag receipt-timing audit for the four headerless encoder topics.

The bag cannot reveal the MCU's sampling time. Receipt gaps and count jumps
therefore describe published evidence, not proof of lost hardware counts.
"""
import argparse
import glob
import json
import math
import sqlite3
import struct
from pathlib import Path


TOPICS = tuple(f"/yahboom/encoder/m{i}" for i in range(1, 5))
UPDATE_TOPIC = "/atlas/encoder_update"


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)], 4)


def audit_series(rows):
    previous = None
    gaps = []
    jumps_after_gap = []
    repeated = 0
    changing = 0
    for stamp, blob in rows:
        if len(blob) != 8 or blob[:4] != b"\x00\x01\x00\x00":
            raise ValueError("unexpected Int32 CDR payload")
        count = struct.unpack_from("<i", blob, 4)[0]
        if previous is not None:
            dt = (stamp - previous[0]) * 1e-9
            if dt < 0:
                raise ValueError("timestamps are not ordered")
            gaps.append(dt)
            change = abs(count - previous[1])
            repeated += change == 0
            changing += change != 0
            if dt > 0.35 and change:
                jumps_after_gap.append(change)
        previous = stamp, count
    return {
        "messages": len(gaps) + bool(previous),
        "dt_median_s": percentile(gaps, 0.5),
        "dt_p95_s": percentile(gaps, 0.95),
        "dt_p99_s": percentile(gaps, 0.99),
        "dt_max_s": round(max(gaps), 4) if gaps else None,
        "gaps_over_350ms": sum(dt > 0.35 for dt in gaps),
        "repeated_count_intervals": repeated,
        "changing_count_intervals": changing,
        "count_jumps_after_gap": jumps_after_gap[:20],
    }


def audit_updates(rows):
    ages, cycles, receipts = [], [], []
    sources = {}
    stale = sequence_gaps = 0
    previous = None
    for receipt_ns, blob in sorted(rows):
        if len(blob) < 9 or blob[:4] != b"\x00\x01\x00\x00":
            raise ValueError("unexpected String CDR payload")
        size = struct.unpack_from("<I", blob, 4)[0]
        data = json.loads(blob[8:8 + size].rstrip(b"\x00"))
        seq = data.get("sequence")
        if previous is not None and seq is not None:
            sequence_gaps += max(0, seq - previous - 1)
        previous = seq
        source = data.get("source", "unknown")
        sources[source] = sources.get(source, 0) + 1
        stale += data.get("packet_fresh") is False
        for value, target in ((data.get("packet_age_s"), ages),
                              (data.get("integration_dt_s"), cycles)):
            if isinstance(value, (int, float)) and math.isfinite(value):
                target.append(float(value))
        stamp = data.get("stamp_ns")
        if isinstance(stamp, int):
            receipts.append((receipt_ns - stamp) * 1e-9)
    return {"messages": len(rows), "source_counts": sources,
            "sequence_gaps": sequence_gaps, "packet_stale_samples": stale,
            "packet_age_median_s": percentile(ages, 0.5),
            "packet_age_p95_s": percentile(ages, 0.95),
            "packet_age_max_s": round(max(ages), 4) if ages else None,
            "integration_dt_p95_s": percentile(cycles, 0.95),
            "integration_dt_max_s": round(max(cycles), 4) if cycles else None,
            "bag_receipt_minus_publish_p95_s": percentile(receipts, 0.95)}


def audit_bag(path):
    dbs = sorted(glob.glob(str(Path(path) / "*.db3")))
    if not dbs:
        raise FileNotFoundError(f"no .db3 in {path}")
    series = {name: [] for name in TOPICS}
    updates = []
    for dbpath in dbs:
        with sqlite3.connect(f"file:{Path(dbpath).as_posix()}?mode=ro", uri=True) as db:
            names = {name: (ident, typ) for ident, name, typ in db.execute(
                "SELECT id,name,type FROM topics")}
            for name in TOPICS:
                if name not in names:
                    continue
                ident, typ = names[name]
                if typ != "std_msgs/msg/Int32":
                    raise ValueError(f"unexpected {name} type: {typ}")
                series[name].extend(db.execute(
                    "SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp", (ident,)))
            if UPDATE_TOPIC in names:
                ident, typ = names[UPDATE_TOPIC]
                if typ != "std_msgs/msg/String":
                    raise ValueError(f"unexpected {UPDATE_TOPIC} type: {typ}")
                updates.extend(db.execute(
                    "SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp", (ident,)))
    result = {name.rsplit("/", 1)[-1]: audit_series(sorted(rows)) for name, rows in series.items()}
    result["encoder_update"] = audit_updates(updates) if updates else None
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bags", nargs="+", help="rosbag2 SQLite directories")
    args = parser.parse_args()
    print(json.dumps({str(Path(b).name): audit_bag(b) for b in args.bags}, indent=2))


if __name__ == "__main__":
    main()

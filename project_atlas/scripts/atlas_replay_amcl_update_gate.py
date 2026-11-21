#!/usr/bin/env python3
"""Read-only request-policy replay; not an AMCL or motor-watchdog simulation."""
import argparse
import json
import math
from pathlib import Path
import sqlite3

from atlas_amcl_update_gate import AmclUpdateGate


def replay(bag):
    from rclpy.serialization import deserialize_message
    from nav_msgs.msg import Odometry
    files = list(Path(bag).glob('*.db3'))
    if len(files) != 1:
        raise ValueError('exactly one SQLite bag file required')
    connection = sqlite3.connect(files[0].resolve().as_uri() + '?mode=ro', uri=True)
    gate = AmclUpdateGate()
    previous = None
    tick = None
    counts = dict(timer_ticks=0, requests=0, stationary_ticks=0,
                  stationary_requests=0, missing_or_stale_ticks=0)
    last_tick_pose = None
    for receipt_ns, data in connection.execute(
            "SELECT timestamp,data FROM messages WHERE topic_id IN "
            "(SELECT id FROM topics WHERE name='/odom') ORDER BY timestamp"):
        receipt = receipt_ns * 1e-9
        if tick is None:
            tick = receipt + 1
        while previous is not None and tick <= receipt:
            x, y, yaw, stamp = previous
            counts['timer_ticks'] += 1
            fresh = 0 <= tick-stamp <= .5
            counts['missing_or_stale_ticks'] += int(not fresh)
            allowed = gate.allow(x,y,yaw,stamp,tick)
            counts['requests'] += int(allowed)
            # Strict equality selects genuinely unchanged recorded pose, not
            # merely a small-displacement window. First tick is unclassified.
            stopped = last_tick_pose == (x,y,yaw) and fresh
            counts['stationary_ticks'] += int(stopped)
            counts['stationary_requests'] += int(stopped and allowed)
            last_tick_pose = (x,y,yaw)
            tick += 1
        msg = deserialize_message(data, Odometry)
        q = msg.pose.pose.orientation
        yaw = math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
        previous = (msg.pose.pose.position.x, msg.pose.pose.position.y, yaw,
                    msg.header.stamp.sec + msg.header.stamp.nanosec*1e-9)
    connection.close()
    return dict(bag=str(bag), **counts,
                limitation='Request policy only; no AMCL pose accuracy or mux continuity verdict')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bags', nargs='+')
    args = parser.parse_args()
    print(json.dumps([replay(bag) for bag in args.bags], indent=2))

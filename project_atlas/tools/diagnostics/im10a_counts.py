#!/usr/bin/env python3
"""Read-only histogram of IM10A raw gyro-Z LSB counts in saved rosbag2 sqlite files.

1 LSB = 2000 deg/s / 32768 = 0.061 deg/s. A free-running MEMS gyro at rest shows a spread of
small non-zero counts; a large spike at exactly 0 with few +/-1..3 counts indicates on-sensor
static zeroing. Opens each bag read-only. Usage: im10a_counts.py bag_0.db3 [...]
"""
import collections
import math
import sqlite3
import sys

from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Imu

LSB = math.radians(2000.0) / 32768
for db in sys.argv[1:]:
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    topics = {name: i for i, name in con.execute('select id,name from topics')}
    tid = topics.get('/im10a/imu/unvalidated')
    if tid is None:
        continue
    counts = collections.Counter()
    for (data,) in con.execute('select data from messages where topic_id=?', (tid,)):
        counts[round(deserialize_message(data, Imu).angular_velocity.z / LSB)] += 1
    small = {k: counts[k] for k in range(-12, 13)}
    print(db, 'n=%d' % sum(counts.values()), 'counts -12..12:', small,
          '|count|>12:', sum(v for k, v in counts.items() if abs(k) > 12))

"""Extract original compressed camera frames near recorded turn commands.

Read-only bag access; creates a new output directory, never commands hardware.
"""
import json
import pathlib
import sys
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def main(bag, output):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag, storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    frames, updates = [], []
    while reader.has_next():
        topic, data, ns = reader.read_next()
        if topic not in ('/camera/image_raw/compressed', '/atlas/encoder_update'):
            continue
        msg = deserialize_message(data, types[topic])
        if topic == '/atlas/encoder_update':
            updates.append(json.loads(msg.data))
        else:
            frames.append((msg.header.stamp.sec+msg.header.stamp.nanosec/1e9,
                           ns/1e9, msg.format, bytes(msg.data)))
    if not updates or not frames:
        raise SystemExit('Required recording missing')
    root = pathlib.Path(output)
    root.mkdir(parents=True, exist_ok=False)
    origin = updates[0]['stamp_ns']/1e9
    result = []
    for offset in (26.5, 27.5, 28.5, 29.5, 30.5, 31.5, 32.5):
        frame = min(frames, key=lambda f: abs(f[0]-origin-offset))
        update = min(updates, key=lambda u: abs(u['stamp_ns']/1e9-frame[0]))
        suffix = '.jpg' if frame[3].startswith(b'\xff\xd8') else '.png' if frame[3].startswith(b'\x89PNG') else '.bin'
        path = root / ('frame_' + str(offset) + suffix)
        path.write_bytes(frame[3])
        result.append(dict(file=path.name, requested_offset_s=offset,
            frame_offset_s=frame[0]-origin, receipt_age_s=frame[1]-frame[0],
            steering_command_deg=update['steering_command_deg'],
            format=frame[2]))
    (root/'frames.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main(*sys.argv[1:])

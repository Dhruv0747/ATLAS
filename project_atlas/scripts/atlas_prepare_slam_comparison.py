"""Create an offline replay bag containing scans and odometry TF only.

Never opens a ROS node. Removes recorded map->odom so replay SLAM owns it.
"""
import sys
import rosbag2_py
from rclpy.serialization import deserialize_message, serialize_message
from tf2_msgs.msg import TFMessage


def main():
    source, destination = sys.argv[1:]
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=source, storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('', ''))
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=destination, storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('', ''))
    allowed = {'/scan', '/tf', '/tf_static'}
    for topic in reader.get_all_topics_and_types():
        if topic.name in allowed:
            writer.create_topic(topic)
    counts = {}
    while reader.has_next():
        topic, data, stamp = reader.read_next()
        if topic not in allowed:
            continue
        if topic in {'/tf', '/tf_static'}:
            msg = deserialize_message(data, TFMessage)
            msg.transforms = [t for t in msg.transforms
                              if t.header.frame_id.strip('/') != 'map'
                              and t.child_frame_id.strip('/') != 'map']
            if not msg.transforms:
                continue
            data = serialize_message(msg)
        writer.write(topic, data, stamp)
        counts[topic] = counts.get(topic, 0) + 1
    print(counts)


if __name__ == '__main__':
    main()

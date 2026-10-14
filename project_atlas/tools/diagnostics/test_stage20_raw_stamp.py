import struct
import unittest
from stage20_capture import serialized_source_stamp

class StampTests(unittest.TestCase):
    def test_header_both_endiannesses(self):
        for endian,flag in (('<',1),('>',0)):
            raw=bytes((0,flag,0,0))+struct.pack(endian+'iI',23,1234)
            self.assertEqual(serialized_source_stamp(raw,'nav_msgs/msg/Odometry'),23000001234)
    def test_tf_first_transform_not_whole_array(self):
        raw=b'\x00\x01\x00\x00'+struct.pack('<IiI',2,10,34)
        self.assertEqual(serialized_source_stamp(raw,'tf2_msgs/msg/TFMessage'),10000000034)
    def test_no_header_not_invented(self):
        self.assertIsNone(serialized_source_stamp(bytes(32),'std_msgs/msg/String'))
        self.assertIsNone(serialized_source_stamp(b'\x00\x01\x00\x00'+struct.pack('<I',0),'tf2_msgs/msg/TFMessage'))
    def test_invalid_stamp_rejected(self):
        with self.assertRaises(ValueError):
            serialized_source_stamp(b'\x00\x01\x00\x00'+struct.pack('<iI',1,1000000000),'sensor_msgs/msg/Imu')
if __name__=='__main__':unittest.main()

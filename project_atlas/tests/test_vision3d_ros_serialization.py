"""Native Humble message serialization smoke tests. No node, DDS, USB or robot."""
import sys
import unittest
from pathlib import Path
import struct
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_vision3d_core as C
try:
    from rclpy.serialization import serialize_message,deserialize_message
    from sensor_msgs.msg import Image,PointCloud2,PointField
    HAVE=True
except ImportError:HAVE=False


@unittest.skipUnless(HAVE,'native ROS2 messages unavailable')
class NativeSerialization(unittest.TestCase):
    def test_native_image_roundtrip(self):
        m=Image();m.width=2;m.height=1;m.step=4;m.encoding='16UC1';m.data=struct.pack('<HH',1250,0)
        m.header.frame_id='astra_depth_optical_frame';m.header.stamp.sec=100
        n=deserialize_message(serialize_message(m),Image)
        self.assertEqual(C.depth_at(n,0,0),1.25);self.assertIsNone(C.depth_at(n,1,0));self.assertTrue(C.preview(n,'depth')[0])
    def test_native_cloud_roundtrip(self):
        m=PointCloud2();m.width=1;m.height=1;m.point_step=12;m.row_step=12;m.data=struct.pack('<fff',.1,.2,1.)
        m.fields=[PointField(name=k,offset=i*4,datatype=7,count=1) for i,k in enumerate('xyz')]
        m.header.frame_id='astra_depth_optical_frame';m.header.stamp.sec=100
        n=deserialize_message(serialize_message(m),PointCloud2)
        c=C.cloud_points(n);self.assertEqual(c['source_stamp'],100);self.assertAlmostEqual(c['points'][0][0],.1)


if __name__=='__main__':unittest.main()

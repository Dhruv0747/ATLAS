import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
from astra_bag_adapter import extract, inventory, TOPICS
from astra_replay import command, validate_recorded_bundles
from test_rtabmap_offline import fixture


class AdapterTests(unittest.TestCase):
    def test_missing_real_stream_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            bag=Path(d)/'empty.db3'
            c=sqlite3.connect(bag);c.executescript('create table topics(id integer,name text,type text);create table messages(id integer,topic_id integer,timestamp integer,data blob);');c.close()
            with self.assertRaisesRegex(ValueError,'missing'):extract(bag,Path(d)/'out')
            self.assertFalse((Path(d)/'out').exists())

    def test_native_cdr_unchanged(self):
        from sensor_msgs.msg import Image,CameraInfo
        from rclpy.serialization import serialize_message
        with tempfile.TemporaryDirectory() as d:
            bag=Path(d)/'fixture.db3';c=sqlite3.connect(bag)
            c.executescript('create table topics(id integer,name text,type text);create table messages(id integer,topic_id integer,timestamp integer,data blob);')
            expected=[]
            for i,(topic,key) in enumerate(TOPICS.items(),1):
                msg=CameraInfo() if 'info' in key else Image()
                msg.header.stamp.sec=123;msg.header.stamp.nanosec=987654321
                msg.header.frame_id='astra_optical_frame';msg.width=2;msg.height=2
                if 'info' not in key:
                    msg.encoding='16UC1' if key=='depth' else 'rgb8'
                    msg.step=4 if key=='depth' else 6;msg.data=bytes(msg.step*2)
                else:msg.k=[2.,0.,1.,0.,2.,1.,0.,0.,1.]
                raw=serialize_message(msg);expected.append(raw)
                typ='sensor_msgs/msg/CameraInfo' if 'info' in key else 'sensor_msgs/msg/Image'
                c.execute('insert into topics values(?,?,?)',(i,topic,typ))
                c.execute('insert into messages values(?,?,?,?)',(i,i,124000000000,raw))
            c.commit();c.close();extract(bag,Path(d)/'out')
            manifest=fixture()
            for k in ('rgb','depth'):manifest[k].update(width=2,height=2,frame_id='astra_optical_frame')
            self.assertEqual(validate_recorded_bundles(bag,manifest),1)
            c=sqlite3.connect(Path(d)/'out/capture.sqlite')
            for (stamp,sha,raw),original in zip(c.execute('select stamp_ns,sha256,cdr from messages order by id'),expected):
                self.assertEqual(stamp,123987654321);self.assertEqual(raw,original)
                self.assertEqual(sha,hashlib.sha256(original).hexdigest())
            c.close()

    def test_replay_allowlist(self):
        m=fixture();m.update(odom_topic='/odometry/filtered',scan_topic='/scan')
        rows=[(t,'sensor_msgs/msg/CameraInfo' if 'info' in k else 'sensor_msgs/msg/Image',1) for t,k in TOPICS.items()]
        rows += [('/odometry/filtered','nav_msgs/msg/Odometry',1),('/scan','sensor_msgs/msg/LaserScan',1),('/tf_static','tf2_msgs/msg/TFMessage',1),('/cmd_vel','geometry_msgs/msg/Twist',1)]
        with patch('astra_replay.inventory',return_value=rows):
            cmd=command('fixture.db3',m)
            self.assertNotIn('/cmd_vel',cmd)
            self.assertIn('/astra/depth/image_raw:=/atlas_offline/input/depth',cmd)


if __name__=='__main__':unittest.main()

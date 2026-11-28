"""Isolated WSL ROS domain211/loopback only. No production topic participation."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import unittest


@unittest.skipUnless('microsoft' in platform.release().lower(),'PC WSL only')
class RosObserverTests(unittest.TestCase):
    def test_fresh_without_http_and_publisher_loss(self):
        self.assertEqual(os.environ.get('ROS_DOMAIN_ID'),'211')
        self.assertEqual(os.environ.get('ROS_LOCALHOST_ONLY'),'1')
        import rclpy
        from std_msgs.msg import String
        from geometry_msgs.msg import Twist
        rclpy.init();node=rclpy.create_node('offline_restart_fixture')
        pubs=[node.create_publisher(String,'/atlas/control_policy',10),node.create_publisher(Twist,'/cmd_vel',10),node.create_publisher(String,'/atlas/encoder_health',10)]
        values=[String(data=json.dumps({'stop_latched':True,'manual_only':True,'commission_armed':False,'source':'STOPPED'})),Twist(),String(data=json.dumps({'packet_fresh':True,'link_state':'LIVE','packet_age_s':0,'encoder_interval_delta_m':[0,0,0,0]}))]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'observer.json';child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('restart_safety_observer.py')),'--output',str(p),'--nonce','test','--duration','15'])
            try:
                deadline=time.monotonic()+8;ready=False
                while time.monotonic()<deadline:
                    for pub,val in zip(pubs,values):pub.publish(val)
                    rclpy.spin_once(node,timeout_sec=.05)
                    if p.exists() and json.loads(p.read_text()).get('safe') is True:ready=True;break
                self.assertTrue(ready,'observer did not receive isolated ROS messages')
                # No HTTP server was ever started. Stop messages, retain ROS context.
                time.sleep(1.4)
                self.assertFalse(json.loads(p.read_text())['safe'])
                for _ in range(10):
                    for pub,val in zip(pubs,values):pub.publish(val)
                    rclpy.spin_once(node,timeout_sec=.05)
                self.assertFalse(json.loads(p.read_text())['safe'],'failure must stay latched')
            finally:
                child.terminate();child.wait(timeout=3);node.destroy_node();rclpy.shutdown()
                self.assertEqual(child.returncode,0)

if __name__=='__main__':unittest.main()

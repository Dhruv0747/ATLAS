"""PC-only synthetic IR DDS test. No camera, services, production topics or images saved."""
import os
os.environ['ROS_LOCALHOST_ONLY']='1'
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import atlas_vision3d_web as W
import rclpy
from rclpy.context import Context
from sensor_msgs.msg import Image,CameraInfo

def main():
    ctx=Context();rclpy.init(context=ctx,domain_id=77)
    node=rclpy.create_node('synthetic_ir_fixture',context=ctx)
    svc=W.VisionService({'topics':{'ir':'/astra/ir/image_raw','ir_info':'/astra/ir/camera_info'}})
    transport=W.RosTransport(domain_id=77)
    try:
        transport.start(svc.manifest['topics'],svc.ingest)
        # Exercise discovery after receiver startup, as on ATLAS.
        time.sleep(1)
        pub=node.create_publisher(Image,'/astra/ir/image_raw',10)
        info=node.create_publisher(CameraInfo,'/astra/ir/camera_info',10)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            m=Image();m.header.stamp=node.get_clock().now().to_msg();m.header.frame_id='synthetic_ir'
            m.width=320;m.height=240;m.encoding='mono8';m.step=320;m.data=bytes(range(256))*300
            pub.publish(m)
            c=CameraInfo();c.header=m.header;c.width=320;c.height=240;info.publish(c)
            time.sleep(1/30)
        st=svc.status();body,headers=svc.raw('ir')
        assert st['streams']['ir']['received']>30 and body==bytes(range(256))*300
        assert 'ir_info' in st['camera_info']
        print(json.dumps({'synthetic_only':True,'domain':77,'rmw':rclpy.get_rmw_implementation_identifier(),
            'ir':st['streams']['ir'],'camera_info':st['camera_info'],'raw_bytes':len(body),'headers':headers}))
    finally:
        transport.stop();node.destroy_node();ctx.shutdown()

if __name__=='__main__':main()

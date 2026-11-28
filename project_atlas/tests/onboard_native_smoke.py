"""Explicit PC-only native smoke, isolated loopback domains183/184/185."""
import json,os,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/vision3d'))
from rtabmap_offline import isolated_env
env=isolated_env();os.environ.clear();os.environ.update(env)
import rclpy
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image,CameraInfo,LaserScan
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import StaticTransformBroadcaster,TransformBroadcaster

def main():
    with tempfile.TemporaryDirectory() as td:
        d=Path(td);session=d/'session';session.mkdir()
        cal=dict(device_serial='synthetic',source='measured_target',independently_validated=True,
                 validation_evidence='SYNTHETIC ONLY',width=2,height=2,frame_id='astra_optical_frame',
                 k=[2.,0.,1.,0.,2.,1.,0.,0.,1.],d=[0.]*5,distortion_model='plumb_bob')
        (d/'cal.json').write_text(json.dumps(cal))
        c=json.loads((ROOT/'config/onboard_mapping.json').read_text())
        c.update(enabled=True,serial='synthetic',camera_domain=183,production_domain=184,mapping_domain=185,
                 registered_depth_topic='/astra/depth/image_raw',rgb_calibration=str(d/'cal.json'),depth_calibration=str(d/'cal.json'),
                 registration_evidence='synthetic',tf_evidence='synthetic',odom_topic='/odom',duration_s=8,
                 tf_edges=[['odom','base_link'],['base_link','astra_optical_frame']])
        (d/'config.json').write_text(json.dumps(c));contexts=[];nodes=[]
        for domain in (183,184,185):
            ctx=Context();rclpy.init(context=ctx,domain_id=domain);contexts.append(ctx)
            nodes.append(rclpy.create_node('smoke_'+str(domain),context=ctx))
        cam,prod,sink=nodes
        executor=SingleThreadedExecutor(context=contexts[2]);executor.add_node(sink)
        pubs={k:cam.create_publisher(t,c[topic],qos_profile_sensor_data) for k,t,topic in
              [('rgb',Image,'rgb_topic'),('depth',Image,'registered_depth_topic'),('rgb_info',CameraInfo,'rgb_info_topic'),('depth_info',CameraInfo,'depth_info_topic')]}
        op=prod.create_publisher(Odometry,'/odom',qos_profile_sensor_data);sp=prod.create_publisher(LaserScan,'/scan',qos_profile_sensor_data)
        static=StaticTransformBroadcaster(prod);dynamic=TransformBroadcaster(prod)
        st=TransformStamped();st.header.frame_id='base_link';st.child_frame_id='astra_optical_frame';st.transform.rotation.w=1.;static.sendTransform(st)
        received=[];sink.create_subscription(Image,'/atlas_mapping/input/depth',lambda m:received.append((m.header.stamp.sec,m.header.stamp.nanosec,bytes(m.data))),qos_profile_sensor_data)
        log=(d/'adapter.log').open('w');child=subprocess.Popen([sys.executable,str(ROOT/'tools/vision3d/onboard_adapter.py'),str(d/'config.json'),str(session)],env=env,stdout=log,stderr=log)
        try:
            start=time.monotonic()
            while time.monotonic()-start<9 and child.poll() is None:
                stamp=prod.get_clock().now().to_msg()
                ot=TransformStamped();ot.header.stamp=stamp;ot.header.frame_id='odom';ot.child_frame_id='base_link';ot.transform.rotation.w=1.;dynamic.sendTransform(ot)
                od=Odometry();od.header=ot.header;od.child_frame_id='base_link';od.pose.pose.orientation.w=1.
                for i in (0,7,14,21,28,35):od.pose.covariance[i]=.001
                op.publish(od)
                scan=LaserScan();scan.header=ot.header;scan.header.frame_id='base_link';scan.ranges=[1.]*5;sp.publish(scan)
                for k,pub in pubs.items():
                    m=CameraInfo() if 'info' in k else Image();m.header.stamp=stamp;m.header.frame_id='astra_optical_frame';m.width=m.height=2
                    if 'info' in k:m.k=cal['k'];m.d=cal['d'];m.distortion_model='plumb_bob'
                    else:m.encoding='rgb8' if k=='rgb' else '16UC1';m.step=6 if k=='rgb' else 4;m.data=bytes([232,3]*4) if k=='depth' else bytes(12)
                    pub.publish(m)
                executor.spin_once(timeout_sec=.05);time.sleep(.05)
            child.wait(timeout=4);log.close()
            print((d/'adapter.log').read_text()[-1200:])
            assert child.returncode==0,child.returncode
            state=json.loads((session/'adapter.json').read_text())
            assert received and state['bundles']>0 and state['error'] is None,state
            assert all(raw==bytes([232,3]*4) for sec,ns,raw in received)
            print(json.dumps(dict(native_adapter='PASS',forwarded_depth=len(received),state=state)))
        finally:
            if child.poll() is None:child.terminate();child.wait(timeout=3)
            executor.shutdown()
            for n in nodes:n.destroy_node()
            for ctx in contexts:rclpy.shutdown(context=ctx)

if __name__=='__main__':main()

"""Native message serialization, fake controller/cache; no camera or ROS nodes."""
import json
from pathlib import Path
import sqlite3
import sys
import threading
from types import SimpleNamespace as N
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import rgbd_recording as R
from test_calibration_capture import observation
from sensor_msgs.msg import Image,CameraInfo,LaserScan
from nav_msgs.msg import Odometry
from tf2_msgs.msg import TFMessage
from geometry_msgs.msg import TransformStamped
from rclpy.serialization import serialize_message


def docs():
    return {k:dict(device_serial='test',source='measured_target',independently_validated=True,
        validation_evidence='SYNTHETIC TEST ONLY',width=2,height=2,frame_id='astra_optical_frame',
        k=[2.,0.,1.,0.,2.,1.,0.,0.,1.],d=[0.]*5,distortion_model='plumb_bob') for k in ('rgb','depth')}


def messages(stamp):
    rows={}
    for k in R.TYPES:
        m=CameraInfo() if 'info' in k else Image();m.width=m.height=2
        m.header.frame_id='astra_optical_frame';m.header.stamp.sec=stamp//10**9;m.header.stamp.nanosec=stamp%10**9
        if 'info' in k:m.k=docs()['rgb']['k'];m.d=[0.]*5;m.distortion_model='plumb_bob'
        else:m.encoding='rgb8' if k=='rgb' else '16UC1';m.step=6 if k=='rgb' else 4;m.data=bytes(m.step*2)
        rows[k]=m
    return rows


def context(stamp):
    def tf(parent,child):
        t=TransformStamped();t.header.frame_id=parent;t.child_frame_id=child;t.transform.rotation.w=1.
        t.header.stamp.sec=stamp//10**9;t.header.stamp.nanosec=stamp%10**9;return t
    o=Odometry();o.header.frame_id='odom';o.child_frame_id='base_link';o.header.stamp=tf('a','b').header.stamp
    s=LaserScan();s.header.frame_id='base_link';s.header.stamp=o.header.stamp
    return dict(tf=TFMessage(transforms=[tf('odom','base_link')]),
                tf_static=TFMessage(transforms=[tf('base_link','astra_optical_frame')]),odom=o,scan=s)


@pytest.fixture
def rig(monkeypatch):
    clock=[0.];ctrl=N(lock=threading.RLock(),child=None);vision=N(lock=threading.RLock(),transport=None,messages={})
    def start(mode,**kwargs):
        assert mode=='concurrent';ctrl.child=N(pid=99999999,poll=lambda:None)
    def stop():ctrl.child.poll=lambda:0
    ctrl.start=Mock(side_effect=start);ctrl.stop=Mock(side_effect=stop);ctrl.touch=Mock();ctrl.release_capture=Mock()
    ctrl.status=lambda:dict(worker_pid=ctrl.child.pid,driver_pid=99999998,driver_stopped=True,cloud_stopped=True)
    def touch():vision.messages=messages(int((100+clock[0])*10**9))
    vision.touch=touch;vision.stop=Mock()
    def sleep(t):clock[0]+=t
    session=R.Recording(ctrl,vision,lambda:observation(clock[0]),lambda:context(int((100+clock[0])*10**9)),
                        clock=lambda:clock[0],wall_ns=lambda:int((100+clock[0])*10**9),sleep=sleep)
    monkeypatch.setattr(R.os,'killpg',Mock(side_effect=ProcessLookupError))
    return session,ctrl,vision,clock


def test_complete_and_native_bag_compatibility(rig,tmp_path):
    session,ctrl,vision,clock=rig
    result=session.run(tmp_path/'run',docs(),'test',approved=True)
    assert result['status']=='COMPLETE' and result['shutdown_verified']
    ctrl.start.assert_called_once();ctrl.stop.assert_called_once();vision.stop.assert_called_once()
    assert 60<=clock[0]<60.2
    bag=R.export_bag(tmp_path/'run')
    import rosbag2_py
    reader=rosbag2_py.SequentialReader();reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
    assert len(reader.get_all_topics_and_types())==8
    name,cdr,stamp=reader.read_next();assert name in ('/tf','/tf_static','/odom','/scan')
    with sqlite3.connect(tmp_path/'run/capture.sqlite') as db:
        original=db.execute('select cdr from messages order by id limit 1').fetchone()[0]
    assert bytes(cdr)==original
    from astra_replay import validate_recorded_bundles
    assert validate_recorded_bundles(bag,dict(docs(),units_to_m=.001))>0
    with sqlite3.connect(bag) as db:
        assert 'durability: 1' in db.execute("select offered_qos_profiles from topics where name='/tf_static'").fetchone()[0]
    with pytest.raises(RuntimeError):session.run(tmp_path/'again',docs(),'test',approved=True)


@pytest.mark.parametrize('mode',['noapproval','badcal','missingtf','missingframes','unsafe','write','stopfailure'])
def test_abort_preserves_evidence(rig,tmp_path,monkeypatch,mode):
    session,ctrl,vision,clock=rig;cal=docs()
    if mode=='badcal':cal['rgb']['k'][0]=float('nan')
    if mode=='missingtf':session.context=lambda:{}
    if mode=='missingframes':vision.touch=lambda:None
    if mode=='unsafe':
        session.observer=lambda:dict(observation(clock[0]),cpu=75 if clock[0]>.2 else 60)
    if mode=='write':monkeypatch.setattr(R.Evidence,'write',Mock(side_effect=OSError('disk full')))
    if mode=='stopfailure':ctrl.stop.side_effect=RuntimeError('stop failed')
    result=session.run(tmp_path/'run',cal,'test',approved=mode!='noapproval')
    assert result['status']=='ABORTED'
    assert (tmp_path/'run/result.json').exists() and result['database_sha256']
    if mode in ('badcal','missingtf','noapproval'):ctrl.start.assert_not_called()
    else:ctrl.start.assert_called_once();ctrl.stop.assert_called_once()
    if mode=='stopfailure':assert result['shutdown_verified'] is False
    with pytest.raises(ValueError):R.export_bag(tmp_path/'run')


def test_context_rejects_missing_transform():
    c=context(100000000000);c['tf_static'].transforms.clear()
    with pytest.raises(ValueError):R.validate_context(c,100000000000,'astra_optical_frame',100000000000)


def test_existing_owner_not_stopped(rig,tmp_path):
    session,ctrl,vision,clock=rig
    ctrl.child=N(pid=123,poll=lambda:None)
    result=session.run(tmp_path/'run',docs(),'test',approved=True)
    assert result['status']=='ABORTED'
    ctrl.start.assert_not_called();ctrl.stop.assert_not_called();vision.stop.assert_not_called()


def test_startup_time_included_and_no_start_after_deadline(rig,tmp_path):
    session,ctrl,vision,clock=rig
    def slow():clock[0]=61;return observation(61)
    session.observer=slow
    result=session.run(tmp_path/'run',docs(),'test',approved=True)
    assert result['status']=='ABORTED'
    ctrl.start.assert_not_called()


def test_missing_driver_shutdown_evidence_is_not_pass(rig,tmp_path):
    session,ctrl,vision,clock=rig;ctrl.status=lambda:{'state':'OFF'}
    result=session.run(tmp_path/'run',docs(),'test',approved=True)
    assert result['status']=='ABORTED' and result['shutdown_verified'] is False


def test_driver_group_survives_worker_is_rejected(rig,tmp_path,monkeypatch):
    session,ctrl,vision,clock=rig
    def alive(pid,sig):
        if pid==99999998:return
        raise ProcessLookupError
    monkeypatch.setattr(R.os,'killpg',alive)
    result=session.run(tmp_path/'run',docs(),'test',approved=True)
    assert result['status']=='ABORTED' and result['shutdown_verified'] is False


def test_staggered_cache_and_different_dimensions(rig,tmp_path):
    session,ctrl,vision,clock=rig;cal=docs();cal['rgb']['width']=3
    pending={};n=[0]
    def touch():
        k=list(R.TYPES)[n[0]%4];n[0]+=1
        # One complete batch every0.4s; cache changes one stream per tick.
        stamp=int((100+int((n[0]-1)/4)*.4)*10**9)
        msg=messages(stamp)[k]
        if k.startswith('rgb'):
            msg.width=3
            if k=='rgb':msg.step=9;msg.data=bytes(18)
        pending[k]=msg;vision.messages=dict(pending)
    vision.touch=touch
    # Valid context includes both bounding transforms for earlier image stamps.
    def ctx():
        now=int((100+clock[0])*10**9);c=context(now)
        past=context(max(100000000000,now-500000000))['tf'].transforms[0]
        c['tf'].transforms.insert(0,past);return c
    session.context=ctx
    result=session.run(tmp_path/'run',cal,'test',approved=True)
    assert result['status']=='COMPLETE',result


def test_interruption_and_transport_cleanup_failure(rig,tmp_path):
    session,ctrl,vision,clock=rig
    def interrupted(t):raise KeyboardInterrupt('cancelled')
    session.sleep=interrupted;vision.stop.side_effect=RuntimeError('transport stop failed')
    result=session.run(tmp_path/'run',docs(),'test',approved=True)
    assert result['status']=='ABORTED' and 'transport_cleanup_error' in result
    ctrl.stop.assert_called_once()


def test_conversion_tamper_rejected(rig,tmp_path):
    session,ctrl,vision,clock=rig
    result=session.run(tmp_path/'run',docs(),'test',approved=True)
    assert result['status']=='COMPLETE'
    with (tmp_path/'run/capture.sqlite').open('ab') as f:f.write(b'tampered')
    with pytest.raises(ValueError,match='checksum'):R.export_bag(tmp_path/'run')
    assert not (tmp_path/'run/replay.db3').exists()


def test_real_provider_admission_does_not_expire_first_heartbeat(rig,tmp_path):
    session,ctrl,vision,clock=rig
    def sample(cpu,window):
        clock[0]+=.02  # real resource-read overhead after initial one-second window
        return dict(observation(clock[0]),cpu=cpu,cpu_window_s=window)
    session.observer=R.ExistingSafety(sample,clock=lambda:clock[0],sleep=lambda t:clock.__setitem__(0,clock[0]+t),
        counters=lambda:(int(clock[0]*1000),int(clock[0]*400)))
    def interrupted(t):raise KeyboardInterrupt('test completed first bundle')
    session.sleep=interrupted
    result=session.run(tmp_path/'run',docs(),'test',approved=True)
    assert result['bundles']==1 and result['reason']=='test completed first bundle'
    assert result['shutdown_verified'] and clock[0]>1
    assert ctrl.start.call_args.kwargs['deadline']==60


def test_original_tf_batches_preserved(rig,tmp_path,monkeypatch):
    session,ctrl,vision,clock=rig
    original=context(100000000000)
    serialized={};real_metadata=R.metadata
    def capture(kind,msg,serializer,receipt):
        row=real_metadata(kind,msg,serializer,receipt);serialized[kind]=row['cdr'];return row
    monkeypatch.setattr(R,'metadata',capture)
    session.context=lambda:dict(original,tf=[original['tf']],tf_static=[original['tf_static']])
    session.sleep=lambda t:(_ for _ in ()).throw(KeyboardInterrupt('bounded test'))
    session.run(tmp_path/'run',docs(),'test',approved=True)
    with sqlite3.connect(tmp_path/'run/capture.sqlite') as db:
        for key in ('tf','tf_static'):
            from rclpy.serialization import deserialize_message
            cdr=db.execute('select cdr from messages where stream=?',(key,)).fetchone()[0]
            assert cdr==serialized[key]
            assert deserialize_message(cdr,TFMessage)==original[key]

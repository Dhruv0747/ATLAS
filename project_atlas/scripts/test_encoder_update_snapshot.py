"""Exercise the actual odometry method without importing ROS or hardware."""
import ast
import json
import math
from pathlib import Path
from types import SimpleNamespace as N
import unittest
from unittest.mock import Mock
from atlas_encoder_selection import EncoderDeltaEstimator, WheelStillnessDetector, four_wheel_path_scales


def odometry():
    return N(header=N(), child_frame_id='',
             pose=N(pose=N(position=N(),orientation=N()),covariance=[0.]*36),
             twist=N(twist=N(linear=N(),angular=N()),covariance=[0.]*36))


tree=ast.parse(Path(__file__).with_name('yahboom_base.py').read_text(encoding='utf-8'))
method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_publish_yahboom_odom')
scope=dict(math=math,json=json,Odometry=odometry,String=lambda **kw:N(**kw),
           FRONT_STEER_CENTER=90,REAR_STEER_CENTER=90,four_wheel_path_scales=four_wheel_path_scales)
exec(compile(ast.Module(body=[method],type_ignores=[]),'odometry_method','exec'),scope)


class SnapshotTest(unittest.TestCase):
    def make(self):
        estimator=EncoderDeltaEstimator()
        estimator.update([0]*4,range(4))
        s=N(_last_odom_t=.9,_excluded_encoders=set(),_encoder_fault_since={},
            _encoder_packet_fresh=True,_wheel_stillness=WheelStillnessDetector(1.0),
            _applied_motor_outputs=(0.,0.,0.,0.),_front_applied_angle=90,_rear_applied_angle=90,
            _wheelbase_m=.367,_drive_pid_config=N(geometry=N(track_width_m=.26)),
            _encoder_positions=['rear_left','rear_right','front_left','front_right'],
            _encoder_delta_estimator=estimator,_wheel_distance_m=[.02]*4,
            _pub_odom_source=Mock(),_x=0.,_y=0.,_yaw=0.,_save_odom_state=Mock(),
            get_clock=lambda:N(now=lambda:N(to_msg=lambda:N(sec=10,nanosec=5))),
            _pub_odom=Mock(),_pub_encoder_update=Mock(),_encoder_update_sequence=0,
            _last_enc=[100]*4,_enc_origin=[0]*4,_encoder_packet_stamp=.99,
            _encoder_calibration=N(counts_per_revolution=[2000]*4,encoder_signs=[1]*4,wheel_circumference_m=.4),
            get_logger=Mock())
        s._pub_encoder_update.get_subscription_count.return_value=1
        return s

    def test_coherent_snapshot_and_unchanged_motion(self):
        s=self.make();scope['_publish_yahboom_odom'](s,0,0,0,1.)
        report=json.loads(s._pub_encoder_update.publish.call_args.args[0].data)
        self.assertEqual(report['stamp_ns'],10000000005)
        self.assertEqual(report['accepted_channels'],[1,2,3,4])
        self.assertEqual(report['raw_counts'],[100]*4)
        self.assertAlmostEqual(report['accepted_delta_m'],.02)
        self.assertAlmostEqual(s._x,.02)
        self.assertAlmostEqual(s._yaw,0)

    def test_no_subscriber_no_serialization(self):
        s=self.make();s._pub_encoder_update.get_subscription_count.return_value=0
        scope['_publish_yahboom_odom'](s,0,0,0,1.)
        s._pub_encoder_update.publish.assert_not_called()
        self.assertAlmostEqual(s._x,.02)

    def test_diagnostic_failure_does_not_break_odom(self):
        s=self.make();s._pub_encoder_update.publish.side_effect=RuntimeError('test')
        scope['_publish_yahboom_odom'](s,0,0,0,1.)
        s._pub_odom.publish.assert_called_once()
        self.assertAlmostEqual(s._x,.02)

    def test_disagreement_stays_rejected(self):
        s=self.make();s._wheel_distance_m=[.02,.02,-.02,-.02]
        scope['_publish_yahboom_odom'](s,0,0,0,1.)
        report=json.loads(s._pub_encoder_update.publish.call_args.args[0].data)
        self.assertEqual(report['accepted_channels'],[])
        self.assertEqual(report['accepted_delta_m'],0)
        self.assertEqual(s._x,0)

    def _cov(self,s):
        msg=s._pub_odom.publish.call_args.args[0]
        return msg.pose.covariance[0],msg.twist.covariance[0]

    def test_parked_without_consensus_trusts_zero_velocity_only_after_hold(self):
        # Two channels faulted -> no 3-of-4 consensus. Pose stays inflated; the zero-velocity
        # twist keeps normal covariance only after 1 s of identical counts confirmed by newer
        # packets with motors off. Source label unchanged.
        s=self.make();s._encoder_fault_since={0:0.,1:0.}
        for k in range(8):
            s._encoder_packet_stamp=1.0+0.1*k
            scope['_publish_yahboom_odom'](s,0,0,0,1.0+0.1*k)
        self.assertEqual(self._cov(s),(0.05*1000,0.10*1000))
        for k in range(8,14):
            s._encoder_packet_stamp=1.0+0.1*k
            scope['_publish_yahboom_odom'](s,0,0,0,1.0+0.1*k)
        self.assertEqual(self._cov(s),(0.05*1000,0.10))
        self.assertEqual(s._pub_odom_source.publish.call_args.args[0].data,'feedback_unavailable')
        self.assertEqual(s._x,0)

    def test_driven_motors_or_stale_packets_stay_inflated(self):
        s=self.make();s._encoder_fault_since={0:0.,1:0.};s._applied_motor_outputs=(0.,20.,0.,0.)
        for k in range(20):
            s._encoder_packet_stamp=1.0+0.1*k
            scope['_publish_yahboom_odom'](s,0,0,0,1.0+0.1*k)
        self.assertEqual(self._cov(s)[1],0.10*1000)
        s=self.make();s._encoder_fault_since={0:0.,1:0.};s._encoder_packet_fresh=False
        for k in range(20):
            scope['_publish_yahboom_odom'](s,0,0,0,1.0+0.1*k)
        self.assertEqual(self._cov(s)[1],0.10*1000)


if __name__=='__main__':unittest.main()

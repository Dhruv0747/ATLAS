import math
from types import SimpleNamespace as N
import unittest
from stage19_summarize import trajectory_fidelity,summary


def msg(t,x,y,h):
    return N(header=N(stamp=N(sec=int(t),nanosec=int((t-int(t))*1e9))),
        pose=N(pose=N(position=N(x=x,y=y),orientation=N(x=0,y=0,z=math.sin(h/2),w=math.cos(h/2))),
               covariance=[0.0]*36))


class Stage19SummaryTests(unittest.TestCase):
    def test_rigid_frame_change_is_not_false_motion_divergence(self):
        a={'/odom':[(0,msg(0,10,20,math.pi/2)),(1,msg(1,10,21,math.pi/2))]}
        b={'/odom':[(0,msg(0,0,0,0)),(1,msg(1,1,0,0))]}
        r=trajectory_fidelity(a,b)
        self.assertAlmostEqual(r['max_gauge_aligned_xy_difference_m'],0)
        self.assertAlmostEqual(r['max_relative_heading_difference_deg'],0)

    def test_real_relative_disagreement_survives_initial_alignment(self):
        a={'/odom':[(0,msg(0,0,0,0)),(1,msg(1,1,0,0))]}
        b={'/odom':[(0,msg(0,10,20,0)),(1,msg(1,10,22,.2))]}
        r=trajectory_fidelity(a,b)
        self.assertGreater(r['max_gauge_aligned_xy_difference_m'],2)
        self.assertAlmostEqual(r['final_relative_heading_difference_deg'],math.degrees(.2))

    def test_no_overlap_is_unknown_not_zero_error(self):
        a={'/odom':[(0,msg(0,0,0,0)),(1,msg(1,1,0,0))]}
        b={'/odom':[(2,msg(2,0,0,0)),(3,msg(3,1,0,0))]}
        self.assertEqual(trajectory_fidelity(a,b)['status'],'UNKNOWN')

    def test_zero_jumps_does_not_label_localization_fixed(self):
        r=summary({},0)
        self.assertEqual(r['max_jump_m'],0)
        self.assertIsNone(r['post_stop_xy_span_m'])
        self.assertTrue(r['truth'].startswith('UNKNOWN'))


if __name__=='__main__':unittest.main()

"""Exercises the existing matcher cancellation hook, without ROS or motors."""
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_localization_verify_core as core


class SearchBudgetTests(unittest.TestCase):
    def test_cancellation_before_map_allocation(self):
        def abort(): raise TimeoutError('cancelled')
        with self.assertRaises(TimeoutError):
            core.global_search({},np.empty((0,2)),np.empty((0,2)),checkpoint=abort)

    def test_cancellation_during_heading_search(self):
        calls=[]
        def check():
            calls.append(1)
            if len(calls)==4: raise TimeoutError('deadline')
        occupied=np.zeros((20,20),dtype=bool);occupied[:,0]=True
        m=dict(res=.1,origin=[0.,0.],w=20,h=20,occupied=occupied,free=~occupied,
               dist=np.tile(np.arange(20)*.1,(20,1)))
        points=np.array([[.4,.4],[.4,-.4]])
        with self.assertRaises(TimeoutError):
            core.global_search(m,points,points,checkpoint=check)
        self.assertEqual(len(calls),4)

if __name__=='__main__': unittest.main()

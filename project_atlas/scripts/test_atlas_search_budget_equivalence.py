"""Pacing must not change geometry, candidate order or verdicts; no ROS/network."""
import math
import tempfile
import unittest

from atlas_background_search_budget import BackgroundSearchBudget
import atlas_localization_verify_core as core
from test_atlas_localization_verify import write_map, ray_scan, ROOM_A, ROOM_B, SYMMETRIC_B


class SearchBudgetEquivalence(unittest.TestCase):
    def test_identical_hypotheses_and_verdict_for_distinct_and_ambiguous_rooms(self):
        for walls, pose in ((ROOM_A + ROOM_B, (1., 1., .4)),
                            (ROOM_A + ROOM_B, (7., 1., -.8)),
                            (SYMMETRIC_B, (8., 1.25, .0))):
            with self.subTest(pose=pose), tempfile.TemporaryDirectory() as directory:
                m = core.load_map(write_map(directory, walls))
                amin, inc, ranges = ray_scan(walls, pose)
                pts, held = core.endpoints(amin, inc, ranges, (0., 0., 0.))
                baseline = core.global_search(m, pts, held)
                now = [0., 0.]
                checks = []
                def wall(): return now[0]
                def cpu(): return now[1]
                def pause(delay): now[0] += delay
                def deadline(): checks.append(now[0])
                budget = BackgroundSearchBudget(deadline, wall=wall, cpu=cpu, pause=pause)
                def checkpoint():
                    now[0] += .001
                    now[1] += .001
                    budget()
                paced = core.global_search(m, pts, held, checkpoint=checkpoint)
                self.assertEqual(baseline, paced)
                self.assertEqual(core.decide(baseline, len(pts)).as_dict(),
                                 core.decide(paced, len(pts)).as_dict())
                self.assertGreater(len(checks), 10)


if __name__ == '__main__': unittest.main()

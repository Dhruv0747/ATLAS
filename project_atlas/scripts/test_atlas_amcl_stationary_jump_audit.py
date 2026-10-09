import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from atlas_amcl_stationary_jump_audit import (analyze, cloud_support, compose, map_model,
                                               nearest_at_or_before, replay_summary,
                                               score_scan)


def point(x=0, y=0):
    return SimpleNamespace(x=x, y=y)


class StationaryJumpAuditTest(unittest.TestCase):
    def test_cloud_support_separates_position_and_heading(self):
        cloud = np.array([[0, 0, 0], [.1, 0, math.pi], [2, 0, 0]])
        support = cloud_support(cloud, [1, 1, 2], np.array([0, 0, 0]), np.array([2, 0, 0]))
        self.assertEqual(support["before_xy_weight"], .5)
        self.assertEqual(support["before_xy_heading_weight"], .25)
        self.assertEqual(support["after_xy_weight"], .5)

    def test_map_projection_respects_origin_and_laser_rotation(self):
        grid = [0] * 100
        grid[5 * 10 + 6] = 100
        info = SimpleNamespace(height=10, width=10, resolution=1.,
                               origin=SimpleNamespace(position=point(),
                                   orientation=SimpleNamespace(x=0, y=0, z=0, w=1)))
        model = map_model(SimpleNamespace(info=info, data=grid))
        # Laser forward point becomes +Y after a +90-degree mount rotation.
        result = score_scan(np.array([[1., 0.]]), np.array([6.5, 4.5, 0]),
                            np.array([0, 0, math.pi / 2]), model)
        self.assertEqual(result["within_15cm_wall_fraction"], 1)
        self.assertEqual(result["known_endpoint_fraction"], 1)
        self.assertEqual(result["premature_mapped_obstacle_fraction"], 0)

    def test_ray_detects_mapped_wall_before_matching_endpoint(self):
        grid = [0] * 100
        grid[5 * 10 + 6] = 100
        grid[7 * 10 + 6] = 100
        info = SimpleNamespace(height=10, width=10, resolution=1.,
                               origin=SimpleNamespace(position=point(),
                                   orientation=SimpleNamespace(x=0, y=0, z=0, w=1)))
        model = map_model(SimpleNamespace(info=info, data=grid))
        result = score_scan(np.array([[4., 0.]]), np.array([6.5, 3.5, 0]),
                            np.array([0, 0, math.pi / 2]), model)
        self.assertEqual(result["within_15cm_wall_fraction"], 1)
        self.assertEqual(result["premature_mapped_obstacle_fraction"], 1)

    def test_nearest_prior_does_not_use_future_data(self):
        rows = [(1., "old"), (2., "future")]
        self.assertEqual(nearest_at_or_before(rows, 1.2, .5)[1], "old")
        self.assertIsNone(nearest_at_or_before(rows, 1.2, .1))

    def test_replay_uses_source_static_tf_when_output_omits_it(self):
        grid = [0] * 100
        grid[5 * 10 + 6] = 100
        info = SimpleNamespace(height=10, width=10, resolution=1.,
                               origin=SimpleNamespace(position=point(),
                                   orientation=SimpleNamespace(x=0, y=0, z=0, w=1)))
        scan = SimpleNamespace(ranges=[1.] * 30, angle_min=0., angle_increment=0.,
                               range_min=.1, range_max=10.)
        output = ([(1., np.array([6.5, 4.5, 0]), None, 2.)], [],
                  [(2., 1., scan)], [], [], SimpleNamespace(info=info, data=grid), {})
        source = ([], [], [], [], [], None,
                  {("base_footprint", "laser_frame"): np.array([0, 0, math.pi / 2])})
        with patch("atlas_amcl_stationary_jump_audit.read_bag", side_effect=[output, source]):
            result = replay_summary("replay", source_bag="original")
        self.assertEqual(result["scan_pairs"], 1)
        self.assertEqual(result["median_endpoint_fit_15cm"], 1.)

    def test_jump_audit_uses_source_static_tf_when_output_omits_it(self):
        grid = [0] * 100
        grid[5 * 10 + 6] = 100
        info = SimpleNamespace(height=10, width=10, resolution=1.,
                               origin=SimpleNamespace(position=point(),
                                   orientation=SimpleNamespace(x=0, y=0, z=0, w=1)))
        output = ([], [], [], [], [], SimpleNamespace(info=info, data=grid), {})
        source = ([], [], [], [], [], None,
                  {("base_footprint", "laser_frame"): np.array([0, 0, math.pi / 2])})
        with patch("atlas_amcl_stationary_jump_audit.read_bag", side_effect=[output, source]):
            result = analyze("replay", source_bag="original")
        self.assertEqual(result["events"], [])


if __name__ == "__main__":
    unittest.main()

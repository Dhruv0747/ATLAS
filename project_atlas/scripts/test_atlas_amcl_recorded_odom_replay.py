import unittest
from types import SimpleNamespace

import yaml

from atlas_amcl_recorded_odom_replay import (ALLOWED, keep_tf,
                                              replay_localization_params)


class RecordedOdomReplayTest(unittest.TestCase):
    def test_no_actuator_topics(self):
        self.assertEqual(ALLOWED, {"/scan", "/tf", "/tf_static", "/odom"})

    def test_keep_original_odom_tf_but_not_old_amcl_tf(self):
        def transform(parent, child):
            return SimpleNamespace(header=SimpleNamespace(frame_id=parent),
                                   child_frame_id=child)
        msg = SimpleNamespace(transforms=[transform("/map", "/odom"),
                                          transform("/odom", "/base_link"),
                                          transform("/base_link", "/base_footprint")])
        kept = keep_tf(msg)
        self.assertEqual([(t.header.frame_id, t.child_frame_id)
                          for t in kept.transforms],
                         [("/odom", "/base_link"),
                          ("/base_link", "/base_footprint")])

    def test_stationary_updates_are_replay_only(self):
        raw = yaml.safe_dump({"amcl": {"ros__parameters": {
            "update_min_d": .05, "update_min_a": .05}},
            "map_server": {"ros__parameters": {}}})
        seed = {"x": 1., "y": 2., "z": 0., "yaw": 0.}
        original = replay_localization_params(raw, "/tmp/map.yaml", seed)
        experiment = replay_localization_params(raw, "/tmp/map.yaml", seed, True)
        self.assertEqual(original["amcl"]["ros__parameters"]["update_min_d"], .05)
        self.assertEqual(experiment["amcl"]["ros__parameters"]["update_min_d"], 0.)
        self.assertEqual(experiment["amcl"]["ros__parameters"]["update_min_a"], 0.)


if __name__ == "__main__":
    unittest.main()

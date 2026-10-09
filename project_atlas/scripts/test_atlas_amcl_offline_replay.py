import unittest
import yaml

from atlas_amcl_offline_replay import localization_params
from atlas_fusion_replay import ALLOWED


class AmclReplayTest(unittest.TestCase):
    def test_replay_excludes_actuator_topics(self):
        self.assertFalse(ALLOWED & {"/cmd_vel", "/cmd_vel_nav", "/cmd_vel_joy",
                                    "/atlas/steering_cmd"})

    def test_only_offline_seed_and_clock_change_nav_params(self):
        source = {"amcl": {"ros__parameters": {"use_sim_time": False,
                                                 "alpha1": .2}},
                  "map_server": {"ros__parameters": {"yaml_filename": ""}}}
        seed = {"x": 1.0, "y": 2.0, "z": 0.0, "yaw": 3.0,
                "seed_age_s": 0.5}
        result = localization_params(yaml.safe_dump(source), "/tmp/saved.yaml", seed)
        self.assertEqual(result["amcl"]["ros__parameters"]["initial_pose"],
                         {"x": 1.0, "y": 2.0, "z": 0.0, "yaw": 3.0})
        self.assertTrue(result["amcl"]["ros__parameters"]["set_initial_pose"])
        self.assertEqual(result["map_server"]["ros__parameters"]["yaml_filename"],
                         "/tmp/saved.yaml")
        self.assertEqual(source["amcl"]["ros__parameters"],
                         {"use_sim_time": False, "alpha1": .2})


if __name__ == "__main__":
    unittest.main()

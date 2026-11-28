import unittest

from atlas_fusion_bag_analyzer import select_imu_topic


class FusionBagAnalyzerTest(unittest.TestCase):
    def test_prefers_corrected_gyro_when_both_topics_exist(self):
        self.assertEqual(select_imu_topic({
            "/imu/data": "sensor_msgs/msg/Imu",
            "/im10a/imu/bias_corrected_candidate": "sensor_msgs/msg/Imu",
        }), "/im10a/imu/bias_corrected_candidate")

    def test_raw_gyro_fallback(self):
        self.assertEqual(select_imu_topic({"/imu/data": "sensor_msgs/msg/Imu"}),
                         "/imu/data")


if __name__ == "__main__":
    unittest.main()

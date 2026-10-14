import struct
import unittest

from moving_yaw_evidence import decode_imu_z, integrate_gyro, summarize_window


class MovingYawEvidenceTests(unittest.TestCase):
    def test_imu_cdr_source_stamp_and_z(self):
        # CDR offsets are relative to the encapsulation, not byte zero.
        name = b"base_link\x00"
        blob = bytearray(b"\x00\x01\x00\x00")
        blob += struct.pack("<iI", 12, 250_000_000)
        blob += struct.pack("<I", len(name)) + name
        blob += bytes((8 - (len(blob) - 4) % 8) % 8)
        blob += struct.pack("<16d", *([0.0] * 15), -0.25)
        stamp, z = decode_imu_z(blob)
        self.assertAlmostEqual(stamp, 12.25)
        self.assertEqual(z, -0.25)

    def test_integral_clips_window_and_rejects_gap(self):
        yaw, covered = integrate_gyro([(0, 0), (1, 1), (1.2, 1), (2, 9)], 1.0, 1.4)
        self.assertAlmostEqual(yaw, 0.2)
        self.assertAlmostEqual(covered, 0.2)

    def test_wrong_sign_is_not_corrected_by_a_global_flip(self):
        def row(t, yaw):
            return {"stamp_ns": int(t * 1e9), "accepted_delta_m": 0.1,
                    "applied_curvature_per_m": yaw / 0.1,
                    "raw_counts": [0] * 4, "wheel_distances_m": [0.0] * 4,
                    "steering_command_deg": [90, 90],
                    "accepted_channels": [1, 2, 3, 4], "packet_fresh": True}
        first = summarize_window([row(0, 0.1)], [(0, -0.1), (0.2, -0.1)], 0, 0.2)
        second = summarize_window([row(1, -0.1)], [(1, -0.1), (1.2, -0.1)], 1, 1.2)
        self.assertLess(first["wheel_yaw_deg"] * first["gyro_yaw_deg"], 0.0)
        self.assertGreater(second["wheel_yaw_deg"] * second["gyro_yaw_deg"], 0.0)


if __name__ == "__main__":
    unittest.main()

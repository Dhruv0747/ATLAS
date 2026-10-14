import math
import unittest

from steering_angle_measurement import road_angle, rolling_delta, video_ros_time, visual_measurement


def project(x, y):
    # Deliberately tilted camera: raw image angles are not road-wheel angles.
    return [(800*x + 200*y + 300)/(0.2*x + 0.1*y + 1),
            (100*x - 650*y + 400)/(0.2*x + 0.1*y + 1)]


class SteeringMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.reference = [{'image_xy': project(x, y), 'plane_xy_m': [x, y]}
                          for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
        self.chassis = [project(0.1, 0.5), project(0.9, 0.5)]

    def test_perspective_and_direction(self):
        for degrees in (-25, 0, 20):
            a = math.radians(degrees)
            wheel = [project(0.2, 0.4), project(0.2+0.5*math.cos(a), 0.4+0.5*math.sin(a))]
            self.assertAlmostEqual(road_angle(self.reference, self.chassis, wheel), degrees, places=8)

    def test_uncertainty_is_reported(self):
        wheel = [project(0.2, 0.4), project(0.7, 0.4)]
        result = visual_measurement(self.reference, self.chassis, wheel, 1)
        self.assertGreater(result['point_picking_bound_deg'], 0)
        self.assertIn('non-coplanarity', result['unmeasured_errors'])

    def test_degenerate_reference_rejected(self):
        with self.assertRaises(ValueError):
            road_angle([self.reference[0]]*4, self.chassis, self.chassis)

    def test_sync_interpolation_and_clock_step_rejection(self):
        anchors = [{'video_pts_s': 1, 'ros_time_ns': 10_000_000_000, 'uncertainty_s': .1},
                   {'video_pts_s': 11, 'ros_time_ns': 20_000_000_000, 'uncertainty_s': .1}]
        self.assertEqual(video_ros_time(6, anchors), (15_000_000_000, .1))
        anchors[1]['ros_time_ns'] += 1_000_000_000
        with self.assertRaises(ValueError):
            video_ros_time(6, anchors)

    def test_four_wheel_rolling_recovers_left_right_and_reverse(self):
        positions = [(-.1835, .13), (-.1835, -.13), (.1835, .13), (.1835, -.13)]
        for dx, dy, yaw in ((.2, 0, .1), (.2, .02, -.1), (-.2, 0, .1)):
            angles, distances = [], []
            for x, y in positions:
                vx, vy = dx-yaw*y, dy+yaw*x
                # Road wheel axis is directed frontwards even during reverse.
                angle = math.atan2(vy, vx)
                if dx < 0:
                    angle = math.atan2(-vy, -vx)
                angles.append(math.degrees(angle))
                distances.append(vx*math.cos(angle)+vy*math.sin(angle))
            result = rolling_delta(angles, distances, positions)
            self.assertTrue(result['observable'])
            self.assertAlmostEqual(result['dx_m'], dx)
            self.assertAlmostEqual(result['dy_m'], dy)
            self.assertAlmostEqual(result['dyaw_rad'], yaw)
            self.assertLess(max(abs(r) for r in result['lateral_slip_residuals_m']), 1e-8)

    def test_two_encoders_are_not_universally_sufficient(self):
        positions = [(-.1835, .13), (.1835, -.13)]
        self.assertFalse(rolling_delta([-20, 20], [.1, .1], positions)['observable'])
        self.assertTrue(rolling_delta([-20, 20], [.1, .1], positions, .01)['observable'])
        self.assertFalse(rolling_delta([0, 0], [.1, .1], positions, .01)['observable'])


if __name__ == '__main__':
    unittest.main()

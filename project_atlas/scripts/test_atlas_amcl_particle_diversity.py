import unittest
from atlas_amcl_particle_diversity import summarize_particles


class ParticleDiversityTests(unittest.TestCase):
    def test_uniform_duplicates_have_high_ess_but_one_support(self):
        result = summarize_particles([(1., 2., .3)] * 2000, [1.] * 2000)
        self.assertAlmostEqual(result["weight_ess"], 2000.)
        self.assertEqual(result["unique_at_1e_minus_6_m_rad"], 1)

    def test_broad_uniform_cloud_is_not_collapsed(self):
        result = summarize_particles([(0., 0., 0.), (1., 0., 0.), (0., 1., .5)], [1.] * 3)
        self.assertEqual(result["unique_at_1e_minus_6_m_rad"], 3)
        self.assertEqual(result["x_extent_m"], 1.)

    def test_floating_noise_does_not_inflate_effective_support(self):
        result = summarize_particles([(1., 2., 0.), (1., 2. + 1e-14, 0.)], [1., 1.])
        self.assertEqual(result["unique_exact"], 2)
        self.assertEqual(result["unique_at_1e_minus_6_m_rad"], 1)

    def test_invalid_data_rejected(self):
        for points, weights in [([], []), ([(0., 0., 0.)], [0.]),
                                ([(float("nan"), 0., 0.)], [1.]),
                                ([(0., 0., 0.)], [-1.])]:
            with self.assertRaises(ValueError):
                summarize_particles(points, weights)


if __name__ == "__main__":
    unittest.main()

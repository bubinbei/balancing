import unittest

import numpy as np

from balancing_host.uncertainty import bootstrap_runs


class BootstrapTests(unittest.TestCase):
    def test_calibration_noise_increases_uncertainty_and_seed_is_reproducible(self):
        H = np.array([[1 + 0.2j, 0.2 - 0.1j], [0.1 + 0.4j, 1.1 + 0.3j],
                      [0.4 - 0.2j, -0.3 + 0.5j]])
        V = H @ np.array([100 + 20j, 50 - 30j])
        rng = np.random.default_rng(714)
        baseline = V + rng.normal(0, 0.5, (30, 3)) + 1j * rng.normal(0, 0.5, (30, 3))
        noise_a = rng.normal(0, 1, (30, 3)) + 1j * rng.normal(0, 1, (30, 3))
        noise_b = rng.normal(0, 1, (30, 3)) + 1j * rng.normal(0, 1, (30, 3))
        def estimate(scale):
            return bootstrap_runs(baseline, V + H[:, 0] * 300 + scale * noise_a,
                                  V + H[:, 1] * 300j + scale * noise_b, 300, 300j,
                                  np.eye(6) * 0.01, repetitions=200)
        low, high = estimate(0.5), estimate(10)
        self.assertEqual(low, estimate(0.5))
        self.assertGreater(np.trace(high["covariance_real"]), np.trace(low["covariance_real"]) * 10)


if __name__ == "__main__":
    unittest.main()

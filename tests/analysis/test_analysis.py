import tempfile
from pathlib import Path
import unittest

import numpy as np
from scipy import stats

from balancing_host.analysis import (fft_spectrum, harmonic_fit, influence_matrix,
                                     phase_from_index, phase_from_teeth, real_matrix,
                                     rigid_body_acceleration, solve_correction, synchronous_average)
from balancing_host.capture_analysis import analyze_capture
from balancing_host.protocol import ProtocolError
from balancing_host.recording import Recorder
from balancing_host.synthetic import stream


class SignalTests(unittest.TestCase):
    def test_known_amplitude_phase_offset_trend_and_delay(self):
        time = np.arange(0, 3, 1 / 1344)
        indices = np.arange(0, 3.1, 0.1)
        phase = phase_from_index(indices, list(range(len(indices))))
        delay = 0.003
        expected = np.array([0.03 * np.exp(0.6j), 0.12 * np.exp(-0.9j)])
        values = np.real(np.exp(1j * 2 * np.pi * 10 * (time[:, None] - delay)) * expected)
        values += np.array([1, -2]) + time[:, None] * np.array([0.01, -0.02])
        result = harmonic_fit(time, values, phase, delays_s=delay)
        np.testing.assert_allclose(result.coefficient, expected, atol=1e-12)
        self.assertLess(np.max(result.residual_rms), 1e-12)
        with self.assertRaises(ProtocolError):
            harmonic_fit(time, values, phase, delays_s=None)
        with self.assertRaises(ProtocolError):
            harmonic_fit(time, values, phase, quality=np.ones(len(time)))

    def test_fft_and_angular_average_match_harmonic(self):
        time = np.arange(3000) / 1000
        values = 0.04 * np.cos(2 * np.pi * 10 * time + 0.3) + 2
        phase = phase_from_index(np.arange(31) / 10, list(range(31)))
        freq, amps = fft_spectrum(time, values)
        self.assertAlmostEqual(freq[np.argmax(amps)], 10)
        self.assertAlmostEqual(np.max(amps), 0.04, places=6)
        angle, average, turns = synchronous_average(time, values, phase)
        coefficient = np.mean((average - average.mean()) * np.exp(-1j * angle)) * 2
        self.assertLess(abs(coefficient - 0.04 * np.exp(0.3j)), 0.00004)

    def test_bad_phase_and_extrapolation_refused(self):
        with self.assertRaises(ProtocolError):
            phase_from_index([0, 1, 2], [0, 1, 3])
        phase = phase_from_index([0, 1, 2], [0, 1, 2])
        with self.assertRaises(ProtocolError):
            phase.evaluate([-0.001])
        with self.assertRaises(ProtocolError):
            phase.evaluate([0.5], 2)

    def test_jitter_drift_axis_rotation_and_reverse_rotation(self):
        rng = np.random.default_rng(1407)
        times = np.arange(4000) / 1344
        times = times * 1.0003 + rng.uniform(-0.00005, 0.00005, len(times))
        phase_times = np.arange(-1, 33) / 10
        phase = phase_from_index(phase_times, list(range(len(phase_times))), direction=-1)
        theta = phase.evaluate(times)
        vector = np.array([0.03 * np.exp(0.3j), 0.06 * np.exp(-0.4j), 0.02 * np.exp(1j)])
        rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
        values = np.real(np.exp(1j * theta[:, None]) * vector) @ rotation.T
        result = harmonic_fit(times, values, phase)
        np.testing.assert_allclose(result.coefficient, rotation @ vector, atol=1e-12)
        with self.assertRaises(ProtocolError):
            harmonic_fit(times, values, phase, quality=[])

    def test_runup_multitooth_phase(self):
        omega, alpha, duration, ppr = 30.0, 8.0, 8, 60
        theta_end = omega * duration + alpha * duration**2 / 2
        angles = np.arange(int(theta_end / (2 * np.pi / ppr))) * 2 * np.pi / ppr
        teeth = 2 * angles / (omega + np.sqrt(omega**2 + 2 * alpha * angles))
        indices = teeth[::ppr]
        phase = phase_from_teeth(teeth, list(range(len(teeth))), indices,
                                 list(range(len(indices))), ppr=ppr)
        time = np.linspace(0.1, teeth[-1] - 0.01, 5000)
        error_deg = np.rad2deg(phase.evaluate(time) - (omega * time + alpha * time**2 / 2))
        self.assertLess(np.percentile(np.abs(error_deg), 95), 1)
        np.testing.assert_allclose(phase.evaluate(indices), np.arange(len(indices)) * 2 * np.pi, atol=1e-10)
        quantized = np.round(teeth * 1000000) / 1000000
        noisy_phase = phase_from_teeth(quantized, list(range(len(teeth))), quantized[::ppr],
                                       list(range(len(indices))), ppr=ppr)
        targets = np.linspace(0.1, teeth[-1] - 0.1, 300)
        kinematics, uncertainty = noisy_phase.kinematics(targets, window_s=0.1)
        self.assertLess(np.percentile(np.abs(kinematics[:, 2] - alpha), 95), 0.25)
        self.assertTrue(np.all(uncertainty >= 0))
        with self.assertRaises(ProtocolError):
            noisy_phase.evaluate(targets, 2)

    def test_rigid_body_acceleration(self):
        result = rigid_body_acceleration([0, 0, 0], [0, 0, 10], [0, 0, 2], [0.1, 0, 0])
        np.testing.assert_allclose(result, [-10, 0.2, 0])

    def test_end_to_end_synthetic_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "capture"
            with Recorder(directory, "synthetic") as recorder:
                for data in stream(1.0):
                    list(recorder.append(data))
            result = analyze_capture(directory)
            self.assertEqual(result["data_kind"], "synthetic")
            self.assertAlmostEqual(result["rpm_mean"], 600, delta=0.1)
            np.testing.assert_allclose(result["harmonic"]["amplitude_peak"][:3], [0.03] * 3, atol=0.00001)
            np.testing.assert_allclose(result["harmonic"]["phase_deg"][:3], np.rad2deg([0.35, 0.75, 1.15]), atol=0.03)


class BalanceTests(unittest.TestCase):
    def setUp(self):
        self.H = np.array([[1 + 0.3j, 0.2 - 0.1j], [0.1 + 0.2j, 1.2 + 0.5j],
                           [0.6 - 0.2j, -0.4 + 0.3j], [0.4 + 0.8j, 0.7 - 0.2j]])
        self.U = np.array([100 * np.exp(0.4j), 70 * np.exp(-1.2j)])
        self.V = self.H @ self.U
        self.C = np.eye(8) * 0.25

    def test_calibration_and_correction_sign(self):
        a, b = 250 * np.exp(0.2j), 300 * np.exp(-0.7j)
        matrix = influence_matrix(self.V, self.V + self.H[:, 0] * a, self.V + self.H[:, 1] * b, a, b)
        np.testing.assert_allclose(matrix, self.H)
        result = solve_correction(matrix, self.V, self.C, max_std_gmm=1)
        correction = np.array(result["correction_real"]) + 1j * np.array(result["correction_imag"])
        np.testing.assert_allclose(correction, -self.U, atol=1e-10)
        np.testing.assert_allclose(result["predicted_residual_real"], 0, atol=1e-10)
        self.assertEqual(result["rank"], 4)

    def test_real_matrix_component_order(self):
        u = np.array([self.U[0].real, self.U[0].imag, self.U[1].real, self.U[1].imag])
        np.testing.assert_allclose(real_matrix(self.H) @ u, np.r_[self.V.real, self.V.imag])

    def test_units_do_not_change_result(self):
        scale = np.array([1000, 0.001, 2, 100])
        noise_scale = np.diag(np.r_[scale, scale])
        first = solve_correction(self.H, self.V, self.C)
        second = solve_correction(self.H * scale[:, None], self.V * scale,
                                  noise_scale @ self.C @ noise_scale)
        np.testing.assert_allclose(first["correction_real"], second["correction_real"], atol=1e-6)
        # Exact zero cross terms can differ by floating-point roundoff after SVD.
        np.testing.assert_allclose(first["covariance_real"], second["covariance_real"], rtol=1e-6, atol=1e-12)

    def test_unobservable_or_redundant_models_refused(self):
        with self.assertRaises(ProtocolError):
            solve_correction(np.column_stack([self.H[:, 0]] * 2), self.V, self.C)
        with self.assertRaises(ProtocolError):
            solve_correction(self.H, self.V, np.ones((8, 8)))
        with self.assertRaises(ProtocolError):
            solve_correction(self.H, self.V, self.C, max_std_gmm=0.00001)
        nearly_same = self.H.copy()
        nearly_same[:, 1] = nearly_same[:, 0] + 1e-7 * self.H[:, 1]
        with self.assertRaises(ProtocolError):
            solve_correction(nearly_same, self.V, self.C, max_std_gmm=20)

    def test_conditional_95_percent_interval_coverage(self):
        rng = np.random.default_rng(20261029)
        true_correction = np.array([-self.U[0].real, -self.U[0].imag, -self.U[1].real, -self.U[1].imag])
        covered = 0
        for _ in range(250):
            noise = rng.multivariate_normal(np.zeros(8), self.C)
            result = solve_correction(self.H, self.V + noise[:4] + 1j * noise[4:], self.C)
            estimate = np.array([result["correction_real"][0], result["correction_imag"][0],
                                 result["correction_real"][1], result["correction_imag"][1]])
            error = estimate - true_correction
            statistic = error @ np.linalg.solve(result["covariance_real"], error)
            covered += statistic <= stats.chi2.ppf(0.95, 4)
        self.assertGreaterEqual(covered / 250, 0.90)
        self.assertLessEqual(covered / 250, 0.99)


if __name__ == "__main__":
    unittest.main()

"""Export reproducible numerical evidence; all inputs are synthetic truth."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats
from scipy.spatial.transform import Rotation

from balancing_host.analysis import (harmonic_fit, influence_matrix, phase_from_index,
                                     phase_from_teeth, rigid_body_acceleration, solve_correction)


def verify():
    times = np.arange(0, 3, 1 / 1344)
    indices = np.arange(0, 3.1, 0.1)
    phase = phase_from_index(indices, list(range(len(indices))))
    truth = np.array([0.03 * np.exp(0.6j), 0.12 * np.exp(-0.9j)])
    values = np.real(np.exp(1j * 2 * np.pi * 10 * (times[:, None] - 0.003)) * truth)
    values += [1, -2] + times[:, None] * [0.01, -0.02]
    result = harmonic_fit(times, values, phase, delays_s=0.003)
    amplitude_relative_error = float(np.max(np.abs(np.abs(result.coefficient) / np.abs(truth) - 1)))
    phase_error = float(np.max(np.abs(np.rad2deg(np.angle(result.coefficient / truth)))))
    H = np.array([[1 + 0.3j, 0.2 - 0.1j], [0.1 + 0.2j, 1.2 + 0.5j],
                  [0.6 - 0.2j, -0.4 + 0.3j], [0.4 + 0.8j, 0.7 - 0.2j]])
    U = np.array([100 * np.exp(0.4j), 70 * np.exp(-1.2j)])
    V = H @ U
    ua, ub = 250 * np.exp(0.2j), 300 * np.exp(-0.7j)
    estimated_H = influence_matrix(V, V + H[:, 0] * ua, V + H[:, 1] * ub, ua, ub)
    covariance = np.eye(8) * 0.25
    solved = solve_correction(estimated_H, V, covariance)
    corrected = np.array(solved["correction_real"]) + 1j * np.array(solved["correction_imag"])
    correction_error = float(np.max(np.abs(corrected + U) / np.abs(U)))
    rng = np.random.default_rng(20261029)
    expected = np.array([-U[0].real, -U[0].imag, -U[1].real, -U[1].imag])
    covered = 0
    for _ in range(250):
        noise = rng.multivariate_normal(np.zeros(8), covariance)
        trial = solve_correction(H, V + noise[:4] + 1j * noise[4:], covariance)
        estimate = np.array([trial["correction_real"][0], trial["correction_imag"][0],
                             trial["correction_real"][1], trial["correction_imag"][1]])
        error = estimate - expected
        covered += error @ np.linalg.solve(trial["covariance_real"], error) <= stats.chi2.ppf(0.95, 4)
    transients = []
    for omega, alpha in ((30.0, 8.0), (100.0, -8.0)):
        theta_end = omega * 8 + alpha * 8**2 / 2
        angles = np.arange(int(theta_end / (2 * np.pi / 60))) * 2 * np.pi / 60
        teeth = 2 * angles / (omega + np.sqrt(omega**2 + 2 * alpha * angles))
        index = teeth[::60]
        teeth = np.round(teeth * 1000000) / 1000000
        index = teeth[::60]
        phase = phase_from_teeth(teeth, list(range(len(teeth))), index, list(range(len(index))), ppr=60)
        t = np.linspace(0.1, teeth[-1] - 0.1, 1000)
        kinematics, _ = phase.kinematics(t, window_s=0.1)
        error_deg = np.rad2deg(phase.evaluate(t) - (omega * t + alpha * t**2 / 2))
        transients.append(dict(initial_omega_rad_s=omega, alpha_rad_s2=alpha,
                               phase_error_p95_deg=float(np.percentile(np.abs(error_deg), 95)),
                               timer_quantization_us=1, kinematics_window_s=0.1,
                               omega_error_p95_rad_s=float(np.percentile(np.abs(kinematics[:, 1] - omega - alpha * t), 95)),
                               alpha_error_p95_rad_s2=float(np.percentile(np.abs(kinematics[:, 2] - alpha), 95))))
    t = np.linspace(0, 5, 10001)
    dt = t[1] - t[0]
    roll, yaw = 0.01 * np.sin(5 * t), 0.02 * np.sin(3 * t + 0.4)
    rd, yd = 0.05 * np.cos(5 * t), 0.06 * np.cos(3 * t + 0.4)
    rdd, ydd = -0.25 * np.sin(5 * t), -0.18 * np.sin(3 * t + 0.4)
    rotation = Rotation.from_euler("xz", np.column_stack([roll, yaw]))
    positions = rotation.apply(np.broadcast_to([0.2, 0.03, 0.02], (len(t), 3)))
    omega = np.column_stack([rd * np.cos(yaw), rd * np.sin(yaw), yd])
    alpha = np.column_stack([rdd * np.cos(yaw) - rd * yd * np.sin(yaw),
                             rdd * np.sin(yaw) + rd * yd * np.cos(yaw), ydd])
    predicted = rigid_body_acceleration(np.zeros_like(positions), omega, alpha, positions)
    numerical = (positions[2:] - 2 * positions[1:-1] + positions[:-2]) / dt**2
    rigid_error = float(np.max(np.abs(predicted[1:-1] - numerical)))
    assert amplitude_relative_error < 0.001 and phase_error < 0.1 and correction_error < 0.001
    assert 0.90 <= covered / 250 <= 0.99
    assert all(item["phase_error_p95_deg"] <= 1 for item in transients)
    assert all(item["alpha_error_p95_rad_s2"] <= 0.25 for item in transients)
    assert rigid_error < 1e-5
    return dict(data_kind="synthetic", seed=20261029, amplitude_relative_error=amplitude_relative_error,
                phase_error_deg=phase_error, correction_relative_error=correction_error,
                conditional_95_interval_coverage=covered / 250, coverage_trials=250,
                coverage_scope="Gaussian observation noise; H known exactly; excludes calibration and systematic error",
                transients=transients, rigid_3d_max_acceleration_error_m_s2=rigid_error,
                rigid_scope="known synthetic orientation and angular derivatives; no orientation estimator acceptance",
                physical_accuracy_confirmed=False, checks_passed=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
    print(json.dumps(result, indent=2))

"""Phase/order analysis and covariance-weighted two-plane correction.

All units and conventions are explicit. Conditional statistical uncertainty
does not include unmeasured drive effects or uncertainty of calibration H.
"""

from dataclasses import dataclass

import numpy as np
from scipy import interpolate, linalg, signal, stats

from .protocol import ProtocolError, require


def array(value, *, ndim=None):
    result = np.asarray(value, dtype=float)
    require(np.all(np.isfinite(result)), "nonfinite analysis input")
    if ndim is not None:
        require(result.ndim == ndim, "invalid array dimensions")
    return result


def increasing(value, name):
    result = array(value, ndim=1)
    require(len(result) >= 2 and np.all(np.diff(result) > 0), f"{name} must strictly increase")
    return result


def checked_sequences(values):
    sequence = list(values)
    require(len(sequence) >= 2, "not enough phase events")
    require(all(type(v) in (int, np.int64, np.uint64, np.uint32, np.int32) and 0 <= int(v) < 2**32
                for v in sequence), "invalid phase sequence")
    require(all((int(b) - int(a)) & 0xFFFFFFFF == 1 for a, b in zip(sequence, sequence[1:])),
            "missing, duplicate, or reordered phase events")


@dataclass
class Phase:
    times: np.ndarray
    angles: np.ndarray
    method: str
    direction: int

    def evaluate(self, times, derivative=0):
        times = array(times)
        require(np.all(times >= self.times[0]) and np.all(times <= self.times[-1]),
                "phase extrapolation is forbidden")
        if self.method == "index_linear":
            if derivative == 0:
                return np.interp(times, self.times, self.angles)
            require(derivative == 1, "index-only phase does not establish intra-revolution acceleration")
            indices = np.clip(np.searchsorted(self.times, times, side="right") - 1, 0, len(self.times) - 2)
            return (np.diff(self.angles) / np.diff(self.times))[indices]
        require(derivative in (0, 1), "use windowed kinematics for angular acceleration")
        return interpolate.PchipInterpolator(self.times, self.angles, extrapolate=False)(times, nu=derivative)

    def kinematics(self, times, *, window_s=0.1):
        """Centred local cubic fit; explicit smoothing instead of twice differentiating ticks.

        Returned uncertainties are conditional residual-noise estimates. Missing
        teeth, geometric errors and bias require separate validation.
        """
        require(self.method == "tooth_pchip", "index-only phase does not establish intra-revolution acceleration")
        targets = array(times, ndim=1)
        require(0 < window_s <= 10 and len(targets) <= 10000, "invalid kinematics window/size")
        half = window_s / 2
        require(np.all(targets - half >= self.times[0]) and np.all(targets + half <= self.times[-1]),
                "kinematics window is not bracketed")
        values, uncertainties = [], []
        for target in targets:
            left, right = np.searchsorted(self.times, [target - half, target + half])
            t = (self.times[left:right] - target) / half
            require(len(t) >= 8, "too few tooth events in kinematics window")
            design = np.column_stack([np.ones(len(t)), t, t**2, t**3])
            origin = self.angles[left]
            solution, _, rank, _ = linalg.lstsq(design, self.angles[left:right] - origin)
            require(rank == 4, "unobservable kinematics polynomial")
            residual = self.angles[left:right] - origin - design @ solution
            variance = float(residual @ residual) / (len(t) - 4)
            covariance = variance * linalg.inv(design.T @ design)
            transform = np.array([1, 1 / half, 2 / half**2])
            values.append([solution[0] + origin, solution[1] / half, 2 * solution[2] / half**2])
            uncertainties.append(np.sqrt(np.maximum(np.diag(covariance)[:3], 0)) * transform)
        return np.asarray(values), np.asarray(uncertainties)


def phase_from_index(times_s, sequences, *, direction=1, zero_angle_rad=0):
    times = increasing(times_s, "index timestamps")
    checked_sequences(sequences)
    require(len(times) == len(sequences) and direction in (-1, 1), "invalid index phase")
    angles = zero_angle_rad + direction * 2 * np.pi * np.arange(len(times))
    return Phase(times, angles, "index_linear", direction)


def phase_from_teeth(tooth_times_s, tooth_sequences, index_times_s, index_sequences, *, ppr,
                     direction=1, zero_angle_rad=0, index_tolerance_teeth=0.1):
    teeth = increasing(tooth_times_s, "tooth timestamps")
    indices = increasing(index_times_s, "index timestamps")
    checked_sequences(tooth_sequences)
    checked_sequences(index_sequences)
    require(len(teeth) == len(tooth_sequences) and len(indices) == len(index_sequences), "phase lengths differ")
    require(type(ppr) is int and 2 <= ppr <= 65535 and direction in (-1, 1), "invalid PPR/direction")
    require(0 <= index_tolerance_teeth <= 0.25, "invalid index alignment tolerance")
    aligned = []
    for index in indices:
        position = int(np.searchsorted(teeth, index))
        candidates = [p for p in (position - 1, position) if 0 <= p < len(teeth)]
        nearest = min(candidates, key=lambda p: abs(teeth[p] - index))
        interval = np.median(np.diff(teeth[max(0, nearest - 2):min(len(teeth), nearest + 3)]))
        require(abs(teeth[nearest] - index) <= index_tolerance_teeth * interval + 1e-12,
                "index is not aligned to a configured tooth")
        aligned.append(nearest)
    require(all(b - a == ppr for a, b in zip(aligned, aligned[1:])), "index/tooth count mismatch")
    angles = zero_angle_rad + direction * 2 * np.pi * (np.arange(len(teeth)) - aligned[0]) / ppr
    return Phase(teeth, angles, "tooth_pchip", direction)


@dataclass
class Harmonic:
    coefficient: np.ndarray
    covariance_real: np.ndarray
    residual_rms: np.ndarray
    samples: int
    turns: float

    def as_dict(self):
        return dict(real=self.coefficient.real.tolist(), imag=self.coefficient.imag.tolist(),
                    amplitude_peak=np.abs(self.coefficient).tolist(),
                    phase_deg=np.rad2deg(np.angle(self.coefficient)).tolist(),
                    covariance_real=self.covariance_real.tolist(), residual_rms=self.residual_rms.tolist(),
                    samples=self.samples, turns=self.turns,
                    uncertainty_model="conditional white residual noise; calibration/drive effects excluded")


def harmonic_fit(times_s, values, phase, *, quality=None, delays_s=0.0, trend=True):
    times = increasing(times_s, "sample timestamps")
    values = array(values)
    if values.ndim == 1:
        values = values[:, None]
    require(values.ndim == 2 and len(values) == len(times), "invalid sample matrix")
    require(len(values) >= 16, "not enough samples")
    if quality is not None:
        quality = np.asarray(quality)
        require(quality.shape in ((len(times),), values.shape), "quality dimensions differ from samples")
        require(np.all(quality == 0), "window contains quality flags")
    require(delays_s is not None, "unknown sensor/filter delay")
    delays = np.broadcast_to(array(delays_s), (values.shape[1],))
    require(np.all(delays >= 0), "negative sensor delay")
    valid = np.all((times[:, None] - delays >= phase.times[0]) &
                   (times[:, None] - delays <= phase.times[-1]), axis=1)
    times, values = times[valid], values[valid]
    require(len(times) >= 16, "not enough samples with bracketed phase")
    angles = phase.evaluate(times)
    turns = abs(float(angles[-1] - angles[0])) / (2 * np.pi)
    require(turns >= 2, "window spans fewer than two revolutions")
    inverses, coefficients, residuals = [], [], []
    for column, delay in enumerate(delays):
        theta = phase.evaluate(times - delay)
        design = np.column_stack([np.cos(theta), np.sin(theta), np.ones(len(times))])
        if trend:
            design = np.column_stack([design, (times - times.mean()) / np.ptp(times)])
        solution, _, rank, singular = linalg.lstsq(design, values[:, column])
        require(rank == design.shape[1] and singular[0] / singular[-1] < 1e8, "unobservable harmonic")
        inverse = linalg.pinv(design)
        inverses.append(np.vstack([inverse[0], -inverse[1]]))
        coefficients.append(solution[0] - 1j * solution[1])
        residuals.append(values[:, column] - design @ solution)
    residual = np.column_stack(residuals)
    noise_cov = residual.T @ residual / (len(times) - design.shape[1])
    channels = values.shape[1]
    covariance = np.empty((2 * channels, 2 * channels))
    for a in range(channels):
        for b in range(channels):
            block = noise_cov[a, b] * inverses[a] @ inverses[b].T
            covariance[np.ix_([a, a + channels], [b, b + channels])] = block
    return Harmonic(np.asarray(coefficients), covariance,
                    np.sqrt(np.mean(residual * residual, axis=0)), len(times), turns)


def synchronous_average(times_s, values, phase, *, points=256):
    times = increasing(times_s, "sample timestamps")
    values = array(values)
    require(values.shape[0] == len(times) and 16 <= points <= 4096, "invalid synchronous average")
    angle = phase.evaluate(times) * phase.direction
    first = int(np.ceil(angle[0] / (2 * np.pi)))
    last = int(np.floor(angle[-1] / (2 * np.pi)))
    require(last - first >= 2, "not enough complete revolutions")
    grid = np.arange(points) * 2 * np.pi / points
    matrix = []
    for turn in range(first, last):
        target = turn * 2 * np.pi + grid
        if values.ndim == 1:
            matrix.append(np.interp(target, angle, values))
        else:
            matrix.append(np.column_stack([np.interp(target, angle, values[:, c]) for c in range(values.shape[1])]))
    return grid * phase.direction, np.mean(matrix, axis=0), np.asarray(matrix)


def fft_spectrum(times_s, values):
    times = increasing(times_s, "sample timestamps")
    values = array(values, ndim=1)
    require(len(times) == len(values) and len(times) >= 16, "invalid FFT input")
    step = float(np.median(np.diff(times)))
    require(np.max(np.diff(times)) < 2 * step, "FFT window contains a sample gap")
    grid = np.arange(times[0], times[-1] + step * 0.01, step)
    signal_uniform = np.interp(grid, times, values)
    window = signal.windows.hann(len(grid), sym=False)
    spectrum = np.fft.rfft((signal_uniform - np.mean(signal_uniform)) * window)
    amplitudes = 2 * np.abs(spectrum) / np.sum(window)
    amplitudes[0] /= 2
    if len(grid) % 2 == 0:
        amplitudes[-1] /= 2
    return np.fft.rfftfreq(len(grid), step), amplitudes


def rigid_body_acceleration(origin_acceleration, angular_velocity, angular_acceleration, position):
    """Kinematics in one common frame, in m/s2, rad/s, rad/s2 and metres."""
    origin, omega, alpha, r = [array(v) for v in
                               (origin_acceleration, angular_velocity, angular_acceleration, position)]
    require(origin.shape[-1] == omega.shape[-1] == alpha.shape[-1] == r.shape[-1] == 3,
            "rigid body vectors must have three components")
    return origin + np.cross(alpha, r) + np.cross(omega, np.cross(omega, r))


def influence_matrix(baseline, trial_a, trial_b, u_a_gmm, u_b_gmm):
    baseline = np.asarray(baseline, dtype=complex)
    require(baseline.ndim == 1 and len(baseline) >= 2, "at least two response channels required")
    require(abs(u_a_gmm) > 0 and abs(u_b_gmm) > 0, "zero trial unbalance")
    a, b = np.asarray(trial_a, dtype=complex), np.asarray(trial_b, dtype=complex)
    require(a.shape == baseline.shape == b.shape, "trial response shapes differ")
    result = np.column_stack([(a - baseline) / u_a_gmm, (b - baseline) / u_b_gmm])
    require(np.all(np.isfinite(result)), "invalid influence matrix")
    return result


def real_matrix(matrix):
    matrix = np.asarray(matrix, dtype=complex)
    require(matrix.ndim == 2 and matrix.shape[1] == 2 and np.all(np.isfinite(matrix)), "invalid two-plane matrix")
    a, b = matrix[:, 0], matrix[:, 1]
    return np.block([[a.real[:, None], -a.imag[:, None], b.real[:, None], -b.imag[:, None]],
                     [a.imag[:, None], a.real[:, None], b.imag[:, None], b.real[:, None]]])


def solve_correction(matrix, response, covariance_real, *, reference_gmm=(100, 100),
                     max_std_gmm=None, max_condition=None, min_residual_p=None):
    matrix = np.asarray(matrix, dtype=complex)
    model = real_matrix(matrix)
    response = np.asarray(response, dtype=complex)
    require(response.shape == (matrix.shape[0],) and np.all(np.isfinite(response)), "invalid response")
    covariance = array(covariance_real, ndim=2)
    require(covariance.shape == (len(model), len(model)) and np.allclose(covariance, covariance.T),
            "invalid covariance dimensions/symmetry")
    eigenvalues, vectors = linalg.eigh(covariance)
    require(eigenvalues[0] > 0 and eigenvalues[0] > eigenvalues[-1] * 1e-14,
            "singular noise covariance; remove redundant channels or explicitly validate regularization")
    whitening = (vectors / np.sqrt(eigenvalues)).T
    refs = array(reference_gmm, ndim=1)
    require(refs.shape == (2,) and np.all(refs > 0), "invalid reference unbalance")
    scale = np.diag(np.repeat(refs, 2))
    design = whitening @ model @ scale
    target = whitening @ np.r_[response.real, response.imag]
    z, _, rank, singular = linalg.lstsq(design, -target, cond=1e-10)
    require(rank == 4, "two correction planes are not independently observable")
    condition = float(singular[0] / singular[-1])
    require(max_condition is None or condition <= max_condition, "conditioning exceeds configured limit")
    u = scale @ z
    # Avoid squaring the condition number by inverting A.T@A.
    _, singular_cov, right = linalg.svd(design, full_matrices=False)
    covariance_u = scale @ ((right.T / singular_cov**2) @ right) @ scale
    standard_error = np.sqrt(np.diag(covariance_u))
    require(max_std_gmm is None or np.all(standard_error <= max_std_gmm),
            "uncertainty exceeds configured g.mm limit")
    residual = design @ z + target
    dof = len(target) - 4
    chi2 = float(residual @ residual)
    p_value = float(stats.chi2.sf(chi2, dof)) if dof > 0 else None
    require(min_residual_p is None or (p_value is not None and p_value >= min_residual_p),
            "residual inconsistent with configured noise model")
    correction = np.array([u[0] + 1j * u[1], u[2] + 1j * u[3]])
    return dict(correction_real=correction.real.tolist(), correction_imag=correction.imag.tolist(),
                magnitude_gmm=np.abs(correction).tolist(), addition_angle_deg=np.rad2deg(np.angle(correction)).tolist(),
                covariance_real=covariance_u.tolist(), standard_error_components_gmm=standard_error.tolist(),
                rank=int(rank), condition=condition, singular_values=singular.tolist(),
                chi2=chi2, degrees_of_freedom=dof, residual_p=p_value,
                predicted_residual_real=(response + matrix @ correction).real.tolist(),
                predicted_residual_imag=(response + matrix @ correction).imag.tolist(),
                uncertainty_model="conditional on exact H and supplied covariance; calibration/drive errors excluded",
                unit="g.mm", angular_convention="added mass; removal is 180 degrees opposite")

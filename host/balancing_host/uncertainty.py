"""Bootstrap independent repeated RUNS, never individual correlated samples."""

import numpy as np

from .analysis import influence_matrix, solve_correction
from .protocol import ProtocolError, require


def bootstrap_runs(baselines, trials_a, trials_b, u_a_gmm, u_b_gmm, covariance_real, *,
                   seed=20261029, repetitions=500, paired=False):
    """Resample complete complex response vectors from independent runs.

    paired=True requires a genuinely paired acquisition design. Systematic
    mass/radius/angle/drive bias is not estimated by this procedure.
    """
    groups = [np.asarray(v, dtype=complex) for v in (baselines, trials_a, trials_b)]
    require(all(g.ndim == 2 and g.shape[0] >= 5 and np.all(np.isfinite(g)) for g in groups),
            "at least five independent finite run responses required per group")
    require(len({g.shape[1] for g in groups}) == 1 and groups[0].shape[1] >= 2, "response channels differ")
    require(not paired or len({len(g) for g in groups}) == 1, "paired groups must have equal size")
    require(type(repetitions) is int and 200 <= repetitions <= 10000, "invalid bootstrap count")
    rng = np.random.default_rng(seed)
    corrections, refused = [], 0
    for _ in range(repetitions):
        common = rng.integers(0, len(groups[0]), len(groups[0])) if paired else None
        means = [g[common if paired else rng.integers(0, len(g), len(g))].mean(axis=0) for g in groups]
        matrix = influence_matrix(*means, u_a_gmm, u_b_gmm)
        try:
            result = solve_correction(matrix, means[0], covariance_real)
        except ProtocolError:
            refused += 1
            continue
        corrections.append([result["correction_real"][0], result["correction_imag"][0],
                            result["correction_real"][1], result["correction_imag"][1]])
    require(refused <= 0.05 * repetitions and len(corrections) >= 200,
            "bootstrap is unstable/unobservable in too many repetitions")
    values = np.asarray(corrections)
    return dict(seed=seed, repetitions=repetitions, accepted=len(values), refused=refused, paired=paired,
                component_order=["Re_U_A", "Im_U_A", "Re_U_B", "Im_U_B"], unit="g.mm",
                covariance_real=np.cov(values, rowvar=False).tolist(),
                component_percentile_95_low=np.percentile(values, 2.5, axis=0).tolist(),
                component_percentile_95_high=np.percentile(values, 97.5, axis=0).tolist(),
                interpretation="componentwise percentile intervals, not a joint confidence region",
                excludes=["dependent runs unless modeled", "trial mass/radius/angle systematic error",
                          "unknown synchronous drive effects", "changes of setup outside the sampled runs"])

"""Two-point removal equivalence for a rigid rotor; never a machining approval."""

import itertools
import math

import numpy as np

from .protocol import require


def demo_geometry():
    return dict(data_kind="model_example", dimensions_verified=False,
                plane_x_mm=[-340, 340], phase_mark="pulley_top_at_index_zero",
                counterweights=[dict(id=f"CW{i + 1}", x_mm=x, radius_mm=65,
                                     center_angle_deg=0 if 2 <= i <= 5 else 180,
                                     half_arc_deg=55)
                                for i, x in enumerate([-260, -190, -110, -40, 40, 110, 190, 260])])


def plan_two_point_removal(correction, geometry):
    """Enumerate pairs, preserving both complex unbalance and axial moment.

    Angles/radii/arcs must be supplied explicitly. Here an arc only describes
    illustrative geometry; it does not encode strength, holes or oil galleries.
    Minimum total removed mass is only a mathematical tie-breaking objective.
    """
    correction = np.asarray(correction, dtype=complex)
    require(correction.shape == (2,) and np.all(np.isfinite(correction)), "invalid correction")
    xa, xb = geometry["plane_x_mm"]
    require(all(type(v) in (int, float) and math.isfinite(v) for v in (xa, xb)) and xa < xb,
            "invalid reference planes")
    weights = geometry["counterweights"]
    require(2 <= len(weights) <= 32, "invalid counterweight count")
    require(len({w["id"] for w in weights}) == len(weights), "duplicate counterweight id")
    for w in weights:
        require(all(type(w[k]) in (int, float) and math.isfinite(w[k])
                    for k in ("x_mm", "radius_mm", "center_angle_deg", "half_arc_deg")), "invalid geometry")
        require(w["radius_mm"] > 0 and 0 < w["half_arc_deg"] <= 180, "invalid radius/arc")
    # Negative added correction is the material-removal vector.
    target_force = -sum(correction)
    target_moment = -(xa * correction[0] + xb * correction[1])
    result = dict(model_only=True, machining_approved=False, actions=[], status="no_two_point_candidate")
    if np.max(np.abs(correction)) < 1e-12:
        return {**result, "status": "not_required"}
    candidates = []
    for a, b in itertools.combinations(weights, 2):
        span = b["x_mm"] - a["x_mm"]
        if abs(span) < 1e-9:
            continue
        ra = (b["x_mm"] * target_force - target_moment) / span
        rb = (target_moment - a["x_mm"] * target_force) / span
        actions = []
        for w, removal in ((a, ra), (b, rb)):
            if abs(removal) < 1e-12:
                continue
            angle = float(np.angle(removal, deg=True) % 360)
            distance = abs((angle - w["center_angle_deg"] + 180) % 360 - 180)
            if distance > w["half_arc_deg"] + 1e-9:
                break
            actions.append(dict(counterweight=w["id"], x_mm=w["x_mm"], radius_mm=w["radius_mm"],
                                removal_gmm=float(abs(removal)), mass_g=float(abs(removal) / w["radius_mm"]),
                                removal_angle_deg=angle, removal_real=float(removal.real),
                                removal_imag=float(removal.imag)))
        else:
            candidates.append(actions)
    if not candidates:
        return result
    actions = min(candidates, key=lambda plan: sum(a["mass_g"] for a in plan))
    # Return an independently inspectable projection to the original planes.
    equivalent = np.zeros(2, dtype=complex)
    for a in actions:
        added = -complex(a["removal_real"], a["removal_imag"])
        equivalent += added * np.array([(xb - a["x_mm"]) / (xb - xa), (a["x_mm"] - xa) / (xb - xa)])
    return {**result, "status": "demo_candidate", "actions": actions,
            "equivalent_added_real": equivalent.real.tolist(), "equivalent_added_imag": equivalent.imag.tolist()}

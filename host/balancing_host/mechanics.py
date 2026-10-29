"""Small-angle estimates only; dimensions, material and load paths need acceptance."""

import math

from .protocol import require


def sizing(value):
    names = ("moving_mass_kg", "suspension_length_m", "half_span_m", "yaw_inertia_kg_m2",
             "roll_inertia_about_suspension_kg_m2", "cg_below_suspension_m",
             "wire_diameter_mm", "wire_young_modulus_pa", "trial_mass_g", "trial_radius_mm")
    for name in names:
        require(type(value.get(name)) in (int, float) and math.isfinite(value[name])
                and value[name] > 0, f"missing/invalid {name}")
    require(value.get("data_kind") in ("model_example", "measured_inputs"), "explicit model provenance required")
    require(value.get("suspensions") in (2, 4), "two or four suspension wires required")
    mass, length = value["moving_mass_kg"], value["suspension_length_m"]
    g, count = 9.80665, value["suspensions"]
    area = math.pi * (value["wire_diameter_mm"] / 1000)**2 / 4
    tension = mass * g / count
    roll_inertia = value["roll_inertia_about_suspension_kg_m2"]
    h = value["cg_below_suspension_m"]
    axial_stiffness = count * value["wire_young_modulus_pa"] * area / length
    vertical_axial_hz = math.sqrt(axial_stiffness / mass) / (2 * math.pi)
    result = dict(data_kind=value["data_kind"], manufacturing_approval=False,
                  assumptions=["rigid cradle", "equal vertical wires and equal upper/lower spacing",
                               "small angles", "balanced static load", "drive/cables/hoses neglected",
                               "roll inertia is about the suspension line, not about the centre of mass",
                               "isolated mode estimates; coupling and support compliance neglected",
                               "no check of clamps, ceiling, wood joints, bearings, lubrication or guards"],
                  moving_mass_kg=mass,
                  pendulum_hz=math.sqrt(g / length) / (2 * math.pi),
                  transverse_stiffness_n_m=mass * g / length,
                  yaw_hz=math.sqrt(mass * g * value["half_span_m"]**2 /
                                   (value["yaw_inertia_kg_m2"] * length)) / (2 * math.pi),
                  roll_hz=math.sqrt(mass * g * h / roll_inertia) / (2 * math.pi),
                  static_tension_per_wire_n=tension, static_wire_stress_mpa=tension / area / 1000000,
                  axial_wire_stiffness_total_n_m=axial_stiffness,
                  vertical_axial_hz=vertical_axial_hz,
                  vertical_axial_1x_rpm=60 * vertical_axial_hz,
                  speed_cases=[])
    require(isinstance(value.get("rpm_cases"), list) and 1 <= len(value["rpm_cases"]) <= 32, "invalid speed cases")
    unbalance = value["trial_mass_g"] * value["trial_radius_mm"]
    for rpm in value["rpm_cases"]:
        require(type(rpm) in (int, float) and math.isfinite(rpm) and rpm > 0, "invalid RPM")
        omega = rpm * 2 * math.pi / 60
        force = unbalance * 1e-6 * omega**2
        result["speed_cases"].append(dict(rpm=rpm, rotation_hz=rpm / 60, trial_unbalance_gmm=unbalance,
                                          centrifugal_force_n=force,
                                          high_speed_displacement_um=unbalance * 1e-6 / mass * 1e6,
                                          high_speed_acceleration_mg=force / mass / g * 1000))
    return result

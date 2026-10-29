import json
import math
from pathlib import Path
import unittest

from balancing_host.mechanics import sizing
from balancing_host.protocol import ProtocolError


class MechanicsTests(unittest.TestCase):
    def test_documented_100_gmm_example(self):
        values = json.loads((Path(__file__).parents[2] / "mechanics/sizing-example.json").read_text())
        result = sizing(values)
        self.assertFalse(result["manufacturing_approval"])
        self.assertAlmostEqual(result["pendulum_hz"], 0.557, delta=0.001)
        self.assertAlmostEqual(result["vertical_axial_hz"], 27.31, delta=0.01)
        self.assertAlmostEqual(result["vertical_axial_1x_rpm"], 1638.82, delta=0.1)
        case = next(case for case in result["speed_cases"] if case["rpm"] == 1000)
        self.assertAlmostEqual(case["high_speed_displacement_um"], 10 / 3, places=12)
        self.assertAlmostEqual(case["high_speed_acceleration_mg"], 3.73, delta=0.01)
        with self.assertRaises(ProtocolError):
            sizing({**values, "moving_mass_kg": None})

    def test_axial_mode_scaling_and_static_deflection(self):
        values = json.loads((Path(__file__).parents[2] / "mechanics/sizing-example.json").read_text())
        base = sizing(values)
        for changed, ratio in (({"wire_diameter_mm": 3}, 2),
                               ({"moving_mass_kg": 120}, 0.5),
                               ({"suspension_length_m": 3.2}, 0.5),
                               ({"suspensions": 4}, math.sqrt(2))):
            with self.subTest(changed=changed):
                result = sizing({**values, **changed})
                self.assertAlmostEqual(result["vertical_axial_hz"], base["vertical_axial_hz"] * ratio)
        # Independent static-extension relation: omega**2 = g / extension.
        extension_m = values["moving_mass_kg"] * 9.80665 / base["axial_wire_stiffness_total_n_m"]
        self.assertAlmostEqual((2 * math.pi * base["vertical_axial_hz"])**2, 9.80665 / extension_m)
        thicker = sizing({**values, "wire_diameter_mm": 3})
        self.assertEqual(thicker["pendulum_hz"], base["pendulum_hz"])


if __name__ == "__main__":
    unittest.main()

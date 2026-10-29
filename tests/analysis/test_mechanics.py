import json
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
        case = next(case for case in result["speed_cases"] if case["rpm"] == 1000)
        self.assertAlmostEqual(case["high_speed_displacement_um"], 10 / 3, places=12)
        self.assertAlmostEqual(case["high_speed_acceleration_mg"], 3.73, delta=0.01)
        with self.assertRaises(ProtocolError):
            sizing({**values, "moving_mass_kg": None})


if __name__ == "__main__":
    unittest.main()

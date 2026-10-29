import unittest

import numpy as np

from balancing_host.counterweights import demo_geometry, plan_two_point_removal
from balancing_host.protocol import ProtocolError


class CounterweightTests(unittest.TestCase):
    def test_user_layout_and_couple_transfer_to_inner_planes(self):
        geometry = demo_geometry()
        self.assertEqual([w["center_angle_deg"] for w in geometry["counterweights"]],
                         [180, 180, 0, 0, 0, 0, 180, 180])
        correction = np.array([-80, 80], dtype=complex)
        plan = plan_two_point_removal(correction, geometry)
        self.assertEqual(plan["status"], "demo_candidate")
        self.assertFalse(plan["machining_approved"])
        self.assertEqual([a["counterweight"] for a in plan["actions"]], ["CW3", "CW8"])
        self.assertAlmostEqual(plan["actions"][0]["mass_g"], (80 * 680 / 370) / 65)
        recovered = np.array(plan["equivalent_added_real"]) + 1j * np.array(plan["equivalent_added_imag"])
        np.testing.assert_allclose(recovered, correction, atol=1e-12)

    def test_complex_transfer_and_removal_sign(self):
        correction = -np.array([80 * np.exp(1j * np.deg2rad(35)), 55 * np.exp(1j * np.deg2rad(210))])
        plan = plan_two_point_removal(correction, demo_geometry())
        self.assertEqual(plan["status"], "demo_candidate")
        recovered = np.array(plan["equivalent_added_real"]) + 1j * np.array(plan["equivalent_added_imag"])
        np.testing.assert_allclose(recovered, correction, atol=1e-12)
        self.assertTrue(all(a["mass_g"] > 0 for a in plan["actions"]))

    def test_no_material_at_required_angles_is_not_a_drilling_instruction(self):
        plan = plan_two_point_removal([-60j, -60j], demo_geometry())
        self.assertEqual(plan["status"], "no_two_point_candidate")
        self.assertEqual(plan["actions"], [])
        self.assertEqual(plan_two_point_removal([0, 0], demo_geometry())["status"], "not_required")

    def test_geometry_validation(self):
        geometry = demo_geometry()
        geometry["counterweights"][0]["radius_mm"] = 0
        with self.assertRaises(ProtocolError):
            plan_two_point_removal([1, 2], geometry)

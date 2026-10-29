import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np

from balancing_host.demo import build_demo, make_server


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_demo()

    def test_known_inputs_and_independent_corrected_run(self):
        self.assertEqual(self.data["data_kind"], "synthetic")
        self.assertFalse(self.data["hardware_connected"])
        for case in self.data["scenarios"]:
            injected = np.array(case["injected_real"]) + 1j * np.array(case["injected_imag"])
            solve = case["before"]["solver"]
            correction = np.array(solve["correction_real"]) + 1j * np.array(solve["correction_imag"])
            np.testing.assert_allclose(correction, -injected, atol=4)
            self.assertEqual(solve["rank"], 4)
            self.assertLess(max(p["unbalance_gmm"] for p in case["after"]["planes"]), 5)
            self.assertTrue(all(p["equivalent_mass_g"] == p["unbalance_gmm"] / 100
                                for p in case["before"]["planes"]))
            self.assertNotEqual(case["after"]["accel_rms_mg"], [0, 0])

    def test_couple_visible_when_translation_cancels(self):
        case = next(c for c in self.data["scenarios"] if c["id"] == "couple")
        self.assertAlmostEqual(case["before"]["motion_real"][0], 0)
        self.assertGreater(abs(case["before"]["motion_real"][2]), 0)
        self.assertGreater(min(p["unbalance_gmm"] for p in case["before"]["planes"]), 70)

    def test_http_serves_packaged_assets_not_project_files(self):
        with make_server() as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                for path in ("/", "/demo.js", "/model.js", "/styles.css", "/api/demo"):
                    with urlopen(url + path, timeout=3) as response:
                        self.assertEqual(response.status, 200)
                        self.assertTrue(response.read())
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                with urlopen(url + "/api/demo", timeout=3) as response:
                    self.assertEqual(json.load(response)["seed"], 52840)
                with self.assertRaises(HTTPError) as error:
                    urlopen(url + "/../../STATE.md", timeout=3)
                self.assertEqual(error.exception.code, 404)
            finally:
                server.shutdown()
                thread.join(timeout=3)

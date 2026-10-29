"""Local synthetic UI; no serial port, device discovery or motor control."""

from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.resources import files
import json
import math
import webbrowser

import numpy as np

from .analysis import harmonic_fit, influence_matrix, phase_from_index, solve_correction
from .counterweights import demo_geometry, plan_two_point_removal


def build_demo():
    """Generate trial runs and an independent post-correction run, deterministically.

    This is an illustrative rigid-body response, not identified stand mechanics.
    The UI bypasses acquisition: it demonstrates the existing analysis functions.
    """
    rpm, seconds, rate, mass = 900, 4, 800, 15.0
    omega = rpm * 2 * math.pi / 60
    times = np.arange(seconds * rate) / rate
    phase_times = np.arange(seconds * rpm // 60 + 1) * 60 / rpm
    phase = phase_from_index(phase_times, np.arange(len(phase_times)))
    carrier = np.exp(1j * omega * times)
    rng = np.random.default_rng(52840)
    geometry = demo_geometry()
    noise_std = np.array([0.020, 0.020, 0.0015, 0.0015])

    def motion(unbalance):
        a, b = unbalance * 1e-6  # g.mm -> kg.m
        return np.array([(a + b) / mass, (a + b) * 0.1 / 0.6,
                         (b - a) * 0.34 / 2.0])  # y translation, roll, yaw

    def response(unbalance):
        y, roll, yaw = motion(unbalance)
        return np.array([-omega**2 * (y + roll * 0.1 - yaw * 0.34),
                         -omega**2 * (y + roll * 0.1 + yaw * 0.34),
                         1j * omega * roll, 1j * omega * yaw])

    def run(unbalance):
        values = (carrier[:, None] * response(unbalance)).real
        values += rng.normal(size=values.shape) * noise_std
        return harmonic_fit(times, values, phase)

    def serialize(unbalance, fitted, calibration):
        solved = solve_correction(calibration, fitted.coefficient, fitted.covariance_real,
                                  max_condition=100)
        correction = np.array(solved["correction_real"]) + 1j * np.array(solved["correction_imag"])
        estimated = -correction
        planes = []
        for name, u, c in zip(("A", "B"), estimated, correction):
            planes.append(dict(name=name, unbalance_gmm=float(abs(u)), radius_mm=100,
                               equivalent_mass_g=float(abs(u) / 100),
                               heavy_angle_deg=float(np.angle(u, deg=True) % 360),
                               addition_angle_deg=float(np.angle(c, deg=True) % 360)))
        m = motion(unbalance)
        return dict(planes=planes, motion_real=m.real.tolist(), motion_imag=m.imag.tolist(),
                    accel_rms_mg=(np.abs(fitted.coefficient[:2]) / math.sqrt(2) / 9.80665 * 1000).tolist(),
                    solver=solved, removal_plan=plan_two_point_removal(correction, geometry))

    scenarios = []
    definitions = [("asymmetric", "Разный дисбаланс A / B", [80 * np.exp(1j * np.deg2rad(35)),
                                                            55 * np.exp(1j * np.deg2rad(210))]),
                   ("force", "Силовой: одинаковые направления", [60j, 60j]),
                   ("couple", "Моментный: противоположные направления", [80, -80])]
    for key, label, values in definitions:
        unbalance = np.asarray(values, dtype=complex)
        baseline = run(unbalance)
        trial_a = run(unbalance + [100, 0])
        trial_b = run(unbalance + [0, 100])
        calibration = influence_matrix(baseline.coefficient, trial_a.coefficient,
                                       trial_b.coefficient, 100, 100)
        before = serialize(unbalance, baseline, calibration)
        c = np.array(before["solver"]["correction_real"]) + 1j * np.array(before["solver"]["correction_imag"])
        after_unbalance = unbalance + c
        after = serialize(after_unbalance, run(after_unbalance), calibration)
        scenarios.append(dict(id=key, label=label, before=before, after=after,
                              injected_real=unbalance.real.tolist(), injected_imag=unbalance.imag.tolist()))
    return dict(data_kind="synthetic", hardware_connected=False, rpm=rpm, seconds=seconds,
                sample_rate_hz=rate, model_moving_mass_kg=mass, seed=52840,
                model_note="Illustrative 15 kg model; flywheel/pulley mass and real inertias are unknown.",
                angle_convention="0 degrees at top, clockwise, both planes viewed from A towards B",
                channel_units=["m/s2", "m/s2", "rad/s", "rad/s"], geometry=geometry, scenarios=scenarios)


def make_server(port=0):
    payload = json.dumps(build_demo(), ensure_ascii=False, allow_nan=False).encode("utf-8")
    assets = files("balancing_host").joinpath("demo_assets")
    routes = {"/": ("index.html", "text/html; charset=utf-8"),
              "/demo.js": ("demo.js", "text/javascript; charset=utf-8"),
              "/model.js": ("model.js", "text/javascript; charset=utf-8"),
              "/styles.css": ("styles.css", "text/css; charset=utf-8")}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/demo":
                data, content_type = payload, "application/json; charset=utf-8"
            elif self.path in routes:
                name, content_type = routes[self.path]
                data = assets.joinpath(name).read_bytes()
            elif self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    # Deliberately fixed to loopback. Only four bundled assets and synthetic JSON.
    return HTTPServer(("127.0.0.1", port), Handler)


def serve_demo(port=0, open_browser=False):
    with make_server(port) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"SYNTHETIC DEMO: {url}", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

"""Conservative single-source offline 1x report from verified BLC1 captures."""

import hashlib
from pathlib import Path

import numpy as np

from .analysis import fft_spectrum, harmonic_fit, phase_from_index, phase_from_teeth, synchronous_average
from .protocol import require
from .recording import inspect_recording, replay


def rational(value):
    require(isinstance(value, dict) and set(value) == {"numerator", "denominator"}, "unknown channel scale")
    require(type(value["numerator"]) is int and type(value["denominator"]) is int
            and value["denominator"] > 0 and value["numerator"] > 0, "invalid channel scale")
    return value["numerator"] / value["denominator"]


def analyze_capture(path, *, sensor_id=0, max_samples=2000000):
    path = Path(path)
    raw = path / "raw.blc" if path.is_dir() else path
    check = inspect_recording(raw)
    require(check["archive_hash_matches"] is not False, "archive hash does not match finalized metadata")
    require(check["semantic_issues"] == 0 and set(check["decoder_counts"]) <= {"frames"},
            "capture has integrity/quality errors; select and validate a clean segment first")
    require(check["session"]["orderly_end_received"], "capture has no validated END")
    configurations, keys = {}, set()
    samples, teeth, indices = [], [], []
    for event in replay(raw):
        value = event["payload"]
        if "config" in event:
            key = event["session_uuid"], value["revision"], value["epoch"]
            configurations[key] = event["config"]
            require(len(configurations) <= 16, "too many epochs; split capture before analysis")
        if event["kind"] not in ("SAMPLES", "EDGES"):
            continue
        require(event["eligible"], "capture contains an ineligible data frame")
        key = event["session_uuid"], value["revision"], value["epoch"]
        keys.add(key)
        require(len(keys) == 1, "multiple sessions/configs/epochs; select one before analysis")
        for record in value["records"]:
            if event["kind"] == "SAMPLES" and record["source"] == sensor_id:
                samples.append(record)
            elif event["kind"] == "EDGES":
                (teeth if record["source"] == 0 else indices).append(record)
        require(len(samples) + len(teeth) + len(indices) <= max_samples, "offline analysis sample limit exceeded")
    require(len(keys) == 1 and samples, "selected source has no measurements")
    config = configurations[next(iter(keys))]
    sensor = next(s for s in config["sensors"] if s["id"] == sensor_id)
    require(len(indices) >= 3, "at least three revolution indices required")
    phase_config = {p["id"]: p for p in config["phase_inputs"]}
    require(1 in phase_config and phase_config[1]["ppr"] == 1, "one index per revolution required")
    require(0 not in phase_config or teeth, "configured tooth input has no events")
    if teeth:
        require(phase_config[0]["rotation_sign"] == phase_config[1]["rotation_sign"],
                "phase inputs disagree on rotation direction")
    direction = phase_config[1]["rotation_sign"]
    zero = phase_config[1]["zero_angle_udeg"] * np.pi / 180000000
    index_times = [r["timestamp_us"] / 1000000 for r in indices]
    if teeth:
        phase = phase_from_teeth([r["timestamp_us"] / 1000000 for r in teeth],
                                 [r["sequence"] for r in teeth], index_times,
                                 [r["sequence"] for r in indices], ppr=phase_config[0]["ppr"],
                                 direction=direction, zero_angle_rad=zero)
    else:
        phase = phase_from_index(index_times, [r["sequence"] for r in indices], direction=direction,
                                 zero_angle_rad=zero)
    times = np.array([r["timestamp_us"] for r in samples]) / 1000000
    counts = np.array([r["counts"] for r in samples], dtype=float)
    axis_map = np.array(sensor["axis_map"], dtype=float)
    require(axis_map.shape == (3, 3) and np.allclose(axis_map @ axis_map.T, np.eye(3), atol=1e-8)
            and np.isclose(np.linalg.det(axis_map), 1), "unverified axis transformation")
    acceleration = (counts[:, :3] * rational(sensor["scale"]["accel_g"])) @ axis_map.T
    channels = ["acc_x_g", "acc_y_g", "acc_z_g"]
    delays = [sensor["filter_delay_us"]["accel"]] * 3
    values = acceleration
    if sensor["channel_mask"] == 63:
        gyro = (counts[:, 3:] * rational(sensor["scale"]["gyro_dps"])) @ axis_map.T
        values = np.column_stack([values, gyro])
        channels += ["gyro_x_dps", "gyro_y_dps", "gyro_z_dps"]
        delays += [sensor["filter_delay_us"]["gyro"]] * 3
    require(all(type(delay) is int and delay >= 0 for delay in delays), "unknown filter delay")
    quality = np.array([r["quality"] for r in samples])
    estimate = harmonic_fit(times, values, phase, quality=quality, delays_s=np.array(delays) / 1000000)
    valid = (times >= phase.times[0]) & (times <= phase.times[-1])
    rpm = np.abs(phase.evaluate(times[valid], 1)) * 60 / (2 * np.pi)
    stationary = float(np.std(rpm) / np.mean(rpm)) <= 0.01
    grid, average, turns = synchronous_average(times, values, phase, delays_s=np.array(delays) / 1000000)
    result = dict(data_kind="synthetic" if config["simulated"] else "physical_unverified",
                  source_id=sensor_id, channels=channels, raw_sha256=check["sha256"],
                  session_uuid=next(iter(keys))[0], config_revision=next(iter(keys))[1], time_epoch=next(iter(keys))[2],
                  phase_method=phase.method, rotation_sign_assumed=direction, rpm_mean=float(np.mean(rpm)),
                  rpm_relative_std=float(np.std(rpm) / np.mean(rpm)), stationary=stationary,
                  harmonic=estimate.as_dict(), synchronous_turns=len(turns),
                  filter_delays_s=(np.array(delays) / 1000000).tolist(),
                  synchronous_delay_compensated=True,
                  synchronous_angle_rad=grid.tolist(), synchronous_mean=average.tolist(),
                  interpretation="sensor mounting motion, not absolute crank angle or mass distribution")
    if stationary:
        frequency, amplitude = fft_spectrum(times[valid], values[valid, 0])
        selected = (frequency > np.mean(rpm) / 60 * 0.8) & (frequency < np.mean(rpm) / 60 * 1.2)
        if np.any(selected):
            positions = np.flatnonzero(selected)
            peak = positions[np.argmax(amplitude[selected])]
            result["fft_1x"] = dict(frequency_hz=float(frequency[peak]), amplitude_peak=float(amplitude[peak]))
    return result

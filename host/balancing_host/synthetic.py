"""Explicitly artificial BLC1 source. Never label its output as bench/rotor."""

import hashlib
import heapq
import math

from .protocol import END, Frame, Type, batch_payload, canonical_json, config_chunks, require

SYNTHETIC_UUID = "00112233445566778899aabbccddeeff"


def synthetic_config():
    sensors = []
    for identifier in range(4):
        bmi = identifier % 2 == 0
        sensor = dict(id=identifier, model="BMI160" if bmi else "LIS3DH", chip_id=209 if bmi else 51,
                      location="A" if identifier < 2 else "B", channel_mask=63 if bmi else 7,
                      odr_hz={"accel": {"numerator": 800 if bmi else 1344, "denominator": 1},
                              "gyro": {"numerator": 800, "denominator": 1} if bmi else None},
                      acc_range_g=2, gyro_range_dps=250 if bmi else None, power_mode="synthetic",
                      filters={"accel": "synthetic_no_filter", "gyro": "synthetic_no_filter" if bmi else None},
                      counts_format="bmi_i16" if bmi else "lis_hr_i12_sign_extended",
                      scale={"accel_g": {"numerator": 1, "denominator": 16384 if bmi else 1000},
                             "gyro_dps": {"numerator": 1, "denominator": 131} if bmi else None},
                      axis_map=[[1, 0, 0], [0, 1, 0], [0, 0, 1]], register_readback={},
                      timestamp_source="hardware_drdy", filter_delay_us={"accel": 0, "gyro": 0 if bmi else None})
        sensors.append(sensor)
    return dict(profile_id="synthetic-four-sensor-v1", schema=1, spi_hz=4000000,
                sensor_layout_revision="synthetic-v1", mounting_revision="synthetic-v1",
                mechanics_revision="synthetic-no-rig", drive_revision="synthetic-no-drive",
                sensors=sensors,
                phase_inputs=[dict(id=i, role="tooth" if i == 0 else "index", ppr=60 if i == 0 else 1,
                                   edge="rising", rotation_sign=1, zero_angle_udeg=0,
                                   conditioning_revision="synthetic-perfect") for i in range(2)],
                capture=dict(timer_tick_ns=1000, timestamp_source="hardware_drdy", epoch_policy="new_on_start",
                             spi_timeout_us=200),
                queues=dict(tx_bytes=65536, capture_slots=256, gap_slots=32, policy="drop_newest"),
                transport="usb_cdc", simulated=True)


def hello_payload(config=None, uuid=SYNTHETIC_UUID):
    config = config or synthetic_config()
    return canonical_json(dict(session_uuid=uuid, protocol=1, firmware_git="unknown",
                               firmware_build_id="unknown", board_id="synthetic-not-a-board", boot_reason="power_on",
                               time_epoch=1, config_revision=1,
                               config_sha256=hashlib.sha256(canonical_json(config)).hexdigest(), max_payload=1024,
                               timestamp_tick_ns=1000, simulated=True, next_request_id=1))


def stream(seconds=2.0, rpm=600.0, *, uuid=SYNTHETIC_UUID):
    require(math.isfinite(seconds) and 0 < seconds <= 86400, "invalid synthetic duration")
    require(math.isfinite(rpm) and 60 <= rpm <= 3000, "invalid synthetic RPM")
    sequence = 0

    def frame(kind, payload, time_us=0):
        nonlocal sequence
        value = Frame(kind, sequence, time_us, payload, 1).encode()
        sequence = (sequence + 1) & 0xFFFFFFFF
        return value

    config = synthetic_config()
    yield frame(Type.HELLO, hello_payload(config, uuid))
    for chunk in config_chunks(config):
        yield frame(Type.CONFIG, chunk)
    frequencies = [800.0, 1344.0, 800.0, 1344.0, rpm, rpm / 60]
    queue = [(0.0, source, 0) for source in range(6)]
    heapq.heapify(queue)
    samples, edges = [], []
    batch_start = 0.0
    last_timestamp = 0
    while queue:
        time_s, source, index = heapq.heappop(queue)
        if time_s >= seconds:
            break
        timestamp = 1000000 + round(time_s * 1000000)
        last_timestamp = timestamp
        if source < 4:
            scale = 16384 if source % 2 == 0 else 1000
            theta = 2 * math.pi * (rpm / 60) * time_s
            phase = 0.35 + 0.15 * source
            values = [round(scale * 0.03 * math.cos(theta + phase + 0.4 * axis)) for axis in range(3)]
            values[2] += scale  # Artificial gravity/DC offset, within the selected range.
            gyro = [round(131 * 0.1 * math.cos(theta + phase))] * 3 if source % 2 == 0 else [0, 0, 0]
            samples.append((source, 63 if source % 2 == 0 else 7, 0, index, timestamp, *values, *gyro))
        else:
            edges.append((timestamp, index, 0, source - 4, 1))
        heapq.heappush(queue, ((index + 1) / frequencies[source], source, index + 1))
        if time_s - batch_start >= 0.004 or len(samples) == 36 or len(edges) == 63:
            if samples:
                yield frame(Type.SAMPLES, batch_payload(Type.SAMPLES, samples), min(r[4] for r in samples))
                samples.clear()
            if edges:
                yield frame(Type.EDGES, batch_payload(Type.EDGES, edges), min(r[0] for r in edges))
                edges.clear()
            batch_start = time_s
    if samples:
        yield frame(Type.SAMPLES, batch_payload(Type.SAMPLES, samples), min(r[4] for r in samples))
    if edges:
        yield frame(Type.EDGES, batch_payload(Type.EDGES, edges), min(r[0] for r in edges))
    last_data = sequence - 1
    yield frame(Type.END, END.pack(bytes.fromhex(uuid), 1, 1, last_data, 0, 1, last_timestamp, 0, 0), last_timestamp)

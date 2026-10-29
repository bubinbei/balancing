"""Optional USB CDC adapter. No port discovery, reset, or motor control."""

import math
from pathlib import Path
import time

from .commands import CommandClient
from .protocol import ACK, Frame, ProtocolError, Type, canonical_json, require
from .recording import Recorder


def record_serial(port, output, seconds, data_kind, *, start=False, serial_factory=None):
    require(math.isfinite(seconds) and 0 < seconds <= 86400, "invalid recording duration")
    require(data_kind in ("bench", "rotor"), "physical transport requires bench or rotor data kind")
    require(not Path(output).exists(), "output already exists")
    if serial_factory is None:
        from serial import Serial
        serial_factory = Serial
    client = CommandClient()
    requested_config = requested_start = False
    accepted_start = False
    config_digest = None
    with serial_factory(port=port, baudrate=115200, timeout=0.1, write_timeout=0.2) as serial:
        # A virtual CDC baud rate is not a claim about UART throughput.
        with Recorder(output, data_kind) as recorder:
            began = time.monotonic()

            def receive(data):
                nonlocal requested_config, requested_start, accepted_start, config_digest
                for event in recorder.append(data):
                    payload = event["payload"]
                    if event["kind"] == "HELLO":
                        require(not payload["simulated"], "physical capture received synthetic HELLO")
                        if client.uuid != payload["session_uuid"]:
                            require(not requested_start, "device reset during acquisition")
                            client.identify(payload)
                    if event["kind"] == "ACK":
                        body = canonical_json(payload["body"])
                        ack = ACK.pack(bytes.fromhex(payload["session_uuid"]), payload["request_id"],
                                       payload["opcode"], payload["status"], payload["revision"], len(body), 0) + body
                        answer = client.acknowledge(Frame(Type.ACK, 0, 0, ack))
                        if answer is not None and answer["status"]:
                            raise ProtocolError(f"Device refused command: {answer['status']}")
                        if answer is not None and answer["opcode"] == 4 and answer["status"] == 0:
                            accepted_start = True
                    if "config_sha256" in event:
                        config_digest = event["config_sha256"]
                    if start and recorder.session.uuid is not None and client.pending is None:
                        if not requested_config:
                            client.prepare(2)
                            requested_config = True
                        elif config_digest is not None and not requested_start:
                            client.prepare(4, recorder.session.config_key[0], {"config_sha256": config_digest})
                            requested_start = True

            def send_pending():
                if client.pending is not None:
                    data = client.poll(time.monotonic())
                    if data is not None:
                        written = serial.write(data)
                        require(written == len(data), "partial USB command write; outcome uncertain")

            try:
                while time.monotonic() - began < seconds:
                    receive(serial.read(8192))
                    if start and recorder.session.uuid is None and time.monotonic() - began > 5:
                        raise ProtocolError("No HELLO received within 5 seconds")
                    send_pending()
            finally:
                if accepted_start and not client.uncertain and client.pending is None:
                    client.prepare(5)
                    deadline = time.monotonic() + 1
                    while time.monotonic() < deadline and not recorder.session.ended:
                        send_pending()
                        receive(serial.read(8192))

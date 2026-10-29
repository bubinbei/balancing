"""Control-only emulated USB peer; never opens a real serial port.

The peer uses physical-mode wire flags to exercise that branch of the host.
It emits no sensor measurements. Temporary archives are test artefacts only.
"""

from collections import deque
import json
from pathlib import Path
import tempfile
import unittest

from balancing_host.protocol import ACK, END, Decoder, Frame, Type, canonical_json, config_chunks, decode_payload
from balancing_host.recording import inspect_recording
from balancing_host.synthetic import SYNTHETIC_UUID, hello_payload, synthetic_config
from balancing_host.transport import record_serial


class FakeControlPort:
    def __init__(self, reject_start=False):
        self.queue = deque()
        self.sequence = 0
        self.epoch = 1
        self.start_calls = self.stop_calls = 0
        self.reject_start = reject_start
        self.closed = False
        self.config = synthetic_config()
        self.config["simulated"] = False
        hello = json.loads(hello_payload(self.config))
        hello["simulated"] = False
        self.emit(Type.HELLO, canonical_json(hello))

    def factory(self, **options):
        assert options["port"] == "EMULATED_CONTROL_ONLY"
        return self

    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True

    def emit(self, kind, payload):
        self.queue.append(Frame(kind, self.sequence, 0, payload).encode())
        self.sequence += 1

    def read(self, size):
        return self.queue.popleft() if self.queue else b""

    def write(self, data):
        frames = list(Decoder().feed(data))
        assert len(frames) == 1
        command = decode_payload(frames[0])
        opcode, identifier = command["opcode"], command["request_id"]
        status = 4 if opcode == 4 and self.reject_start else 0
        body = b"{}"
        if opcode == 4:
            self.start_calls += 1
            if status == 0:
                self.epoch = 2
                body = canonical_json({"time_epoch": 2})
        if opcode == 5:
            self.stop_calls += 1
        self.emit(Type.ACK, ACK.pack(bytes.fromhex(SYNTHETIC_UUID), identifier, opcode, status,
                                     1, len(body), 0) + body)
        if opcode == 2 or opcode == 4 and status == 0:
            for chunk in config_chunks(self.config, epoch=self.epoch):
                self.emit(Type.CONFIG, chunk)
        if opcode == 5:
            self.emit(Type.END, END.pack(bytes.fromhex(SYNTHETIC_UUID), 1, self.epoch,
                                        0, 0, 17, 0, 0, 0))
        return len(data)


class TransportTests(unittest.TestCase):
    def test_handshake_start_stop_without_hardware(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "control-test"
            port = FakeControlPort()
            record_serial("EMULATED_CONTROL_ONLY", output, 0.1, "bench", start=True,
                          serial_factory=port.factory)
            self.assertTrue(port.closed)
            self.assertEqual((port.start_calls, port.stop_calls), (1, 1))
            result = inspect_recording(output / "raw.blc")
            self.assertTrue(result["session"]["orderly_end_received"])
            self.assertEqual(result["semantic_issues"], 0)

    def test_refused_start_does_not_claim_or_stop_a_started_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            port = FakeControlPort(reject_start=True)
            with self.assertRaisesRegex(ValueError, "refused command"):
                record_serial("EMULATED_CONTROL_ONLY", Path(temporary) / "control-test",
                              0.1, "bench", start=True, serial_factory=port.factory)
            self.assertTrue(port.closed)
            self.assertEqual((port.start_calls, port.stop_calls), (1, 0))


if __name__ == "__main__":
    unittest.main()

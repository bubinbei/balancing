import hashlib
import json
from pathlib import Path
import struct
import unittest
import zlib

from balancing_host.protocol import (ACK, COMMAND, CONFIG, COUNTERS, END, GAP, HEADER,
                                     PREFIX, STATUS, Decoder, Frame, ProtocolError, Type,
                                     batch_payload, canonical_json, config_chunks,
                                     decode_json, decode_payload)
from balancing_host.session import ConfigAssembly, Session
from balancing_host.synthetic import hello_payload, stream, synthetic_config


class WireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parents[1] / "fixtures/synthetic/protocol-vectors.json"
        cls.golden = json.loads(path.read_text(encoding="utf-8"))

    def test_independent_vectors(self):
        self.assertEqual(self.golden["crc_check_123456789"], "cbf43926")
        for vector in self.golden["vectors"]:
            raw = bytes.fromhex(vector["raw_hex"])
            frames = list(Decoder().feed(raw))
            self.assertEqual(len(frames), 1, vector["name"])
            frame = frames[0]
            self.assertEqual(frame.payload.hex(), vector["payload_hex"])
            self.assertEqual(frame.sequence, vector["sequence"])
            self.assertEqual(frame.timestamp_us, vector["timestamp_us"])
            self.assertEqual(frame.encode(), raw)
            if "counts" in vector:
                self.assertEqual(decode_payload(frame)["records"][0]["counts"], vector["counts"])
        self.assertEqual(len(bytes.fromhex(self.golden["vectors"][-1]["raw_hex"])), 1052)

    def test_every_split_position(self):
        for vector in self.golden["vectors"]:
            raw = bytes.fromhex(vector["raw_hex"])
            for position in range(len(raw) + 1):
                decoder = Decoder()
                frames = list(decoder.feed(raw[:position])) + list(decoder.feed(raw[position:]))
                decoder.finish()
                self.assertEqual(len(frames), 1)
                self.assertEqual(list(decoder.issues), [])

    def test_corruption_resynchronizes_and_magic_is_not_a_delimiter(self):
        original = Frame(200, 1, 0, b"hello BLC1 inside").encode()
        bad = bytearray(original)
        bad[-1] ^= 1
        fake = HEADER.pack(b"BLC1", 1, 200, 0, 65535, 0, 0, 0)
        decoder = Decoder()
        frames = list(decoder.feed(b"noise" + bad + fake + original * 2))
        self.assertEqual([f.sequence for f in frames], [1, 1])
        self.assertGreater(decoder.counts["crc"], 0)
        self.assertGreater(decoder.counts["length"], 0)

    def test_incompatible_header_is_not_accepted(self):
        for offset, value in ((4, 2), (6, 4), (10, 1)):
            raw = bytearray(Frame(200, 1, 0, b"").encode())
            raw[offset] = value
            raw[-4:] = struct.pack("<I", zlib.crc32(raw[:-4]))
            decoder = Decoder()
            self.assertEqual(list(decoder.feed(raw)), [])
            self.assertEqual(decoder.counts["incompatible_header"], 1)

    def test_decoder_memory_and_recent_diagnostics_are_bounded(self):
        decoder = Decoder()
        self.assertEqual(sum(1 for _ in decoder.feed(b"x" * 5000000)), 0)
        self.assertLessEqual(decoder.high_water, 16384)
        self.assertLessEqual(len(decoder.issues), 64)
        self.assertLessEqual(len(decoder.buffer), 3)
        decoder.finish()
        self.assertEqual(decoder.counts["partial_tail"], 1)

    def test_json_limits_and_canonical_form(self):
        self.assertEqual(canonical_json({"z": "\U0001d11e", "a": 2}), b'{"a":2,"z":"\\ud834\\udd1e"}')
        for data in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":' + b'[' * 12 + b'0' + b']' * 12 + b'}'):
            with self.assertRaises(ProtocolError):
                decode_json(data)
        for value in ({"x": 1.5}, {"x": [0] * 33}, {"x": "a" * 257}):
            with self.assertRaises(ProtocolError):
                canonical_json(value)
        with self.assertRaises(ProtocolError):
            decode_json(b'{ "x": 1}', canonical=True)

    def test_invalid_record_and_count(self):
        sample = (1, 7, 0, 0, 100, 1, 2, 3, 9, 0, 0)
        frame = Frame(Type.SAMPLES, 0, 100, batch_payload(Type.SAMPLES, [sample]))
        with self.assertRaises(ProtocolError):
            decode_payload(frame)
        frame = Frame(Type.SAMPLES, 0, 100, PREFIX.pack(1, 1, 36, 28, 0))
        with self.assertRaises(ProtocolError):
            decode_payload(frame)

    def test_remaining_payload_types(self):
        uuid = bytes.fromhex("00112233445566778899aabbccddeeff")
        payloads = [(Type.STATUS, STATUS.pack(1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0) + b"\0" * 64),
                    (Type.GAP, GAP.pack(1, 1, 1, 0, 4, 8, 1, 0, 100, 100)),
                    (Type.COMMAND, COMMAND.pack(uuid, 1, 1, 4, 2, 0, 0) + b"{}"),
                    (Type.ACK, ACK.pack(uuid, 1, 4, 0, 1, 2, 0) + b"{}"),
                    (Type.END, END.pack(uuid, 1, 1, 0, 0, 17, 0, 0, 0))]
        for kind, payload in payloads:
            frames = list(Decoder().feed(Frame(kind, 0, 0, payload, 1).encode()))
            self.assertEqual(len(frames), 1)
            self.assertIsInstance(decode_payload(frames[0]), dict)

    def test_config_chunks_duplicate_conflict_timeout_and_hash(self):
        chunks = [decode_payload(Frame(Type.CONFIG, i, 0, p, 1))
                  for i, p in enumerate(config_chunks(synthetic_config()))]
        assembly = ConfigAssembly()
        self.assertIsNone(assembly.add(chunks[0], 0))
        self.assertIsNone(assembly.add(chunks[0], 0.1))
        with self.assertRaises(ProtocolError):
            assembly.add({**chunks[0], "chunk": b"X" + chunks[0]["chunk"][1:]}, 0.2)
        assembly = ConfigAssembly()
        assembly.add(chunks[0], 0)
        with self.assertRaises(ProtocolError):
            assembly.add(chunks[1], 2.01)
        assembly = ConfigAssembly()
        for chunk in chunks[:-1]:
            assembly.add(chunk, 0)
        with self.assertRaises(ProtocolError):
            assembly.add({**chunks[-1], "chunk": chunks[-1]["chunk"][:-1] + b"X"}, 0)

    def test_full_session_and_raw_sequence_wrap(self):
        session, decoder = Session(), Decoder()
        events = [session.consume(f) for raw in stream(0.05) for f in decoder.feed(raw)]
        self.assertTrue(session.ended)
        self.assertTrue(any(e["eligible"] for e in events))
        self.assertEqual([e for e in events if e["issues"] and e["kind"] != "HELLO"], [])
        self.assertLessEqual(len(session.sources), 6)
        from balancing_host.session import sequence_issue
        self.assertIsNone(sequence_issue(0xFFFFFFFF, 0, "test"))
        self.assertEqual(sequence_issue(1, 3, "test")["missing"], 1)

    def test_no_config_and_session_reset(self):
        decoder, session = Decoder(), Session()
        frame = Frame(Type.SAMPLES, 0, 100, batch_payload(Type.SAMPLES, [(0, 7, 0, 0, 100, 1, 2, 3, 0, 0, 0)]), 1)
        self.assertFalse(session.consume(frame)["eligible"])
        for raw in stream(0.01):
            for frame in decoder.feed(raw):
                session.consume(frame)
        for raw in stream(0.01, uuid="ffeeddccbbaa99887766554433221100"):
            for frame in decoder.feed(raw):
                event = session.consume(frame)
        self.assertTrue(session.ended)
        self.assertEqual(event["issues"], [])


if __name__ == "__main__":
    unittest.main()

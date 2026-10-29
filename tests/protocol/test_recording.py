import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from balancing_host.commands import CommandClient
from balancing_host.protocol import ACK, Frame, ProtocolError, Type
from balancing_host.recording import Recorder, inspect_recording, replay, write_all
from balancing_host.synthetic import SYNTHETIC_UUID, hello_payload, stream


class RecordingTests(unittest.TestCase):
    def test_raw_bytes_replay_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "capture"
            raw = b"".join(stream(0.05))
            with Recorder(directory, "synthetic") as recorder:
                received = []
                for offset in range(0, len(raw), 113):
                    received.extend(recorder.append(raw[offset:offset + 113]))
            self.assertEqual((directory / "raw.blc").read_bytes(), raw)
            self.assertEqual(list(replay(directory / "raw.blc", chunk_size=71)), received)
            metadata = json.loads((directory / "metadata.json").read_text())
            self.assertEqual(metadata["raw_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(metadata["data_kind"], "synthetic")
            with self.assertRaises(FileExistsError):
                Recorder(directory, "synthetic")

    def test_corrupt_bytes_and_incomplete_tail_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "capture"
            raw = b"garbage" + b"".join(stream(0.02))[:-3]
            with Recorder(directory, "synthetic") as recorder:
                list(recorder.append(raw))
            self.assertEqual((directory / "raw.blc").read_bytes(), raw)
            summary = inspect_recording(directory / "raw.blc")
            self.assertFalse(summary["session"]["orderly_end_received"])
            self.assertIn("partial_tail", summary["decoder_counts"])
            diagnostics = []
            list(replay(directory / "raw.blc", on_issue=diagnostics.append))
            self.assertIn("garbage", {issue["code"] for issue in diagnostics})
            self.assertIn("partial_tail", {issue["code"] for issue in diagnostics})

    def test_finalized_hash_mismatch_is_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "capture"
            with Recorder(directory, "synthetic") as recorder:
                for packet in stream(0.01):
                    list(recorder.append(packet))
            path = directory / "metadata.json"
            metadata = json.loads(path.read_text())
            metadata["raw_sha256"] = "0" * 64
            path.write_text(json.dumps(metadata))
            self.assertFalse(inspect_recording(directory / "raw.blc")["archive_hash_matches"])

    def test_degraded_end_is_not_a_clean_capture(self):
        from balancing_host.protocol import Decoder, END
        from balancing_host.cli import valid_capture
        for flags, pending in ((0, 0), (3, 0), (5, 0), (9, 0), (1, 2)):
            with self.subTest(flags=flags, pending=pending), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary) / "capture"
                packets = list(stream(0.01))
                original = list(Decoder().feed(packets[-1]))[0]
                fields = list(END.unpack(original.payload))
                fields[5], fields[7] = flags, pending
                packets[-1] = Frame(Type.END, original.sequence, original.timestamp_us,
                                     END.pack(*fields), 1).encode()
                with Recorder(directory, "synthetic") as recorder:
                    for packet in packets:
                        list(recorder.append(packet))
                summary = inspect_recording(directory / "raw.blc")
                self.assertFalse(valid_capture(summary))
                self.assertTrue(summary["session"]["had_gaps"])

    def test_short_writes_are_completed(self):
        class ShortWriter:
            def __init__(self): self.data = bytearray()
            def write(self, data):
                self.data.extend(data[:3])
                return min(3, len(data))
        output = ShortWriter()
        write_all(output, b"abcdefghijklmn")
        self.assertEqual(output.data, b"abcdefghijklmn")

    def test_replay_preserves_config_timeout_arrival_clock(self):
        from balancing_host.protocol import Decoder
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "capture"
            clock = [0.0]
            packets = list(stream(0.01))
            with Recorder(directory, "synthetic", clock=lambda: clock[0]) as recorder:
                events = []
                events.extend(recorder.append(packets[0]))
                events.extend(recorder.append(packets[1]))
                clock[0] = 3.0
                for packet in packets[2:]:
                    events.extend(recorder.append(packet))
            rebuilt = list(replay(directory / "raw.blc"))
            self.assertEqual(rebuilt, events)
            self.assertTrue(any("timeout" in str(e["issues"]) for e in rebuilt))

    def test_disk_write_failure_preserves_exact_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "capture"
            recorder = Recorder(directory, "synthetic")
            original = recorder.raw
            class FailWriter:
                remaining = 29
                def write(self, data):
                    if not self.remaining:
                        raise OSError("injected disk full")
                    n = min(self.remaining, len(data))
                    self.remaining -= n
                    return original.write(data[:n])
                def fileno(self): return original.fileno()
                def close(self): return original.close()
            recorder.raw = FailWriter()
            raw = b"".join(stream(0.01))
            with self.assertRaises(OSError):
                with recorder:
                    list(recorder.append(raw))
            self.assertEqual((directory / "raw.blc").read_bytes(), raw[:29])
            self.assertEqual(recorder.bytes, 29)
            self.assertTrue(recorder.closed)

    def test_crash_leaves_recoverable_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "crashed"
            code = ("import os,sys; from balancing_host.recording import Recorder; "
                    "from balancing_host.synthetic import stream; r=Recorder(sys.argv[1],'synthetic'); "
                    "[list(r.append(x)) for x in list(stream(0.01))[:-1]]; r.sync(); os._exit(23)")
            result = subprocess.run([sys.executable, "-c", code, str(directory)], capture_output=True)
            self.assertEqual(result.returncode, 23, result.stderr)
            result = inspect_recording(directory / "raw.blc")
            self.assertGreater(result["bytes"], 0)
            self.assertFalse(result["session"]["orderly_end_received"])
            self.assertEqual(json.loads((directory / "metadata.json").read_text())["status"], "recording")

    def test_physical_label_does_not_make_synthetic_data_real(self):
        with tempfile.TemporaryDirectory() as temporary:
            with Recorder(Path(temporary) / "capture", "bench") as recorder:
                events = [e for raw in stream(0.01) for e in recorder.append(raw)]
            self.assertTrue(all(not e["eligible"] for e in events))

    def test_reset_after_data_preserves_missing_previous_end(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "reset"
            first = list(stream(0.01))[:-1]
            second = list(stream(0.01, uuid="ffeeddccbbaa99887766554433221100"))
            with Recorder(directory, "synthetic") as recorder:
                events = [e for packet in first + second for e in recorder.append(packet)]
            self.assertTrue(any(i["code"] == "previous_session_incomplete" for e in events for i in e["issues"]))
            result = inspect_recording(directory / "raw.blc")
            self.assertGreater(result["semantic_issues"], 0)
            self.assertTrue(result["session"]["had_gaps"])


class CommandTests(unittest.TestCase):
    def client(self):
        client = CommandClient()
        client.identify(json.loads(hello_payload()))
        return client

    def test_finite_identical_retries_and_uncertain_result(self):
        client = self.client()
        client.prepare(4, 1, {"config_sha256": "0" * 64})
        transmissions = [client.poll(float(i)) for i in range(4)]
        self.assertEqual(len(set(transmissions)), 1)
        with self.assertRaises(ProtocolError):
            client.poll(4)
        with self.assertRaises(ProtocolError):
            client.prepare(4)

    def test_ack_matches_uuid_id_opcode(self):
        client = self.client()
        client.prepare(5)
        client.poll(0)
        def ack(identifier):
            return Frame(Type.ACK, 0, 0, ACK.pack(bytes.fromhex(SYNTHETIC_UUID), identifier, 5, 0, 1, 2, 0) + b"{}")
        self.assertIsNone(client.acknowledge(ack(99)))
        self.assertIsNotNone(client.acknowledge(ack(1)))
        self.assertIsNone(client.pending)
        client.prepare(5)
        self.assertEqual(client.pending.request_id, 2)

    def test_one_pending_and_readonly_id(self):
        client = self.client()
        client.prepare(2)
        self.assertEqual(client.pending.request_id, 0)
        self.assertEqual(client.next_id, 1)
        with self.assertRaises(ProtocolError):
            client.prepare(4)


if __name__ == "__main__":
    unittest.main()

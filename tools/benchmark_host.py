"""Bounded-duration synthetic pipeline benchmark; does not access hardware."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
import uuid

from balancing_host.recording import Recorder, inspect_recording
from balancing_host.synthetic import stream


def benchmark(seconds):
    if not 1 <= seconds <= 120:
        raise ValueError("duration must be 1..120 seconds")
    with tempfile.TemporaryDirectory(prefix="balancing-synthetic-") as temporary:
        directory = Path(temporary) / "capture"
        started = time.perf_counter()
        rounds = 0
        with Recorder(directory, "synthetic") as recorder:
            while time.perf_counter() - started < seconds:
                rounds += 1
                for packet in stream(0.25, rpm=1000, uuid=uuid.UUID(int=rounds).hex):
                    for _ in recorder.append(packet):
                        pass
        elapsed = time.perf_counter() - started
        size = recorder.bytes
        check = inspect_recording(directory / "raw.blc")
        assert check["semantic_issues"] == 0 and set(check["decoder_counts"]) == {"frames"}
        assert check["session"]["orderly_end_received"]
        return dict(data_kind="synthetic", duration_s=elapsed, bytes=size, sessions=rounds,
                    host_source_sha256=recorder.software_hash,
                    encoded_bytes_per_second=size / elapsed, target_bytes_per_second=250000,
                    throughput_target_met=size / elapsed >= 250000,
                    decoder_high_water=recorder.decoder.high_water, decoder_limit=16384,
                    raw_sha256=check["sha256"], semantic_issues=check["semantic_issues"],
                    archive="temporary archive removed after verified replay",
                    scope="short host pipeline benchmark, not 30-minute/90-minute device acceptance")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = benchmark(args.seconds)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as file:
            json.dump(result, file, indent=2)
    print(json.dumps(result, indent=2))
    return 0 if result["throughput_target_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Explicit CLI; importing the package never opens a port or starts hardware."""

import argparse
import json
from pathlib import Path
import sys

from .protocol import ProtocolError
from .recording import Recorder, inspect_recording, replay
from .synthetic import stream


def valid_capture(result):
    return (not result["semantic_issues"]
            and result.get("archive_hash_matches") is not False
            and all(k == "frames" for k in result["decoder_counts"])
            and result["session"]["orderly_end_received"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="BLC1 capture, replay and synthetic verification")
    commands = parser.add_subparsers(dest="command", required=True)
    synth = commands.add_parser("simulate", help="Create explicitly synthetic measurements")
    synth.add_argument("--output", type=Path, required=True, help="New directory; existing paths are refused")
    synth.add_argument("--seconds", type=float, default=2)
    synth.add_argument("--rpm", type=float, default=600)
    inspect = commands.add_parser("inspect", help="Verify raw file without connecting hardware")
    inspect.add_argument("path", type=Path)
    repeat = commands.add_parser("replay", help="Decode raw file into JSONL without repairing bytes")
    repeat.add_argument("path", type=Path)
    repeat.add_argument("--output", type=Path, required=True)
    record = commands.add_parser("record", help="USB capture from an explicitly named port")
    record.add_argument("--port", required=True)
    record.add_argument("--output", required=True, type=Path)
    record.add_argument("--seconds", required=True, type=float)
    record.add_argument("--kind", choices=("bench", "rotor"), required=True)
    record.add_argument("--start", action="store_true", help="Handshake/START/STOP acquisition; never controls a motor")
    analyze = commands.add_parser("analyze", help="Offline 1x and synchronous-average report")
    analyze.add_argument("path", type=Path)
    analyze.add_argument("--source", type=int, choices=range(4), default=0)
    analyze.add_argument("--output", type=Path, required=True)
    solve = commands.add_parser("solve", help="Two-plane correction from explicit calibration/noise JSON")
    solve.add_argument("path", type=Path)
    solve.add_argument("--output", type=Path, required=True)
    size = commands.add_parser("size", help="Mechanical small-angle estimates; not manufacturing approval")
    size.add_argument("path", type=Path)
    size.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "simulate":
            with Recorder(args.output, "synthetic") as recorder:
                for data in stream(args.seconds, args.rpm):
                    for _ in recorder.append(data):
                        pass
            result = inspect_recording(args.output / "raw.blc")
            print(json.dumps(result, indent=2))
            if not valid_capture(result):
                return 1
        elif args.command == "inspect":
            raw = args.path / "raw.blc" if args.path.is_dir() else args.path
            result = inspect_recording(raw)
            print(json.dumps(result, indent=2))
            if not valid_capture(result):
                return 1
        elif args.command == "replay":
            raw = args.path / "raw.blc" if args.path.is_dir() else args.path
            with args.output.open("x", encoding="utf-8", newline="\n") as file:
                def log_issue(issue):
                    file.write(json.dumps({"kind": "HOST_DIAGNOSTIC", **issue}) + "\n")
                for event in replay(raw, on_issue=log_issue):
                    file.write(json.dumps(event, ensure_ascii=True) + "\n")
            print(f"Replay written: {args.output}")
        elif args.command == "record":
            from .transport import record_serial
            record_serial(args.port, args.output, args.seconds, args.kind, start=args.start)
            result = inspect_recording(args.output / "raw.blc")
            print(json.dumps(result, indent=2))
            if not valid_capture(result):
                return 1
        elif args.command == "analyze":
            from .capture_analysis import analyze_capture
            result = analyze_capture(args.path, sensor_id=args.source)
            with args.output.open("x", encoding="utf-8") as file:
                json.dump(result, file, indent=2, allow_nan=False)
            print(f"Analysis written: {args.output}")
        elif args.command == "solve":
            import numpy as np
            from .analysis import solve_correction
            value = json.loads(args.path.read_text(encoding="utf-8"))
            result = solve_correction(np.array(value["H_real"]) + 1j * np.array(value["H_imag"]),
                                      np.array(value["V_real"]) + 1j * np.array(value["V_imag"]),
                                      value["covariance_real"], **value.get("limits", {}))
            result["data_kind"] = value["data_kind"]
            with args.output.open("x", encoding="utf-8") as file:
                json.dump(result, file, indent=2, allow_nan=False)
            print(f"Correction written: {args.output}")
        elif args.command == "size":
            from .mechanics import sizing
            result = sizing(json.loads(args.path.read_text(encoding="utf-8")))
            with args.output.open("x", encoding="utf-8") as file:
                json.dump(result, file, indent=2, allow_nan=False)
            print(f"Model estimates written: {args.output}")
        return 0
    except (OSError, ValueError, ProtocolError, KeyError, TypeError, IndexError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

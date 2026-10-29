"""Append-only raw archive, diagnostics, crash-readable prefix, and replay."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import time

from .protocol import Decoder, ProtocolError, require
from .session import Session


def write_all(file, data):
    view = memoryview(data)
    while view:
        written = file.write(view)
        if not written:
            raise OSError("write made no progress")
        view = view[written:]


class Recorder:
    """Never repairs raw bytes. A new directory is required for every capture.

    fsync is periodic (default one second), and on orderly close. A process/OS
    crash can lose the uncommitted interval; sudden power-loss protection is
    filesystem/device dependent and is not promised by this class.
    """

    def __init__(self, directory, data_kind, *, fsync_interval=1.0, clock=time.monotonic):
        require(data_kind in ("synthetic", "bench", "rotor"), "invalid data kind")
        require(fsync_interval > 0, "fsync interval must be positive")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.clock, self.interval = clock, fsync_interval
        self.last_sync = clock()
        self.raw = self.events = None
        self.closed = False
        self.data_kind = data_kind
        self.bytes = 0
        self.sessions = 0
        self.started = clock()
        self.feed_time = 0.0
        self.digest = hashlib.sha256()
        source_hash = hashlib.sha256()
        for source in sorted(Path(__file__).parent.glob("*.py")):
            source_hash.update(source.name.encode("ascii") + b"\0" + source.read_bytes())
        self.software_hash = source_hash.hexdigest()
        self.session = Session(lambda: self.feed_time)
        self.decoder = Decoder(self._issue)
        try:
            self.raw = (self.directory / "raw.blc").open("xb", buffering=0)
            self.events = (self.directory / "events.jsonl").open("xb", buffering=0)
            self._metadata("recording")
        except BaseException:
            for file in (self.raw, self.events):
                if file is not None:
                    file.close()
            raise

    def _metadata(self, status, **extra):
        value = dict(schema=1, data_kind=self.data_kind, status=status, raw_file="raw.blc",
                     bytes=self.bytes, raw_sha256=self.digest.hexdigest(), sessions=self.sessions,
                     host_source_sha256=self.software_hash, python_version=platform.python_version(),
                     fsync_interval_s=self.interval, decoder_counts=dict(self.decoder.counts),
                     decoder_high_water=self.decoder.high_water, **extra)
        temporary = self.directory / "metadata.tmp"
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(value, file, indent=2, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, self.directory / "metadata.json")

    def _event(self, value):
        write_all(self.events, (json.dumps(value, ensure_ascii=True, separators=(",", ":"),
                                          allow_nan=False) + "\n").encode("ascii"))

    def _issue(self, issue):
        self.session.had_gaps = True
        self._event({"kind": "HOST_DIAGNOSTIC", **issue})

    def append(self, data):
        require(not self.closed, "recorder already closed")
        require(len(data) <= 65536, "input chunk exceeds 64 KiB")
        if not data:
            return
        offset = self.bytes
        self.feed_time = self.clock() - self.started
        # FileIO may make short writes; account for exactly the bytes persisted.
        view = memoryview(data)
        while view:
            written = self.raw.write(view)
            if not written:
                raise OSError("raw write made no progress")
            self.digest.update(view[:written])
            self.bytes += written
            view = view[written:]
        self._event(dict(kind="HOST_CHUNK", offset=offset, size=len(data), elapsed_us=round(self.feed_time * 1000000)))
        self.feed_time = round(self.feed_time * 1000000) / 1000000
        for frame in self.decoder.feed(data):
            event = self.session.consume(frame)
            if event["kind"] == "HELLO" and any(i["code"] == "session_started" for i in event["issues"]):
                self.sessions += 1
            if bool(frame.flags & 1) != (self.data_kind == "synthetic"):
                event["eligible"] = False
                event["issues"].append({"code": "recording_kind_mismatch"})
                self.session.had_gaps = True
            self._event(event)
            yield event
        if self.clock() - self.last_sync >= self.interval:
            self.sync()

    def sync(self):
        for file in (self.raw, self.events):
            os.fsync(file.fileno())
        self.last_sync = self.clock()

    def close(self, *, error=None):
        if self.closed:
            return
        try:
            self.decoder.finish()
            summary = self.session.finish()
            self._event({"kind": "HOST_END", **summary, "error": error})
            self.sync()
            self._metadata("closed" if error is None else "error", session=summary, error=error)
        finally:
            self.closed = True
            for file in (self.raw, self.events):
                if file is not None:
                    file.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.close(error=None if kind is None else str(value))
        except OSError:
            if kind is None:
                raise
        return False


def input_chunks(raw_path, chunk_size):
    """Replay recorded chunk arrival times when the companion journal exists.

    A bare binary file has no host arrival clock: use a constant clock rather
    than accidentally basing protocol timeouts on replay execution speed.
    Unindexed crash tails are returned with timing_known=False.
    """
    path = Path(raw_path)
    events_path = path.with_name("events.jsonl")
    with path.open("rb") as raw:
        elapsed = 0.0
        if path.name == "raw.blc" and events_path.exists():
            with events_path.open("rb") as events:
                while line := events.readline(131073):
                    require(len(line) <= 131072, "journal line exceeds bound")
                    if not line.endswith(b"\n"):
                        break  # Crash tail: raw bytes are still recovered below.
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeError) as exc:
                        raise ProtocolError("invalid companion journal") from exc
                    require(isinstance(event, dict), "journal row is not an object")
                    if event.get("kind") != "HOST_CHUNK":
                        continue
                    require(event["offset"] == raw.tell() and 0 < event["size"] <= 65536,
                            "invalid recorded chunk offset/size")
                    current = event["elapsed_us"] / 1000000
                    require(current >= elapsed, "arrival clock moved backwards")
                    elapsed = current
                    data = raw.read(event["size"])
                    require(len(data) == event["size"], "journal extends beyond raw archive")
                    yield elapsed, data, True
        while data := raw.read(chunk_size):
            yield elapsed, data, False


def replay(raw_path, *, chunk_size=8192, on_issue=None):
    require(1 <= chunk_size <= 65536, "invalid read chunk size")
    now = [0.0]
    decoder, session = Decoder(on_issue), Session(lambda: now[0])
    for elapsed, data, _ in input_chunks(raw_path, chunk_size):
        now[0] = elapsed
        for frame in decoder.feed(data):
            yield session.consume(frame)
    decoder.finish()


def inspect_recording(raw_path, *, chunk_size=8192):
    now = [0.0]
    decoder, session = Decoder(), Session(lambda: now[0])
    raw_hash = hashlib.sha256()
    size = 0
    issue_count = 0
    for elapsed, data, _ in input_chunks(raw_path, chunk_size):
        now[0] = elapsed
        raw_hash.update(data)
        size += len(data)
        for frame in decoder.feed(data):
            event = session.consume(frame)
            issue_count += len([i for i in event["issues"] if i["code"] != "session_started"])
    decoder.finish()
    metadata_path = Path(raw_path).with_name("metadata.json")
    archive_hash_matches = None
    if Path(raw_path).name == "raw.blc" and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("status") in ("closed", "error"):
            archive_hash_matches = metadata.get("bytes") == size and metadata.get("raw_sha256") == raw_hash.hexdigest()
    return dict(bytes=size, sha256=raw_hash.hexdigest(), archive_hash_matches=archive_hash_matches,
                decoder_counts=dict(decoder.counts),
                decoder_high_water=decoder.high_water, semantic_issues=issue_count,
                session=session.finish())

"""Session/configuration and sequence integrity without fabricating measurements."""

from __future__ import annotations

import hashlib
import time

from .protocol import ProtocolError, Type, decode_json, decode_payload, require, validate_config


class ConfigAssembly:
    def __init__(self):
        self.key = None
        self.data = bytearray()
        self.started = 0.0

    def clear(self):
        self.key = None
        self.data.clear()

    def add(self, chunk, now):
        key = (chunk["revision"], chunk["epoch"], chunk["digest"], chunk["total"])
        if self.key is not None and now - self.started > 2:
            self.clear()
            raise ProtocolError("CONFIG assembly timeout")
        if chunk["flags"] & 1 and key != self.key:
            self.clear()
            self.key, self.started = key, now
        require(self.key == key, "CONFIG continuation without matching FIRST")
        offset, data = chunk["offset"], chunk["chunk"]
        if offset < len(self.data):
            require(offset + len(data) <= len(self.data) and self.data[offset:offset + len(data)] == data,
                    "conflicting CONFIG retransmission")
        else:
            require(offset == len(self.data), "nonsequential CONFIG chunk")
            self.data.extend(data)
        require(len(self.data) <= 8192, "CONFIG assembly bound exceeded")
        if chunk["flags"] & 2:
            require(len(self.data) == chunk["total"], "incomplete CONFIG")
            require(hashlib.sha256(self.data).hexdigest() == chunk["digest"], "CONFIG SHA mismatch")
            value = validate_config(decode_json(bytes(self.data), limit=8192, canonical=True))
            self.clear()
            return value
        return None


def sequence_issue(previous, current, label):
    if previous is None:
        return None
    delta = (current - previous) & 0xFFFFFFFF
    if delta == 1:
        return None
    return dict(code=label, previous=previous, received=current,
                missing=delta - 1 if 1 < delta < 2**31 else None,
                classification="hole" if 1 < delta < 2**31 else "duplicate_or_reorder")


class Session:
    """Only one current configuration and bounded per-source state are retained."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.uuid = None
        self.hello = None
        self.simulated = None
        self.config = None
        self.config_key = None
        self.assembly = ConfigAssembly()
        self.last_frame = None
        self.last_data = None
        self.sources = {}
        self.ended = False
        self.end_orderly = False
        self.had_gaps = False
        self.frames = 0
        self.last_totals = {}

    def consume(self, frame):
        value = decode_payload(frame)
        issues = []
        event = dict(kind=Type(frame.kind).name if frame.kind in Type._value2member_map_ else "UNKNOWN",
                     frame_sequence=frame.sequence, timestamp_us=frame.timestamp_us,
                     session_uuid=self.uuid, simulated=bool(frame.flags & 1), eligible=False,
                     issues=issues)
        if frame.kind == Type.HELLO:
            if value["session_uuid"] != self.uuid:
                self.uuid, self.simulated = value["session_uuid"], value["simulated"]
                self.config = self.config_key = None
                self.assembly.clear()
                self.sources.clear()
                self.last_totals.clear()
                self.last_frame = self.last_data = None
                self.ended = self.had_gaps = False
                self.end_orderly = False
                issues.append({"code": "session_started"})
            self.hello = value
            event["session_uuid"] = self.uuid
        problem = sequence_issue(self.last_frame, frame.sequence, "frame_sequence")
        if problem:
            issues.append(problem)
            self.had_gaps = True
        duplicate = problem is not None and problem["classification"] == "duplicate_or_reorder"
        if not duplicate:
            self.last_frame = frame.sequence
        self.frames += 1
        if self.uuid is None:
            issues.append({"code": "no_session"})
        elif bool(frame.flags & 1) != self.simulated:
            issues.append({"code": "mixed_simulation"})
        elif not duplicate:
            try:
                self._consume(frame, value, event)
            except ProtocolError as exc:
                issues.append({"code": "session_error", "detail": str(exc)})
                self.had_gaps = True
        # First HELLO is a normal lifecycle event, not an invalid data window.
        event["eligible"] = (event["eligible"] and not issues)
        event["payload"] = {k: v for k, v in value.items() if k != "chunk"}
        if "chunk" in value:
            event["payload"]["chunk_hex"] = value["chunk"].hex()
        return event

    def _consume(self, frame, value, event):
        if frame.kind == Type.CONFIG:
            config = self.assembly.add(value, self.clock())
            if config is not None:
                require(config["simulated"] == self.simulated, "CONFIG simulated mismatch")
                if value["revision"] == self.hello["config_revision"]:
                    require(value["digest"] == self.hello["config_sha256"], "HELLO/CONFIG hash mismatch")
                if self.config_key is not None:
                    require(value["revision"] >= self.config_key[0] and value["epoch"] >= self.config_key[1],
                            "CONFIG revision/epoch moved backwards")
                new_key = value["revision"], value["epoch"]
                if new_key != self.config_key:
                    self.last_data = None
                    self.ended = False
                    self.end_orderly = False
                self.config = config
                self.config_key = new_key
                event["config"] = config
                event["config_sha256"] = value["digest"]
        elif frame.kind in (Type.SAMPLES, Type.EDGES):
            require(not self.ended, "data after END")
            key = value["revision"], value["epoch"]
            require(self.config is not None and key == self.config_key, "data without current CONFIG")
            group = "sensors" if frame.kind == Type.SAMPLES else "phase_inputs"
            configured = {item["id"]: item for item in self.config[group]}
            for record in value["records"]:
                source = record["source"]
                require(source in configured, "unconfigured source")
                if frame.kind == Type.SAMPLES:
                    require(record["mask"] == configured[source]["channel_mask"], "sample mask differs from CONFIG")
                    if record["quality"]:
                        event["issues"].append({"code": "sample_quality", "source": source,
                                                "quality": record["quality"]})
                else:
                    expected_level = int(configured[source]["edge"] == "rising")
                    require(record["level"] == expected_level, "edge differs from CONFIG")
                    if record["flags"]:
                        event["issues"].append({"code": "edge_quality", "source": source,
                                                "flags": record["flags"]})
                source_key = frame.kind, source
                previous = self.sources.get(source_key)
                if previous:
                    issue = sequence_issue(previous[0], record["sequence"], "source_sequence")
                    if issue:
                        event["issues"].append({**issue, "source": source})
                    if key[1] == previous[1] and record["timestamp_us"] <= previous[2]:
                        event["issues"].append({"code": "source_time", "source": source})
                self.sources[source_key] = record["sequence"], key[1], record["timestamp_us"]
            self.last_data = frame.sequence
            event["eligible"] = True
        elif frame.kind == Type.GAP:
            self.had_gaps = True
            event["issues"].append({"code": "device_gap", "count_unknown": bool(value["flags"] & 1)})
        elif frame.kind == Type.END:
            require(value["session_uuid"] == self.uuid, "END UUID mismatch")
            require(self.config_key == (value["revision"], value["epoch"]), "END epoch/config mismatch")
            require(bool(value["flags"] & 16) == (self.last_data is None), "END NO_DATA mismatch")
            if self.last_data is not None:
                require(value["last_data_sequence"] == self.last_data, "END last data mismatch")
            self.ended = True
            self.end_orderly = bool(value["flags"] & 1)
            if not self.end_orderly or value["flags"] & 14 or value["pending_gaps"]:
                self.had_gaps = True
                event["issues"].append({"code": "end_degraded", "flags": value["flags"],
                                        "pending_gaps": value["pending_gaps"]})
        elif frame.kind == Type.ACK:
            require(value["session_uuid"] == self.uuid, "ACK UUID mismatch")
        elif frame.kind == Type.STATUS:
            totals = dict(value["counters"])
            for group in ("sensors", "inputs"):
                for item in value[group]:
                    for name in ("observed", "valid_reads", "known_dropped", "unknown_losses", "fifo_overruns"):
                        if name in item:
                            totals[f"{group}:{item['source']}:{name}"] = item[name]
            for name, total in totals.items():
                require(total >= self.last_totals.get(name, 0), "STATUS counter regressed: " + name)
            self.last_totals.update(totals)
            if value["health"]:
                event["issues"].append({"code": "device_health", "flags": value["health"]})
        elif frame.kind not in (Type.HELLO, Type.COMMAND):
            event["issues"].append({"code": "unknown_type", "value": frame.kind})

    def finish(self):
        return dict(session_uuid=self.uuid, end_received=self.ended,
                    orderly_end_received=self.ended and self.end_orderly,
                    had_gaps=self.had_gaps, frames=self.frames,
                    status="ended" if self.ended else "incomplete")

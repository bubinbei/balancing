"""BLC1 wire format, bounded JSON, and incrementally resynchronizing decoder."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from enum import IntEnum
import hashlib
import json
import math
import re
import struct
import zlib

MAGIC = b"BLC1"
MAX_PAYLOAD = 1024
MAX_BUFFER = 16384
HEADER = struct.Struct("<4sBBHHHIQ")
PREFIX = struct.Struct("<IIHHI")
SAMPLE = struct.Struct("<BBHIQ6h")
EDGE = struct.Struct("<QIHBB")
CONFIG = struct.Struct("<IIIIHHI32s")
STATUS = struct.Struct("<IIHHHHIIHHI")
SENSOR_STATUS = struct.Struct("<BBHIQQQQII")
INPUT_STATUS = struct.Struct("<BBHIQQII")
GAP = struct.Struct("<IIBBHIIIQQ")
COMMAND = struct.Struct("<16sIIHHHH")
ACK = struct.Struct("<16sIHHIHH")
END = struct.Struct("<16sIIIHHQII")
COUNTERS = ("rx_crc_errors_total", "tx_dropped_frames_total", "spi_timeouts_total",
            "capture_overrun_suspected_total", "invalid_commands_total",
            "usb_stall_events_total", "missing_drdy_windows_total", "time_epoch_resets_total")


class Type(IntEnum):
    HELLO = 1
    CONFIG = 2
    SAMPLES = 3
    EDGES = 4
    STATUS = 5
    GAP = 6
    END = 7
    COMMAND = 128
    ACK = 129


class ProtocolError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProtocolError(message)


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key.isascii(), "JSON keys must be ASCII")
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _tree(value, depth=0, canonical=False):
    require(depth <= 8, "JSON nesting exceeds 8")
    if isinstance(value, dict):
        for key, child in value.items():
            require(isinstance(key, str) and key.isascii() and len(key) <= 256, "invalid JSON key")
            _tree(child, depth + 1, canonical)
    elif isinstance(value, list):
        require(len(value) <= 32, "JSON array exceeds 32")
        for child in value:
            _tree(child, depth + 1, canonical)
    elif isinstance(value, str):
        require(len(value) <= 256 and not any(0xD800 <= ord(c) <= 0xDFFF for c in value),
                "invalid JSON string")
    elif type(value) is float:
        require(not canonical and math.isfinite(value), "invalid JSON float")
    else:
        require(value is None or type(value) in (bool, int), "unsupported JSON value")


def canonical_json(value):
    _tree(value, canonical=True)
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def decode_json(data, *, limit=MAX_PAYLOAD, canonical=False):
    require(len(data) <= limit, "JSON byte limit exceeded")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ProtocolError("nonfinite JSON")))
        _tree(value, canonical=canonical)
        require(isinstance(value, dict), "JSON root must be an object")
        if canonical:
            require(canonical_json(value) == data, "CONFIG JSON is not canonical")
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProtocolError(str(exc)) from exc


def validate_hello(value, simulated):
    required = {"session_uuid", "protocol", "firmware_git", "firmware_build_id", "board_id",
                "boot_reason", "time_epoch", "config_revision", "config_sha256", "max_payload",
                "timestamp_tick_ns", "simulated", "next_request_id"}
    require(required <= value.keys(), "incomplete HELLO")
    require(isinstance(value["session_uuid"], str)
            and re.fullmatch("[0-9a-f]{32}", value["session_uuid"]) is not None, "bad session UUID")
    require(type(value["protocol"]) is int and value["protocol"] == 1
            and type(value["max_payload"]) is int and value["max_payload"] == 1024
            and type(value["timestamp_tick_ns"]) is int and value["timestamp_tick_ns"] == 1000,
            "incompatible HELLO")
    require(type(value["simulated"]) is bool and value["simulated"] == simulated,
            "HELLO simulated flag mismatch")
    for name in ("time_epoch", "config_revision", "next_request_id"):
        require(integer(value[name], 0, 0xFFFFFFFF), f"bad HELLO {name}")
    require(isinstance(value["config_sha256"], str)
            and re.fullmatch("[0-9a-f]{64}", value["config_sha256"]) is not None,
            "bad CONFIG hash")
    require(all(isinstance(value[key], str) and value[key].isascii()
                for key in ("firmware_git", "firmware_build_id", "board_id", "boot_reason")),
            "invalid HELLO text fields")


def validate_config(value):
    required = {"profile_id", "schema", "spi_hz", "sensor_layout_revision", "mounting_revision",
                "mechanics_revision", "drive_revision", "sensors", "phase_inputs", "capture",
                "queues", "transport", "simulated"}
    require(required <= value.keys(), "incomplete CONFIG")
    require(type(value["schema"]) is int and value["schema"] == 1
            and value["transport"] == "usb_cdc", "unsupported CONFIG")
    require(type(value["simulated"]) is bool, "invalid CONFIG simulated")
    require(isinstance(value["sensors"], list) and len(value["sensors"]) <= 4, "invalid sensors")
    require(isinstance(value["phase_inputs"], list) and len(value["phase_inputs"]) <= 2, "invalid phase inputs")
    for group, maximum in (("sensors", 3), ("phase_inputs", 1)):
        identifiers = []
        for item in value[group]:
            require(isinstance(item, dict) and integer(item.get("id"), 0, maximum), "bad source ID")
            identifiers.append(item["id"])
        require(len(set(identifiers)) == len(identifiers), "duplicate source ID")
    sensor_fields = {"id", "model", "chip_id", "location", "channel_mask", "odr_hz", "acc_range_g",
                     "gyro_range_dps", "power_mode", "filters", "counts_format", "scale", "axis_map",
                     "register_readback", "timestamp_source", "filter_delay_us"}
    for sensor in value["sensors"]:
        require(sensor_fields <= sensor.keys(), "incomplete sensor CONFIG")
        expected = "BMI160" if sensor["id"] in (0, 2) else "LIS3DH"
        require(sensor["model"] == expected, "sensor ID/model mismatch")
        require(sensor["channel_mask"] in ((7, 63) if expected == "BMI160" else (7,)), "bad channel mask")
    for item in value["phase_inputs"]:
        require({"id", "role", "ppr", "edge", "rotation_sign", "zero_angle_udeg",
                 "conditioning_revision"} <= item.keys(), "incomplete phase CONFIG")
        require(integer(item["ppr"], 1, 65535) and item["rotation_sign"] in (-1, 1)
                and item["edge"] in ("rising", "falling"), "invalid phase CONFIG")
        require(item["role"] == ("tooth" if item["id"] == 0 else "index"), "phase ID/role mismatch")
    for key in ("capture", "queues"):
        require(isinstance(value[key], dict), "invalid capture/queues CONFIG")
    return value


@dataclass(frozen=True)
class Frame:
    kind: int
    sequence: int
    timestamp_us: int
    payload: bytes
    flags: int = 0

    def encode(self):
        require(len(self.payload) <= MAX_PAYLOAD and not self.flags & ~1, "invalid frame length/flags")
        header = HEADER.pack(MAGIC, 1, self.kind, self.flags, len(self.payload), 0,
                             self.sequence, self.timestamp_us)
        body = header + self.payload
        return body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)


def batch_payload(kind, records, revision=1, epoch=1):
    layout = SAMPLE if kind == Type.SAMPLES else EDGE
    require(kind in (Type.SAMPLES, Type.EDGES), "not a batch type")
    require(1 <= len(records) <= (MAX_PAYLOAD - 16) // layout.size, "invalid batch count")
    return PREFIX.pack(revision, epoch, len(records), layout.size, 0) + b"".join(layout.pack(*r) for r in records)


def config_chunks(config, revision=1, epoch=1):
    validate_config(config)
    data = canonical_json(config)
    require(1 <= len(data) <= 8192, "CONFIG exceeds 8192 bytes")
    digest = hashlib.sha256(data).digest()
    for offset in range(0, len(data), 968):
        chunk = data[offset:offset + 968]
        flags = (1 if offset == 0 else 0) | (2 if offset + len(chunk) == len(data) else 0)
        yield CONFIG.pack(revision, epoch, len(data), offset, len(chunk), flags, 0, digest) + chunk


def decode_payload(frame):
    data, kind = frame.payload, frame.kind
    if kind == Type.HELLO:
        value = decode_json(data)
        validate_hello(value, bool(frame.flags & 1))
        return value
    if kind == Type.CONFIG:
        require(len(data) >= CONFIG.size, "short CONFIG prefix")
        revision, epoch, total, offset, size, flags, reserved, digest = CONFIG.unpack_from(data)
        require(1 <= total <= 8192 and 1 <= size <= 968 and offset + size <= total
                and len(data) == 56 + size and not reserved and not flags & ~3, "invalid CONFIG chunk")
        require(bool(flags & 1) == (offset == 0) and bool(flags & 2) == (offset + size == total),
                "invalid CONFIG FIRST/LAST")
        return dict(revision=revision, epoch=epoch, total=total, offset=offset, flags=flags,
                    digest=digest.hex(), chunk=data[56:])
    if kind in (Type.SAMPLES, Type.EDGES):
        require(len(data) >= 16, "short batch prefix")
        revision, epoch, count, size, reserved = PREFIX.unpack_from(data)
        layout = SAMPLE if kind == Type.SAMPLES else EDGE
        require(size == layout.size and count > 0 and not reserved
                and len(data) == 16 + count * size, "invalid batch count/size")
        records = []
        for offset in range(16, len(data), size):
            row = layout.unpack_from(data, offset)
            if kind == Type.SAMPLES:
                sensor, mask, quality, sequence, timestamp, *counts = row
                require(sensor <= 3 and mask in ((7, 63) if sensor in (0, 2) else (7,))
                        and not quality & ~63, "invalid sample ID/mask/quality")
                require(all(count == 0 for bit, count in enumerate(counts) if not mask & (1 << bit)),
                        "inactive sample channel must be zero")
                records.append(dict(source=sensor, mask=mask, quality=quality, sequence=sequence,
                                    timestamp_us=timestamp, counts=counts))
            else:
                timestamp, sequence, flags, source, level = row
                require(source <= 1 and level <= 1 and not flags & ~31, "invalid edge")
                records.append(dict(source=source, sequence=sequence, timestamp_us=timestamp,
                                    flags=flags, level=level))
        require(frame.timestamp_us == min(r["timestamp_us"] for r in records), "invalid t_base_us")
        return dict(revision=revision, epoch=epoch, records=records)
    if kind == Type.GAP:
        require(len(data) == 40, "invalid GAP length")
        values = GAP.unpack(data)
        value = dict(zip(("revision", "epoch", "stream_kind", "source", "reason", "first_sequence",
                          "count", "flags", "first_us", "last_us"), values))
        require(value["stream_kind"] <= 3 and value["reason"] in range(1, 11)
                and not value["flags"] & ~7, "invalid GAP flags/reason")
        require((value["count"] == 0xFFFFFFFF) if value["flags"] & 1
                else 0 < value["count"] < 2**31, "invalid GAP count")
        require((value["first_us"] == value["last_us"] == 0) if value["flags"] & 2
                else value["first_us"] <= value["last_us"], "invalid GAP time")
        return value
    if kind in (Type.COMMAND, Type.ACK):
        require(len(data) >= 32, "short command/ACK prefix")
        if kind == Type.COMMAND:
            uuid, request, revision, opcode, size, flags, reserved = COMMAND.unpack_from(data)
            require(not flags and not reserved and size <= 992, "invalid COMMAND")
            value = dict(session_uuid=uuid.hex(), request_id=request, revision=revision, opcode=opcode)
        else:
            uuid, request, opcode, status, revision, size, reserved = ACK.unpack_from(data)
            require(not reserved and size <= 256 and status <= 7, "invalid ACK")
            value = dict(session_uuid=uuid.hex(), request_id=request, revision=revision,
                         opcode=opcode, status=status)
        require(len(data) == 32 + size, "invalid command/ACK body length")
        value["body"] = decode_json(data[32:]) if size else {}
        return value
    if kind == Type.END:
        require(len(data) == 48, "invalid END length")
        uuid, revision, epoch, last, reason, flags, time, gaps, reserved = END.unpack(data)
        require(not reserved and reason <= 3 and not flags & ~31, "invalid END")
        require(not flags & 16 or last == 0, "invalid NO_DATA sequence")
        return dict(session_uuid=uuid.hex(), revision=revision, epoch=epoch, last_data_sequence=last,
                    reason=reason, flags=flags, end_us=time, pending_gaps=gaps)
    if kind == Type.STATUS:
        return _status(data)
    return {"unknown_type": kind, "payload_hex": data.hex()}


def _status(data):
    require(len(data) >= 96, "short STATUS")
    prefix = STATUS.unpack_from(data)
    revision, epoch, state, health, sensors, inputs, used, high, slots, slot_high, stall = prefix
    require(state <= 5 and not health & ~31 and sensors <= 4 and inputs <= 2
            and len(data) == 96 + 48 * sensors + 32 * inputs, "invalid STATUS")
    require(used <= high <= 65536 and slots <= slot_high <= 256, "invalid STATUS queue bounds")
    value = dict(revision=revision, epoch=epoch, state=state, health=health, tx_used=used,
                 tx_high_water=high, capture_used=slots, capture_high_water=slot_high,
                 usb_stall_ms=stall, sensors=[], inputs=[])
    offset = 32
    for _ in range(sensors):
        row = SENSOR_STATUS.unpack_from(data, offset)
        require(row[0] <= 3 and not row[2] & ~3, "invalid sensor STATUS")
        value["sensors"].append(dict(zip(("source", "mask", "flags", "last_sequence", "observed",
                                                "valid_reads", "known_dropped", "unknown_losses",
                                                "fifo_overruns", "spi_error"), row)))
        offset += 48
    for _ in range(inputs):
        row = INPUT_STATUS.unpack_from(data, offset)
        require(row[0] <= 1 and row[1] <= 1 and not row[2] & ~1, "invalid input STATUS")
        value["inputs"].append(dict(zip(("source", "edge", "flags", "last_sequence", "observed",
                                               "known_dropped", "unknown_losses", "min_interval_us"), row)))
        offset += 32
    for group in ("sensors", "inputs"):
        require(len({item["source"] for item in value[group]}) == len(value[group]), "duplicate STATUS source")
    value["counters"] = dict(zip(COUNTERS, struct.unpack_from("<8Q", data, offset)))
    return value


class Decoder:
    """Constant-size input buffer; frames are yielded, not accumulated internally.

    Raw archival belongs to the recorder, before decoding. Recent issues are
    bounded to 64; an optional callback can stream all diagnostics to disk.
    """

    def __init__(self, on_issue=None):
        self.buffer = bytearray()
        self.issues = deque(maxlen=64)
        self.counts = Counter()
        self.high_water = 0
        self.on_issue = on_issue

    def issue(self, code, **detail):
        event = {"code": code, **detail}
        self.counts[code] += 1
        self.issues.append(event)
        if self.on_issue is not None:
            self.on_issue(event)

    def feed(self, data):
        for offset in range(0, len(data), 4096):
            self.buffer.extend(data[offset:offset + 4096])
            self.high_water = max(self.high_water, len(self.buffer))
            require(len(self.buffer) <= MAX_BUFFER, "internal decoder bound exceeded")
            yield from self._drain()

    def _drain(self):
        while len(self.buffer) >= 4:
            position = self.buffer.find(MAGIC)
            if position != 0:
                remove = position if position >= 0 else len(self.buffer) - 3
                self.issue("garbage", bytes=remove)
                del self.buffer[:remove]
                continue
            if len(self.buffer) < 24:
                return
            _, version, kind, flags, size, reserved, sequence, timestamp = HEADER.unpack_from(self.buffer)
            if size > MAX_PAYLOAD:
                self.issue("length", payload_length=size)
                del self.buffer[0]
                continue
            total = 28 + size
            if len(self.buffer) < total:
                return
            body = bytes(self.buffer[:24 + size])
            crc, = struct.unpack_from("<I", self.buffer, 24 + size)
            if zlib.crc32(body) & 0xFFFFFFFF != crc:
                self.issue("crc")
                del self.buffer[0]
                continue
            del self.buffer[:total]
            if version != 1 or reserved or flags & ~1:
                self.issue("incompatible_header", version=version, reserved=reserved, flags=flags)
                continue
            frame = Frame(kind, sequence, timestamp, body[24:], flags)
            try:
                decode_payload(frame)
            except (ProtocolError, TypeError, struct.error) as exc:
                self.issue("payload", detail=str(exc))
                continue
            self.counts["frames"] += 1
            yield frame

    def finish(self):
        if self.buffer:
            self.issue("partial_tail", bytes=len(self.buffer))
            self.buffer.clear()

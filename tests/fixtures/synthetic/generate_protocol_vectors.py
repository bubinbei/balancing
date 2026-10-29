"""Independent golden generator: no production imports, struct, or zlib.

Run explicitly to regenerate protocol-vectors.json; inspect the diff.
"""

import json
from pathlib import Path


def number(value, length, signed=False):
    return value.to_bytes(length, "little", signed=signed)


def crc32(data):
    value = 0xFFFFFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
    return value ^ 0xFFFFFFFF


def frame(kind, sequence, timestamp, payload):
    header = b"BLC1" + bytes([1, kind]) + number(1, 2) + number(len(payload), 2)
    header += number(0, 2) + number(sequence, 4) + number(timestamp, 8)
    return (header + payload + number(crc32(header + payload), 4)).hex()


def generate():
    prefix = lambda size: number(1, 4) + number(2, 4) + number(1, 2) + number(size, 2) + number(0, 4)
    counts = [-32768, -1, 0, 1, 32767, -1234]
    sample = bytes([0, 63]) + number(0, 2) + number(0xFFFFFFFE, 4) + number(123456, 8)
    sample += b"".join(number(v, 2, True) for v in counts)
    edge = number(99999, 8) + number(7, 4) + number(0, 2) + bytes([1, 1])
    vectors = [dict(name="unknown-empty", type=200, sequence=5, timestamp_us=0,
                    payload_hex="", raw_hex=frame(200, 5, 0, b"")),
               dict(name="sample-negative", type=3, sequence=8, timestamp_us=123456,
                    counts=counts, payload_hex=(prefix(28) + sample).hex(),
                    raw_hex=frame(3, 8, 123456, prefix(28) + sample)),
               dict(name="index-edge", type=4, sequence=9, timestamp_us=99999,
                    payload_hex=(prefix(16) + edge).hex(),
                    raw_hex=frame(4, 9, 99999, prefix(16) + edge)),
               dict(name="maximum-frame", type=200, sequence=0xFFFFFFFF, timestamp_us=2**40,
                    payload_hex=(b"\xa5" * 1024).hex(),
                    raw_hex=frame(200, 0xFFFFFFFF, 2**40, b"\xa5" * 1024))]
    return dict(data_kind="synthetic", generator="independent to_bytes + bitwise CRC32",
                crc_check_123456789=f"{crc32(b'123456789'):08x}", vectors=vectors)


if __name__ == "__main__":
    Path(__file__).with_name("protocol-vectors.json").write_text(
        json.dumps(generate(), indent=2) + "\n", encoding="utf-8")

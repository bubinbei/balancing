"""One pending command, exact retransmissions, finite retries, ACK matching."""

from dataclasses import dataclass

from .protocol import COMMAND, Frame, ProtocolError, Type, canonical_json, decode_payload, require

MUTATING = {3, 4, 5, 7}


@dataclass
class Pending:
    opcode: int
    request_id: int
    raw: bytes
    sent_at: float | None = None
    attempts: int = 0


class CommandClient:
    def __init__(self):
        self.uuid = "0" * 32
        self.next_id = 1
        self.sequence = 0
        self.simulated = False
        self.pending = None
        self.uncertain = False

    def identify(self, hello):
        require(self.pending is None, "cannot replace session with a pending command")
        self.uuid = hello["session_uuid"]
        self.next_id = hello["next_request_id"]
        self.simulated = hello["simulated"]
        self.uncertain = False

    def prepare(self, opcode, revision=0, body=None):
        require(self.pending is None and not self.uncertain, "command pending or outcome uncertain")
        require(opcode in range(1, 8), "unsupported opcode")
        require(opcode == 1 or self.uuid != "0" * 32, "HELLO required first")
        request = self.next_id if opcode in MUTATING else 0
        if opcode in MUTATING:
            require(1 <= request < 0xFFFFFFFF, "request ID exhausted; new session required")
            self.next_id += 1
        data = canonical_json(body or {})
        require(len(data) <= 992, "command body too large")
        payload = COMMAND.pack(bytes.fromhex(self.uuid), request, revision, opcode, len(data), 0, 0) + data
        raw = Frame(Type.COMMAND, self.sequence, 0, payload, int(self.simulated)).encode()
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        self.pending = Pending(opcode, request, raw)

    def poll(self, now):
        require(self.pending is not None, "no pending command")
        pending = self.pending
        if pending.sent_at is not None and now - pending.sent_at < 1:
            return None
        if pending.attempts >= 4:  # Initial transmission plus at most three repeats.
            self.pending = None
            self.uncertain = True
            raise ProtocolError("ACK timeout: command outcome uncertain")
        pending.attempts += 1
        pending.sent_at = now
        return pending.raw

    def acknowledge(self, frame):
        if frame.kind != Type.ACK or self.pending is None:
            return None
        value = decode_payload(frame)
        pending = self.pending
        if (value["session_uuid"], value["request_id"], value["opcode"]) != (
                self.uuid, pending.request_id, pending.opcode):
            return None
        self.pending = None
        return value

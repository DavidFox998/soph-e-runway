"""The receipt chain: append-only, hash-chained, replayable.

Every gate verdict, ledger movement and heartbeat profile in a run is an
entry here. The chain is the product: replay recomputes every hash and
re-derives the run, and a chain that does not verify, refuses.

Pure stdlib. Canonical JSON = sorted keys, no insignificant whitespace,
UTF-8. hash = SHA-256 over the canonical form of
{seq, ts, kind, payload, prev_hash}.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

GENESIS_HASH = "0" * 64

ENTRY_KINDS = (
    "run_start",
    "claim",
    "gate_verdict",
    "ledger_move",
    "heartbeat_profile",
    "run_end",
)


def canonical(obj: object) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def entry_hash(seq: int, ts: str, kind: str, payload: dict, prev_hash: str) -> str:
    body = {
        "seq": seq,
        "ts": ts,
        "kind": kind,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    return hashlib.sha256(canonical(body)).hexdigest()


@dataclass
class Entry:
    seq: int
    ts: str
    kind: str
    payload: dict
    prev_hash: str
    hash: str

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "kind": self.kind,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Entry":
        return cls(
            seq=d["seq"],
            ts=d["ts"],
            kind=d["kind"],
            payload=d["payload"],
            prev_hash=d["prev_hash"],
            hash=d["hash"],
        )


@dataclass
class ReceiptChain:
    entries: list[Entry] = field(default_factory=list)

    def append(self, kind: str, payload: dict, ts: str | None = None) -> Entry:
        if kind not in ENTRY_KINDS:
            raise ValueError(f"unknown entry kind: {kind!r}")
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat()
        seq = len(self.entries)
        prev_hash = self.entries[-1].hash if self.entries else GENESIS_HASH
        h = entry_hash(seq, ts, kind, payload, prev_hash)
        entry = Entry(seq=seq, ts=ts, kind=kind, payload=payload,
                      prev_hash=prev_hash, hash=h)
        self.entries.append(entry)
        return entry

    def verify(self) -> bool:
        """Recompute the whole chain. Any tamper, gap or reorder fails."""
        prev_hash = GENESIS_HASH
        for i, e in enumerate(self.entries):
            if e.seq != i:
                return False
            if e.prev_hash != prev_hash:
                return False
            if e.hash != entry_hash(e.seq, e.ts, e.kind, e.payload, e.prev_hash):
                return False
            prev_hash = e.hash
        return True

    def replay(self) -> list[dict]:
        """Re-derive the run: the payload sequence, iff the chain verifies."""
        if not self.verify():
            raise ValueError("receipt chain does not verify; replay refused")
        return [e.payload for e in self.entries]

    def verdicts(self) -> list[dict]:
        return [e.payload for e in self.entries if e.kind == "gate_verdict"]

    def to_jsonl(self) -> str:
        return "\n".join(
            json.dumps(e.to_dict(), sort_keys=True) for e in self.entries
        )

    @classmethod
    def from_jsonl(cls, text: str) -> "ReceiptChain":
        chain = cls()
        for line in text.splitlines():
            line = line.strip()
            if line:
                chain.entries.append(Entry.from_dict(json.loads(line)))
        return chain

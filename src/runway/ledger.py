"""The sandbox ledger rail: holds, captures, releases — never over cap.

Offline and append-only in spirit: every mutation is a LedgerEvent, and
the ledger's invariant is checked on every mutation:

    held_cents + captured_cents <= cap_cents        (per mandate, always)

Idempotency: every mutating call takes an idempotency key. Repeating a
key returns the ORIGINAL event and changes nothing — a retried hold can
never double-hold. Runner keys follow `{run_id}:{seq}:{gate}`.

Assumption, stated plainly: single-threaded, in-memory, with an optional
JSON snapshot. This is a demo rail, not a payments system; the shape is
the product (authorize → capture | release, with named reasons).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

RELEASE_REASONS = ("gate_refusal", "run_abort", "superseded_offer")


class LedgerError(Exception):
    """A mutation that would break the ledger's invariant or references
    a hold that does not exist / is no longer open."""


@dataclass
class MandateAccount:
    mandate_id: str
    cap_cents: int
    held_cents: int = 0
    captured_cents: int = 0


@dataclass
class LedgerEvent:
    seq: int
    op: str  # "authorize" | "capture" | "release"
    idempotency_key: str
    mandate_id: str
    amount_cents: int
    merchant: str | None = None
    reason: str | None = None
    held_cents: int = 0      # mandate totals AFTER the event
    captured_cents: int = 0

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "op": self.op,
            "idempotency_key": self.idempotency_key,
            "mandate_id": self.mandate_id,
            "amount_cents": self.amount_cents,
            "merchant": self.merchant,
            "reason": self.reason,
            "held_cents": self.held_cents,
            "captured_cents": self.captured_cents,
        }


@dataclass
class _Hold:
    key: str
    mandate_id: str
    amount_cents: int
    merchant: str | None
    state: str = "open"  # "open" | "captured" | "released"


@dataclass
class Ledger:
    accounts: dict[str, MandateAccount] = field(default_factory=dict)
    events: list[LedgerEvent] = field(default_factory=list)
    _by_key: dict[str, LedgerEvent] = field(default_factory=dict)
    _holds: dict[str, _Hold] = field(default_factory=dict)

    # -- setup ---------------------------------------------------------
    def open_mandate(self, mandate_id: str, cap_cents: int) -> MandateAccount:
        if cap_cents <= 0:
            raise LedgerError("a mandate account needs a positive cap")
        if mandate_id in self.accounts:
            raise LedgerError(f"mandate {mandate_id!r} already open")
        acct = MandateAccount(mandate_id=mandate_id, cap_cents=cap_cents)
        self.accounts[mandate_id] = acct
        return acct

    def _account(self, mandate_id: str) -> MandateAccount:
        try:
            return self.accounts[mandate_id]
        except KeyError:
            raise LedgerError(f"unknown mandate {mandate_id!r}") from None

    def _record(self, op, key, mandate_id, amount, merchant, reason) -> LedgerEvent:
        acct = self._account(mandate_id)
        ev = LedgerEvent(
            seq=len(self.events),
            op=op,
            idempotency_key=key,
            mandate_id=mandate_id,
            amount_cents=amount,
            merchant=merchant,
            reason=reason,
            held_cents=acct.held_cents,
            captured_cents=acct.captured_cents,
        )
        self.events.append(ev)
        self._by_key[key] = ev
        return ev

    # -- mutations -----------------------------------------------------
    def authorize(self, idempotency_key: str, mandate_id: str,
                  amount_cents: int, merchant: str | None = None) -> LedgerEvent:
        """Place a hold. Duplicate key returns the original event."""
        if idempotency_key in self._by_key:
            return self._by_key[idempotency_key]
        acct = self._account(mandate_id)
        if amount_cents <= 0:
            raise LedgerError("hold amount must be positive")
        if acct.held_cents + acct.captured_cents + amount_cents > acct.cap_cents:
            raise LedgerError("over_cap_cumulative")
        acct.held_cents += amount_cents
        self._holds[idempotency_key] = _Hold(
            key=idempotency_key, mandate_id=mandate_id,
            amount_cents=amount_cents, merchant=merchant,
        )
        return self._record("authorize", idempotency_key, mandate_id,
                            amount_cents, merchant, None)

    def capture(self, hold_key: str, idempotency_key: str | None = None) -> LedgerEvent:
        """Convert an open hold into a capture (the money settles)."""
        key = idempotency_key or f"{hold_key}:capture"
        if key in self._by_key:
            return self._by_key[key]
        hold = self._holds.get(hold_key)
        if hold is None or hold.state != "open":
            raise LedgerError(f"hold {hold_key!r} is not open")
        acct = self._account(hold.mandate_id)
        acct.held_cents -= hold.amount_cents
        acct.captured_cents += hold.amount_cents
        hold.state = "captured"
        return self._record("capture", key, hold.mandate_id,
                            hold.amount_cents, hold.merchant, None)

    def release(self, hold_key: str, reason: str,
                idempotency_key: str | None = None) -> LedgerEvent:
        """Release an open hold (the money goes back). Named reasons only."""
        if reason not in RELEASE_REASONS:
            raise LedgerError(f"unknown release reason {reason!r}")
        key = idempotency_key or f"{hold_key}:release"
        if key in self._by_key:
            return self._by_key[key]
        hold = self._holds.get(hold_key)
        if hold is None or hold.state != "open":
            raise LedgerError(f"hold {hold_key!r} is not open")
        acct = self._account(hold.mandate_id)
        acct.held_cents -= hold.amount_cents
        hold.state = "released"
        return self._record("release", key, hold.mandate_id,
                            hold.amount_cents, hold.merchant, reason)

    # -- views ---------------------------------------------------------
    def open_holds(self, mandate_id: str) -> list[_Hold]:
        return [h for h in self._holds.values()
                if h.mandate_id == mandate_id and h.state == "open"]

    def state(self) -> dict:
        return {
            mid: {
                "cap_cents": a.cap_cents,
                "held_cents": a.held_cents,
                "captured_cents": a.captured_cents,
            }
            for mid, a in self.accounts.items()
        }

    def snapshot(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "accounts": self.state(),
                    "events": [e.to_dict() for e in self.events],
                },
                f,
                indent=2,
            )

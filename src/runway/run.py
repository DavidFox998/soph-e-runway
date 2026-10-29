"""The environment (build Stage 2): the chain becomes a run.

One live pass per claim:

    CLAIM_EMITTED -> Offer gate -> Payment gate -> LEDGER_HOLD

each step appended to the receipt chain as it happens. A gate refusal
short-circuits: RUN_REFUSED is appended, every open hold is released
(ledger reason `gate_refusal`), HOLDS_RELEASED is appended, and the run
returns REFUSED. **A refusal is a return value, not an exception.**

`replay` re-derives a run from its sealed receipt alone — no tenant,
no network — and must reproduce the outcome, every verdict, and the
head hash bit-for-bit. Entry kinds stay within the receipt schema;
the operation lives in each payload's `op`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable

from .claims import Claim, Measurement
from .gates import Mandate, Verdict, gate_offer, gate_payment
from .ledger import Ledger, LedgerError
from .receipts import GENESIS_HASH, ReceiptChain

OUTCOMES = ("SETTLED", "REFUSED", "ABORTED")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunResult:
    outcome: str
    receipt_head_hash: str
    ledger_state: dict
    verdicts: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome {self.outcome!r}")


class Environment:
    """Drives one mandate's run. Construct, submit claims, then settle
    (implicit in run_mandate) — or watch it refuse."""

    def __init__(self, mandate: Mandate, *, run_id: str,
                 mandate_id: str | None = None,
                 clock: Callable[[], str] = _now):
        self.mandate = mandate
        self.run_id = run_id
        self.mandate_id = mandate_id or f"m-{run_id}"
        self.clock = clock
        self.chain = ReceiptChain()
        self.ledger = Ledger()
        self.ledger.open_mandate(self.mandate_id, mandate.cap_cents)
        self._seq = 0
        self.closed = False
        self.outcome: str | None = None
        self.chain.append("run_start", {
            "op": "RUN_START",
            "run_id": run_id,
            "mandate_id": self.mandate_id,
            "mandate": {
                "item": mandate.item,
                "attributes": dict(mandate.attributes),
                "cap_cents": mandate.cap_cents,
                "currency": mandate.currency,
            },
        }, ts=self.clock())

    # -- internals -----------------------------------------------------
    @staticmethod
    def _ledger_payload(op_name: str, ev) -> dict:
        """Chain payload for a ledger event. The chain-level op
        (LEDGER_HOLD / LEDGER_CAPTURE / LEDGER_RELEASE) is written
        LAST so it cannot be overwritten by the ledger event's own
        op field, which is preserved as `ledger_op`."""
        return {**ev.to_dict(), "op": op_name, "ledger_op": ev.op}

    def _head(self) -> str:
        return self.chain.entries[-1].hash if self.chain.entries else GENESIS_HASH

    def _release_all(self, reason: str) -> int:
        total = 0
        for hold in self.ledger.open_holds(self.mandate_id):
            ev = self.ledger.release(hold.key, reason=reason)
            total += ev.amount_cents
            self.chain.append("ledger_move",
                              self._ledger_payload("LEDGER_RELEASE", ev),
                              ts=self.clock())
        self.chain.append("ledger_move", {
            "op": "HOLDS_RELEASED",
            "mandate_id": self.mandate_id,
            "released_cents": total,
            "reason": reason,
        }, ts=self.clock())
        return total

    def _refuse(self, verdict: Verdict) -> RunResult:
        self.chain.append("run_end", {
            "op": "RUN_REFUSED",
            "gate": verdict.gate,
            "reason": verdict.reason,
        }, ts=self.clock())
        self._release_all("gate_refusal")
        self.closed = True
        self.outcome = "REFUSED"
        return self._result()

    def _result(self) -> RunResult:
        return RunResult(
            outcome=self.outcome or "ABORTED",
            receipt_head_hash=self._head(),
            ledger_state=self.ledger.state(),
            verdicts=self.chain.verdicts(),
        )

    # -- the pass ------------------------------------------------------
    def submit_claim(self, claim: Claim,
                     measurement: Measurement | None) -> RunResult | None:
        """Run one claim down the Runway. Returns None while the run is
        still open (claim held), or the final RunResult on refusal."""
        if self.closed:
            raise RuntimeError("run is closed")
        self._seq += 1
        seq = self._seq
        self.chain.append("claim", {
            "op": "CLAIM_EMITTED", "claim": claim.to_dict(),
        }, ts=self.clock())

        claim.measurement = measurement
        v = gate_offer(self.mandate, claim)
        self.chain.append("gate_verdict", {
            "op": "GATE_VERDICT", "gate": v.gate, "status": v.status,
            "reason": v.reason, "claim_id": claim.claim_id,
        }, ts=self.clock())
        if v.status == "refuse":
            return self._refuse(v)

        measured = measurement.measured_value
        amount = measured["price_cents"]
        acct = self.ledger.accounts[self.mandate_id]
        pay_claim = Claim(
            claim_id=f"{claim.claim_id}:payment",
            kind="payment",
            subject={"item": self.mandate.item},
            asserted_by="environment",
            asserted_value={"amount_cents": amount},
            measurement=Measurement(
                measured_by=measurement.measured_by,
                measured_value={
                    "amount_cents": amount,
                    "currency": measured.get("currency", self.mandate.currency),
                },
                evidence_refs=list(measurement.evidence_refs),
            ),
        )
        v2 = gate_payment(
            self.mandate, pay_claim,
            already_paid_cents=acct.held_cents + acct.captured_cents,
        )
        self.chain.append("gate_verdict", {
            "op": "GATE_VERDICT", "gate": v2.gate, "status": v2.status,
            "reason": v2.reason, "claim_id": pay_claim.claim_id,
        }, ts=self.clock())
        if v2.status == "refuse":
            return self._refuse(v2)

        key = f"{self.run_id}:{seq}:payment"
        try:
            ev = self.ledger.authorize(
                key, self.mandate_id, amount,
                merchant=claim.asserted_value.get("merchant"),
            )
        except LedgerError:
            return self.abort("ledger_invariant")
        self.chain.append("ledger_move",
                          self._ledger_payload("LEDGER_HOLD", ev),
                          ts=self.clock())
        return None

    def settle(self) -> RunResult:
        if self.closed:
            return self._result()
        for hold in self.ledger.open_holds(self.mandate_id):
            ev = self.ledger.capture(hold.key)
            self.chain.append("ledger_move",
                              self._ledger_payload("LEDGER_CAPTURE", ev),
                              ts=self.clock())
        self.chain.append("run_end", {"op": "RUN_SETTLED"}, ts=self.clock())
        self.closed = True
        self.outcome = "SETTLED"
        return self._result()

    def abort(self, reason: str = "run_abort") -> RunResult:
        if self.closed:
            return self._result()
        self.chain.append("run_end", {
            "op": "RUN_ABORTED", "reason": reason,
        }, ts=self.clock())
        self._release_all("run_abort")
        self.closed = True
        self.outcome = "ABORTED"
        return self._result()


def run_mandate(mandate: Mandate,
                proposals: Iterable[Claim],
                receipt_path: str,
                *,
                measurer: Callable[[Claim], Measurement | None],
                run_id: str,
                mandate_id: str | None = None,
                clock: Callable[[], str] = _now) -> RunResult:
    """Drive every proposal down the Runway. All pass -> settle.
    Any refusal -> short-circuit REFUSED. The receipt is written to
    receipt_path as JSONL either way — a refused run is still a run,
    and its receipt is the proof."""
    environment = Environment(mandate, run_id=run_id, mandate_id=mandate_id, clock=clock)
    result: RunResult | None = None
    for claim in proposals:
        result = environment.submit_claim(claim, measurer(claim))
        if result is not None:
            break
    if result is None:
        result = environment.settle()
    with open(receipt_path, "w", encoding="utf-8") as f:
        f.write(environment.chain.to_jsonl() + "\n")
    return result


def replay(receipt_path: str, mandate: Mandate) -> RunResult:
    """Re-derive a run from its sealed receipt alone. The chain must
    verify; the outcome, verdicts, ledger state and head hash are read
    back out of the sealed payloads, so a replay of a refused run
    reproduces REFUSED with the identical head hash."""
    with open(receipt_path, encoding="utf-8") as f:
        chain = ReceiptChain.from_jsonl(f.read())
    if not chain.verify():
        raise ValueError("receipt chain does not verify; replay refused")

    outcome = "ABORTED"
    ledger_state: dict = {}
    cap = mandate.cap_cents
    for e in chain.entries:
        p = e.payload
        op = p.get("op")
        if e.kind == "run_start":
            ledger_state = {p["mandate_id"]: {
                "cap_cents": cap, "held_cents": 0, "captured_cents": 0}}
            mid = p["mandate_id"]
        elif op in ("LEDGER_HOLD", "LEDGER_CAPTURE", "LEDGER_RELEASE"):
            ledger_state[p["mandate_id"]]["held_cents"] = p["held_cents"]
            ledger_state[p["mandate_id"]]["captured_cents"] = p["captured_cents"]
        elif op == "RUN_SETTLED":
            outcome = "SETTLED"
        elif op == "RUN_REFUSED":
            outcome = "REFUSED"
        elif op == "RUN_ABORTED":
            outcome = "ABORTED"
    head = chain.entries[-1].hash if chain.entries else GENESIS_HASH
    return RunResult(
        outcome=outcome,
        receipt_head_hash=head,
        ledger_state=ledger_state,
        verdicts=chain.verdicts(),
    )

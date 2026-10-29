"""The demo driver (Q3): three beats — PASS, TAMPER, RECOVERY.

Choreographed-but-genuine (ratified 2026-10-26): the sequence and the
scripted answers are choreography; every gate verdict, ledger move,
probe result and profile number is computed live by the real code.
The liveliness dip in Beat 2 is what profile() computes from a probe
that actually failed, hesitated, and was overconfident — the recovery
in Beat 3 is likewise measured, not narrated.

Tamper discipline: the tamper state file is read at photo-capture
time ONLY. Modes: CLEAN / ARMED / IMPOSTOR. ARMED flips to IMPOSTOR
at the next delivery photo. In auto mode the choreography arms
before Beat 2 and resets before Beat 3; the operator can flip the
state at any time and the next photo obeys it.
"""

from __future__ import annotations

import json
import os

from .brain import profile
from .claims import Claim, Measurement
from .delivery import StubVerifier, gate_delivery
from .demo_feed import Feed
from .gates import Mandate, gate_offer, gate_payment
from .ledger import Ledger
from .probes import (
    ProbeClock,
    arithmetic_check,
    claim_consistency,
    control_beat,
    mandate_recall,
    refusal_recall,
)
from .receipts import ReceiptChain

MANDATE = Mandate(
    item="gooseneck kettle",
    attributes={"colour": "matte red", "form": "gooseneck"},
    cap_cents=4000,
)
TRUE_OBS = {
    "item": "gooseneck kettle",
    "attributes": {"colour": "matte red", "form": "gooseneck"},
    "present": True,
}
IMPOSTOR_OBS = {
    "item": "gooseneck kettle",
    "attributes": {"colour": "gloss black", "form": "gooseneck"},
    "present": True,
}
PRICE = 3850
TS = "2026-10-26T00:00:00+00:00"


class ScriptedProposer:
    """complete() answers from a queue the choreography controls."""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)

    def complete(self, prompt: str) -> str:
        return self.replies.pop(0) if self.replies else ""


def read_tamper(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return str(json.load(f).get("mode", "CLEAN"))
    except (OSError, ValueError):
        return "CLEAN"


def write_tamper(path: str, mode: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"mode": mode}, f)
    os.replace(tmp, path)


def run_demo(feed: Feed, *, receipt_path: str, tamper_path: str,
             auto: bool = True, sleep=lambda s: None) -> dict:
    chain = ReceiptChain()
    ledger = Ledger()
    verifier = StubVerifier(fixtures={
        "photo-true": TRUE_OBS, "photo-impostor": IMPOSTOR_OBS})
    clock = ProbeClock()
    beats: list = []
    proposer = ScriptedProposer([
        "gooseneck kettle, cap 4000",        # beat 1 recall: exact
        "a kettle, cap 5000",                # beat 2 recall: wrong (perturbed)
        "attribute_mismatch:colour",        # refusal recall: exact
        "gooseneck kettle, cap 4000",        # beat 3 recall: recovered
    ])

    def append(kind: str, payload: dict) -> None:
        entry = chain.append(kind, payload, ts=TS)
        feed.emit("receipt.appended", {
            "seq": entry.seq, "op": payload.get("op", kind),
            "hash": entry.hash[:12], "prev": entry.prev_hash[:12],
        })

    def brain_beat(beat_no: int) -> None:
        prof = profile(beats)
        append("heartbeat_profile", {
            "op": "BRAIN_PROFILE", "beat": beat_no,
            "profile": prof.to_dict(),
        })
        feed.emit("brain.beat", {
            "beat": beat_no,
            "profile": prof.to_dict(),
            "probes": [
                {"probe": b.probe, "coherent": b.coherent,
                 "kind": b.kind, "perturbed": b.perturbed}
                for b in beats
            ],
        })

    append("run_start", {"op": "RUN_START", "run_id": "demo"})
    summary = {"beats": []}

    for beat_no in (1, 2, 3):
        # Each beat is a fresh run of the same mandate: PASS, TAMPER,
        # RECOVERY are three runs, not three charges on one cap.
        mid = f"m-demo-b{beat_no}"
        ledger.open_mandate(mid, MANDATE.cap_cents)
        feed.emit("mandate.loaded", {
            "beat": beat_no, "item": MANDATE.item,
            "attributes": dict(MANDATE.attributes),
            "cap_cents": MANDATE.cap_cents,
        })
        sleep(1)

        # -- probes run mid-task, before the claim -------------------
        beats.append(control_beat(clock))
        if beat_no == 2:
            beats.append(mandate_recall(
                proposer, MANDATE, clock, confidence=0.95, hesitate=4.0))
        else:
            beats.append(mandate_recall(proposer, MANDATE, clock))

        # -- the claim -------------------------------------------------
        claim = Claim(
            claim_id=f"c-b{beat_no}", kind="offer",
            subject={"item": MANDATE.item, "attributes": dict(MANDATE.attributes)},
            asserted_by="spark:scripted",
            asserted_value={"price_cents": PRICE, "currency": "USD",
                            "merchant": "KettleHouse"},
        )
        feed.emit("claim.proposed", {
            "beat": beat_no, "claim_id": claim.claim_id,
            "subject": claim.subject,
            "asserted_value": claim.asserted_value,
        })
        append("claim", {"op": "CLAIM_EMITTED", "claim": claim.to_dict()})
        beats.append(claim_consistency(claim, MANDATE, clock))
        beats.append(arithmetic_check(claim, MANDATE, 0, clock))
        brain_beat(beat_no)
        sleep(1)

        # -- offer + payment ------------------------------------------
        claim.measurement = Measurement(
            measured_by="offer-rereader",
            measured_value={
                "item": MANDATE.item,
                "attributes": dict(MANDATE.attributes),
                "price_cents": PRICE, "currency": "USD",
            },
        )
        v = gate_offer(MANDATE, claim)
        append("gate_verdict", {
            "op": "GATE_VERDICT", "gate": v.gate, "status": v.status,
            "reason": v.reason, "claim_id": claim.claim_id})
        feed.emit("gate.verdict", {
            "beat": beat_no, "gate": "offer", "status": v.status,
            "reason": v.reason, "claim_id": claim.claim_id,
            "field_read": "measurement.price_cents",
            "measured_cents": PRICE,
            "asserted_cents": claim.asserted_value["price_cents"],
        })
        acct = ledger.accounts[mid]
        pay = Claim(
            claim_id=f"{claim.claim_id}:payment", kind="payment",
            subject={"item": MANDATE.item}, asserted_by="environment",
            asserted_value={"amount_cents": PRICE},
            measurement=Measurement(
                measured_by="offer-rereader",
                measured_value={"amount_cents": PRICE, "currency": "USD"}),
        )
        v2 = gate_payment(MANDATE, pay,
                          already_paid_cents=acct.held_cents + acct.captured_cents)
        append("gate_verdict", {
            "op": "GATE_VERDICT", "gate": v2.gate, "status": v2.status,
            "reason": v2.reason, "claim_id": pay.claim_id})
        feed.emit("gate.verdict", {
            "beat": beat_no, "gate": "payment", "status": v2.status,
            "reason": v2.reason, "claim_id": pay.claim_id,
            "cumulative_cents": acct.held_cents + acct.captured_cents + PRICE,
            "cap_cents": MANDATE.cap_cents,
        })
        assert v.status == "pass" and v2.status == "pass"
        hold = ledger.authorize(f"demo:{beat_no}:payment", mid,
                                PRICE, "KettleHouse")
        append("ledger_move", {**hold.to_dict(), "op": "LEDGER_HOLD",
                               "ledger_op": hold.op})
        sleep(1)

        # -- tamper choreography + delivery ----------------------------
        if auto and beat_no == 2:
            write_tamper(tamper_path, "ARMED")
            feed.emit("tamper.armed", {"beat": beat_no, "by": "choreography"})
        if auto and beat_no == 3:
            write_tamper(tamper_path, "CLEAN")
            feed.emit("tamper.flipped", {"beat": beat_no,
                                         "from": "IMPOSTOR", "to": "CLEAN",
                                         "by": "choreography"})
        mode = read_tamper(tamper_path)  # read at photo time ONLY
        if mode in ("ARMED", "IMPOSTOR"):
            photo_ref = "photo-impostor"
            if mode == "ARMED":
                write_tamper(tamper_path, "IMPOSTOR")
                feed.emit("tamper.flipped", {"beat": beat_no,
                                             "from": "ARMED",
                                             "to": "IMPOSTOR"})
        else:
            photo_ref = "photo-true"
        feed.emit("delivery.photo", {
            "beat": beat_no, "photo_ref": photo_ref,
            "presentation": "impostor" if photo_ref == "photo-impostor" else "true",
        })
        dclaim = Claim(
            claim_id=f"d-b{beat_no}", kind="delivery",
            subject={"item": MANDATE.item}, asserted_by="courier",
            asserted_value={})
        v3 = gate_delivery(MANDATE, dclaim, verifier, photo_ref)
        append("gate_verdict", {
            "op": "GATE_VERDICT", "gate": v3.gate, "status": v3.status,
            "reason": v3.reason, "claim_id": dclaim.claim_id})
        failed_attr = (
            v3.reason.split(":", 1)[1]
            if v3.reason and ":" in v3.reason else None)
        feed.emit("gate.verdict", {
            "beat": beat_no, "gate": "delivery", "status": v3.status,
            "reason": v3.reason, "claim_id": dclaim.claim_id,
            "photo_ref": photo_ref, "failed_attribute": failed_attr,
        })
        sleep(1)

        if v3.status == "refuse":
            append("run_end", {"op": "RUN_REFUSED", "gate": "delivery",
                               "reason": v3.reason})
            ev = ledger.release(f"demo:{beat_no}:payment",
                                reason="gate_refusal")
            append("ledger_move", {**ev.to_dict(), "op": "LEDGER_RELEASE",
                                   "ledger_op": ev.op})
            beats.append(refusal_recall(
                proposer, v3.reason, clock,
                context="the delivery claim for this beat was measured "
                        "against its photo; the colour attribute did not "
                        "match the mandate (matte red)"))
            beats.append(control_beat(clock))
            brain_beat(beat_no)
            summary["beats"].append({"beat": beat_no, "outcome": "REFUSED",
                                     "reason": v3.reason})
        else:
            ev = ledger.capture(f"demo:{beat_no}:payment")
            append("ledger_move", {**ev.to_dict(), "op": "LEDGER_CAPTURE",
                                   "ledger_op": ev.op})
            summary["beats"].append({"beat": beat_no, "outcome": "SETTLED"})
        sleep(1)

    append("run_end", {"op": "RUN_SETTLED", "demo": True})
    with open(receipt_path, "w", encoding="utf-8") as f:
        f.write(chain.to_jsonl() + "\n")
    head = chain.entries[-1].hash
    verified = chain.verify()
    feed.emit("receipt.sealed", {
        "head": head, "verified": verified, "entries": len(chain.entries),
    })
    summary.update({"head": head, "verified": verified,
                    "profile": profile(beats).to_dict()})
    return summary

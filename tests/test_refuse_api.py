"""Public refuse API: a composed profile's gate seals its refusal
through the environment — verdict on the claim, gate_verdict on
the chain, RUN_REFUSED, holds released, chain verifies, replay
reproduces REFUSED with the identical head hash."""

import pytest

from runway.claims import Claim
from runway.gates import Mandate, Verdict
from runway.run import Environment, replay

MANDATE = Mandate(
    item="gooseneck kettle",
    attributes={"colour": "matte red", "form": "gooseneck"},
    cap_cents=4000,
)
TS = "2026-10-29T00:00:00+00:00"


def _env():
    return Environment(MANDATE, run_id="r-refuse", clock=lambda: TS)


def _claim():
    return Claim(
        claim_id="offer-1", kind="offer",
        subject={"item": "gooseneck kettle"},
        asserted_by="tenant:test",
        asserted_value={"price_cents": 3850, "currency": "USD"},
    )


def test_profile_refusal_seals_like_a_gate_refusal(tmp_path):
    env = _env()
    claim = _claim()
    verdict = Verdict("refuse", "consent", "consent_total_mismatch")
    result = env.refuse(verdict, claim)

    assert result.outcome == "REFUSED"
    assert claim.verdict_status == "refuse"
    assert claim.verdict_reason == "consent_total_mismatch"
    assert claim.verdict_gate == "consent"
    assert env.chain.verify()
    assert result.verdicts == [{
        "op": "GATE_VERDICT", "gate": "consent", "status": "refuse",
        "reason": "consent_total_mismatch", "claim_id": "offer-1",
    }]

    path = tmp_path / "receipt.jsonl"
    path.write_text(env.chain.to_jsonl() + "\n", encoding="utf-8")
    rep = replay(str(path), MANDATE)
    assert rep.outcome == "REFUSED"
    assert rep.receipt_head_hash == result.receipt_head_hash


def test_refuse_requires_a_refusal_verdict():
    env = _env()
    with pytest.raises(ValueError):
        env.refuse(Verdict("pass", "consent"))


def test_refuse_on_closed_run_raises():
    env = _env()
    env.refuse(Verdict("refuse", "custody", "custody_no_mandate"))
    with pytest.raises(RuntimeError):
        env.refuse(Verdict("refuse", "custody", "custody_no_mandate"))

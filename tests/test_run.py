"""Q1 acceptance: refusal-first environment + ledger tests."""

import pytest

from runway.claims import Claim, Measurement
from runway.gates import Mandate
from runway.ledger import Ledger, LedgerError
from runway.run import replay, run_mandate

MANDATE = Mandate(
    item="gooseneck kettle",
    attributes={"colour": "matte red", "form": "gooseneck"},
    cap_cents=4000,
)
TS = "2026-10-26T00:00:00+00:00"


def _clock():
    return TS


def _claim(cid, price):
    return Claim(
        claim_id=cid, kind="offer",
        subject={"item": "gooseneck kettle"},
        asserted_by="spark:stub",
        asserted_value={"price_cents": price, "currency": "USD",
                        "merchant": "KettleHouse"},
    )


def _measurer(prices):
    def measure(claim):
        p = prices[claim.claim_id]
        if p is None:
            return None
        return Measurement(
            measured_by="offer-rereader",
            measured_value={
                "item": "gooseneck kettle",
                "attributes": {"colour": "matte red", "form": "gooseneck"},
                "price_cents": p, "currency": "USD",
            },
        )
    return measure


def _run(tmp_path, claims, prices):
    path = str(tmp_path / "receipt.jsonl")
    result = run_mandate(
        MANDATE, claims, path,
        measurer=_measurer(prices), run_id="run-1", clock=_clock,
    )
    return result, path


def test_happy_path_settles_and_holds_become_captures(tmp_path):
    result, path = _run(tmp_path, [_claim("c1", 3850)], {"c1": 3850})
    assert result.outcome == "SETTLED"
    state = result.ledger_state["m-run-1"]
    assert state["held_cents"] == 0
    assert state["captured_cents"] == 3850
    assert [v["status"] for v in result.verdicts] == ["pass", "pass"]


def test_over_cap_refuses_at_offer_and_holds_nothing(tmp_path):
    result, path = _run(tmp_path, [_claim("c1", 3900)], {"c1": 4500})
    assert result.outcome == "REFUSED"
    offer = result.verdicts[0]
    assert (offer["gate"], offer["status"], offer["reason"]) == (
        "offer", "refuse", "over_cap")
    state = result.ledger_state["m-run-1"]
    assert state["held_cents"] == 0 and state["captured_cents"] == 0


def test_cumulative_cap_trips_at_payment_and_releases_first_hold(tmp_path):
    claims = [_claim("c1", 3000), _claim("c2", 1500)]
    result, path = _run(tmp_path, claims, {"c1": 3000, "c2": 1500})
    assert result.outcome == "REFUSED"
    payment = result.verdicts[-1]
    assert (payment["gate"], payment["reason"]) == (
        "payment", "over_cap_cumulative")
    state = result.ledger_state["m-run-1"]
    assert state["held_cents"] == 0 and state["captured_cents"] == 0
    text = open(path).read()
    assert '"gate_refusal"' in text and "HOLDS_RELEASED" in text


def test_unmeasured_claim_refuses(tmp_path):
    result, _ = _run(tmp_path, [_claim("c1", 100)], {"c1": None})
    assert result.outcome == "REFUSED"
    assert result.verdicts[0]["reason"] == "unmeasured"


def test_replay_reproduces_refused_run_bit_for_bit(tmp_path):
    claims = [_claim("c1", 3000), _claim("c2", 1500)]
    result, path = _run(tmp_path, claims, {"c1": 3000, "c2": 1500})
    again = replay(path, MANDATE)
    assert again.outcome == result.outcome == "REFUSED"
    assert again.receipt_head_hash == result.receipt_head_hash
    assert again.verdicts == result.verdicts
    assert again.ledger_state == result.ledger_state


def test_replay_reproduces_settled_run(tmp_path):
    result, path = _run(tmp_path, [_claim("c1", 3850)], {"c1": 3850})
    again = replay(path, MANDATE)
    assert again == result


def test_replay_refuses_tampered_receipt(tmp_path):
    result, path = _run(tmp_path, [_claim("c1", 3850)], {"c1": 3850})
    text = open(path).read().replace("3850", "3800", 1)
    open(path, "w").write(text)
    with pytest.raises(ValueError):
        replay(path, MANDATE)


def test_duplicate_idempotency_key_never_double_holds():
    ledger = Ledger()
    ledger.open_mandate("m", 4000)
    first = ledger.authorize("run:1:payment", "m", 2000, "KettleHouse")
    dupe = ledger.authorize("run:1:payment", "m", 2000, "KettleHouse")
    assert dupe is first
    assert ledger.accounts["m"].held_cents == 2000
    assert len(ledger.events) == 1


def test_ledger_invariant_is_a_wall():
    ledger = Ledger()
    ledger.open_mandate("m", 4000)
    ledger.authorize("k1", "m", 3000)
    with pytest.raises(LedgerError):
        ledger.authorize("k2", "m", 1500)
    ev = ledger.release("k1", reason="superseded_offer")
    assert ledger.accounts["m"].held_cents == 0
    assert ev.reason == "superseded_offer"

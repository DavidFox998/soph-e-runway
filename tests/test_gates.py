from runway.claims import Claim, Measurement
from runway.gates import Mandate, gate_offer, gate_payment

MANDATE = Mandate(
    item="gooseneck kettle",
    attributes={"colour": "matte red", "form": "gooseneck"},
    cap_cents=4000,
)


def _offer(measured_value, asserted_price=3900):
    return Claim(
        claim_id="c1",
        kind="offer",
        subject={"item": "gooseneck kettle"},
        asserted_by="agent",
        asserted_value={"price_cents": asserted_price, "currency": "USD"},
        measurement=None
        if measured_value is None
        else Measurement(measured_by="offer-rereader",
                         measured_value=measured_value),
    )


GOOD = {"item": "gooseneck kettle",
        "attributes": {"colour": "matte red", "form": "gooseneck"},
        "price_cents": 3850, "currency": "USD"}


def test_exact_offer_in_cap_passes():
    assert gate_offer(MANDATE, _offer(GOOD)).status == "pass"


def test_unmeasured_refuses_even_if_asserted_cheap():
    v = gate_offer(MANDATE, _offer(None, asserted_price=100))
    assert (v.status, v.reason) == ("refuse", "unmeasured")


def test_wrong_item_refuses():
    v = gate_offer(MANDATE, _offer({**GOOD, "item": "saucepan"}))
    assert (v.status, v.reason) == ("refuse", "item_mismatch")


def test_wrong_colour_refuses_gate4_standard_at_gate2():
    bad = {**GOOD, "attributes": {"colour": "black", "form": "gooseneck"}}
    v = gate_offer(MANDATE, _offer(bad))
    assert (v.status, v.reason) == ("refuse", "attribute_mismatch:colour")


def test_over_cap_refuses_even_when_asserted_under():
    v = gate_offer(MANDATE, _offer({**GOOD, "price_cents": 4500},
                                   asserted_price=3900))
    assert (v.status, v.reason) == ("refuse", "over_cap")


def test_payment_cumulative_cap():
    claim = Claim(
        claim_id="p1", kind="payment", subject={}, asserted_by="agent",
        asserted_value={},
        measurement=Measurement(measured_by="rail",
                                measured_value={"amount_cents": 500}),
    )
    ok = gate_payment(MANDATE, claim, already_paid_cents=3400)
    assert ok.status == "pass"
    claim2 = Claim(
        claim_id="p2", kind="payment", subject={}, asserted_by="agent",
        asserted_value={},
        measurement=Measurement(measured_by="rail",
                                measured_value={"amount_cents": 500}),
    )
    v = gate_payment(MANDATE, claim2, already_paid_cents=3600)
    assert (v.status, v.reason) == ("refuse", "over_cap_cumulative")

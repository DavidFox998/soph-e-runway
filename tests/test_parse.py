"""Q4 acceptance: refusal-first mandate parser tests."""

import json
from datetime import date

from runway.parse import ParsedMandate, ParseRefusal, StubProposer, parse_mandate
from runway.receipts import ReceiptChain

TODAY = date(2026, 10, 26)
TS = "2026-10-26T00:00:00+00:00"


def _reply(**kw):
    base = {"item": None, "attributes": {}, "price_cap_cents": None,
            "deadline": None, "unresolved": []}
    base.update(kw)
    return json.dumps(base)


def _parse(text, reply):
    return parse_mandate(text, today=TODAY, spark_client=StubProposer(reply))


def test_fully_pinned_input_parses_clean():
    out = _parse(
        "matte red gooseneck kettle, $40 cap, delivered 2026-10-30",
        _reply(item="gooseneck kettle",
               attributes={"colour": "matte red", "form": "gooseneck"},
               price_cap_cents=4000, deadline="2026-10-30"),
    )
    assert isinstance(out, ParsedMandate)
    assert out.item_identity == "gooseneck kettle"
    assert out.price_cap_cents == 4000
    assert out.deadline == date(2026, 10, 30)
    assert dict(out.required_attributes) == {
        "colour": "matte red", "form": "gooseneck"}
    m = out.to_mandate()
    assert m.cap_cents == 4000 and m.item == "gooseneck kettle"


def test_nice_kettle_under_forty_bucks_refuses():
    out = _parse(
        "a nice kettle under forty bucks",
        _reply(item="nice kettle", price_cap_cents=4000,
               unresolved=["deadline not given"]),
    )
    assert isinstance(out, ParseRefusal)
    assert "VAGUE_ITEM" in out.codes
    assert "FUZZY_CAP" in out.codes  # never converted, ever


def test_word_cap_with_honest_model_still_refuses_fuzzy():
    out = _parse(
        "gooseneck kettle under forty bucks, delivered 2026-10-30",
        _reply(item="gooseneck kettle", deadline="2026-10-30",
               unresolved=["cap given in words"]),
    )
    assert isinstance(out, ParseRefusal)
    assert "FUZZY_CAP" in out.codes


def test_by_friday_is_relative_deadline():
    out = _parse(
        "gooseneck kettle, $40 cap, by Friday",
        _reply(item="gooseneck kettle", price_cap_cents=4000),
    )
    assert isinstance(out, ParseRefusal)
    assert "RELATIVE_DEADLINE" in out.codes


def test_model_must_not_resolve_friday_itself():
    out = _parse(
        "gooseneck kettle, $40 cap, by Friday",
        _reply(item="gooseneck kettle", price_cap_cents=4000,
               deadline="2026-10-30"),
    )
    assert isinstance(out, ParseRefusal)
    assert "RELATIVE_DEADLINE" in out.codes


def test_model_invented_attribute_refuses():
    out = _parse(
        "gooseneck kettle, $40 cap, delivered 2026-10-30",
        _reply(item="gooseneck kettle",
               attributes={"colour": "matte red"},
               price_cap_cents=4000, deadline="2026-10-30"),
    )
    assert isinstance(out, ParseRefusal)
    assert "UNCLEAR_ATTRIBUTE" in out.codes


def test_model_cap_conversion_is_schema_violation():
    out = _parse(
        "gooseneck kettle, $40 cap, delivered 2026-10-30",
        _reply(item="gooseneck kettle", price_cap_cents=5000,
               deadline="2026-10-30"),
    )
    assert isinstance(out, ParseRefusal)
    assert "SCHEMA_VIOLATION" in out.codes


def test_missing_everything_refuses_with_reasons():
    out = _parse("a kettle please", _reply(item="kettle"))
    assert isinstance(out, ParseRefusal)
    assert "MISSING_CAP" in out.codes
    assert "MISSING_DEADLINE" in out.codes


def test_malformed_reply_emits_no_mandate():
    out = _parse("matte red gooseneck kettle, $40 cap, delivered 2026-10-30",
                 "sure, one kettle coming up!")
    assert isinstance(out, ParseRefusal)
    assert out.codes == ("SCHEMA_VIOLATION",)


def test_past_deadline_refuses():
    out = _parse(
        "gooseneck kettle, $40 cap, delivered 2026-10-20",
        _reply(item="gooseneck kettle", price_cap_cents=4000,
               deadline="2026-10-20"),
    )
    assert isinstance(out, ParseRefusal)
    assert "PAST_DEADLINE" in out.codes


def test_both_outcomes_are_hash_chained():
    chain = ReceiptChain()
    ok = parse_mandate(
        "matte red gooseneck kettle, $40 cap, delivered 2026-10-30",
        today=TODAY, chain=chain, ts=TS,
        spark_client=StubProposer(_reply(
            item="gooseneck kettle",
            attributes={"colour": "matte red", "form": "gooseneck"},
            price_cap_cents=4000, deadline="2026-10-30")))
    assert isinstance(ok, ParsedMandate)
    bad = parse_mandate(
        "a nice kettle under forty bucks", today=TODAY, chain=chain, ts=TS,
        spark_client=StubProposer(_reply(item="nice kettle")))
    assert isinstance(bad, ParseRefusal)
    assert chain.verify()
    ops = [e.payload["op"] for e in chain.entries]
    assert ops == ["PARSE_PROPOSED", "PARSE_VERDICT",
                   "PARSE_PROPOSED", "PARSE_VERDICT"]

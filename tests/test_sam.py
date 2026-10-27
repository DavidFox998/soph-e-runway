"""Q2: SAM wire-format parser + adapter tests (offline; grammar
fixtures built from Meta's normative protocol doc examples)."""

import pytest

from runway.claims import Claim
from runway.delivery import SamApiVerifier, gate_delivery
from runway.gates import Mandate
from runway.sam import (
    SamShapeError,
    measure,
    measure_from_texts,
    parse_sam_text,
)

DOC_LINE = (
    "<0f>0<|box;x1=10;y1=20;x2=14;y2=24;w=100;h=80|>"
    "<|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>"
)
CONF_LINE = (
    "<0f>0<|box;x1=100;y1=100;x2=499;y2=399;w=1024;h=768;c=0.92|>"
    "<|mask;x=0;y=0;c=0.92;data=300,400,~abcde!!!!!|>"
)


def test_parse_doc_example():
    records = parse_sam_text(DOC_LINE)
    assert len(records) == 1
    r = records[0]
    assert r.object_id == "0"
    assert (r.box.x1, r.box.y2, r.box.w, r.box.h) == (10, 24, 100, 80)
    assert (r.box.width, r.box.height) == (5, 5)  # inclusive x2/y2
    assert (r.mask.height, r.mask.width) == (5, 5)
    assert r.mask.encoding == "one_bit"
    assert r.box.confidence is None  # missing confidence is not zero


def test_parse_confidence_and_lossless():
    r = parse_sam_text(CONF_LINE)[0]
    assert r.box.confidence == 0.92
    assert r.mask.encoding == "lossless"
    assert (r.box.width, r.box.height) == (400, 300)


def test_empty_lane_is_zero_records_not_an_error():
    assert parse_sam_text("") == []


def test_malformed_record_raises_never_silent():
    with pytest.raises(SamShapeError):
        parse_sam_text("<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10|>")  # no mask
    with pytest.raises(SamShapeError):
        parse_sam_text("<0f>0<|box;x1=1;y1=2;x2=3;w=10;h=10|>"
                       "<|mask;x=0;y=0;data=5,5,!!!!!|>")  # missing y2
    with pytest.raises(SamShapeError):
        parse_sam_text('garbage without a frame marker')


def _transport(item_text, color_text):
    def t(image_b64, phrase):
        return color_text if "matte red" in phrase else item_text
    return t


def test_measure_all_attributes_measured():
    gm = measure("AAAA", transport=_transport(CONF_LINE, CONF_LINE))
    assert gm.attributes["present"].present is True
    assert gm.attributes["matte_red"].state == "measured"
    assert gm.attributes["matte_red"].present is True  # IoU 1.0 with itself
    assert gm.attributes["gooseneck_silhouette"].state == "measured"
    assert len(gm.raw_ref) == 64


def test_measure_absent_item():
    gm = measure("AAAA", transport=_transport("", ""))
    assert gm.attributes["present"].present is False
    assert gm.attributes["present"].state == "measured"


def test_measure_undecidable_color_is_ambiguous():
    gm = measure("AAAA", transport=_transport(CONF_LINE, ""))
    assert gm.attributes["matte_red"].state == "ambiguous"
    assert gm.attributes["matte_red"].present is None


MANDATE = Mandate(
    item="gooseneck kettle",
    attributes={"colour": "matte red", "form": "gooseneck"},
    cap_cents=4000,
)


def test_gate4_refuses_ambiguous_by_name():
    gm = measure("AAAA", transport=_transport(CONF_LINE, ""))
    verifier = SamApiVerifier(
        sam_measure=lambda b64: gm, photo_loader=lambda ref: b"jpg")
    claim = Claim(claim_id="d1", kind="delivery",
                  subject={"item": "gooseneck kettle"}, asserted_by="courier", asserted_value={})
    v = gate_delivery(MANDATE, claim, verifier, "photo-1")
    assert (v.status, v.reason) == ("refuse", "ambiguous:colour")


def test_gate4_passes_when_sam_measures_clean():
    gm = measure("AAAA", transport=_transport(CONF_LINE, CONF_LINE))
    verifier = SamApiVerifier(
        sam_measure=lambda b64: gm, photo_loader=lambda ref: b"jpg")
    claim = Claim(claim_id="d1", kind="delivery",
                  subject={"item": "gooseneck kettle"}, asserted_by="courier", asserted_value={})
    v = gate_delivery(MANDATE, claim, verifier, "photo-1")
    assert v.status == "pass"
    assert claim.measurement.evidence_refs[0].startswith("sam-raw:")

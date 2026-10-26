"""Gate 4 against the fixed photo discipline: the true delivery passes;
every named impostor refuses; anything unmeasured refuses."""

from runway.claims import Claim
from runway.delivery import SamApiVerifier, StubVerifier, gate_delivery
from runway.gates import Mandate

MANDATE = Mandate(
    item="gooseneck kettle",
    attributes={"colour": "matte red", "form": "gooseneck"},
    cap_cents=4000,
)

TRUE_PHOTO = {
    "item": "gooseneck kettle",
    "attributes": {"colour": "matte red", "form": "gooseneck"},
    "present": True,
}

STUB = StubVerifier(fixtures={
    "photos/true.jpg": TRUE_PHOTO,
    "photos/black-kettle.jpg": {
        "item": "gooseneck kettle",
        "attributes": {"colour": "black", "form": "gooseneck"},
        "present": True,
    },
    "photos/stovetop-kettle.jpg": {
        "item": "gooseneck kettle",
        "attributes": {"colour": "matte red", "form": "stovetop"},
        "present": True,
    },
    "photos/saucepan.jpg": {
        "item": "saucepan",
        "attributes": {"colour": "matte red", "form": "saucepan"},
        "present": True,
    },
    "photos/box-only.jpg": {
        "item": "gooseneck kettle",
        "attributes": {"colour": "matte red", "form": "gooseneck"},
        "present": False,
    },
})


def _claim() -> Claim:
    return Claim(
        claim_id="d1",
        kind="delivery",
        subject={"item": "gooseneck kettle"},
        asserted_by="courier",
        asserted_value={"delivered": True},
    )


def test_true_delivery_passes():
    v = gate_delivery(MANDATE, _claim(), STUB, "photos/true.jpg")
    assert v.status == "pass"


def test_impostor_wrong_colour_refuses():
    v = gate_delivery(MANDATE, _claim(), STUB, "photos/black-kettle.jpg")
    assert (v.status, v.reason) == ("refuse", "attribute_mismatch:colour")


def test_impostor_wrong_form_refuses():
    v = gate_delivery(MANDATE, _claim(), STUB, "photos/stovetop-kettle.jpg")
    assert (v.status, v.reason) == ("refuse", "attribute_mismatch:form")


def test_impostor_wrong_item_refuses():
    v = gate_delivery(MANDATE, _claim(), STUB, "photos/saucepan.jpg")
    assert (v.status, v.reason) == ("refuse", "item_mismatch")


def test_impostor_box_only_refuses():
    v = gate_delivery(MANDATE, _claim(), STUB, "photos/box-only.jpg")
    assert (v.status, v.reason) == ("refuse", "item_absent")


def test_unknown_photo_is_unmeasured_not_a_guess():
    v = gate_delivery(MANDATE, _claim(), STUB, "photos/never-seen.jpg")
    assert (v.status, v.reason) == ("refuse", "unmeasured")


def test_unconfigured_sam_backend_refuses_unmeasured():
    v = gate_delivery(MANDATE, _claim(), SamApiVerifier(), "photos/true.jpg")
    assert (v.status, v.reason) == ("refuse", "unmeasured")
